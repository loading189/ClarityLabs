from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Tuple

from backend.app.norma.ledger import LedgerRow, check_ledger_integrity
from backend.app.norma.normalize import NormalizedTransaction

from .schema import Signal, Severity


Window = Tuple[date, date]


def _as_date(value: datetime | date) -> date:
    return value if isinstance(value, date) and not isinstance(value, datetime) else value.date()


def _window_bounds(end_date: date, days: int) -> Window:
    start = end_date - timedelta(days=days - 1)
    return start, end_date


def _prior_window(window: Window, days: int) -> Window:
    prior_end = window[0] - timedelta(days=1)
    prior_start = prior_end - timedelta(days=days - 1)
    return prior_start, prior_end


def _filter_txns(txns: Iterable[NormalizedTransaction], window: Window) -> List[NormalizedTransaction]:
    start, end = window
    return [t for t in txns if start <= _as_date(t.occurred_at) <= end]


def _balance_as_of(ledger: List[LedgerRow], cutoff: date) -> Optional[float]:
    balance = None
    for row in ledger:
        if _as_date(row.occurred_at) <= cutoff:
            balance = float(row.balance)
        else:
            break
    return balance


def _explanation_seed(
    *,
    summary: str,
    formula: str,
    inputs: List[str],
    notes: Optional[str] = None,
    details: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "summary": summary,
        "formula": formula,
        "inputs": inputs,
    }
    if notes:
        payload["notes"] = notes
    if details:
        payload["details"] = details
    return payload


def _missing_signal(
    *,
    signal_id: str,
    signal_type: str,
    window_label: str,
    missing: List[str],
    reason: str,
) -> Signal:
    return Signal(
        id=signal_id,
        type=signal_type,
        severity="yellow",
        window=window_label,
        baseline_value=None,
        current_value=None,
        delta=None,
        explanation_seed=_explanation_seed(
            summary="Insufficient data to compute signal.",
            formula="N/A",
            inputs=missing,
            notes=reason,
        ),
        confidence=0.0,
    )


def cash_runway_trend_signal(
    txns: Iterable[NormalizedTransaction],
    ledger: Iterable[LedgerRow],
    *,
    window_days: int = 30,
) -> Signal:
    """
    Cash runway trend.

    Formula:
      runway_days = cash_balance / avg_daily_outflow
      delta = runway_days(current_window) - runway_days(prior_window)

    Required inputs:
      - Ledger rows with running balances.
      - Outflow transactions across two consecutive windows.
    """
    txns_list = list(txns)
    ledger_list = list(ledger)

    if not txns_list or not ledger_list:
        return _missing_signal(
            signal_id="cash_runway_trend",
            signal_type="cash_runway_trend",
            window_label=f"{window_days}d_vs_prior_{window_days}d",
            missing=["transactions", "ledger"],
            reason="Need both transactions and ledger rows to compute runway trend.",
        )

    check_ledger_integrity(ledger_list)

    end_date = max(_as_date(row.occurred_at) for row in ledger_list)
    current_window = _window_bounds(end_date, window_days)
    prior_window = _prior_window(current_window, window_days)

    current_cash = _balance_as_of(ledger_list, current_window[1])
    prior_cash = _balance_as_of(ledger_list, prior_window[1])

    current_txns = _filter_txns(txns_list, current_window)
    prior_txns = _filter_txns(txns_list, prior_window)

    current_outflow = sum(float(t.amount) for t in current_txns if t.direction == "outflow")
    prior_outflow = sum(float(t.amount) for t in prior_txns if t.direction == "outflow")

    if current_cash is None or prior_cash is None or current_outflow <= 0 or prior_outflow <= 0:
        return _missing_signal(
            signal_id="cash_runway_trend",
            signal_type="cash_runway_trend",
            window_label=f"{window_days}d_vs_prior_{window_days}d",
            missing=["cash_balance", "outflow"],
            reason="Missing cash balance snapshots or outflow volume for runway calculation.",
        )

    current_runway = current_cash / (current_outflow / window_days)
    prior_runway = prior_cash / (prior_outflow / window_days)
    delta = current_runway - prior_runway

    pct_change = delta / prior_runway if prior_runway else 0.0
    if pct_change <= -0.25:
        severity: Severity = "red"
    elif pct_change <= -0.10:
        severity = "yellow"
    else:
        severity = "green"

    return Signal(
        id="cash_runway_trend",
        type="cash_runway_trend",
        severity=severity,
        window=f"{window_days}d_vs_prior_{window_days}d",
        baseline_value=round(prior_runway, 2),
        current_value=round(current_runway, 2),
        delta=round(delta, 2),
        explanation_seed=_explanation_seed(
            summary="Cash runway trend based on average daily outflow.",
            formula="runway_days = cash_balance / avg_daily_outflow",
            inputs=["ledger.balance", "txns.amount", "txns.direction"],
            details={
                "current_cash": round(current_cash, 2),
                "prior_cash": round(prior_cash, 2),
                "current_outflow": round(current_outflow, 2),
                "prior_outflow": round(prior_outflow, 2),
            },
        ),
        confidence=0.68,
    )


