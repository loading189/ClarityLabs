from __future__ import annotations

from typing import List, Optional

from backend.app.norma.facts import Facts, WindowPair

from .core import mk_signal, Severity
from . import register


def _get_window(facts: Facts, window_days: int = 30) -> Optional[WindowPair]:
    rw = facts.windows
    if rw is None:
        return None
    return rw.windows.get(window_days)


def _pct_change(current: float, previous: float) -> float | None:
    """
    Deterministic percent change.

    Returns:
      (current - previous) / previous

    If previous is 0:
      - if current is 0 => 0.0
      - else => None (undefined; we handle explicitly in signals)
    """
    if previous == 0:
        return 0.0 if current == 0 else None
    return (current - previous) / previous


@register
def build_window_stability_signals(facts: Facts) -> List:
    """
    Window-based stability signals (30d vs previous 30d).

    Uses the generalized rolling windows:
      facts.windows.windows[30] -> WindowPair
    """
    w = _get_window(facts, 30)
    if w is None:
        return [
            mk_signal(
                key="window_insufficient",
                title="Recent Activity Window",
                severity="yellow",
                dimension="stability",
                priority=50,
                value=None,
                message="Not enough recent transaction history to compute 30-day comparisons.",
                inputs=["windows"],
                conditions={"window_days": 30},
                evidence={"txn_count": facts.meta.txn_count, "anchor_date": facts.meta.as_of},
                why="30-day stability signals require transactions within the last ~60 days.",
                how_to_fix="Import additional transactions to enable rolling window comparisons.",
            )
        ]

    return [
        revenue_drop_30d_signal(facts, w),
        expense_spike_30d_signal(facts, w),
        net_drop_30d_signal(facts, w),
    ]


def revenue_drop_30d_signal(facts: Facts, w: WindowPair):
    """
    Revenue drop: last 30d inflow vs previous 30d inflow.

    Rule (MVP thresholds, tune later):
    - red    if inflow down >= 40% AND previous inflow >= $2,000
    - yellow if inflow down >= 20% AND previous inflow >= $2,000
    - green otherwise

    Notes:
    - If previous inflow is 0 and current > 0 => treat as "new inflow" (green).
    - If previous inflow is 0 and current is 0 => insufficient (yellow).
    """
    last_in = float(w.last_inflow)
    prev_in = float(w.prev_inflow)

    pct = _pct_change(last_in, prev_in)

    inputs = [
        "windows[30].last_inflow",
        "windows[30].prev_inflow",
        "windows[30].anchor_date",
    ]
    conditions = {
        "window_days": 30,
        "min_prev_inflow_for_signal": 2000,
        "yellow_drop_pct": 0.20,
        "red_drop_pct": 0.40,
    }
    evidence = {
        "anchor_date": w.anchor_date,
        "last_30d_inflow": last_in,
        "prev_30d_inflow": prev_in,
        "pct_change": None if pct is None else round(pct, 4),
    }

    # Handle undefined percent change due to prev_in=0
    if pct is None:
        if last_in == 0:
            return mk_signal(
                key="revenue_window_insufficient",
                title="Revenue Trend",
                severity="yellow",
                dimension="revenue",
                priority=60,
                value=None,
                message="No inflows detected in the last 60 days; revenue trend is unclear.",
                inputs=inputs,
                conditions=conditions,
                evidence=evidence,
                why="Percent-change revenue signals need a non-zero prior inflow baseline.",
                how_to_fix="Confirm sales deposits are being imported. If revenue is seasonal, consider viewing a longer history window.",
            )

        # prev_in=0, last_in>0 => new inflows
        return mk_signal(
            key="revenue_new_inflow",
            title="Revenue Trend",
            severity="green",
            dimension="revenue",
            priority=20,
            value={"last_30d_inflow": round(last_in, 2), "prev_30d_inflow": round(prev_in, 2)},
            message=f"Inflows appeared in the last 30 days (${last_in:,.0f}) after no prior inflows.",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="A 30-day percent change is undefined when the previous window is $0, but the presence of new inflows is generally positive.",
        )

    # If prior inflow is too small, treat as informational (avoid noisy % swings)
    if prev_in < conditions["min_prev_inflow_for_signal"]:
        return mk_signal(
            key="revenue_baseline_small",
            title="Revenue Trend",
            severity="green",
            dimension="revenue",
            priority=10,
            value={"last_30d_inflow": round(last_in, 2), "prev_30d_inflow": round(prev_in, 2)},
            message="Revenue comparison is stable (baseline is small).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="The prior window inflow is below the baseline threshold used to avoid noisy percent swings.",
        )

    drop = -pct  # drop is positive if inflows decreased
    if drop >= conditions["red_drop_pct"]:
        return mk_signal(
            key="revenue_drop_red",
            title="Revenue Drop Detected",
            severity="red",
            dimension="revenue",
            priority=90,
            value={
                "drop_pct": round(drop, 2),
                "last_30d_inflow": round(last_in, 2),
                "prev_30d_inflow": round(prev_in, 2),
            },
            message=f"Inflows fell ~{drop:.0%} vs the prior 30 days (${prev_in:,.0f} → ${last_in:,.0f}).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="A large revenue decline over a rolling 30-day window can indicate demand loss, delayed collections, or operational disruption.",
            how_to_fix="Verify receivables timing and pipeline. Compare customer payments and invoicing volume vs the prior month.",
        )

    if drop >= conditions["yellow_drop_pct"]:
        return mk_signal(
            key="revenue_drop_yellow",
            title="Revenue Softening",
            severity="yellow",
            dimension="revenue",
            priority=70,
            value={
                "drop_pct": round(drop, 2),
                "last_30d_inflow": round(last_in, 2),
                "prev_30d_inflow": round(prev_in, 2),
            },
            message=f"Inflows are down ~{drop:.0%} vs the prior 30 days (${prev_in:,.0f} → ${last_in:,.0f}).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="A moderate revenue decline is an early warning signal that can affect cash coverage.",
            how_to_fix="Review top customers and unpaid invoices. Confirm upcoming deposits expected in the next 2–3 weeks.",
        )

    return mk_signal(
        key="revenue_ok",
        title="Revenue Trend",
        severity="green",
        dimension="revenue",
        priority=15,
        value={"last_30d_inflow": round(last_in, 2), "prev_30d_inflow": round(prev_in, 2)},
        message="Inflows are stable vs the prior 30 days.",
        inputs=inputs,
        conditions=conditions,
        evidence=evidence,
        why="No meaningful 30-day inflow decline was detected under the configured thresholds.",
    )


