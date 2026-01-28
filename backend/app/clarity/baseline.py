from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any
import statistics


@dataclass(frozen=True)
class RollingBaseline:
    window_months: int
    median_net: float
    mad_net: float
    trend_slope: float


def compute_rolling_baseline(
    monthly_rows: List[Dict[str, Any]],
    window: int = 3,
) -> RollingBaseline:
    """
    Computes a rolling baseline using the last N months.
    Assumes rows are sorted oldest → newest.
    """

    if not monthly_rows:
        return RollingBaseline(window, 0.0, 0.0, 0.0)

    window_rows = monthly_rows[-window:]

    nets = []
    for m in window_rows:
        try:
            nets.append(float(m.get("net") or 0.0))
        except Exception:
            nets.append(0.0)

    if not nets:
        return RollingBaseline(window, 0.0, 0.0, 0.0)

    median_net = statistics.median(nets)

    # Median Absolute Deviation (robust volatility)
    mad_net = statistics.median([abs(n - median_net) for n in nets])

    # Simple linear slope (trend)
    # x = time index, y = net
    if len(nets) < 2:
        slope = 0.0
    else:
        x = list(range(len(nets)))
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(nets)

        num = sum((x[i] - x_mean) * (nets[i] - y_mean) for i in range(len(nets)))
        den = sum((x[i] - x_mean) ** 2 for i in range(len(nets)))
        slope = num / den if den != 0 else 0.0

    return RollingBaseline(
        window_months=window,
        median_net=median_net,
        mad_net=mad_net,
        trend_slope=slope,
    )
