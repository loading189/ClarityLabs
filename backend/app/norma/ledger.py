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
