from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.norma.facts import Facts, facts_to_dict
from backend.app.clarity.signals import Signal, compute_signals
from backend.app.clarity.scoring import compute_business_score


def compute_health_summary(business_id: str, facts: Facts) -> Dict[str, Any]:
    # 1) Signals operate on typed Facts (deterministic, stable contract)
    signals: List[Signal] = compute_signals(facts)
    signals_dicts = [asdict(s) for s in signals]

    # 2) Scoring operates on JSON-friendly dict (boundary object)
    facts_dict = facts_to_dict(facts)
    breakdown = compute_business_score(facts=facts_dict, signals=signals_dicts)

    highlights = [s["title"] for s in signals_dicts[:3]]

    return {
        "business_id": business_id,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "risk": breakdown.risk,
        "health_score": breakdown.overall,
        "pillars": {
            "liquidity": breakdown.liquidity,
            "stability": breakdown.stability,
            "discipline": breakdown.discipline,
        },
        "highlights": highlights,
        "signals": signals_dicts,
        # Optional but useful for debugging/UI:
        "facts": facts_dict,
    }
