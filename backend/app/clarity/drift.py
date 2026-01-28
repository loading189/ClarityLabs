from __future__ import annotations
from dataclasses import dataclass
from .baseline import RollingBaseline


@dataclass(frozen=True)
class DriftAssessment:
    level: str            # "none" | "mild" | "severe"
    penalty: int
    explanation: str


def assess_drift(
    baseline: RollingBaseline,
    current_net: float,
) -> DriftAssessment:
    """
    Determines if the business is drifting away from its recent norm.
    """

    deviation = current_net - baseline.median_net
    band = max(baseline.mad_net, 1.0)  # prevent divide-by-zero

    # Normalize deviation
    z = deviation / band

    if z >= -0.5:
        return DriftAssessment("none", 0, "Net is within normal range")

    if z >= -1.5:
        return DriftAssessment(
            "mild",
            3,
            "Net income is trending below recent norms",
        )

    return DriftAssessment(
        "severe",
        7,
        "Net income has deteriorated significantly versus recent history",
    )