def expense_creep_signal(
    txns: Iterable[NormalizedTransaction],
    *,
    window_days: int = 30,
) -> Signal:
    """
    Expense creep signal.

    Formula:
      For each category:
        delta = outflow_current - outflow_prior
      Report the category with the largest positive delta.

    Required inputs:
      - Outflow transactions with categories across two consecutive windows.
    """
    txns_list = list(txns)
    if not txns_list:
        return _missing_signal(
            signal_id="expense_creep",
            signal_type="expense_creep",
            window_label=f"{window_days}d_vs_prior_{window_days}d",
            missing=["transactions"],
            reason="Need transactions to compute expense creep.",
        )

    end_date = max(_as_date(t.occurred_at) for t in txns_list)
    current_window = _window_bounds(end_date, window_days)
    prior_window = _prior_window(current_window, window_days)

    def _totals(window: Window) -> Dict[str, float]:
        totals: Dict[str, float] = defaultdict(float)
        for t in _filter_txns(txns_list, window):
            if t.direction != "outflow":
                continue
            totals[(t.category or "uncategorized").strip().lower()] += float(t.amount or 0.0)
        return totals

    current_totals = _totals(current_window)
    prior_totals = _totals(prior_window)

    if not current_totals and not prior_totals:
        return _missing_signal(
            signal_id="expense_creep",
            signal_type="expense_creep",
            window_label=f"{window_days}d_vs_prior_{window_days}d",
            missing=["outflow"],
            reason="No outflow transactions in either window.",
        )

    best_category = None
    best_delta = 0.0
    best_current = 0.0
    best_prior = 0.0

    categories = set(current_totals) | set(prior_totals)
    for cat in categories:
        cur = current_totals.get(cat, 0.0)
        prior = prior_totals.get(cat, 0.0)
        delta = cur - prior
        if delta > best_delta:
            best_delta = delta
            best_category = cat
            best_current = cur
            best_prior = prior

    if not best_category:
        return Signal(
            id="expense_creep",
            type="expense_creep",
            severity="green",
            window=f"{window_days}d_vs_prior_{window_days}d",
            baseline_value=round(sum(prior_totals.values()), 2),
            current_value=round(sum(current_totals.values()), 2),
            delta=0.0,
            explanation_seed=_explanation_seed(
                summary="No expense creep detected across categories.",
                formula="delta = outflow_current - outflow_prior",
                inputs=["txns.amount", "txns.direction", "txns.category"],
            ),
            confidence=0.65,
        )

    pct_change = (best_delta / best_prior) if best_prior else 0.0
    if pct_change >= 0.4 and best_delta >= 500:
        severity = "red"
    elif pct_change >= 0.2 and best_delta >= 250:
        severity = "yellow"
    else:
        severity = "green"

    return Signal(
        id="expense_creep",
        type="expense_creep",
        severity=severity,
        window=f"{window_days}d_vs_prior_{window_days}d",
        baseline_value=round(best_prior, 2),
        current_value=round(best_current, 2),
        delta=round(best_delta, 2),
        explanation_seed=_explanation_seed(
            summary="Expense creep detected in the largest-increase category.",
            formula="delta = outflow_current - outflow_prior",
            inputs=["txns.amount", "txns.direction", "txns.category"],
            details={
                "category": best_category,
                "current_outflow": round(best_current, 2),
                "prior_outflow": round(best_prior, 2),
            },
        ),
        confidence=0.62,
    )


