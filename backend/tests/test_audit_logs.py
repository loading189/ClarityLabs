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
from backend.app.services import audit_service


@pytest.fixture()
def db_session():
    db_path = Path("test_audit_logs.db")
    engine.dispose()
    if db_path.exists():
        db_path.unlink()
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


def _create_audit_log(
    db_session,
    business_id: str,
    *,
    audit_id: str,
    created_at: datetime,
    event_type: str = "categorization_change",
    actor: str = "system",
):
    row = AuditLog(
        id=audit_id,
        business_id=business_id,
        event_type=event_type,
        actor=actor,
        reason="test",
        before_state={"status": "before"},
        after_state={"status": "after"},
        created_at=created_at,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_audit_log_ordering(db_session):
    biz = _create_business(db_session)
    _create_audit_log(
        db_session,
        biz.id,
        audit_id="00000000-0000-0000-0000-000000000001",
        created_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        event_type="rule_create",
    )
    _create_audit_log(
        db_session,
        biz.id,
        audit_id="00000000-0000-0000-0000-000000000002",
        created_at=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
        event_type="rule_update",
    )
    _create_audit_log(
        db_session,
        biz.id,
        audit_id="00000000-0000-0000-0000-000000000003",
        created_at=datetime(2024, 1, 3, 12, 0, tzinfo=timezone.utc),
        event_type="categorization_change",
    )

    result = audit_service.list_audit_events(db_session, biz.id, limit=10)
    event_types = [item["event_type"] for item in result["items"]]
    assert event_types == ["categorization_change", "rule_update", "rule_create"]


def test_audit_log_filters(db_session):
    biz = _create_business(db_session)
    _create_audit_log(
        db_session,
        biz.id,
        audit_id="00000000-0000-0000-0000-000000000011",
        created_at=datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc),
        event_type="rule_create",
        actor="system",
    )
    _create_audit_log(
        db_session,
        biz.id,
        audit_id="00000000-0000-0000-0000-000000000012",
        created_at=datetime(2024, 2, 2, 9, 0, tzinfo=timezone.utc),
        event_type="vendor_default_set",
        actor="user",
    )

    result = audit_service.list_audit_events(
        db_session,
        biz.id,
        limit=10,
        event_type="vendor_default_set",
    )
    assert [item["event_type"] for item in result["items"]] == ["vendor_default_set"]

    result = audit_service.list_audit_events(db_session, biz.id, limit=10, actor="system")
    assert [item["actor"] for item in result["items"]] == ["system"]

    result = audit_service.list_audit_events(
        db_session,
        biz.id,
        limit=10,
        since=datetime(2024, 2, 2, 0, 0, tzinfo=timezone.utc),
    )
    assert [item["event_type"] for item in result["items"]] == ["vendor_default_set"]

    result = audit_service.list_audit_events(
        db_session,
        biz.id,
        limit=10,
        until=datetime(2024, 2, 1, 23, 59, tzinfo=timezone.utc),
    )
    assert [item["event_type"] for item in result["items"]] == ["rule_create"]


def test_audit_log_cursor_pagination(db_session):
    biz = _create_business(db_session)
    timestamps = [
        datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 3, 2, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 3, 3, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 3, 4, 12, 0, tzinfo=timezone.utc),
    ]
    ids = [
        "00000000-0000-0000-0000-000000000021",
        "00000000-0000-0000-0000-000000000022",
        "00000000-0000-0000-0000-000000000023",
        "00000000-0000-0000-0000-000000000024",
    ]
    for audit_id, created_at in zip(ids, timestamps):
        _create_audit_log(
            db_session,
            biz.id,
            audit_id=audit_id,
            created_at=created_at,
        )

    first_page = audit_service.list_audit_events(db_session, biz.id, limit=2)
    assert [item["id"] for item in first_page["items"]] == [ids[3], ids[2]]
    assert first_page["next_cursor"] is not None

    second_page = audit_service.list_audit_events(
        db_session,
        biz.id,
        limit=2,
        cursor=first_page["next_cursor"],
    )
    assert [item["id"] for item in second_page["items"]] == [ids[1], ids[0]]
    assert second_page["next_cursor"] is None
