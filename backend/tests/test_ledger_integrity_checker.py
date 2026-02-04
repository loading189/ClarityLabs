from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.norma.ledger import (  # noqa: E402
    LedgerIntegrityError,
    LedgerRow,
    build_cash_ledger,
    check_ledger_integrity,
)
from backend.app.norma.normalize import NormalizedTransaction  # noqa: E402


def _txn(source_event_id: str, occurred_at: datetime, description: str, amount: float, direction: str):
    return NormalizedTransaction(
        id=None,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        date=occurred_at.date(),
        description=description,
        amount=amount,
        direction=direction,
        account="bank",
        category="sales",
        counterparty_hint=None,
    )


def test_check_ledger_integrity_passes_known_good_ledger():
    occurred_at = datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc)
    txns = [
        _txn("evt_1", occurred_at, "Deposit", 100.0, "inflow"),
        _txn("evt_2", occurred_at, "Vendor", 40.0, "outflow"),
    ]
    ledger = build_cash_ledger(txns, opening_balance=10.0)

    summary = check_ledger_integrity(ledger, opening_balance=10.0)

    assert summary["rows"] == 2
    assert summary["net_cash_flow"] == 60.0
    assert summary["inflow_total"] == 100.0
    assert summary["outflow_total"] == -40.0


def test_check_ledger_integrity_fails_on_discontinuous_balance():
    occurred_at = datetime(2024, 3, 2, 9, 0, tzinfo=timezone.utc)
    txns = [
        _txn("evt_1", occurred_at, "Deposit", 100.0, "inflow"),
    ]
    ledger = build_cash_ledger(txns, opening_balance=0.0)
    bad = [replace(ledger[0], balance=999.0)]

    with pytest.raises(LedgerIntegrityError, match="running balance mismatch"):
        check_ledger_integrity(bad, opening_balance=0.0)


def test_check_ledger_integrity_fails_on_ordering():
    t1 = datetime(2024, 3, 2, 9, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 3, 2, 10, 0, tzinfo=timezone.utc)
    ledger = [
        LedgerRow(
            occurred_at=t2,
            source_event_id="evt_2",
            date=t2.date(),
            description="Later",
            amount=10.0,
            category="sales",
            balance=10.0,
        ),
        LedgerRow(
            occurred_at=t1,
            source_event_id="evt_1",
            date=t1.date(),
            description="Earlier",
            amount=5.0,
            category="sales",
            balance=15.0,
        ),
    ]

    with pytest.raises(LedgerIntegrityError, match="deterministically ordered"):
        check_ledger_integrity(ledger, opening_balance=0.0)


def test_check_ledger_integrity_fails_on_net_mismatch():
    occurred_at = datetime(2024, 3, 3, 9, 0, tzinfo=timezone.utc)
    txns = [
        _txn("evt_1", occurred_at, "Micro inflow", 0.016, "inflow"),
        _txn("evt_2", occurred_at, "Micro outflow", 0.014, "outflow"),
    ]
    ledger = build_cash_ledger(txns, opening_balance=0.0)

    with pytest.raises(LedgerIntegrityError, match="inflow \\+ outflow does not equal net"):
        check_ledger_integrity(ledger, opening_balance=0.0)
