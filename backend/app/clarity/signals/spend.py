# backend/app/signals/spend.py
from __future__ import annotations

from typing import List

from backend.app.norma.facts import CategoryTotal, Facts
from . import register
from .core import mk_signal, Severity


@register
def build_spend_signals(facts: Facts) -> List:
    return [top_spend_driver_signal(facts.totals_by_category)]

def _top_spend_event_refs(txns, limit: int = 10):
    # txns are normalized txns built from raw events in demo_health_by_business
    # but inside signals you currently only get Facts, not txns.
    # So: we need to pass txn refs into Facts OR compute in the demo endpoint.

    return []


def top_spend_driver_signal(totals_by_category: List[CategoryTotal]):
    inputs = ["totals_by_category[*].category", "totals_by_category[*].total"]
    conditions = {"top_n": 3, "warn_if_top_share_above": 0.70}

    if not totals_by_category:
        return mk_signal(
            key="spend_drivers_missing",
            title="Top Spend Drivers",
            severity="yellow",
            dimension="spend",
            priority=55,
            value=None,
            inputs=inputs,
            conditions=conditions,
            message="No category totals available to identify spend drivers.",
            why="Spend driver analysis requires totals_by_category from Norma.",
            how_to_fix="Ensure transactions include categories and totals_by_category is computed.",
        )

    spend = [r for r in totals_by_category if float(r.total) < 0]
    if not spend:
        return mk_signal(
            key="spend_drivers_none",
            title="Top Spend Drivers",
            severity="green",
            dimension="spend",
            priority=10,
            value=[],
            inputs=inputs,
            conditions=conditions,
            message="No spend categories detected.",
            why="All category totals were non-negative in this dataset.",
        )

    spend_sorted = sorted(spend, key=lambda r: abs(float(r.total)), reverse=True)
    top = spend_sorted[:3]

    total_spend = sum(abs(float(r.total)) for r in spend_sorted)
    top_share = (sum(abs(float(r.total)) for r in top) / total_spend) if total_spend else 0.0

    severity: Severity = "green"
    if top_share > 0.70:
        severity = "yellow"

    return mk_signal(
        key="top_spend_drivers",
        title="Top Spend Drivers",
        severity=severity,
        dimension="spend",
        priority=60,
        value={
            "top": [{"category": r.category, "spend": round(abs(float(r.total)), 2)} for r in top],
            "top_3_share_of_spend": round(top_share, 2),
        },
        inputs=inputs,
        conditions=conditions,
        message=(
            f"Top spend categories drive ~{top_share:.0%} of total spend: "
            + ", ".join([f"{r.category} (${abs(float(r.total)):,.0f})" for r in top])
            + "."
        ),
        evidence={"total_spend": round(total_spend, 2), "top_share": round(top_share, 4)},
        why="A small number of categories often drive most cash burn; concentration increases sensitivity to changes in these costs.",
        how_to_fix="Review payroll first, then fixed commitments like rent and debt payments.",
    )
