from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AssistantMessage, Business, HealthSignalState
from backend.app.services import health_score_service


class ProgressOut(BaseModel):
    business_id: str
    window_days: int
    generated_at: str
    health_score: Dict[str, float]
    open_signals: Dict[str, int]
    plans: Dict[str, int]
    streak_days: int
    top_domains_open: List[Dict[str, Any]]


def _require_business(db: Session, business_id: str) -> None:
    if not db.get(Business, business_id):
        raise ValueError("business not found")


def _daily_briefs_by_date(db: Session, business_id: str) -> Dict[str, Dict[str, Any]]:
    rows = (
        db.execute(
            select(AssistantMessage)
            .where(AssistantMessage.business_id == business_id, AssistantMessage.kind == "daily_brief")
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        )
        .scalars()
        .all()
    )
    by_date: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        payload = row.content_json if isinstance(row.content_json, dict) else {}
        date_key = str(payload.get("date") or "")
        if not date_key or date_key in by_date:
            continue
        by_date[date_key] = payload
    return by_date


def _is_open_state(status: str) -> bool:
    return status not in {"resolved", "closed"}


def _domain_for_state(state: HealthSignalState) -> str:
    payload = state.payload_json if isinstance(state.payload_json, dict) else {}
    payload_domain = str(payload.get("domain") or "").strip().lower()
    if payload_domain:
        return payload_domain
    signal_type = str(state.signal_type or "").strip().lower()
    if "." in signal_type:
        return signal_type.split(".", 1)[0] or "unknown"
    return "unknown"


def _plan_rows(db: Session, business_id: str) -> List[AssistantMessage]:
    return (
        db.execute(
            select(AssistantMessage)
            .where(AssistantMessage.business_id == business_id, AssistantMessage.kind == "plan")
            .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        )
        .scalars()
        .all()
    )


def get_progress(db: Session, business_id: str, window_days: int = 7) -> ProgressOut:
    _require_business(db, business_id)
    now = datetime.now(timezone.utc)
    today = now.date()
    window_date = today - timedelta(days=window_days)

    score_now = float(health_score_service.compute_health_score(db, business_id).get("score") or 0.0)

    states = (
        db.execute(select(HealthSignalState).where(HealthSignalState.business_id == business_id))
        .scalars()
        .all()
    )
    open_states = [state for state in states if _is_open_state(str(state.status or ""))]

    briefs = _daily_briefs_by_date(db, business_id)
    today_brief = briefs.get(today.isoformat()) or {}
    window_brief = briefs.get(window_date.isoformat()) or {}

    today_metrics = today_brief.get("metrics") if isinstance(today_brief.get("metrics"), dict) else {}
    window_metrics = window_brief.get("metrics") if isinstance(window_brief.get("metrics"), dict) else {}

    today_score = today_metrics.get("health_score")
    window_score = window_metrics.get("health_score")
    score_delta = 0.0
    if isinstance(today_score, (int, float)) and isinstance(window_score, (int, float)):
        score_delta = round(float(today_score) - float(window_score), 2)

    today_open = today_metrics.get("open_signals_count")
    window_open = window_metrics.get("open_signals_count")
    open_delta = 0
    if isinstance(today_open, int) and isinstance(window_open, int):
        open_delta = today_open - window_open

    active_count = 0
    completed_count_window = 0
    window_start_dt = datetime.combine(window_date, datetime.min.time(), tzinfo=timezone.utc)
    for row in _plan_rows(db, business_id):
        content = row.content_json if isinstance(row.content_json, dict) else {}
        status = str(content.get("status") or "open")
        if status in {"open", "in_progress"}:
            active_count += 1
        if status != "done":
            continue
        completed_at = str(content.get("completed_at") or content.get("updated_at") or "")
        if not completed_at:
            continue
        try:
            completed_dt = datetime.fromisoformat(completed_at).astimezone(timezone.utc)
        except ValueError:
            continue
        if completed_dt >= window_start_dt:
            completed_count_window += 1

    streak_days = 0
    cursor = today
    while True:
        if cursor.isoformat() not in briefs:
            break
        streak_days += 1
        cursor = cursor - timedelta(days=1)

    domain_counts = Counter(_domain_for_state(state) for state in open_states)
    top_domains_open = [
        {"domain": domain, "count": count}
        for domain, count in sorted(domain_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]

    return ProgressOut(
        business_id=business_id,
        window_days=window_days,
        generated_at=now.isoformat(),
        health_score={"current": round(score_now, 2), "delta_window": score_delta},
        open_signals={"current": len(open_states), "delta_window": open_delta},
        plans={"active_count": active_count, "completed_count_window": completed_count_window},
        streak_days=streak_days,
        top_domains_open=top_domains_open,
    )
