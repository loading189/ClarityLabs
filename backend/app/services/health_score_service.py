from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AuditLog, Business, HealthSignalState
from backend.app.services.signals_service import SIGNAL_CATALOG
from backend.app.services import changes_service

logger = logging.getLogger(__name__)


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
        logger.warning("Health score requested for missing business_id=%s", business_id)
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



def _signal_penalty_estimate(state: Optional[HealthSignalState], signal_type: Optional[str], severity: Optional[str], status: Optional[str]) -> float:
    catalog = _catalog_meta(signal_type or (state.signal_type if state else None))
    domain = catalog.get("domain") or "unknown"
    resolved_status = status or (state.status if state else "open")
    resolved_severity = severity or (state.severity if state else None) or catalog.get("default_severity") or "warning"
    domain_weight = _domain_weight(domain)
    severity_weight = _severity_weight(resolved_severity)
    profile = catalog.get("scoring_profile") or {}
    profile_weight = float(profile.get("weight", 1.0)) * float(profile.get("domain_weight", 1.0))
    persistence = _persistence_multiplier(state) if state else 1.0
    return round(domain_weight * severity_weight * profile_weight * _status_multiplier(resolved_status) * persistence, 2)


def explain_health_score_change(db: Session, business_id: str, since_hours: int = 72, limit: int = 20) -> Dict[str, Any]:
    _require_business(db, business_id)
    bounded_limit = max(1, min(limit, 20))
    changes = changes_service.list_changes_window(db, business_id, since_hours=since_hours, limit=bounded_limit)
    signal_states = (
        db.execute(select(HealthSignalState).where(HealthSignalState.business_id == business_id))
        .scalars()
        .all()
    )
    state_map = {state.signal_id: state for state in signal_states}

    impacts: List[Dict[str, Any]] = []
    for change in changes:
        signal_id = str(change.get("signal_id") or "")
        if not signal_id:
            continue
        change_type = str(change.get("type") or "signal_status_updated")
        state = state_map.get(signal_id)
        signal_type = state.signal_type if state else None
        if change_type == "signal_detected":
            penalty = _signal_penalty_estimate(state, signal_type, change.get("severity"), "open")
            delta = -penalty
            rationale = f"Detected signal increases penalty by {penalty}."
        elif change_type == "signal_resolved":
            penalty = _signal_penalty_estimate(state, signal_type, change.get("severity"), "open")
            delta = penalty
            rationale = f"Resolved signal removes estimated penalty {penalty}."
        else:
            audit = db.get(AuditLog, change.get("id"))
            before = audit.before_state if audit and isinstance(audit.before_state, dict) else {}
            after = audit.after_state if audit and isinstance(audit.after_state, dict) else {}
            before_status = str(before.get("status") or "open")
            after_status = str(after.get("status") or (state.status if state else "open"))
            before_penalty = _signal_penalty_estimate(state, signal_type, change.get("severity"), before_status)
            after_penalty = _signal_penalty_estimate(state, signal_type, change.get("severity"), after_status)
            delta = round(before_penalty - after_penalty, 2)
            rationale = f"Status changed from {before_status} to {after_status}; estimated penalty delta {delta}."

        impacts.append(
            {
                "signal_id": signal_id,
                "domain": (state and _catalog_meta(state.signal_type).get("domain")) or change.get("domain"),
                "severity": (state.severity if state else None) or change.get("severity"),
                "change_type": change_type,
                "estimated_penalty_delta": round(delta, 2),
                "rationale": rationale,
            }
        )

    impacts_sorted = sorted(
        impacts,
        key=lambda row: (
            -abs(float(row.get("estimated_penalty_delta", 0.0))),
            str(row.get("change_type", "")),
            str(row.get("signal_id", "")),
        ),
    )[:bounded_limit]

    net_delta = round(sum(float(item["estimated_penalty_delta"]) for item in impacts_sorted), 2)
    if net_delta > 0:
        headline = f"Health score likely improved by {net_delta} points from recent changes."
    elif net_delta < 0:
        headline = f"Health score likely declined by {abs(net_delta)} points from recent changes."
    else:
        headline = "Health score appears stable from recent changes."

    top_drivers = [
        f"{item['signal_id']} ({item['change_type'].replace('_', ' ')}, {item['estimated_penalty_delta']})"
        for item in impacts_sorted[:3]
    ]

    return {
        "business_id": business_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "window": {"since_hours": since_hours},
        "changes": changes,
        "impacts": impacts_sorted,
        "summary": {
            "headline": headline,
            "net_estimated_delta": net_delta,
            "top_drivers": top_drivers,
        },
    }
