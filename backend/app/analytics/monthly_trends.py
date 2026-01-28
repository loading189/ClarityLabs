from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Optional
import statistics
from datetime import datetime

from backend.app.norma.ledger_series import monthly_cashflow_from_ledger_rows

Status = Literal["no_data", "in_band", "below_band", "above_band"]

@dataclass(frozen=True)
class Band:
    center: float
    lower: float
    upper: float
    mad: float
    k: float

@dataclass(frozen=True)
class MetricTrend:
    metric: str  # "net" | "inflow" | "outflow" | "cash_end"
    series: List[Dict[str, Any]]  # rows include inflow/outflow/net/cash_end/value
    band: Optional[Dict[str, Any]]
    status: Status
    current: Optional[Dict[str, Any]]
    slope: float
    volatility_mad: float


def _safe_float(x: Any) -> float:
    try:
        return float(x or 0.0)
    except Exception:
        return 0.0


def _median(xs: List[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def _mad(xs: List[float], med: float) -> float:
    if not xs:
        return 0.0
    return statistics.median([abs(x - med) for x in xs]) if len(xs) > 1 else 0.0


def _slope(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    x = list(range(len(values)))
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(values)
    num = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(len(values)))
    den = sum((x[i] - x_mean) ** 2 for i in range(len(values)))
    return num / den if den != 0 else 0.0


def _compute_band(values: List[float], k: float) -> Band:
    med = _median(values)
    mad = _mad(values, med)
    band = max(mad, 1.0)  # avoid zero-width band
    return Band(center=med, lower=med - k * band, upper=med + k * band, mad=mad, k=k)


def _status_for(value: float, band: Band) -> Status:
    if value < band.lower:
        return "below_band"
    if value > band.upper:
        return "above_band"
    return "in_band"


def _parse_month(s: str) -> Optional[tuple[int, int]]:
    # expects "YYYY-MM"
    try:
        y, m = s.split("-")
        return int(y), int(m)
    except Exception:
        return None


def _month_from_iso(dt_iso: str) -> Optional[str]:
    try:
        # handles "...Z" too
        dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        return None


def _compute_cash_end_by_month(
    months: List[str],
    ledger_rows: Optional[List[Dict[str, Any]]],
) -> Dict[str, float]:
    """
    For each month in `months`, find the last ledger balance within that month.
    If missing, omit.
    """
    if not ledger_rows:
        return {}

    latest: Dict[str, tuple[str, float]] = {}
    for r in ledger_rows:
        m = _month_from_iso(str(r.get("occurred_at") or ""))
        if not m:
            continue
        bal = _safe_float(r.get("balance"))
        ts = str(r.get("occurred_at") or "")
        prev = latest.get(m)
        if prev is None or ts > prev[0]:
            latest[m] = (ts, bal)

    out: Dict[str, float] = {}
    for m in months:
        if m in latest:
            out[m] = float(latest[m][1])
    return out


def _compute_cash_summary(current_cash: float, series_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    burn_rate_3m: average of (-net) for last 3 months where net < 0 (or 0 if not burning)
    runway_months: current_cash / burn_rate_3m if burn_rate_3m > 0 else None
    """
    nets = [float(_safe_float(r.get("net"))) for r in series_rows]
    last3 = nets[-3:] if len(nets) >= 3 else nets

    burns = [(-n) for n in last3 if n < 0]
    burn_rate_3m = float(statistics.mean(burns)) if burns else 0.0
    runway = (current_cash / burn_rate_3m) if burn_rate_3m > 0 else None

    return {
        "current_cash": float(current_cash),
        "burn_rate_3m": float(burn_rate_3m),
        "runway_months": None if runway is None else float(runway),
    }


def build_monthly_trends_payload(
    facts_json: Dict[str, Any],
    lookback_months: int = 12,
    k: float = 2.0,
    ledger_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Deterministic monthly trends payload.

    Input: facts_json from facts_to_dict (monthly_inflow_outflow already computed)
    Output: net + inflow + outflow + cash_end trends, each with baseline band and status.
    """

    rows = monthly_cashflow_from_ledger_rows(ledger_rows) if ledger_rows else []
    if not rows:
        rows = facts_json.get("monthly_inflow_outflow") or []
    if not isinstance(rows, list) or len(rows) == 0:
        return {
            "experiment": {"granularity": "month", "lookback_months": lookback_months, "band_method": "mad", "k": k},
            "metrics": {},
            "series": [],
            "band": None,
            "status": "no_data",
            "current": None,
            "cash": {"current_cash": float(_safe_float(facts_json.get("current_cash"))), "burn_rate_3m": 0.0, "runway_months": None},
        }

    series_rows = rows[-lookback_months:] if lookback_months > 0 else rows[:]

    series: List[Dict[str, Any]] = []
    for r in series_rows:
        m = str(r.get("month") or "")
        inflow = _safe_float(r.get("inflow"))
        outflow = _safe_float(r.get("outflow"))
        net = _safe_float(r.get("net"))
        series.append({"month": m, "inflow": inflow, "outflow": outflow, "net": net})

    months = [s["month"] for s in series]
    cash_end_map = _compute_cash_end_by_month(months, ledger_rows)

    # attach cash_end into every row (fallback to None/0 if missing)
    for s in series:
        m = s["month"]
        s["cash_end"] = float(cash_end_map.get(m, 0.0)) if cash_end_map else 0.0

    def build_metric(metric: str) -> MetricTrend:
        vals = [_safe_float(s.get(metric)) for s in series]
        if len(vals) < 2:
            current_row = series[-1] if series else None
            current = None
            if current_row:
                current = {"month": current_row["month"], metric: _safe_float(current_row.get(metric)), "value": _safe_float(current_row.get(metric))}
            return MetricTrend(
                metric=metric,
                series=[{**s, "value": _safe_float(s.get(metric))} for s in series],
                band=None,
                status="no_data",
                current=current,
                slope=_slope(vals),
                volatility_mad=0.0,
            )

        band = _compute_band(vals, k=k)
        current_val = vals[-1]
        status = _status_for(current_val, band)
        current = {"month": series[-1]["month"], metric: current_val, "value": current_val}

        return MetricTrend(
            metric=metric,
            series=[{**s, "value": _safe_float(s.get(metric))} for s in series],
            band=asdict(band),
            status=status,
            current=current,
            slope=_slope(vals),
            volatility_mad=band.mad,
        )

    net_trend = build_metric("net")
    inflow_trend = build_metric("inflow")
    outflow_trend = build_metric("outflow")
    cash_end_trend = build_metric("cash_end")

    metrics = {
        "net": asdict(net_trend),
        "inflow": asdict(inflow_trend),
        "outflow": asdict(outflow_trend),
        "cash_end": asdict(cash_end_trend),
    }

    current_cash = _safe_float(facts_json.get("current_cash"))
    cash_summary = _compute_cash_summary(current_cash, series)

    # backward-compatible net keys still exist
    return {
        "experiment": {"granularity": "month", "lookback_months": lookback_months, "band_method": "mad", "k": k},
        "metrics": metrics,
        "cash": cash_summary,

        # legacy keys (net)
        "series": metrics["net"]["series"],
        "band": metrics["net"]["band"],
        "status": metrics["net"]["status"],
        "current": metrics["net"]["current"],
    }
