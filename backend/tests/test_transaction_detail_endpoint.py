from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_transaction_detail.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import (
    Account,
    AuditLog,
    Business,
    BusinessCategoryMap,
    Category,
    HealthSignalState,
    Organization,
    RawEvent,
    TxnCategorization,
)
from backend.app.services.transaction_service import transaction_detail


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
    org = Organization(name="Txn Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Txn Biz")
    db.add(biz)
    db.flush()
    return biz


def _category(db, biz_id: str):
    acct = Account(business_id=biz_id, name="Meals", type="expense", subtype="meals")
    db.add(acct)
    db.flush()
    cat = Category(business_id=biz_id, name="Meals", account_id=acct.id, system_key="meals")
    db.add(cat)
    db.flush()
    db.add(BusinessCategoryMap(business_id=biz_id, system_key="meals", category_id=cat.id))
    db.flush()
    return cat


def test_transaction_detail_includes_raw_and_categorization(db_session):
    biz = _biz(db_session)
    cat = _category(db_session, biz.id)
    ev = RawEvent(
        business_id=biz.id,
        source="bank",
        source_event_id="evt-1",
        occurred_at=datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc),
        payload={
            "type": "transaction.posted",
            "transaction": {
                "transaction_id": "evt-1",
                "amount": -25.0,
                "name": "Coffee Shop",
                "merchant_name": "Coffee Shop",
            },
        },
    )
    db_session.add(ev)
    db_session.flush()
    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt-1",
            category_id=cat.id,
            source="manual",
            confidence=1.0,
        )
    )
    db_session.add(
        AuditLog(
            business_id=biz.id,
            event_type="categorization_change",
            actor="user",
            reason="manual",
            source_event_id="evt-1",
            before_state=None,
            after_state={"category_id": cat.id},
        )
    )
    db_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="sig-evt-1",
            signal_type="expense_creep_by_vendor",
            status="resolved",
            severity="high",
            title="Expense creep: Coffee Shop",
            summary="Spend increased",
            payload_json={"evidence_source_event_ids": ["evt-1"]},
        )
    )
    db_session.commit()

    detail = transaction_detail(db_session, biz.id, "evt-1")
    assert detail["raw_event"]["source_event_id"] == "evt-1"
    assert detail["raw_event"]["payload"]["transaction"]["amount"] == -25.0
    assert detail["normalized_txn"]["description"] == "Coffee Shop"
    assert detail["normalized_txn"]["direction"] == "outflow"
    assert detail["normalized_txn"]["amount"] == 25.0
    assert detail["categorization"]["category_id"] == cat.id
    assert detail["ledger_context"] is not None
    assert detail["audit_history"][0]["event_type"] == "categorization_change"
    assert detail["related_signals"][0]["signal_id"] == "sig-evt-1"
    assert "suggested_category" in detail
    assert "rule_suggestion" in detail
    assert detail["related_signals"][0]["recommended_actions"]
