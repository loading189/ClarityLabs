from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest
from statistics import pstdev

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ledger_anchor_traceability.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Account, Business, Category, Organization, RawEvent, TxnCategorization
from backend.app.services import ledger_service, monitoring_service, signals_service


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
    org = Organization(name="Anchor Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Anchor Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _create_categories(db_session, business_id: str) -> dict[str, Category]:
    expense_account = Account(business_id=business_id, name="Operating Expense", type="expense")
    revenue_account = Account(business_id=business_id, name="Sales", type="revenue")
    db_session.add_all([expense_account, revenue_account])
    db_session.flush()

    categories = {
        "General": Category(business_id=business_id, account_id=expense_account.id, name="General"),
        "Payroll": Category(business_id=business_id, account_id=expense_account.id, name="Payroll"),
        "Uncategorized": Category(business_id=business_id, account_id=expense_account.id, name="Uncategorized"),
        "Sales": Category(business_id=business_id, account_id=revenue_account.id, name="Sales"),
    }
    db_session.add_all(categories.values())
    db_session.flush()
    return categories


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


def _seed_traceability_dataset(db_session, business_id: str) -> None:
    categories = _create_categories(db_session, business_id)
    anchor = date(2024, 6, 30)
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"evt-{counter:04d}"

    def add_txn(day: date, amount: float, direction: str, description: str, counterparty: str, category: str) -> None:
        event_id = next_id()
        occurred_at = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        _add_raw_event(
            db_session,
            business_id,
            event_id,
            occurred_at,
            amount,
            direction,
            description,
            counterparty,
        )
        _categorize(db_session, business_id, event_id, categories[category].id)

    # Prior revenue window inflows (low volatility)
    prior_inflow_dates = [anchor - timedelta(days=59 - i * 3) for i in range(10)]
    prior_inflow_amounts = [280, 300, 320, 290, 310, 305, 295, 315, 285, 300]
    for day, amount in zip(prior_inflow_dates, prior_inflow_amounts):
        add_txn(day, amount, "inflow", "Subscription", "Customer Base", "Sales")

    # Current revenue window inflows (volatile + concentrated)
    current_inflows = [
        (anchor - timedelta(days=0), 800, "Big Customer"),
        (anchor - timedelta(days=1), 200, "Big Customer"),
        (anchor - timedelta(days=2), 150, "Customer D"),
        (anchor - timedelta(days=3), 100, "Customer B"),
        (anchor - timedelta(days=4), 100, "Customer C"),
    ]
    for day, amount, customer in current_inflows:
        add_txn(day, amount, "inflow", "Invoice", customer, "Sales")

    # Prior window daily outflows (for cash trend down)
    for offset in range(43, 29, -1):
        day = anchor - timedelta(days=offset)
        add_txn(day, 20, "outflow", "Office supplies", "Base Vendor", "General")

    # Early window outflows (timing mismatch)
    for idx, offset in enumerate(range(29, 19, -1)):
        day = anchor - timedelta(days=offset)
        category = "Uncategorized" if idx < 5 else "General"
        add_txn(day, 300, "outflow", "Ops spend", "Base Vendor", category)

    # Current window daily outflows (cash trend down + uncategorized)
    for idx, offset in enumerate(range(13, -1, -1)):
        day = anchor - timedelta(days=offset)
        category = "Uncategorized" if idx < 10 else "General"
        add_txn(day, 200, "outflow", "Operational spend", "Base Vendor", category)

    # Expense creep (Acme)
    add_txn(anchor - timedelta(days=25), 150, "outflow", "Acme", "Acme", "General")
    add_txn(anchor - timedelta(days=20), 150, "outflow", "Acme", "Acme", "General")
    add_txn(anchor - timedelta(days=10), 400, "outflow", "Acme", "Acme", "General")
    add_txn(anchor - timedelta(days=2), 400, "outflow", "Acme", "Acme", "General")

    # New recurring expense
    add_txn(anchor - timedelta(days=25), 120, "outflow", "New SaaS", "New SaaS", "General")
    add_txn(anchor - timedelta(days=15), 120, "outflow", "New SaaS", "New SaaS", "General")
    add_txn(anchor - timedelta(days=5), 120, "outflow", "New SaaS", "New SaaS", "General")

    # Payroll cliff + spike day
    add_txn(anchor, 8000, "outflow", "Payroll", "Payroll Inc", "Payroll")

    db_session.commit()
    monitoring_service.pulse(db_session, business_id)


def _run_anchor_query(db_session, business_id: str, anchor_query: dict[str, object], highlight: list[str] | None = None):
    start_date = anchor_query.get("start_date")
    end_date = anchor_query.get("end_date")
    query = {
        "start_date": date.fromisoformat(start_date) if isinstance(start_date, str) else None,
        "end_date": date.fromisoformat(end_date) if isinstance(end_date, str) else None,
        "accounts": anchor_query.get("accounts") or None,
        "vendors": anchor_query.get("vendors") or None,
        "categories": anchor_query.get("categories") or None,
        "search": anchor_query.get("search") or None,
        "direction": anchor_query.get("direction") or None,
        "source_event_ids": anchor_query.get("source_event_ids") or None,
        "highlight_source_event_ids": highlight,
        "limit": 2000,
        "offset": 0,
    }
    return ledger_service.ledger_query(db_session, business_id, **query)


def _average_balance(rows: list[dict]) -> float:
    last_by_date = {}
    for row in rows:
        last_by_date[row["date"]] = float(row["balance"])
    values = list(last_by_date.values())
    if not values:
        return 0.0
    return sum(values) / len(values)


def _daily_std(rows: list[dict]) -> float:
    totals = {}
    for row in rows:
        amount = float(row["amount"])
        totals[row["date"]] = totals.get(row["date"], 0.0) + abs(amount)
    series = list(totals.values())
    return pstdev(series) if len(series) > 1 else 0.0


def _expected_metric(evidence_key: str, query: dict[str, object], payload: dict[str, object], rows: list[dict], summary: dict) -> float:
    direction = query.get("direction")
    if evidence_key == "total_inflow":
        return float(summary["total_in"])
    if evidence_key in {"total_outflow", "outflow_total", "latest_total", "cliff_total"}:
        return float(summary["total_out"])
    if evidence_key in {"current_total", "prior_total", "counterparty_total", "baseline_avg"}:
        if direction == "inflow":
            return float(summary["total_in"])
        if direction == "outflow":
            return float(summary["total_out"])
    if evidence_key in {"txn_count", "uncategorized_count"}:
        return float(summary["row_count"])
    if evidence_key == "current_std":
        return round(_daily_std(rows), 2)
    if evidence_key == "current_avg_balance":
        return round(_average_balance(rows), 2)
    raise AssertionError(f"Unhandled evidence key: {evidence_key}")


def test_anchor_traceability_parity_and_pagination(db_session):
    biz = _create_business(db_session)
    _seed_traceability_dataset(db_session, biz.id)

    states, _ = signals_service.list_signal_states(db_session, biz.id)
    signal_types = {row["type"] for row in states}
    expected = {
        "expense_creep_by_vendor",
        "low_cash_runway",
        "unusual_outflow_spike",
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
    }
    assert expected.issubset(signal_types)

    for signal in states:
        explain = signals_service.get_signal_explain(db_session, biz.id, signal["id"])
        payload = explain["state"]["metadata"] or {}
        for anchor in explain["ledger_anchors"]:
            query = anchor["query"]
            highlight_ids = query.get("source_event_ids") if isinstance(query, dict) else None
            payload_result = _run_anchor_query(db_session, biz.id, query, highlight=highlight_ids)
            rows = payload_result["rows"]
            summary = payload_result["summary"]

            if highlight_ids:
                highlighted = {row["source_event_id"] for row in rows if row.get("is_highlighted")}
                assert set(highlight_ids).issubset(highlighted)

            for evidence_key in anchor.get("evidence_keys", []):
                expected_value = _expected_metric(evidence_key, query, payload, rows, summary)
                actual = payload.get(evidence_key)
                assert actual is not None
                assert round(float(actual), 2) == round(float(expected_value), 2)

            if summary["row_count"] > 3:
                collected = []
                offset = 0
                while True:
                    page = ledger_service.ledger_query(
                        db_session,
                        biz.id,
                        start_date=date.fromisoformat(query["start_date"]),
                        end_date=date.fromisoformat(query["end_date"]),
                        accounts=query.get("accounts"),
                        vendors=query.get("vendors"),
                        categories=query.get("categories"),
                        search=query.get("search"),
                        direction=query.get("direction"),
                        source_event_ids=query.get("source_event_ids"),
                        limit=2,
                        offset=offset,
                    )
                    collected.extend(page["rows"])
                    offset += 2
                    if len(collected) >= summary["row_count"] or not page["rows"]:
                        break
                assert [row["source_event_id"] for row in collected] == [row["source_event_id"] for row in rows]


def test_signal_explain_anchor_highlight_consistency(db_session):
    biz = _create_business(db_session)
    _seed_traceability_dataset(db_session, biz.id)

    states, _ = signals_service.list_signal_states(db_session, biz.id)
    expense_signal_id = next(row["id"] for row in states if row["type"] == "expense_creep_by_vendor")
    explain = signals_service.get_signal_explain(db_session, biz.id, expense_signal_id)

    anchor = next(item for item in explain["ledger_anchors"] if "current_total" in item.get("evidence_keys", []))
    query = anchor["query"]
    highlight_ids = query.get("source_event_ids")

    payload_result = _run_anchor_query(db_session, biz.id, query, highlight=highlight_ids)
    rows = payload_result["rows"]
    summary = payload_result["summary"]

    if highlight_ids:
        highlighted = {row["source_event_id"] for row in rows if row.get("is_highlighted")}
        assert set(highlight_ids).issubset(highlighted)

    expected_value = _expected_metric("current_total", query, explain["state"]["metadata"], rows, summary)
    assert round(float(explain["state"]["metadata"]["current_total"]), 2) == round(float(expected_value), 2)