def expense_spike_30d_signal(facts: Facts, w: WindowPair):
    """
    Expense spike: last 30d outflow vs previous 30d outflow.

    Rule (MVP thresholds):
    - red    if outflow up >= 40% AND previous outflow >= $2,000
    - yellow if outflow up >= 20% AND previous outflow >= $2,000
    - green otherwise

    Notes:
    - If previous outflow is 0 and current > 0 => new spending (yellow if meaningful).
    """
    last_out = float(w.last_outflow)
    prev_out = float(w.prev_outflow)

    pct = _pct_change(last_out, prev_out)

    inputs = [
        "windows[30].last_outflow",
        "windows[30].prev_outflow",
        "windows[30].anchor_date",
    ]
    conditions = {
        "window_days": 30,
        "min_prev_outflow_for_signal": 2000,
        "yellow_spike_pct": 0.20,
        "red_spike_pct": 0.40,
        "new_spend_yellow_if_above": 1500,
    }
    evidence = {
        "anchor_date": w.anchor_date,
        "last_30d_outflow": last_out,
        "prev_30d_outflow": prev_out,
        "pct_change": None if pct is None else round(pct, 4),
    }

    if pct is None:
        # prev_out=0, last_out>0
        sev: Severity = "green"
        if last_out >= conditions["new_spend_yellow_if_above"]:
            sev = "yellow"
        return mk_signal(
            key="expense_new_spend",
            title="Expense Trend",
            severity=sev,
            dimension="spend",
            priority=65 if sev == "yellow" else 20,
            value={"last_30d_outflow": round(last_out, 2), "prev_30d_outflow": round(prev_out, 2)},
            message=f"Outflows increased from $0 to ${last_out:,.0f} over the last 30 days.",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="Percent change is undefined when the prior window is $0; new spending may be normal (startup costs) or a drift signal.",
            how_to_fix="Verify whether the new spend is expected (one-time setup, seasonal ramp). If not expected, review vendor list and approvals.",
        )

    if prev_out < conditions["min_prev_outflow_for_signal"]:
        return mk_signal(
            key="expense_baseline_small",
            title="Expense Trend",
            severity="green",
            dimension="spend",
            priority=10,
            value={"last_30d_outflow": round(last_out, 2), "prev_30d_outflow": round(prev_out, 2)},
            message="Expense comparison is stable (baseline is small).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="The prior window outflow is below the baseline threshold used to avoid noisy percent swings.",
        )

    spike = pct  # positive if outflows increased
    if spike >= conditions["red_spike_pct"]:
        return mk_signal(
            key="expense_spike_red",
            title="Expense Spike Detected",
            severity="red",
            dimension="spend",
            priority=88,
            value={
                "spike_pct": round(spike, 2),
                "last_30d_outflow": round(last_out, 2),
                "prev_30d_outflow": round(prev_out, 2),
            },
            message=f"Outflows rose ~{spike:.0%} vs the prior 30 days (${prev_out:,.0f} → ${last_out:,.0f}).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="A sharp spending increase can quickly compress runway and may indicate vendor drift or an operational issue.",
            how_to_fix="Review largest payments in the last 30 days and compare vendors vs the prior window. Confirm any one-time expenses.",
        )

    if spike >= conditions["yellow_spike_pct"]:
        return mk_signal(
            key="expense_spike_yellow",
            title="Expense Increase",
            severity="yellow",
            dimension="spend",
            priority=68,
            value={
                "spike_pct": round(spike, 2),
                "last_30d_outflow": round(last_out, 2),
                "prev_30d_outflow": round(prev_out, 2),
            },
            message=f"Outflows are up ~{spike:.0%} vs the prior 30 days (${prev_out:,.0f} → ${last_out:,.0f}).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="A moderate spending increase is an early warning that can affect cash buffer and runway.",
            how_to_fix="Confirm whether this was planned (inventory buys, equipment, seasonal labor). If not planned, check top vendors and subscriptions.",
        )

    return mk_signal(
        key="expense_ok",
        title="Expense Trend",
        severity="green",
        dimension="spend",
        priority=15,
        value={"last_30d_outflow": round(last_out, 2), "prev_30d_outflow": round(prev_out, 2)},
        message="Outflows are stable vs the prior 30 days.",
        inputs=inputs,
        conditions=conditions,
        evidence=evidence,
        why="No meaningful 30-day outflow increase was detected under the configured thresholds.",
    )


