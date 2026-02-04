from datetime import datetime, timezone

from backend.app.norma.ledger import build_cash_ledger
from backend.app.norma.normalize import NormalizedTransaction


def _txn(source_event_id: str, occurred_at: datetime, description: str, amount: float, direction: str):
    return NormalizedTransaction(
        id=None,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        date=occurred_at.date(),
        description=description,
        amount=amount,
        direction=direction,  # expects absolute amount
        account="bank",
        category="sales",
        counterparty_hint=None,
    )


def test_build_cash_ledger_empty():
    assert build_cash_ledger([]) == []


def test_build_cash_ledger_orders_same_timestamp_deterministically():
    occurred_at = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
    txns = [
        _txn("evt_b", occurred_at, "Bravo", 50.0, "inflow"),
        _txn("evt_a", occurred_at, "Alpha", 50.0, "inflow"),
        _txn("evt_c", occurred_at, "Alpha", 10.0, "outflow"),
    ]

    ledger = build_cash_ledger(txns, opening_balance=0.0)

    assert [row.source_event_id for row in ledger] == ["evt_a", "evt_b", "evt_c"]
    assert [row.amount for row in ledger] == [50.0, 50.0, -10.0]


def test_build_cash_ledger_running_balance_mixed_directions():
    occurred_at = datetime(2024, 2, 1, 12, 0, tzinfo=timezone.utc)
    txns = [
        _txn("evt_1", occurred_at, "Deposit", 100.0, "inflow"),
        _txn("evt_2", occurred_at, "Vendor", 35.0, "outflow"),
        _txn("evt_3", occurred_at, "Refund", 20.0, "inflow"),
    ]

    ledger = build_cash_ledger(txns, opening_balance=10.0)

    assert [row.balance for row in ledger] == [110.0, 130.0, 95.0]
