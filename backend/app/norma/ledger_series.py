"""
Ledger-derived series helpers.

Shared utilities for computing monthly rollups directly from ledger rows,
so downstream analytics and facts share a single source of truth.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from .ledger import LedgerRow


def _month_key_from_dt(dt: date) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _month_from_iso(dt_iso: str) -> Optional[str]:
    try:
        parsed = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        return _month_key_from_dt(parsed.date())
    except Exception:
        return None


def _month_key(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return _month_key_from_dt(value.date())
    if isinstance(value, date):
        return _month_key_from_dt(value)
    if isinstance(value, str):
        return _month_from_iso(value)
    return None


def monthly_cashflow_from_ledger(ledger: Iterable[LedgerRow]) -> List[Dict[str, float]]:
    monthly: Dict[str, Dict[str, float]] = {}

    for row in ledger:
        month = _month_key(row.occurred_at) or _month_key(row.date)
        if not month:
            continue
        if month not in monthly:
            monthly[month] = {"inflow": 0.0, "outflow": 0.0}

        if row.amount >= 0:
            monthly[month]["inflow"] += float(row.amount)
        else:
            monthly[month]["outflow"] += abs(float(row.amount))

    return [
        {
            "month": month,
            "inflow": monthly[month]["inflow"],
            "outflow": monthly[month]["outflow"],
            "net": monthly[month]["inflow"] - monthly[month]["outflow"],
        }
        for month in sorted(monthly.keys())
    ]


def monthly_cashflow_from_ledger_rows(
    ledger_rows: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, float]]:
    if not ledger_rows:
        return []

    monthly: Dict[str, Dict[str, float]] = {}

    for row in ledger_rows:
        month = _month_key(row.get("occurred_at")) or _month_key(row.get("date"))
        if not month:
            continue
        if month not in monthly:
            monthly[month] = {"inflow": 0.0, "outflow": 0.0}

        amt = float(row.get("amount") or 0.0)
        if amt >= 0:
            monthly[month]["inflow"] += amt
        else:
            monthly[month]["outflow"] += abs(amt)

    return [
        {
            "month": month,
            "inflow": monthly[month]["inflow"],
            "outflow": monthly[month]["outflow"],
            "net": monthly[month]["inflow"] - monthly[month]["outflow"],
        }
        for month in sorted(monthly.keys())
    ]
