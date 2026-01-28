# backend/app/sim/scenarios.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

TruthType = Literal[
    "revenue_drop",
    "expense_spike",
    "deposit_delay",
    "refund_wave",
]

@dataclass(frozen=True)
class TruthEvent:
    id: str
    type: TruthType
    start_at: datetime
    end_at: datetime
    severity: str  # "low"|"med"|"high"
    note: str
    expected_signals: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["start_at"] = self.start_at.isoformat()
        d["end_at"] = self.end_at.isoformat()
        return d


@dataclass(frozen=True)
class ScenarioContext:
    business_id: str
    tz: str  # keep as string for now
    seed: int
    # realistic knobs
    open_hour: int = 11
    close_hour: int = 22
    weekend_open_hour: int = 11
    weekend_close_hour: int = 23

    # stream rates (average events)
    avg_orders_per_hour: float = 18.0
    avg_expenses_per_day: float = 6.0

    # ticket sizes
    avg_order_amount: float = 38.0
    avg_order_stdev: float = 14.0

    # payout timing behavior
    payout_batch_times: List[int] = (2, 14)  # hours of day when deposits happen


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    label: str

    # scenario can declare the truth it injects
    truth_events: List[TruthEvent]

    # scenario parameters that shape event generation
    ctx: ScenarioContext


def scenario_restaurant(ctx: ScenarioContext, start_at: datetime, end_at: datetime) -> ScenarioSpec:
    """
    Restaurant scenario: lots of POS income, periodic vendor purchases, payroll, utilities,
    and optional injected shocks.
    """
    # Keep v0 simple: always include a couple truth events
    # (you can make these optional via request flags later)
    import uuid
    from datetime import timedelta

    mid = start_at + (end_at - start_at) / 2
    te = [
        TruthEvent(
            id=f"truth_{uuid.uuid4().hex[:10]}",
            type="revenue_drop",
            start_at=mid,
            end_at=min(end_at, mid + timedelta(days=10)),
            severity="med",
            note="Dinner traffic falls (local competition / seasonality).",
            expected_signals=["revenue_drop_yellow", "revenue_drop_red"],
        ),
        TruthEvent(
            id=f"truth_{uuid.uuid4().hex[:10]}",
            type="expense_spike",
            start_at=min(end_at, mid + timedelta(days=12)),
            end_at=min(end_at, mid + timedelta(days=13)),
            severity="high",
            note="Equipment repair hits unexpectedly.",
            expected_signals=["expense_spike_yellow", "expense_spike_red", "top_spend_drivers"],
        ),
    ]

    return ScenarioSpec(
        key="restaurant",
        label="Restaurant (POS + vendors + payroll)",
        truth_events=te,
        ctx=ctx,
    )
