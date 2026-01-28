from datetime import datetime, timezone
import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_categorization.db")

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
    bulk_apply_categorization,
    upsert_categorization,
    categorization_metrics,
    get_brain_vendor,
    set_brain_vendor,
    forget_brain_vendor,
    BulkCategorizationIn,
    CategorizationUpsertIn,
    BrainVendorSetIn,
    BrainVendorForgetIn,
)
from backend.app.norma.categorize_brain import brain
from backend.app.norma.merchant import merchant_key, canonical_merchant_name


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


def test_bulk_apply_updates_matching_rows(db_session, brain_store):
    biz = _create_business(db_session)
    category_a = _create_category(db_session, biz.id, "Software", "software")
    category_b = _create_category(db_session, biz.id, "Meals", "meals")

    db_session.add_all(
        [
            _make_event(biz.id, "evt_1", "Acme Coffee #123"),
            _make_event(biz.id, "evt_2", "ACME Coffee 456"),
            _make_event(biz.id, "evt_3", "Other Vendor"),
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
    assert res["updated"] == 1

    rows = (
        db_session.query(TxnCategorization)
        .filter(TxnCategorization.business_id == biz.id)
        .all()
    )
    by_event = {r.source_event_id: r.category_id for r in rows}
    assert by_event["evt_1"] == category_b.id
    assert by_event["evt_2"] == category_b.id
    assert "evt_3" not in by_event


def test_manual_categorization_learns_normalized_canonical_name(db_session, brain_store):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")

    db_session.add(_make_event(biz.id, "evt_10", "ACME CO*123"))
    db_session.commit()

    req = CategorizationUpsertIn(source_event_id="evt_10", category_id=category.id)
    res = upsert_categorization(biz.id, req, db_session)

    assert res["learned"] is True

    mk = merchant_key("ACME CO*123")
    alias = brain.aliases.get(mk)
    assert alias is not None
    merchant = brain.merchants[alias.merchant_id]
    assert merchant.canonical_name == canonical_merchant_name("ACME CO*123")


def test_categorization_metrics_counts(db_session, brain_store):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")

    db_session.add_all(
        [
            _make_event(biz.id, "evt_20", "Known Vendor"),
            _make_event(biz.id, "evt_21", "Unknown Vendor"),
            _make_event(biz.id, "evt_22", "Categorized Vendor"),
        ]
    )
    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt_22",
            category_id=category.id,
            source="manual",
            confidence=1.0,
        )
    )
    db_session.commit()

    brain.apply_label(
        business_id=biz.id,
        alias_key=merchant_key("Known Vendor"),
        canonical_name=canonical_merchant_name("Known Vendor"),
        system_key="software",
        confidence=0.9,
    )

    metrics = categorization_metrics(biz.id, db_session)

    assert metrics.total_events == 3
    assert metrics.posted == 1
    assert metrics.uncategorized == 2
    assert metrics.suggestion_coverage == 1
    assert metrics.brain_coverage == 1


def test_brain_vendor_endpoints_round_trip(db_session, brain_store):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")

    set_req = BrainVendorSetIn(
        merchant_key="ACME CO*123",
        category_id=category.id,
        canonical_name="Acme Co",
    )
    set_res = set_brain_vendor(biz.id, set_req, db_session)

    assert set_res.system_key == "software"
    assert set_res.merchant_key == merchant_key("ACME CO*123")

    get_res = get_brain_vendor(biz.id, merchant_key_value="ACME CO*123", db=db_session)
    assert get_res.merchant_id == set_res.merchant_id
    assert get_res.system_key == "software"

    forget_req = BrainVendorForgetIn(merchant_key="ACME CO*123")
    forget_res = forget_brain_vendor(biz.id, forget_req, db_session)
    assert forget_res == {"status": "ok", "deleted": True}
