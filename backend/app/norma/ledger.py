"""
Norma - ledger construction layer.

Responsibility:
- Convert normalized transactions into a simple cash ledger with a running balance.

Design notes:
- This is an MVP "cash ledger" (not accrual).
- Keep it deterministic: same inputs should produce the same ledger order and balances.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List
import math

from .normalize import NormalizedTransaction


@dataclass(frozen=True)
class LedgerRow:
    """
    A single line in a running cash ledger.

    Invariants:
    - balance is the running total after applying this row's signed amount
    - rows are ordered deterministically
    """
    occurred_at: datetime
    source_event_id: str

    date: date
    description: str
    amount: float
    category: str
    balance: float


def _sort_key(t: NormalizedTransaction) -> tuple:
    # Deterministic ordering even when multiple txns share the same date/time.
    # Prefer occurred_at, then description, then amount, then source_event_id as a stable tie-breaker.
    return (
        t.occurred_at,
        t.description or "",
        float(t.amount or 0.0),
        t.source_event_id or "",
    )


def _signed_amount(t: NormalizedTransaction) -> float:
    amt = float(t.amount or 0.0)
    return amt if t.direction == "inflow" else -amt


def build_cash_ledger(
    txns: Iterable[NormalizedTransaction],
    opening_balance: float = 0.0,
) -> List[LedgerRow]:
    txns_sorted = sorted(txns, key=_sort_key)

    balance = float(opening_balance)
    ledger: List[LedgerRow] = []

    for t in txns_sorted:
        amt = _signed_amount(t)
        balance += amt
        ledger.append(
            LedgerRow(
                occurred_at=t.occurred_at,
                source_event_id=t.source_event_id,
                date=t.date,
                description=t.description,
                amount=amt,
                category=t.category or "uncategorized",
                balance=balance,
            )
        )

    return ledger


class LedgerIntegrityError(ValueError):
    pass


def check_ledger_integrity(
    ledger: Iterable[LedgerRow],
    *,
    opening_balance: float = 0.0,
) -> dict:
    """
    Side-effect-free ledger integrity check.

    Invariants:
    - Running balances are continuous.
    - Inflow + outflow = net cash flow.
    - Amounts are finite signed values.
    - Ledger rows are deterministically ordered.
    """
    rows = list(ledger)
    last_balance = float(opening_balance or 0.0)
    prev_key: tuple | None = None

    inflow = 0.0
    outflow = 0.0
    total = 0.0

    for idx, row in enumerate(rows):
        amount = float(row.amount or 0.0)
        if not math.isfinite(amount):
            raise LedgerIntegrityError(f"Invariant violation: non-finite amount at row {idx}.")

        key = (
            row.occurred_at,
            row.description or "",
            amount,
            row.source_event_id or "",
        )
        if prev_key and key < prev_key:
            raise LedgerIntegrityError(
                "Invariant violation: ledger rows are not deterministically ordered."
            )

        expected = last_balance + amount
        if abs(float(row.balance) - expected) > 1e-6:
            raise LedgerIntegrityError(
                f"Invariant violation: running balance mismatch at row {idx}."
            )

        if amount >= 0:
            inflow += amount
        else:
            outflow += amount

        total += amount
        last_balance = float(row.balance)
        prev_key = key

    net = inflow + outflow
    if abs(net - total) > 1e-6:
        raise LedgerIntegrityError(
            "Invariant violation: inflow + outflow does not equal net cash flow."
        )

    if rows:
        expected_total = rows[-1].balance - float(opening_balance or 0.0)
        if abs(expected_total - total) > 1e-6:
            raise LedgerIntegrityError(
                "Invariant violation: net cash flow does not reconcile to ending balance."
            )

    return {
        "rows": len(rows),
        "net_cash_flow": round(total, 2),
        "inflow_total": round(inflow, 2),
        "outflow_total": round(outflow, 2),
    }
