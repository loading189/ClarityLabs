from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_monitoring_pulse.db")

from sqlalchemy import delete, select

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import (
    Account,
    AuditLog,
    Business,
    Category,
    HealthSignalState,
    MonitorRuntime,
    Organization,
    RawEvent,
    TxnCategorization,
)
from backend.app.services import monitoring_service
from backend.app.signals.v2 import (
    detect_expense_creep_by_vendor,
    detect_low_cash_runway,
    detect_unusual_outflow_spike,
)
from backend.app.norma.normalize import NormalizedTransaction


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
    org = Organization(name="Monitor Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Monitor Biz")
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


def _txn(
    source_event_id: str,
    occurred_at: datetime,
    description: str,
    amount: float,
    direction: str,
    counterparty_hint: str | None = None,
):
    return NormalizedTransaction(
        id=None,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        date=occurred_at.date(),
        description=description,
        amount=amount,
        direction=direction,
        account="bank",
        category="general",
        counterparty_hint=counterparty_hint,
    )


def test_expense_creep_detector():
    base = datetime(2024, 5, 1, tzinfo=timezone.utc)
    txns = []
    for i in range(14):
        txns.append(_txn(f"p{i}", base + timedelta(days=i), "Acme Co", 20.0, "outflow", "Acme Co"))
    for i in range(14):
        txns.append(
            _txn(f"c{i}", base + timedelta(days=14 + i), "Acme Co", 50.0, "outflow", "Acme Co")
        )

    signals = detect_expense_creep_by_vendor("biz-1", txns)
    assert len(signals) == 1
    assert signals[0].signal_type == "expense_creep_by_vendor"
    assert signals[0].payload["delta"] >= 200.0


def test_low_cash_runway_detector():
    base = datetime(2024, 4, 1, tzinfo=timezone.utc)
    txns = [_txn("inflow", base - timedelta(days=1), "Deposit", 2000.0, "inflow")]
    for i in range(30):
        txns.append(_txn(f"burn{i}", base + timedelta(days=i), "Rent", 40.0, "outflow"))

    signals = detect_low_cash_runway("biz-2", txns)
    assert len(signals) == 1
    assert signals[0].severity == "high"


def test_unusual_outflow_spike_detector():
    base = datetime(2024, 3, 1, tzinfo=timezone.utc)
    txns = [
        _txn(f"day{i}", base + timedelta(days=i), "Supplies", 100.0, "outflow")
        for i in range(29)
    ]
    txns.append(_txn("spike", base + timedelta(days=29), "Supplies", 1000.0, "outflow"))

    signals = detect_unusual_outflow_spike("biz-3", txns)
    assert len(signals) == 1
    assert signals[0].signal_type == "unusual_outflow_spike"


def test_pulse_idempotency_and_audit(db_session):
    biz = _create_business(db_session)
    cat = _create_account_and_category(db_session, biz.id)
    now = datetime(2024, 6, 30, tzinfo=timezone.utc)

    _add_raw_event(db_session, biz.id, "prior", now - timedelta(days=20), 300.0, "outflow", "Acme", "Acme")
    _add_raw_event(db_session, biz.id, "current", now - timedelta(days=5), 600.0, "outflow", "Acme", "Acme")
    _categorize(db_session, biz.id, "prior", cat.id)
    _categorize(db_session, biz.id, "current", cat.id)
    db_session.commit()

    first = monitoring_service.pulse(db_session, biz.id)
    assert first["ran"] is True
    initial_count = db_session.execute(
        select(HealthSignalState).where(HealthSignalState.business_id == biz.id)
    ).scalars().all()
    detected_count = db_session.execute(
        select(AuditLog).where(
            AuditLog.business_id == biz.id,
            AuditLog.event_type == "signal_detected",
        )
    ).scalars().all()

    runtime = db_session.get(MonitorRuntime, biz.id)
    runtime.last_pulse_at = runtime.last_pulse_at - timedelta(minutes=11)
    db_session.commit()

    second = monitoring_service.pulse(db_session, biz.id)
    assert second["ran"] is True

    states = db_session.execute(
        select(HealthSignalState).where(HealthSignalState.business_id == biz.id)
    ).scalars().all()
    assert len(states) == len(initial_count)

    audit_rows = db_session.execute(
        select(AuditLog).where(AuditLog.business_id == biz.id)
    ).scalars().all()
    assert sum(1 for row in audit_rows if row.event_type == "signal_detected") == len(detected_count)


def test_pulse_gating_and_resolution(db_session):
    biz = _create_business(db_session)
    cat = _create_account_and_category(db_session, biz.id)
    now = datetime(2024, 7, 15, tzinfo=timezone.utc)

    _add_raw_event(db_session, biz.id, "prior", now - timedelta(days=20), 300.0, "outflow", "Acme", "Acme")
    _add_raw_event(db_session, biz.id, "current", now - timedelta(days=3), 600.0, "outflow", "Acme", "Acme")
    _categorize(db_session, biz.id, "prior", cat.id)
    _categorize(db_session, biz.id, "current", cat.id)
    db_session.commit()

    first = monitoring_service.pulse(db_session, biz.id)
    assert first["ran"] is True

    gate = monitoring_service.pulse(db_session, biz.id)
    assert gate["ran"] is False

    runtime = db_session.get(MonitorRuntime, biz.id)
    runtime.last_pulse_at = runtime.last_pulse_at - timedelta(minutes=11)
    db_session.commit()

    _add_raw_event(
        db_session,
        biz.id,
        "current2",
        now - timedelta(days=2),
        900.0,
        "outflow",
        "Acme",
        "Acme",
    )
    _categorize(db_session, biz.id, "current2", cat.id)
    db_session.commit()

    updated = monitoring_service.pulse(db_session, biz.id)
    assert updated["ran"] is True

    db_session.execute(delete(TxnCategorization).where(TxnCategorization.business_id == biz.id))
    db_session.execute(delete(RawEvent).where(RawEvent.business_id == biz.id))
    db_session.commit()

    runtime = db_session.get(MonitorRuntime, biz.id)
    runtime.last_pulse_at = runtime.last_pulse_at - timedelta(minutes=11)
    db_session.commit()

    resolved = monitoring_service.pulse(db_session, biz.id)
    assert resolved["ran"] is True

    audit_rows = db_session.execute(
        select(AuditLog).where(AuditLog.business_id == biz.id)
    ).scalars().all()
    event_types = {row.event_type for row in audit_rows}
    assert "signal_detected" in event_types
    assert "signal_updated" in event_types
    assert "signal_resolved" in event_types
