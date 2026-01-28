# backend/app/sim/engine.py
from __future__ import annotations

import random
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.sim.scenarios import ScenarioSpec, scenario_restaurant, ScenarioContext, TruthEvent

from backend.app.sim.generators.plaid import make_plaid_transaction_event
from backend.app.sim.generators.stripe import make_stripe_payout_event, make_stripe_fee_event
from backend.app.sim.generators.payroll import make_payroll_run_event


def _rng(seed: int) -> random.Random:
    r = random.Random()
    r.seed(seed)
    return r


def _is_weekend(dt: datetime) -> bool:
    # 5=Sat, 6=Sun
    return dt.weekday() >= 5


def _open_close(ctx: ScenarioContext, dt: datetime) -> tuple[int, int]:
    if _is_weekend(dt):
        return ctx.weekend_open_hour, ctx.weekend_close_hour
    return ctx.open_hour, ctx.close_hour


def _in_business_hours(ctx: ScenarioContext, dt: datetime) -> bool:
    oh, ch = _open_close(ctx, dt)
    return oh <= dt.hour < ch


def _poisson(lmbda: float, r: random.Random) -> int:
    # tiny poisson-ish sampler without numpy; good enough for v0
    # uses exponential inter-arrival approximation
    if lmbda <= 0:
        return 0
    L = pow(2.718281828, -lmbda)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= r.random()
    return max(0, k - 1)


def _normal_pos(mean: float, stdev: float, r: random.Random) -> float:
    v = r.gauss(mean, stdev)
    return max(3.0, v)


def _apply_truth_modifiers(truth: List[TruthEvent], dt: datetime) -> dict:
    """
    Returns modifiers that change generation behavior, without exposing truth.
    """
    mods = {"revenue_mult": 1.0, "expense_mult": 1.0, "deposit_delay_days": 0}

    for t in truth:
        if not (t.start_at <= dt < t.end_at):
            continue

        if t.type == "revenue_drop":
            # medium/high changes size/frequency
            mods["revenue_mult"] *= 0.75 if t.severity == "med" else 0.55

        if t.type == "expense_spike":
            mods["expense_mult"] *= 1.8 if t.severity == "med" else 2.8

        if t.type == "deposit_delay":
            mods["deposit_delay_days"] = max(mods["deposit_delay_days"], 2 if t.severity == "med" else 5)

    return mods


def build_scenario(
    scenario_key: str,
    ctx: ScenarioContext,
    start_at: datetime,
    end_at: datetime,
) -> ScenarioSpec:
    if scenario_key == "restaurant":
        return scenario_restaurant(ctx, start_at, end_at)
    raise ValueError(f"unknown scenario '{scenario_key}'")


def generate_raw_events_for_scenario(
    scenario: ScenarioSpec,
    start_at: datetime,
    end_at: datetime,
) -> Tuple[List[Dict[str, Any]], List[TruthEvent]]:
    """
    Returns (raw_events, truth_events).

    raw_events are DB insert-ready dicts with:
      source, source_event_id, occurred_at (datetime), payload
    """
    ctx = scenario.ctx
    truth = scenario.truth_events

    r = _rng(ctx.seed)
    events: List[Dict[str, Any]] = []

    # Simple bookkeeping for “batch deposits”
    # We'll simulate POS orders as “stripe payouts” + small fees,
    # and expenses as plaid-like outflows
    pending_payout_cents = 0

    # Payroll cadence (biweekly-ish)
    next_payroll = start_at + timedelta(days=14)

    dt = start_at.replace(second=0, microsecond=0)

    while dt < end_at:
        mods = _apply_truth_modifiers(truth, dt)

        # Revenue orders during open hours
        if _in_business_hours(ctx, dt):
            # expected orders per minute = orders/hour / 60
            lmbda = (ctx.avg_orders_per_hour * mods["revenue_mult"]) / 60.0
            n_orders = _poisson(lmbda, r)

            for _ in range(n_orders):
                amt = _normal_pos(ctx.avg_order_amount, ctx.avg_order_stdev, r)
                pending_payout_cents += int(round(amt * 100))

                # record a “fee” occasionally (processing)
                if r.random() < 0.08:
                    fee = make_stripe_fee_event(
                        business_id=ctx.business_id,
                        occurred_at=dt,
                    )
                    events.append(fee)

        # Random daily expenses (sprinkled across day)
        # Use avg_expenses_per_day / (24*60) per minute
        exp_lmbda = (ctx.avg_expenses_per_day * mods["expense_mult"]) / (24.0 * 60.0)
        n_exp = _poisson(exp_lmbda, r)
        for _ in range(n_exp):
            e = make_plaid_transaction_event(
                business_id=ctx.business_id,
                occurred_at=dt,
                cfg=None,
            )
            events.append(e)

        # Payroll event
        if dt >= next_payroll and dt.hour == 9 and dt.minute == 0:
            p = make_payroll_run_event(business_id=ctx.business_id, occurred_at=dt)
            events.append(p)
            next_payroll = next_payroll + timedelta(days=14)

        # Deposit batches at set hours if any pending
        if dt.minute == 0 and dt.hour in list(ctx.payout_batch_times) and pending_payout_cents > 0:
            deposit_dt = dt + timedelta(days=mods.get("deposit_delay_days", 0))
            payout = make_stripe_payout_event(
                business_id=ctx.business_id,
                occurred_at=deposit_dt,
                cfg=None,
            )

            # Override payout amount deterministically from pending
            payout_amount = round(pending_payout_cents / 100.0, 2)
            payout["payload"]["data"]["object"]["amount"] = payout_amount

            events.append(payout)
            pending_payout_cents = 0

        dt = dt + timedelta(minutes=1)

    # Sort events deterministically
    events.sort(key=lambda e: (e["occurred_at"], e["source_event_id"]))
    return events, truth
