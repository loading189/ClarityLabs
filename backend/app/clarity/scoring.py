# backend/app/clarity/scoring.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Union

from backend.app.clarity.signals import Signal  # <-- import your Signal dataclass
from backend.app.clarity.baseline import compute_rolling_baseline
from backend.app.clarity.drift import assess_drift
from backend.app.clarity.seasonality import compute_seasonal_baseline, assess_seasonality


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def severity_penalty(sev: str) -> int:
    if sev == "red":
        return 25
    if sev == "yellow":
        return 10
    return 0


def compute_risk_label(signals: Iterable[Union[Signal, Dict[str, Any]]]) -> str:
    sevs = set()
    for s in signals:
        if isinstance(s, dict):
            sevs.add((s.get("severity") or "green").lower())
        else:
            sevs.add((s.severity or "green").lower())

    if "red" in sevs:
        return "red"
    if "yellow" in sevs:
        return "yellow"
    return "green"


def get_current_cash(facts: Dict[str, Any]) -> float:
    try:
        return float(facts.get("current_cash") or 0.0)
    except Exception:
        return 0.0


def get_monthly_rows(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = facts.get("monthly_inflow_outflow") or []
    return rows if isinstance(rows, list) else []


def last_n_months(monthly_rows: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    return monthly_rows[-n:] if len(monthly_rows) >= n else monthly_rows


def avg_outflow(months: List[Dict[str, Any]]) -> float:
    if not months:
        return 0.0
    vals = []
    for m in months:
        try:
            vals.append(float(m.get("outflow") or 0.0))
        except Exception:
            vals.append(0.0)
    return sum(vals) / max(1, len(vals))


def avg_net(months: List[Dict[str, Any]]) -> float:
    if not months:
        return 0.0
    vals = []
    for m in months:
        try:
            vals.append(float(m.get("net") or 0.0))
        except Exception:
            vals.append(0.0)
    return sum(vals) / max(1, len(vals))


def liquidity_score(facts: Dict[str, Any]) -> float:
    cash = get_current_cash(facts)
    months = last_n_months(get_monthly_rows(facts), 3)
    out = avg_outflow(months)

    if out <= 0:
        return 60.0

    runway = cash / out  # months

    if runway >= 6:
        return 95.0
    if runway >= 3:
        return 75.0 + (runway - 3.0) * (20.0 / 3.0)
    if runway >= 1:
        return 45.0 + (runway - 1.0) * (30.0 / 2.0)
    return 20.0 + runway * 25.0


def stability_score(facts: Dict[str, Any]) -> float:
    months = last_n_months(get_monthly_rows(facts), 3)
    net = avg_net(months)
    out = avg_outflow(months)

    if out <= 0:
        return 80.0 if net >= 0 else 45.0

    ratio = net / out

    if ratio >= 0.20:
        return 95.0
    if ratio >= 0.0:
        return 70.0 + ratio * (25.0 / 0.20)
    if ratio >= -0.20:
        return 40.0 + (ratio + 0.20) * (30.0 / 0.20)
    return 20.0


def discipline_score_from_signals(signals: Iterable[Union[Signal, Dict[str, Any]]]) -> float:
    base = 90.0
    total_penalty = 0.0

    for s in signals:
        if isinstance(s, dict):
            sev = (s.get("severity") or "green").lower()
            w = float(s.get("weight") or 1.0)
        else:
            sev = (s.severity or "green").lower()
            w = 1.0  # you can add weights later based on s.key

        total_penalty += severity_penalty(sev) * w

    return clamp(base - total_penalty * 0.6, 0.0, 100.0)


@dataclass(frozen=True)
class ScoreBreakdown:
    overall: int
    risk: str
    liquidity: int
    stability: int
    discipline: int


def compute_business_score(
    facts: Dict[str, Any],
    signals: List[Dict[str, Any]],
) -> ScoreBreakdown:

    # 1) Pillars
    liq = liquidity_score(facts)
    stab = stability_score(facts)
    disc = discipline_score_from_signals(signals)

    base = 0.50 * liq + 0.30 * stab + 0.20 * disc

    # 2) Monthly rows
    monthly = facts.get("monthly_inflow_outflow", []) or []

    current_month_key = monthly[-1]["month"] if monthly else ""
    current_net = float(monthly[-1]["net"]) if monthly else 0.0

    # 3) Rolling drift
    baseline = compute_rolling_baseline(monthly, window=3)
    drift = assess_drift(baseline, current_net)

    # 4) Seasonality
    seasonal = compute_seasonal_baseline(monthly, lookback_months=12)
    season = assess_seasonality(seasonal, current_month_key, current_net)

    # 5) Drift penalty adjustment (don’t double-punish normal seasonal months)
    drift_penalty = drift.penalty
    if season.level == "none":
        drift_penalty = max(0, drift_penalty - 2)

    # 6) Final overall (compute ONCE)
    overall = clamp(base - drift_penalty - season.penalty, 0.0, 100.0)

    risk = compute_risk_label(signals)

    return ScoreBreakdown(
        overall=int(round(overall)),
        risk=risk,
        liquidity=int(round(clamp(liq, 0, 100))),
        stability=int(round(clamp(stab, 0, 100))),
        discipline=int(round(clamp(disc, 0, 100))),
    )


