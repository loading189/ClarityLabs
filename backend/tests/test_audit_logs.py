from datetime import datetime, timezone
import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_audit_logs.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import (
    Account,
    AuditLog,
    Business,
    BusinessCategoryMap,
    Category,
    Organization,
    RawEvent,
)
from backend.app.api.categorize import (
    CategorizationUpsertIn,
    CategoryRuleIn,
    LabelVendorIn,
    create_category_rule,
    label_vendor,
    upsert_categorization,
)
from backend.app.norma.categorize_brain import brain


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


def _latest_audit_event(db_session, business_id: str, event_type: str):
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.business_id == business_id, AuditLog.event_type == event_type)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .first()
    )


def test_audit_logs_for_categorize_mutations(db_session, brain_store):
    biz = _create_business(db_session)
    category_a = _create_category(db_session, biz.id, "Software", "software")
    category_b = _create_category(db_session, biz.id, "Meals", "meals")

    db_session.add(_make_event(biz.id, "evt_100", "Acme Coffee #123"))
    db_session.commit()

    upsert_categorization(
        biz.id,
        CategorizationUpsertIn(source_event_id="evt_100", category_id=category_a.id),
        db_session,
    )
    upsert_categorization(
        biz.id,
        CategorizationUpsertIn(source_event_id="evt_100", category_id=category_b.id),
        db_session,
    )

    categorization_log = _latest_audit_event(db_session, biz.id, "categorization_change")
    assert categorization_log is not None
    assert categorization_log.business_id == biz.id
    assert categorization_log.source_event_id == "evt_100"
    assert categorization_log.before_state is not None
    assert categorization_log.after_state is not None

    rule = create_category_rule(
        biz.id,
        CategoryRuleIn(contains_text="acme coffee", category_id=category_a.id, priority=50),
        db_session,
    )

    rule_log = _latest_audit_event(db_session, biz.id, "rule_create")
    assert rule_log is not None
    assert rule_log.business_id == biz.id
    assert rule_log.rule_id == rule.id
    assert rule_log.before_state is not None
    assert rule_log.after_state is not None

    label_vendor(
        biz.id,
        LabelVendorIn(source_event_id="evt_100", system_key="software"),
        db_session,
    )
    label_vendor(
        biz.id,
        LabelVendorIn(source_event_id="evt_100", system_key="meals"),
        db_session,
    )

    vendor_log = _latest_audit_event(db_session, biz.id, "vendor_default_set")
    assert vendor_log is not None
    assert vendor_log.business_id == biz.id
    assert vendor_log.source_event_id == "evt_100"
    assert vendor_log.before_state is not None
    assert vendor_log.after_state is not None
