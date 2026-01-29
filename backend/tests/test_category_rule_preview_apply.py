from datetime import datetime, timezone, timedelta
import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_category_rule_preview_apply.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import (
    Organization,
    Business,
    Account,
    Category,
    BusinessCategoryMap,
    CategoryRule,
    RawEvent,
    TxnCategorization,
)
from backend.app.services.categorize_service import preview_category_rule, apply_category_rule


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


def test_preview_category_rule_returns_samples_and_count(db_session):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Utilities", "utilities")

    rule = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="comcast",
        priority=1,
        active=True,
    )
    db_session.add(rule)
    db_session.add(_make_event(biz.id, "evt_match_1", "Comcast Cable"))
    db_session.add(_make_event(biz.id, "evt_match_2", "Comcast Business"))
    db_session.add(_make_event(biz.id, "evt_other", "Random Vendor"))
    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt_match_1",
            category_id=category.id,
            source="manual",
            confidence=1.0,
            note=None,
        )
    )
    db_session.commit()

    res = preview_category_rule(db_session, biz.id, rule.id)

    assert res["matched"] == 1
    assert len(res["samples"]) == 1
    sample = res["samples"][0]
    assert sample["source_event_id"] == "evt_match_2"
    assert sample["description"] == "Comcast Business"


def test_preview_respects_conflict_policy_priority_and_created_at(db_session):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")

    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rule_high = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="acme",
        priority=1,
        active=True,
        created_at=base_time,
    )
    rule_low = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="acme",
        priority=2,
        active=True,
        created_at=base_time + timedelta(minutes=5),
    )
    rule_late = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="acme",
        priority=1,
        active=True,
        created_at=base_time + timedelta(minutes=10),
    )
    db_session.add_all([rule_high, rule_low, rule_late])
    db_session.add(_make_event(biz.id, "evt_acme", "ACME Subscription"))
    db_session.commit()

    res_low = preview_category_rule(db_session, biz.id, rule_low.id)
    res_high = preview_category_rule(db_session, biz.id, rule_high.id)
    res_late = preview_category_rule(db_session, biz.id, rule_late.id)

    assert res_high["matched"] == 1
    assert res_low["matched"] == 0
    assert res_late["matched"] == 0


def test_apply_rule_skips_existing_categorizations_and_updates_run_metadata(db_session):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Meals", "meals")
    other_category = _create_category(db_session, biz.id, "Travel", "travel")

    rule = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="taco",
        priority=1,
        active=True,
    )
    db_session.add(rule)
    db_session.add(_make_event(biz.id, "evt_taco_1", "Taco Spot"))
    db_session.add(_make_event(biz.id, "evt_taco_2", "Taco Spot"))
    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt_taco_1",
            category_id=other_category.id,
            source="manual",
            confidence=1.0,
            note=None,
        )
    )
    db_session.commit()

    res = apply_category_rule(db_session, biz.id, rule.id)
    assert res["matched"] == 1
    assert res["updated"] == 1

    existing = (
        db_session.query(TxnCategorization)
        .filter(TxnCategorization.source_event_id == "evt_taco_1")
        .one()
    )
    assert existing.category_id == other_category.id

    updated = (
        db_session.query(CategoryRule)
        .filter(CategoryRule.id == rule.id)
        .one()
    )
    assert updated.last_run_at is not None
    assert updated.last_run_updated_count == 1
