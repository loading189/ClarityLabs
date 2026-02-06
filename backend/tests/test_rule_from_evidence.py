from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_rule_from_evidence.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import (
    Account,
    AuditLog,
    Business,
    BusinessCategoryMap,
    Category,
    Organization,
    RawEvent,
    TxnCategorization,
)
from backend.app.services import categorize_service


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


def _biz(db):
    org = Organization(name="Rule Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Rule Biz")
    db.add(biz)
    db.flush()
    return biz


def _category(db, biz_id: str):
    acct = Account(business_id=biz_id, name="Supplies", type="expense")
    db.add(acct)
    db.flush()
    cat = Category(business_id=biz_id, name="Supplies", account_id=acct.id, system_key="supplies")
    db.add(cat)
    db.flush()
    db.add(BusinessCategoryMap(business_id=biz_id, system_key="supplies", category_id=cat.id))
    db.flush()
    return cat


def _raw_event(db, biz_id: str, source_event_id: str, description: str):
    ev = RawEvent(
        business_id=biz_id,
        source="bank",
        source_event_id=source_event_id,
        occurred_at=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
        payload={
            "type": "transaction.posted",
            "transaction": {
                "transaction_id": source_event_id,
                "amount": -120.0,
                "name": description,
                "merchant_name": description,
            },
        },
    )
    db.add(ev)
    return ev


def test_rule_preview_and_apply_from_evidence(db_session):
    biz = _biz(db_session)
    cat = _category(db_session, biz.id)

    _raw_event(db_session, biz.id, "evt-1", "Vendor X")
    _raw_event(db_session, biz.id, "evt-2", "Vendor X")
    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt-1",
            category_id=cat.id,
            source="manual",
            confidence=1.0,
        )
    )
    db_session.commit()

    rule = categorize_service.create_category_rule(
        db_session,
        biz.id,
        type(
            "RuleReq",
            (),
            {
                "contains_text": "vendor x",
                "category_id": cat.id,
                "priority": 90,
                "direction": None,
                "account": None,
                "active": True,
            },
        )(),
    )

    preview = categorize_service.preview_category_rule(
        db_session,
        biz.id,
        rule["id"],
        include_posted=True,
    )
    assert preview["matched"] == 2

    applied = categorize_service.apply_category_rule(db_session, biz.id, rule["id"])
    assert applied["updated"] == 1
    assert applied["audit_id"]

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.business_id == biz.id, AuditLog.event_type == "rule_apply")
        .all()
    )
    assert audit_rows
    assert audit_rows[0].rule_id == rule["id"]
