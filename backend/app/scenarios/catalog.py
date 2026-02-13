from __future__ import annotations

from backend.app.scenarios.models import ScenarioSpec


SCENARIO_CATALOG: dict[str, ScenarioSpec] = {
    "baseline_stable": ScenarioSpec(
        id="baseline_stable",
        name="Baseline Stable",
        description="Healthy baseline profile with steady operations.",
        tags=("baseline", "stable"),
    ),
    "persistent_deterioration": ScenarioSpec(
        id="persistent_deterioration",
        name="Persistent Deterioration",
        description="Sustained revenue and liquidity deterioration.",
        tags=("deterioration", "stress"),
    ),
    "flickering_threshold": ScenarioSpec(
        id="flickering_threshold",
        name="Flickering Threshold",
        description="Near-threshold volatility that can repeatedly fire and settle.",
        tags=("flicker", "threshold"),
    ),
    "hygiene_missing_uncategorized": ScenarioSpec(
        id="hygiene_missing_uncategorized",
        name="Hygiene Missing / Uncategorized",
        description="High uncategorized volume for bookkeeping hygiene workflows.",
        tags=("hygiene", "categorization"),
    ),
    "plan_success_story": ScenarioSpec(
        id="plan_success_story",
        name="Plan Success Story",
        description="A stable story useful for demonstrating a successful plan path.",
        tags=("plan-success", "baseline"),
    ),
    "plan_failure_story": ScenarioSpec(
        id="plan_failure_story",
        name="Plan Failure Story",
        description="A stressed story useful for demonstrating failed plan outcomes.",
        tags=("plan-failure", "stress"),
    ),
}


def list_specs() -> list[ScenarioSpec]:
    return [SCENARIO_CATALOG[key] for key in sorted(SCENARIO_CATALOG.keys())]
