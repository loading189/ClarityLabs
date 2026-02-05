from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from backend.app.sim_v2.seeders import finance


@dataclass(frozen=True)
class ScenarioDef:
    id: str
    title: str
    description: str
    expected_signals: List[str]
    apply: Callable[[list, dict], None]


def _noop(events: list, ctx: dict) -> None:
    return None


SCENARIOS: Dict[str, ScenarioDef] = {
    "steady_state": ScenarioDef(
        id="steady_state",
        title="Steady State",
        description="Normal baseline operations with realistic cadence.",
        expected_signals=[],
        apply=_noop,
    ),
    "cash_crunch": ScenarioDef(
        id="cash_crunch",
        title="Cash Crunch",
        description="Outflows accelerate and inflows weaken in recent weeks.",
        expected_signals=["low_cash_runway", "liquidity.runway_low"],
        apply=lambda events, ctx: finance.apply_cash_crunch(events, anchor_date=ctx["anchor_date"], intensity=ctx["intensity"]),
    ),
    "revenue_drop": ScenarioDef(
        id="revenue_drop",
        title="Revenue Drop",
        description="Recent inflows drop materially against baseline.",
        expected_signals=["revenue.decline_vs_baseline"],
        apply=lambda events, ctx: finance.apply_revenue_drop(events, anchor_date=ctx["anchor_date"], intensity=ctx["intensity"]),
    ),
    "expense_spike": ScenarioDef(
        id="expense_spike",
        title="Expense Spike",
        description="Costs spike beyond normal baseline and variance.",
        expected_signals=["expense.spike_vs_baseline", "expense_creep_by_vendor"],
        apply=lambda events, ctx: finance.apply_expense_spike(events, anchor_date=ctx["anchor_date"], intensity=ctx["intensity"]),
    ),
    "vendor_concentration": ScenarioDef(
        id="vendor_concentration",
        title="Vendor Concentration",
        description="One vendor dominates spend profile.",
        expected_signals=["concentration.expense_top_vendor"],
        apply=lambda events, ctx: finance.apply_vendor_concentration(events, anchor_date=ctx["anchor_date"], intensity=ctx["intensity"]),
    ),
    "messy_books": ScenarioDef(
        id="messy_books",
        title="Messy Books",
        description="High uncategorized transaction volume.",
        expected_signals=["hygiene.uncategorized_high"],
        apply=lambda events, ctx: finance.apply_messy_books(events, anchor_date=ctx["anchor_date"], intensity=ctx["intensity"]),
    ),
    "timing_mismatch": ScenarioDef(
        id="timing_mismatch",
        title="Timing Mismatch",
        description="Cash arrival timing mismatches near-term obligations.",
        expected_signals=["timing.inflow_outflow_mismatch", "timing.payroll_rent_cliff"],
        apply=lambda events, ctx: finance.apply_timing_mismatch(events, anchor_date=ctx["anchor_date"], intensity=ctx["intensity"]),
    ),
}

PRESETS: Dict[str, List[dict]] = {
    "healthy": [{"id": "steady_state", "intensity": 1}],
    "cash_strained": [
        {"id": "steady_state", "intensity": 1},
        {"id": "cash_crunch", "intensity": 2},
        {"id": "revenue_drop", "intensity": 1},
        {"id": "expense_spike", "intensity": 2},
        {"id": "vendor_concentration", "intensity": 1},
        {"id": "timing_mismatch", "intensity": 2},
    ],
    "revenue_decline": [
        {"id": "steady_state", "intensity": 1},
        {"id": "revenue_drop", "intensity": 2},
        {"id": "cash_crunch", "intensity": 1},
        {"id": "expense_spike", "intensity": 2},
        {"id": "vendor_concentration", "intensity": 1},
        {"id": "timing_mismatch", "intensity": 1},
        {"id": "messy_books", "intensity": 1},
    ],
    "messy_books": [
        {"id": "steady_state", "intensity": 1},
        {"id": "messy_books", "intensity": 2},
        {"id": "cash_crunch", "intensity": 1},
        {"id": "expense_spike", "intensity": 2},
        {"id": "vendor_concentration", "intensity": 1},
        {"id": "timing_mismatch", "intensity": 1},
    ],
    "stripe_timing": [{"id": "steady_state", "intensity": 1}, {"id": "timing_mismatch", "intensity": 2}],
}


def catalog_payload() -> dict:
    return {
        "presets": [
            {
                "id": pid,
                "title": pid.replace("_", " ").title(),
                "scenarios": config,
            }
            for pid, config in PRESETS.items()
        ],
        "scenarios": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "expected_signals": s.expected_signals,
            }
            for s in SCENARIOS.values()
        ],
    }