def net_drop_30d_signal(facts: Facts, w: WindowPair):
    """
    Net drop: last 30d net vs previous 30d net.

    Rule (MVP):
    - red    if last_net < 0 and worsened by >= $2,000 vs prior
    - yellow if last_net < 0
    - green otherwise
    """
    last_net = float(w.last_net)
    prev_net = float(w.prev_net)
    delta = last_net - prev_net  # negative means net worsened

    inputs = [
        "windows[30].last_net",
        "windows[30].prev_net",
        "windows[30].anchor_date",
    ]
    conditions = {
        "window_days": 30,
        "red_if_last_net_negative_and_delta_below": -2000,
        "yellow_if_last_net_below": 0,
    }
    evidence = {
        "anchor_date": w.anchor_date,
        "last_30d_net": last_net,
        "prev_30d_net": prev_net,
        "delta": delta,
    }

    if last_net < 0 and delta <= conditions["red_if_last_net_negative_and_delta_below"]:
        return mk_signal(
            key="net_drop_red",
            title="Net Cash Decline",
            severity="red",
            dimension="stability",
            priority=85,
            value={
                "last_30d_net": round(last_net, 2),
                "prev_30d_net": round(prev_net, 2),
                "delta": round(delta, 2),
            },
            message=f"Net cash worsened materially: ${prev_net:,.0f} → ${last_net:,.0f} over the last 30 days.",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="A negative net combined with a sharp deterioration suggests the business is absorbing more cash each month.",
            how_to_fix="Cross-check revenue timing and largest expenses. If this is seasonal, verify cash buffer and runway coverage.",
        )

    if last_net < 0:
        return mk_signal(
            key="net_negative_yellow",
            title="Net Cash Negative",
            severity="yellow",
            dimension="stability",
            priority=65,
            value={"last_30d_net": round(last_net, 2), "prev_30d_net": round(prev_net, 2)},
            message=f"Net cash is negative over the last 30 days (${last_net:,.0f}).",
            inputs=inputs,
            conditions=conditions,
            evidence=evidence,
            why="Over the last 30 days, outflows exceeded inflows.",
            how_to_fix="Review recent expenses and confirm expected receivables timing in the next 2–4 weeks.",
        )

    return mk_signal(
        key="net_ok_30d",
        title="Net Cash (30-day)",
        severity="green",
        dimension="stability",
        priority=15,
        value={"last_30d_net": round(last_net, 2), "prev_30d_net": round(prev_net, 2)},
        message="Net cash is positive over the last 30 days.",
        inputs=inputs,
        conditions=conditions,
        evidence=evidence,
        why="Over the last 30 days, inflows exceeded outflows.",
    )
