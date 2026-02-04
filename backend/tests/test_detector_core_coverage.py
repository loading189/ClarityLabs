from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_detector_core_coverage.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import (
    Account,
    Business,
    Category,
    Organization,
    RawEvent,
    TxnCategorization,
)
from backend.app.services import monitoring_service, signals_service


CORE_SIGNAL_IDS = {
    "liquidity.runway_low",
    "liquidity.cash_trend_down",
    "revenue.decline_vs_baseline",
    "revenue.volatility_spike",
    "expense.spike_vs_baseline",
    "expense.new_recurring",
    "timing.inflow_outflow_mismatch",
    "timing.payroll_rent_cliff",
    "concentration.revenue_top_customer",
    "concentration.expense_top_vendor",
    "hygiene.uncategorized_high",
    "hygiene.signal_flapping",
}


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
    org = Organization(name="Detector Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Detector Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _create_account_and_category(db_session, business_id: str, name: str, account_type: str) -> Category:
    acct = Account(business_id=business_id, name=name, type=account_type)
    db_session.add(acct)
    db_session.flush()
    cat = Category(business_id=business_id, account_id=acct.id, name=name)
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
):
    payload = {
        "type": "plaid.transaction",
        "description": description,
        "amount": amount,
        "direction": direction,
        "counterparty_hint": description,
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


def test_detector_registry_covers_core_signals():
    catalog_ids = set(signals_service.SIGNAL_CATALOG.keys())
    assert CORE_SIGNAL_IDS.issubset(catalog_ids)
    assert CORE_SIGNAL_IDS.issubset(monitoring_service.MONITOR_SIGNAL_TYPES)


def test_pulse_emits_liquidity_and_expense_signals(db_session):
    biz = _create_business(db_session)
    revenue_cat = _create_account_and_category(db_session, biz.id, "Sales", "revenue")
    expense_cat = _create_account_and_category(db_session, biz.id, "General", "expense")

    now = datetime(2024, 7, 1, tzinfo=timezone.utc)
    # baseline outflows
    for idx, days in enumerate([25, 20, 15, 10]):
        event_id = f"outflow-base-{idx}"
        _add_raw_event(
            db_session,
            biz.id,
            event_id,
            now - timedelta(days=days),
            100.0,
            "outflow",
            "Vendor A",
        )
        _categorize(db_session, biz.id, event_id, expense_cat.id)

    # recent spike outflow
    _add_raw_event(
        db_session,
        biz.id,
        "outflow-spike",
        now - timedelta(days=1),
        2000.0,
        "outflow",
        "Vendor A",
    )
    _categorize(db_session, biz.id, "outflow-spike", expense_cat.id)

    # modest inflow
    _add_raw_event(
        db_session,
        biz.id,
        "inflow-1",
        now - timedelta(days=3),
        300.0,
        "inflow",
        "Customer A",
    )
    _categorize(db_session, biz.id, "inflow-1", revenue_cat.id)

    db_session.commit()

    monitoring_service.pulse(db_session, biz.id)

    states, _ = signals_service.list_signal_states(db_session, biz.id)
    signal_types = {row["type"] for row in states}
    assert "liquidity.runway_low" in signal_types
    assert "expense.spike_vs_baseline" in signal_types

    expense_signal_id = next(row["id"] for row in states if row["type"] == "expense.spike_vs_baseline")
    explain = signals_service.get_signal_explain(db_session, biz.id, expense_signal_id)
    evidence_keys = {item["key"] for item in explain["evidence"]}
    assert "current_total" in evidence_keys
    current_total = next(item for item in explain["evidence"] if item["key"] == "current_total")
    assert current_total.get("anchors")