def revenue_volatility_signal(
    txns: Iterable[NormalizedTransaction],
    *,
    window_days: int = 60,
) -> Signal:
    """
    Revenue volatility signal.

    Formula:
      coefficient_of_variation = stddev(weekly_inflows) / mean(weekly_inflows)
      delta = current_cv - prior_cv

    Required inputs:
      - Inflow transactions across two consecutive windows.
    """
    txns_list = list(txns)
    if not txns_list:
        return _missing_signal(
            signal_id="revenue_volatility",
            signal_type="revenue_volatility",
            window_label=f"{window_days}d_vs_prior_{window_days}d",
            missing=["transactions"],
            reason="Need inflow transactions to compute revenue volatility.",
        )

    end_date = max(_as_date(t.occurred_at) for t in txns_list)
    current_window = _window_bounds(end_date, window_days)
    prior_window = _prior_window(current_window, window_days)

    def _weekly_totals(window: Window) -> List[float]:
        buckets: Dict[date, float] = defaultdict(float)
        for t in _filter_txns(txns_list, window):
            if t.direction != "inflow":
                continue
            week_start = _as_date(t.occurred_at) - timedelta(days=_as_date(t.occurred_at).weekday())
            buckets[week_start] += float(t.amount or 0.0)
        return list(buckets.values())

    current_totals = _weekly_totals(current_window)
    prior_totals = _weekly_totals(prior_window)

    def _cv(values: List[float]) -> Optional[float]:
        if len(values) < 2:
            return None
        avg = mean(values)
        if avg <= 0:
            return None
        return pstdev(values) / avg

    current_cv = _cv(current_totals)
    prior_cv = _cv(prior_totals)

    if current_cv is None or prior_cv is None:
        return _missing_signal(
            signal_id="revenue_volatility",
            signal_type="revenue_volatility",
            window_label=f"{window_days}d_vs_prior_{window_days}d",
            missing=["weekly_inflows"],
            reason="Need at least two weeks of inflow data in each window.",
        )

    delta = current_cv - prior_cv
    if current_cv >= 0.6 and delta >= 0.1:
        severity: Severity = "red"
    elif current_cv >= 0.4 and delta >= 0.05:
        severity = "yellow"
    else:
        severity = "green"

    return Signal(
        id="revenue_volatility",
        type="revenue_volatility",
        severity=severity,
        window=f"{window_days}d_vs_prior_{window_days}d",
        baseline_value=round(prior_cv, 3),
        current_value=round(current_cv, 3),
        delta=round(delta, 3),
        explanation_seed=_explanation_seed(
            summary="Revenue volatility based on weekly inflow variation.",
            formula="cv = stddev(weekly_inflows) / mean(weekly_inflows)",
            inputs=["txns.amount", "txns.direction", "txns.occurred_at"],
            details={
                "current_week_count": float(len(current_totals)),
                "prior_week_count": float(len(prior_totals)),
            },
        ),
        confidence=0.6,
    )


def generate_core_signals(
    txns: Iterable[NormalizedTransaction],
    ledger: Iterable[LedgerRow],
) -> List[Signal]:
    return [
        cash_runway_trend_signal(txns, ledger),
        expense_creep_signal(txns),
        revenue_volatility_signal(txns),
    ]


def signals_as_dicts(signals: Iterable[Signal]) -> List[Dict[str, object]]:
    return [asdict(signal) for signal in signals]
