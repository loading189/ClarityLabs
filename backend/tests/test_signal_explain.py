from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_signal_explain.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.api.routes.signals import SignalStatusUpdateIn, update_signal_status
from backend.app.models import (
    Account,
    Business,
    Category,
    Organization,
    RawEvent,
    TxnCategorization,
)
from backend.app.services import monitoring_service, signals_service


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
    org = Organization(name="Explain Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Explain Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _create_account_and_category(db_session, business_id: str) -> Category:
    acct = Account(business_id=business_id, name="Operating Expense", type="expense")
    db_session.add(acct)
    db_session.flush()
    cat = Category(business_id=business_id, account_id=acct.id, name="General")
    db_session.add(cat)
    db_session.flush()
    return cat


def _add_raw_event(
    db_session,
    business_id: str,
    source_event_id: str,
    occurred_at: datetime,
    amount: float,
    direction: str,
    description: str,
    counterparty_hint: str | None = None,
):
    payload = {
        "type": "plaid.transaction",
        "description": description,
        "amount": amount,
        "direction": direction,
        "counterparty_hint": counterparty_hint,
    }
    event = RawEvent(
        business_id=business_id,
        source="plaid",
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        payload=payload,
    )
    db_session.add(event)
    return event


def _categorize(db_session, business_id: str, source_event_id: str, category_id: str):
    row = TxnCategorization(
        business_id=business_id,
        source_event_id=source_event_id,
        category_id=category_id,
        confidence=1.0,
        source="manual",
    )
    db_session.add(row)


def _seed_expense_creep(db_session, business_id: str):
    cat = _create_account_and_category(db_session, business_id)
    now = datetime(2024, 6, 30, tzinfo=timezone.utc)
    _add_raw_event(
        db_session,
        business_id,
        "prior",
        now - timedelta(days=20),
        300.0,
        "outflow",
        "Acme",
        "Acme",
    )
    _add_raw_event(
        db_session,
        business_id,
        "current",
        now - timedelta(days=5),
        600.0,
        "outflow",
        "Acme",
        "Acme",
    )
    _categorize(db_session, business_id, "prior", cat.id)
    _categorize(db_session, business_id, "current", cat.id)
    db_session.commit()
    monitoring_service.pulse(db_session, business_id)


def test_explain_endpoint_returns_payload(db_session):
    biz = _create_business(db_session)
    _seed_expense_creep(db_session, biz.id)

    signals, _ = signals_service.list_signal_states(db_session, biz.id)
    assert signals
    signal_id = signals[0]["id"]

    explain = signals_service.get_signal_explain(db_session, biz.id, signal_id)

    assert explain["business_id"] == biz.id
    assert explain["signal_id"] == signal_id
    assert "state" in explain
    assert "detector" in explain
    assert "evidence" in explain
    assert "related_audits" in explain
    assert "links" in explain

    evidence_keys = [item["key"] for item in explain["evidence"]]
    assert evidence_keys == sorted(evidence_keys)


def test_explain_evidence_order_is_deterministic(db_session):
    biz = _create_business(db_session)
    _seed_expense_creep(db_session, biz.id)

    signals, _ = signals_service.list_signal_states(db_session, biz.id)
    signal_id = signals[0]["id"]

    explain = signals_service.get_signal_explain(db_session, biz.id, signal_id)
    evidence_keys = [item["key"] for item in explain["evidence"]]
    assert evidence_keys == sorted(evidence_keys)


def test_explain_includes_recent_audit_for_status_update(db_session):
    biz = _create_business(db_session)
    _seed_expense_creep(db_session, biz.id)

    signals, _ = signals_service.list_signal_states(db_session, biz.id)
    signal_id = signals[0]["id"]

    update_payload = update_signal_status(
        biz.id,
        signal_id,
        SignalStatusUpdateIn(status="resolved", reason="handled", actor="tester"),
        db_session,
    )

    explain = signals_service.get_signal_explain(db_session, biz.id, signal_id)

    assert explain["state"]["status"] == "resolved"
    audit_ids = [entry["id"] for entry in explain["related_audits"]]
    assert update_payload["audit_id"] in audit_ids
