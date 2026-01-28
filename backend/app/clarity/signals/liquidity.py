# backend/app/signals/liquidity.py
from __future__ import annotations

from typing import List

from backend.app.norma.facts import Facts, MonthlyCashflow
from . import register
from .core import mk_signal, Severity


@register
def build_liquidity_signals(facts: Facts) -> List:
    current_cash = float(facts.current_cash)
    monthly = facts.monthly_inflow_outflow
    return [
        cash_status_signal(current_cash),
        burn_and_runway_signal(current_cash, monthly),
    ]


def cash_status_signal(current_cash: float):
    inputs = ["current_cash"]
    conditions = {"yellow_below": 1000, "red_below": 0}

    if current_cash < 0:
        return mk_signal(
            key="cash_negative",
            title="Cash Balance Negative",
            severity="red",
            dimension="liquidity",
            priority=100,
            value=current_cash,
            message=f"Cash is negative (${current_cash:,.2f}). Immediate liquidity risk.",
            inputs=inputs,
            conditions=conditions,
            evidence={"current_cash": current_cash},
            why="Cash below $0 means obligations may be missed without immediate intervention.",
            how_to_fix="Confirm bank balance and pending payments today. Pause discretionary spend and review short-term financing options.",
        )

    if current_cash < 1000:
        return mk_signal(
            key="cash_low",
            title="Cash Balance Low",
            severity="yellow",
            dimension="liquidity",
            priority=80,
            value=current_cash,
            message=f"Cash is low (${current_cash:,.2f}). Watch near-term obligations.",
            inputs=inputs,
            conditions=conditions,
            evidence={"current_cash": current_cash, "threshold": 1000},
            why="Cash is above $0 but below the minimum buffer threshold used in this model.",
            how_to_fix="Review upcoming payroll/rent due dates and delay non-essential spending until the next inflow clears.",
        )

    return mk_signal(
        key="cash_ok",
        title="Cash Balance Healthy",
        severity="green",
        dimension="liquidity",
        priority=10,
        value=current_cash,
        message=f"Cash balance is ${current_cash:,.2f}.",
        inputs=inputs,
        conditions=conditions,
        evidence={"current_cash": current_cash},
        why="Cash is above the minimum buffer threshold used in this model.",
    )


def burn_and_runway_signal(current_cash: float, monthly_inflow_outflow: List[MonthlyCashflow]):
    inputs = ["current_cash", "monthly_inflow_outflow[*].outflow"]
    conditions = {"avg_outflow_window_months": 3, "red_runway_days_below": 30, "yellow_runway_days_below": 60}

    if not monthly_inflow_outflow:
        return mk_signal(
            key="burn_insufficient",
            title="Burn Rate / Runway",
            severity="yellow",
            dimension="liquidity",
            priority=65,
            value=None,
            inputs=inputs,
            conditions=conditions,
            message="No monthly history to estimate burn rate.",
            why="Runway estimation requires monthly outflow history.",
            how_to_fix="Import at least 1–3 months of transactions to estimate burn.",
        )

    last_n = monthly_inflow_outflow[-3:]
    outflows = [float(m.outflow) for m in last_n]
    avg_outflow = sum(outflows) / len(outflows) if outflows else 0.0

    if avg_outflow <= 0:
        return mk_signal(
            key="burn_zero",
            title="Burn Rate / Runway",
            severity="green",
            dimension="liquidity",
            priority=5,
            value={"avg_monthly_outflow": avg_outflow},
            inputs=inputs,
            conditions=conditions,
            message="Outflows are zero or missing; runway not applicable.",
            evidence={"avg_monthly_outflow": avg_outflow},
            why="No meaningful outflow data was detected for the selected months.",
        )

    if current_cash <= 0:
        return mk_signal(
            key="runway_exhausted",
            title="Runway Exhausted",
            severity="red",
            dimension="liquidity",
            priority=98,
            value={"current_cash": current_cash, "avg_monthly_outflow": avg_outflow, "runway_months": 0},
            inputs=inputs,
            conditions=conditions,
            message="Cash is at or below zero; runway is effectively exhausted.",
            evidence={"current_cash": current_cash, "avg_monthly_outflow": avg_outflow},
            why="When cash is at or below $0, the estimated runway is 0 days in this model.",
            how_to_fix="Prioritize payroll/rent coverage. Delay non-critical payments and renegotiate terms where possible.",
        )

    runway_months = current_cash / avg_outflow
    runway_days = runway_months * 30.0

    severity: Severity = "green"
    if runway_days < 30:
        severity = "red"
    elif runway_days < 60:
        severity = "yellow"

    return mk_signal(
        key="runway_estimate",
        title="Estimated Cash Runway",
        severity=severity,
        dimension="liquidity",
        priority=75,
        value={"runway_days": round(runway_days, 1), "avg_monthly_outflow": round(avg_outflow, 2)},
        inputs=inputs,
        conditions=conditions,
        message=f"Estimated runway is {runway_days:.0f} days based on avg monthly outflow of ${avg_outflow:,.2f}.",
        evidence={"current_cash": current_cash, "avg_monthly_outflow": avg_outflow, "runway_days": runway_days},
        why="Runway is estimated as current_cash divided by average monthly outflow (converted to days).",
        how_to_fix="If runway is under 60 days, review payroll timing, discretionary spend, and receivables collection.",
    )
