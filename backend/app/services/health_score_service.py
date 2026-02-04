from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Business, HealthSignalState
from backend.app.services.signals_service import SIGNAL_CATALOG


DOMAIN_WEIGHTS: Dict[str, float] = {
    "liquidity": 1.4,
    "revenue": 1.2,
    "expense": 1.2,
    "timing": 1.1,
    "concentration": 0.9,
    "hygiene": 0.8,
    "unknown": 0.7,
}

SEVERITY_WEIGHTS: Dict[str, float] = {
    "critical": 18.0,
    "high": 16.0,
    "warning": 12.0,
    "medium": 10.0,
    "info": 4.0,
    "low": 6.0,
}

STATUS_MULTIPLIERS: Dict[str, float] = {
    "open": 1.0,
    "in_progress": 0.8,
    "ignored": 0.3,
    "resolved": 0.0,
}


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _severity_weight(severity: Optional[str]) -> float:
    if not severity:
        return SEVERITY_WEIGHTS["warning"]
    return SEVERITY_WEIGHTS.get(severity, SEVERITY_WEIGHTS["warning"])


def _domain_weight(domain: Optional[str]) -> float:
    if not domain:
        return DOMAIN_WEIGHTS["unknown"]
    return DOMAIN_WEIGHTS.get(domain, DOMAIN_WEIGHTS["unknown"])


def _status_multiplier(status: str) -> float:
    return STATUS_MULTIPLIERS.get(status, 1.0)


def _persistence_multiplier(state: HealthSignalState) -> float:
    start = state.detected_at or state.updated_at
    end = state.last_seen_at or state.updated_at or state.detected_at
    if not start or not end:
        return 1.0
    age_days = max((end - start).total_seconds() / 86400.0, 0.0)
    multiplier = 1.0 + (age_days / 14.0)
    return max(1.0, min(2.0, multiplier))


def _catalog_meta(signal_type: Optional[str]) -> Dict[str, Any]:
    if not signal_type:
        return {}
    return SIGNAL_CATALOG.get(signal_type, {})


def compute_health_score(db: Session, business_id: str) -> Dict[str, Any]:
    _require_business(db, business_id)

    states = (
        db.execute(
            select(HealthSignalState)
            .where(HealthSignalState.business_id == business_id)
            .order_by(HealthSignalState.signal_id.asc())
        )
        .scalars()
        .all()
    )

    contributors: List[Dict[str, Any]] = []
    domains: Dict[str, Dict[str, Any]] = {}

    for state in states:
        catalog = _catalog_meta(state.signal_type)
        domain = catalog.get("domain") or "unknown"
        severity = state.severity or catalog.get("default_severity") or "warning"
        status = state.status
        status_multiplier = _status_multiplier(status)
        if status_multiplier <= 0:
            continue

        domain_weight = _domain_weight(domain)
        severity_weight = _severity_weight(severity)
        profile = catalog.get("scoring_profile") or {}
        profile_weight = float(profile.get("weight", 1.0)) * float(profile.get("domain_weight", 1.0))
        persistence = _persistence_multiplier(state)
        penalty = domain_weight * severity_weight * profile_weight * status_multiplier * persistence

        penalty = round(penalty, 2)
        rationale = (
            f"{severity} {domain} signal {status}; "
            f"persists {round(persistence, 2)}x; "
            f"weight={round(domain_weight * severity_weight, 2)}"
        )

        contributor = {
            "signal_id": state.signal_id,
            "domain": domain,
            "status": status,
            "severity": severity,
            "penalty": penalty,
            "rationale": rationale,
        }
        contributors.append(contributor)

        domain_entry = domains.setdefault(
            domain,
            {
                "domain": domain,
                "score": 100.0,
                "penalty": 0.0,
                "contributors": [],
            },
        )
        domain_entry["penalty"] = round(domain_entry["penalty"] + penalty, 2)
        domain_entry["contributors"].append(contributor)

    def _sort_key(item: Dict[str, Any]) -> tuple:
        return (-float(item.get("penalty", 0.0)), str(item.get("domain", "")), str(item.get("signal_id", "")))

    contributors_sorted = sorted(contributors, key=_sort_key)

    domain_list: List[Dict[str, Any]] = []
    for domain_key in sorted(domains.keys()):
        entry = domains[domain_key]
        entry["contributors"] = sorted(entry["contributors"], key=_sort_key)
        entry["score"] = max(0.0, round(100.0 - float(entry["penalty"]), 2))
        domain_list.append(entry)

    total_penalty = round(sum(item["penalty"] for item in contributors_sorted), 2)
    score = max(0.0, round(100.0 - total_penalty, 2))

    return {
        "business_id": business_id,
        "score": score,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domains": domain_list,
        "contributors": contributors_sorted,
        "meta": {
            "model_version": "health_score_v1",
            "weights": {
                "domain": DOMAIN_WEIGHTS,
                "severity": SEVERITY_WEIGHTS,
                "status": STATUS_MULTIPLIERS,
                "persistence": "clamp(1 + age_days/14, 1, 2)",
            },
        },
    }
