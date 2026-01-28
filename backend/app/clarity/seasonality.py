from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import statistics


@dataclass(frozen=True)
class SeasonalPoint:
    month_of_year: int              # 1..12
    median_net: float
    mad_net: float                  # robust band for “normal” variation
    n: int                          # number of observations used


SeasonalBaseline = Dict[int, SeasonalPoint]


def _parse_month_key(month_key: str) -> Optional[tuple[int, int]]:
    """
    Parse 'YYYY-MM' -> (year, month).
    Returns None if invalid.
    """
    try:
        y_str, m_str = month_key.split("-")
        y = int(y_str)
        m = int(m_str)
        if m < 1 or m > 12:
            return None
        return y, m
    except Exception:
        return None


def compute_seasonal_baseline(
    monthly_rows: List[Dict[str, Any]],
    lookback_months: int = 12,
) -> SeasonalBaseline:
    """
    Build per-month-of-year baselines from the last `lookback_months` rows.

    Assumptions:
    - monthly_rows are sorted oldest -> newest
    - each row has: { month: 'YYYY-MM', net: number }

    Design:
    - Robust stats (median + MAD), so a single weird month doesn't dominate.
    """
    if not monthly_rows:
        return {}

    window = monthly_rows[-lookback_months:] if lookback_months > 0 else monthly_rows[:]

    buckets: Dict[int, List[float]] = {}
    for r in window:
        mk = str(r.get("month") or "")
        parsed = _parse_month_key(mk)
        if not parsed:
            continue

        _, month_num = parsed
        try:
            net = float(r.get("net") or 0.0)
        except Exception:
            net = 0.0

        buckets.setdefault(month_num, []).append(net)

    baseline: SeasonalBaseline = {}
    for month_num, nets in buckets.items():
        if not nets:
            continue
        med = statistics.median(nets)
        mad = statistics.median([abs(n - med) for n in nets]) if len(nets) > 1 else 0.0
        baseline[month_num] = SeasonalPoint(
            month_of_year=month_num,
            median_net=med,
            mad_net=mad,
            n=len(nets),
        )

    return baseline


@dataclass(frozen=True)
class SeasonalAssessment:
    level: str            # "none" | "mild" | "severe"
    penalty: int
    explanation: str
    expected_median: float
    band: float
    month_of_year: int
    n: int


def assess_seasonality(
    seasonal: SeasonalBaseline,
    current_month_key: str,
    current_net: float,
) -> SeasonalAssessment:
    """
    Compare current net against the seasonal expectation for that month-of-year.
    """
    parsed = _parse_month_key(current_month_key)
    if not parsed:
        return SeasonalAssessment(
            level="none",
            penalty=0,
            explanation="Seasonality unavailable (invalid month key).",
            expected_median=0.0,
            band=0.0,
            month_of_year=0,
            n=0,
        )

    _, m = parsed
    point = seasonal.get(m)
    if not point or point.n < 2:
        return SeasonalAssessment(
            level="none",
            penalty=0,
            explanation="Seasonality unavailable (insufficient history for this month).",
            expected_median=point.median_net if point else 0.0,
            band=point.mad_net if point else 0.0,
            month_of_year=m,
            n=point.n if point else 0,
        )

    band = max(point.mad_net, 1.0)
    z = (current_net - point.median_net) / band

    # If current month is within normal seasonal range, don't penalize.
    if z >= -0.5:
        return SeasonalAssessment(
            level="none",
            penalty=0,
            explanation="Performance is within normal seasonal range.",
            expected_median=point.median_net,
            band=band,
            month_of_year=m,
            n=point.n,
        )

    if z >= -1.5:
        return SeasonalAssessment(
            level="mild",
            penalty=2,
            explanation="Slightly below seasonal norm for this month.",
            expected_median=point.median_net,
            band=band,
            month_of_year=m,
            n=point.n,
        )

    return SeasonalAssessment(
        level="severe",
        penalty=5,
        explanation="Materially below seasonal norm for this month.",
        expected_median=point.median_net,
        band=band,
        month_of_year=m,
        n=point.n,
    )
