from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_categorization_invariants.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import (
    Organization,
    Business,
    Account,
    Category,
    BusinessCategoryMap,
    RawEvent,
    TxnCategorization,
)
from backend.app.api.categorize import (
    list_txns_to_categorize,
    bulk_apply_categorization,
    create_category_rule,
    set_brain_vendor,
    BulkCategorizationIn,
    CategoryRuleIn,
    BrainVendorSetIn,
)
from backend.app.norma.categorize_brain import brain
from backend.app.norma.merchant import merchant_key


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def brain_store(tmp_path):
    original_path = brain.path
    original_merchants = brain.merchants
    original_aliases = brain.aliases
    original_labels = brain.labels

    brain.path = tmp_path / "brain.json"
    brain.merchants = {}
    brain.aliases = {}
    brain.labels = {}
    yield brain

    brain.path = original_path
    brain.merchants = original_merchants
    brain.aliases = original_aliases
    brain.labels = original_labels


def _create_business(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Test Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _create_category(db_session, business_id: str, name: str, system_key: str):
    account = Account(
        business_id=business_id,
        name=f"{name} Account",
        type="expense",
        subtype=system_key,
    )
    db_session.add(account)
    db_session.flush()
    category = Category(
        business_id=business_id,
        name=name,
        account_id=account.id,
    )
    db_session.add(category)
    db_session.flush()
    mapping = BusinessCategoryMap(
        business_id=business_id,
        system_key=system_key,
        category_id=category.id,
    )
    db_session.add(mapping)
    db_session.flush()
    return category


def _make_event(business_id: str, source_event_id: str, description: str):
    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": source_event_id,
            "amount": -42.0,
            "name": description,
            "merchant_name": description,
        },
    }
    return RawEvent(
        business_id=business_id,
        source="bank",
        source_event_id=source_event_id,
        occurred_at=datetime(2024, 1, 12, 12, 0, tzinfo=timezone.utc),
        payload=payload,
    )


def test_suggestion_maps_to_real_category(db_session, brain_store):
    biz = _create_business(db_session)
    _create_category(db_session, biz.id, "Utilities", "utilities")
    db_session.add(_make_event(biz.id, "evt_util", "Comcast Cable"))
    db_session.commit()

    results = list_txns_to_categorize(biz.id, limit=50, db=db_session)

    assert len(results) == 1
    suggestion = results[0]
    assert suggestion.suggested_system_key == "utilities"
    assert suggestion.suggested_category_id is not None
    assert suggestion.suggested_category_name == "Utilities"


def test_suggestion_requires_category_mapping(db_session, brain_store):
    biz = _create_business(db_session)
    description = "GitHub Subscription"
    db_session.add(_make_event(biz.id, "evt_no_map", description))
    db_session.commit()

    brain.apply_label(
        business_id=biz.id,
        alias_key=merchant_key(description),
        canonical_name=description,
        system_key="mystery_key",
        confidence=0.9,
    )

    results = list_txns_to_categorize(biz.id, limit=50, db=db_session)

    assert len(results) == 1
    suggestion = results[0]
    assert suggestion.suggested_system_key is None
    assert suggestion.suggested_category_id is None
    assert suggestion.suggested_category_name is None


def test_bulk_apply_skips_already_categorized(db_session, brain_store):
    biz = _create_business(db_session)
    category_a = _create_category(db_session, biz.id, "Software", "software")
    category_b = _create_category(db_session, biz.id, "Meals", "meals")

    db_session.add_all(
        [
            _make_event(biz.id, "evt_1", "Acme Coffee #123"),
            _make_event(biz.id, "evt_2", "ACME Coffee 456"),
        ]
    )
    db_session.flush()

    existing = TxnCategorization(
        business_id=biz.id,
        source_event_id="evt_1",
        category_id=category_a.id,
        source="manual",
        confidence=1.0,
    )
    db_session.add(existing)
    db_session.commit()

    req = BulkCategorizationIn(merchant_key="acme coffee", category_id=category_b.id)
    res = bulk_apply_categorization(biz.id, req, db_session)

    assert res["matched_events"] == 2
    assert res["created"] == 1
    assert res["updated"] == 0

    rows = (
        db_session.query(TxnCategorization)
        .filter(TxnCategorization.business_id == biz.id)
        .all()
    )
    by_event = {r.source_event_id: r.category_id for r in rows}
    assert by_event["evt_1"] == category_a.id
    assert by_event["evt_2"] == category_b.id


def test_fix_actions_reject_uncategorized(db_session, brain_store):
    biz = _create_business(db_session)
    uncategorized = _create_category(db_session, biz.id, "Uncategorized", "uncategorized")
    db_session.add(_make_event(biz.id, "evt_uc", "Mystery Vendor"))
    db_session.commit()

    with pytest.raises(HTTPException):
        create_category_rule(
            biz.id,
            CategoryRuleIn(contains_text="mystery", category_id=uncategorized.id),
            db_session,
        )

    with pytest.raises(HTTPException):
        set_brain_vendor(
            biz.id,
            BrainVendorSetIn(merchant_key="mystery vendor", category_id=uncategorized.id),
            db_session,
        )

    with pytest.raises(HTTPException):
        bulk_apply_categorization(
            biz.id,
            BulkCategorizationIn(merchant_key="mystery vendor", category_id=uncategorized.id),
            db_session,
        )
