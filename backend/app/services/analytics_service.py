from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.app.analytics.core import (
    AnalyticsLine,
    compute_cash_summary,
    compute_category_breakdown,
    compute_timeseries,
    compute_vendor_concentration,
    detect_anomalies,
    explain_change,
    line_from_txn,
    COMPUTATION_VERSION,
)


DateLike = date | datetime | str


def build_analytics_lines(txns: Iterable[Any]) -> List[AnalyticsLine]:
    return [line_from_txn(txn) for txn in txns]


def build_dashboard_analytics(
    txns: Iterable[Any],
    *,
    start_at: Optional[DateLike],
    end_at: Optional[DateLike],
    lookback_months: int,
) -> Dict[str, Any]:
    lines = build_analytics_lines(txns)
    if not lines:
        return _empty_payload()

    start_date = _as_date(start_at, default=min(line.occurred_at.date() for line in lines))
    end_date = _as_date(end_at, default=max(line.occurred_at.date() for line in lines))

    last_30_start = end_date - timedelta(days=29)
    prev_30_end = last_30_start - timedelta(days=1)
    prev_30_start = prev_30_end - timedelta(days=29)

    last_30 = compute_cash_summary(lines, last_30_start, end_date)
    prev_30 = compute_cash_summary(lines, prev_30_start, prev_30_end)
    full_range = compute_cash_summary(lines, start_date, end_date)

    monthly_series = compute_timeseries(
        _filter_lines(lines, start_date, end_date), bucket="month"
    )
    if lookback_months > 0:
        monthly_series = monthly_series[-lookback_months:]

    category_breakdown = compute_category_breakdown(lines)
    vendor_concentration = compute_vendor_concentration(lines)
    anomalies = detect_anomalies(lines)

    change_explanations = explain_change(
        _filter_lines(lines, prev_30_start, prev_30_end),
        _filter_lines(lines, last_30_start, end_date),
    )

    return {
        "computation_version": COMPUTATION_VERSION,
        "kpis": {
            "current_cash": full_range["cash_end"],
            "last_30d_inflow": last_30["inflow"],
            "last_30d_outflow": last_30["outflow"],
            "last_30d_net": last_30["net"],
            "prev_30d_inflow": prev_30["inflow"],
            "prev_30d_outflow": prev_30["outflow"],
            "prev_30d_net": prev_30["net"],
        },
        "series": monthly_series,
        "category_breakdown": category_breakdown,
        "vendor_concentration": vendor_concentration,
        "anomalies": anomalies,
        "change_explanations": change_explanations,
    }


def build_trends_analytics(
    txns: Iterable[Any],
    *,
    start_at: Optional[DateLike],
    end_at: Optional[DateLike],
    lookback_months: int,
) -> Dict[str, Any]:
    lines = build_analytics_lines(txns)
    if not lines:
        return _empty_payload()

    start_date = _as_date(start_at, default=min(line.occurred_at.date() for line in lines))
    end_date = _as_date(end_at, default=max(line.occurred_at.date() for line in lines))

    monthly_series = compute_timeseries(
        _filter_lines(lines, start_date, end_date), bucket="month"
    )
    if lookback_months > 0:
        monthly_series = monthly_series[-lookback_months:]

    return {
        "computation_version": COMPUTATION_VERSION,
        "series": monthly_series,
    }


def _filter_lines(lines: List[AnalyticsLine], start: date, end: date) -> List[AnalyticsLine]:
    return [line for line in lines if start <= line.occurred_at.date() <= end]


def _as_date(value: Optional[DateLike], *, default: date) -> date:
    if value is None:
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _empty_payload() -> Dict[str, Any]:
    return {
        "computation_version": COMPUTATION_VERSION,
        "kpis": {
            "current_cash": _empty_metric(),
            "last_30d_inflow": _empty_metric(),
            "last_30d_outflow": _empty_metric(),
            "last_30d_net": _empty_metric(),
            "prev_30d_inflow": _empty_metric(),
            "prev_30d_outflow": _empty_metric(),
            "prev_30d_net": _empty_metric(),
        },
        "series": [],
        "category_breakdown": [],
        "vendor_concentration": [],
        "anomalies": [],
        "change_explanations": {"category_drivers": [], "vendor_drivers": []},
    }


def _empty_metric() -> Dict[str, Any]:
    return {
        "value": 0.0,
        "trace": {
            "supporting_event_ids": [],
            "supporting_line_count": 0,
            "computation_version": COMPUTATION_VERSION,
            "features_snapshot": {},
        },
    }
