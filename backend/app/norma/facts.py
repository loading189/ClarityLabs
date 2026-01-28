"""
Norma - facts layer.

Responsibility:
- Reduce normalized transactions + ledger rows into "facts" that are stable inputs
  to Clarity Labs (signals).
- Facts are accountant-friendly aggregates:
  - current cash
  - monthly inflow/outflow/net
  - totals by category
  - small ledger preview
  - (optional) rolling-window aggregates for better signals

Design notes:
- Keep computations unrounded (full precision).
- Apply rounding/formatting only when serializing for API/UI.
- Facts must be deterministic: same inputs -> same outputs.
- Facts are a contract: changes should be additive and versioned if breaking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .ledger import LedgerRow
from .normalize import NormalizedTransaction


# ----------------------------
# Typed fact records (internal)
# ----------------------------

@dataclass(frozen=True)
class MonthlyCashflow:
    """
    Monthly rollup.

    Invariants:
    - inflow >= 0
    - outflow >= 0 (stored as magnitude, not signed)
    - net = inflow - outflow (can be negative)
    """
    month: str  # "YYYY-MM"
    inflow: float
    outflow: float
    net: float


@dataclass(frozen=True)
class CategoryTotal:
    """
    Category total using signed convention.

    Invariant:
    - total is signed (positive=inflow categories, negative=spend categories)
    """
    category: str
    total: float


@dataclass(frozen=True)
class LedgerPreviewRow:
    """
    A UI-friendly ledger preview row (with provenance).
    """
    occurred_at: str          # ISO datetime string
    source_event_id: str      # stable join key

    date: str                 # ISO date string
    description: str
    amount: float
    category: str
    balance: float



@dataclass(frozen=True)
class FactsMeta:
    """
    Audit/context metadata.

    - as_of: what date these facts are computed through (usually last ledger date)
    - txn_count: number of normalized transactions used
    - months_covered: number of distinct months in monthly rollup
    """
    as_of: Optional[str]  # ISO date string, or None if no data
    txn_count: int
    months_covered: int


@dataclass(frozen=True)
class WindowFacts:
    """
    Rolling-window aggregates for trend-style signals.

    These are optional but extremely useful for robust signals:
    - last_30d_*: totals over the most recent 30 days
    - prev_30d_*: totals over the prior 30 days window (days 31–60 back)

    Deterministic windowing is based on transaction dates (not current time).
    Anchor date = latest transaction date in txns (or None if no txns).
    """
    anchor_date: Optional[str]  # ISO date string
    last_30d_inflow: float
    last_30d_outflow: float
    last_30d_net: float
    prev_30d_inflow: float
    prev_30d_outflow: float
    prev_30d_net: float


@dataclass(frozen=True)
class WindowPair:
    window_days: int
    anchor_date: Optional[str]  # ISO date
    last_inflow: float
    last_outflow: float
    last_net: float
    prev_inflow: float
    prev_outflow: float
    prev_net: float


@dataclass(frozen=True)
class RollingWindowFacts:
    windows: Dict[int, WindowPair]  # {30: WindowPair, 60: ..., 90: ...}


@dataclass(frozen=True)
class Facts:
    """
    Stable, explainable aggregates computed from the normalized transaction stream.
    """
    current_cash: float
    monthly_inflow_outflow: List[MonthlyCashflow]
    totals_by_category: List[CategoryTotal]
    last_10_ledger_rows: List[LedgerPreviewRow]

    # Additive extensions (safe to ignore in callers)
    meta: FactsMeta
    windows: Optional[RollingWindowFacts] = None


# ----------------------------
# Helpers
# ----------------------------

def month_key(d: date) -> str:
    """Convert a date into a YYYY-MM month key."""
    return f"{d.year:04d}-{d.month:02d}"

def compute_window_pair(txns: List[NormalizedTransaction], window_days: int) -> Optional[WindowPair]:
    if not txns:
        return None

    anchor = max(t.date for t in txns)

    last_start = anchor - timedelta(days=window_days - 1)
    prev_start = anchor - timedelta(days=2 * window_days - 1)
    prev_end = anchor - timedelta(days=window_days)

    last_window = [t for t in txns if last_start <= t.date <= anchor]
    prev_window = [t for t in txns if prev_start <= t.date <= prev_end]

    last_in, last_out = _sum_inflow_outflow(last_window)
    prev_in, prev_out = _sum_inflow_outflow(prev_window)

    return WindowPair(
        window_days=window_days,
        anchor_date=anchor.isoformat(),
        last_inflow=last_in,
        last_outflow=last_out,
        last_net=last_in - last_out,
        prev_inflow=prev_in,
        prev_outflow=prev_out,
        prev_net=prev_in - prev_out,
    )


def compute_rolling_window_facts(
    txns: List[NormalizedTransaction],
    window_days_list: Tuple[int, ...] = (30, 60, 90),
) -> Optional[RollingWindowFacts]:
    if not txns:
        return None

    out: Dict[int, WindowPair] = {}
    for d in window_days_list:
        p = compute_window_pair(txns, d)
        if p:
            out[d] = p

    return RollingWindowFacts(windows=out)



def _sum_inflow_outflow(txns: Iterable[NormalizedTransaction]) -> Tuple[float, float]:
    inflow = 0.0
    outflow = 0.0
    for t in txns:
        if t.direction == "inflow":
            inflow += t.amount
        else:
            outflow += t.amount
    return inflow, outflow


def compute_monthly_cashflow(txns: Iterable[NormalizedTransaction]) -> List[MonthlyCashflow]:
    monthly: Dict[str, Dict[str, float]] = {}

    for t in txns:
        k = month_key(t.date)
        if k not in monthly:
            monthly[k] = {"inflow": 0.0, "outflow": 0.0}

        if t.direction == "inflow":
            monthly[k]["inflow"] += t.amount
        else:
            monthly[k]["outflow"] += t.amount

    rows: List[MonthlyCashflow] = []
    for k in sorted(monthly.keys()):
        inflow = monthly[k]["inflow"]
        outflow = monthly[k]["outflow"]
        rows.append(MonthlyCashflow(month=k, inflow=inflow, outflow=outflow, net=inflow - outflow))

    return rows


def compute_category_totals(txns: Iterable[NormalizedTransaction]) -> List[CategoryTotal]:
    cat_totals: Dict[str, float] = {}

    for t in txns:
        # Always ensure a category exists (defensive)
        cat = t.category or "uncategorized"
        signed = t.amount if t.direction == "inflow" else -t.amount
        cat_totals[cat] = cat_totals.get(cat, 0.0) + signed

    # Sort by absolute impact (largest magnitude first)
    rows = [
        CategoryTotal(category=c, total=v)
        for c, v in sorted(cat_totals.items(), key=lambda kv: abs(kv[1]), reverse=True)
    ]
    return rows


def build_ledger_preview(ledger: List[LedgerRow], limit: int = 10) -> List[LedgerPreviewRow]:
    preview: List[LedgerPreviewRow] = []
    for r in ledger[-limit:]:
        preview.append(
            LedgerPreviewRow(
                occurred_at=r.occurred_at.isoformat(),
                source_event_id=r.source_event_id,
                date=r.date.isoformat(),
                description=r.description,
                amount=r.amount,
                category=r.category,
                balance=r.balance,
            )
        )
    return preview



def compute_window_facts(txns: List[NormalizedTransaction]) -> Optional[WindowFacts]:
    """
    Compute 30-day rolling windows anchored to the most recent txn date.
    If there are no transactions, returns None.
    """
    if not txns:
        return None

    # Anchor deterministically to latest txn date (not "now")
    anchor = max(t.date for t in txns)
    start_last = anchor - timedelta(days=29)        # inclusive window: last 30 days
    start_prev = anchor - timedelta(days=59)        # prior window start
    end_prev = anchor - timedelta(days=30)          # inclusive end for previous window

    last_window = [t for t in txns if start_last <= t.date <= anchor]
    prev_window = [t for t in txns if start_prev <= t.date <= end_prev]

    last_in, last_out = _sum_inflow_outflow(last_window)
    prev_in, prev_out = _sum_inflow_outflow(prev_window)

    return WindowFacts(
        anchor_date=anchor.isoformat(),
        last_30d_inflow=last_in,
        last_30d_outflow=last_out,
        last_30d_net=last_in - last_out,
        prev_30d_inflow=prev_in,
        prev_30d_outflow=prev_out,
        prev_30d_net=prev_in - prev_out,
    )


def compute_facts(txns: List[NormalizedTransaction], ledger: List[LedgerRow]) -> Facts:
    """
    Compute Facts from normalized transactions and an already-built ledger.

    Notes:
    - current_cash comes from the final ledger balance if any rows exist.
    - as_of is derived from the last ledger row date if available, else last txn date, else None.
    - windows are computed deterministically from transaction dates.
    """
    monthly_rows = compute_monthly_cashflow(txns)
    cat_rows = compute_category_totals(txns)

    current_cash = ledger[-1].balance if ledger else 0.0
    last10 = build_ledger_preview(ledger, limit=10)

    as_of_date: Optional[date] = None
    if ledger:
        as_of_date = ledger[-1].date
    elif txns:
        as_of_date = max(t.date for t in txns)

    meta = FactsMeta(
        as_of=None if as_of_date is None else as_of_date.isoformat(),
        txn_count=len(txns),
        months_covered=len(monthly_rows),
    )

    windows = compute_rolling_window_facts(txns)


    return Facts(
        current_cash=current_cash,
        monthly_inflow_outflow=monthly_rows,
        totals_by_category=cat_rows,
        last_10_ledger_rows=last10,
        meta=meta,
        windows=windows,
    )


# ----------------------------
# Serialization helpers (API/UI boundary)
# ----------------------------

def round2(x: float) -> float:
    return round(float(x), 2)


def facts_to_dict(facts: Facts) -> dict:
    """
    Convert Facts into JSON-friendly primitives with consistent rounding.

    Backwards compatible:
    - Keeps existing keys: current_cash, monthly_inflow_outflow, totals_by_category, last_10_ledger_rows
    Additive:
    - meta
    - windows
    """
    out = {
        "current_cash": round2(facts.current_cash),
        "monthly_inflow_outflow": [
            {"month": r.month, "inflow": round2(r.inflow), "outflow": round2(r.outflow), "net": round2(r.net)}
            for r in facts.monthly_inflow_outflow
        ],
        "totals_by_category": [{"category": r.category, "total": round2(r.total)} for r in facts.totals_by_category],
      "last_10_ledger_rows": [
    {
        "occurred_at": r.occurred_at,
        "source_event_id": r.source_event_id,
        "date": r.date,
        "description": r.description,
        "amount": round2(r.amount),
        "category": r.category,
        "balance": round2(r.balance),
    }
    for r in facts.last_10_ledger_rows
        ],
        "meta": {
            "as_of": facts.meta.as_of,
            "txn_count": facts.meta.txn_count,
            "months_covered": facts.meta.months_covered,
        },
    }

    if facts.windows is not None:
        out["windows"] = {
            "windows": {
                str(k): {
                    "window_days": v.window_days,
                    "anchor_date": v.anchor_date,
                    "last_inflow": round2(v.last_inflow),
                    "last_outflow": round2(v.last_outflow),
                    "last_net": round2(v.last_net),
                    "prev_inflow": round2(v.prev_inflow),
                    "prev_outflow": round2(v.prev_outflow),
                    "prev_net": round2(v.prev_net),
                }
                for k, v in facts.windows.windows.items()
            }
        }


    return out
