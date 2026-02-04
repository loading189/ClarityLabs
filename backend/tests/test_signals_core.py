from datetime import datetime, timezone
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.norma.ledger import build_cash_ledger  # noqa: E402
from backend.app.norma.normalize import NormalizedTransaction  # noqa: E402
from backend.app.signals.core import (  # noqa: E402
    cash_runway_trend_signal,
    expense_creep_signal,
    generate_core_signals,
    revenue_volatility_signal,
)
from backend.app.signals.schema import Signal  # noqa: E402


def _txn(
    source_event_id: str,
    occurred_at: datetime,
    description: str,
    amount: float,
    direction: str,
    category: str,
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
        category=category,
        counterparty_hint=None,
    )


def test_core_signals_stable_outputs():
    txns = [
        _txn("evt_1", datetime(2024, 2, 15, 12, 0, tzinfo=timezone.utc), "Invoice", 1000.0, "inflow", "sales"),
        _txn("evt_2", datetime(2024, 2, 20, 12, 0, tzinfo=timezone.utc), "Software", 100.0, "outflow", "software"),
        _txn("evt_3", datetime(2024, 2, 25, 12, 0, tzinfo=timezone.utc), "Software", 100.0, "outflow", "software"),
        _txn("evt_3b", datetime(2024, 2, 18, 12, 0, tzinfo=timezone.utc), "Rent", 100.0, "outflow", "rent"),
        _txn("evt_4", datetime(2024, 3, 20, 12, 0, tzinfo=timezone.utc), "Invoice", 800.0, "inflow", "sales"),
        _txn("evt_5", datetime(2024, 3, 25, 12, 0, tzinfo=timezone.utc), "Rent", 500.0, "outflow", "rent"),
        _txn("evt_6", datetime(2024, 3, 30, 12, 0, tzinfo=timezone.utc), "Software", 400.0, "outflow", "software"),
    ]
    ledger = build_cash_ledger(txns, opening_balance=0.0)

    signals = generate_core_signals(txns, ledger)
    by_id = {signal.id: signal for signal in signals}

    assert by_id["cash_runway_trend"].severity == "red"
    assert by_id["expense_creep"].severity in {"yellow", "red"}
    assert by_id["revenue_volatility"].severity in {"green", "yellow", "red"}


def test_missing_inputs_return_safe_signal():
    signal = cash_runway_trend_signal([], [])

    assert signal.severity == "yellow"
    assert signal.baseline_value is None
    assert signal.current_value is None
    assert signal.delta is None

    creep = expense_creep_signal([])
    assert creep.severity == "yellow"
    assert creep.baseline_value is None
    assert creep.current_value is None

    volatility = revenue_volatility_signal([])
    assert volatility.severity == "yellow"
    assert volatility.baseline_value is None
    assert volatility.current_value is None


def test_signals_conform_to_schema():
    txns = [
        _txn("evt_1", datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc), "Invoice", 300.0, "inflow", "sales"),
        _txn("evt_2", datetime(2024, 1, 12, 12, 0, tzinfo=timezone.utc), "Rent", 100.0, "outflow", "rent"),
        _txn("evt_3", datetime(2024, 2, 2, 12, 0, tzinfo=timezone.utc), "Invoice", 200.0, "inflow", "sales"),
        _txn("evt_4", datetime(2024, 2, 9, 12, 0, tzinfo=timezone.utc), "Rent", 120.0, "outflow", "rent"),
        _txn("evt_5", datetime(2024, 2, 16, 12, 0, tzinfo=timezone.utc), "Invoice", 180.0, "inflow", "sales"),
        _txn("evt_6", datetime(2024, 2, 23, 12, 0, tzinfo=timezone.utc), "Invoice", 140.0, "inflow", "sales"),
        _txn("evt_7", datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc), "Invoice", 160.0, "inflow", "sales"),
        _txn("evt_8", datetime(2024, 3, 8, 12, 0, tzinfo=timezone.utc), "Invoice", 220.0, "inflow", "sales"),
    ]
    ledger = build_cash_ledger(txns, opening_balance=0.0)
    signals = [
        cash_runway_trend_signal(txns, ledger),
        expense_creep_signal(txns),
        revenue_volatility_signal(txns),
    ]

    for signal in signals:
        assert isinstance(signal, Signal)
        assert signal.id
        assert signal.type
        assert signal.window
        assert isinstance(signal.explanation_seed, dict)
