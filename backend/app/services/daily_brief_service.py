from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, TypedDict

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models import AssistantMessage, Business, HealthSignalState
from backend.app.services import changes_service, health_score_service, signals_service


class DailyBriefPlaybook(TypedDict):
    id: str
    title: str
    deep_link: Optional[str]


class DailyBriefPriority(TypedDict):
    signal_id: str
    title: str
    severity: str
    status: str
    why_now: str
    recommended_playbooks: List[DailyBriefPlaybook]
    clear_condition_summary: str


class DailyBriefMetrics(TypedDict):
    health_score: float
    delta_7d: Optional[float]
    open_signals_count: int
    new_changes_count: int


class DailyBriefOut(TypedDict):
    business_id: str
    date: str
    generated_at: str
    headline: str
    summary_bullets: List[str]
    priorities: List[DailyBriefPriority]
    metrics: DailyBriefMetrics
    links: Dict[str, str]


_SEVERITY_ORDER = {
    "critical": 6,
    "high": 5,
    "warning": 4,
    "medium": 3,
    "info": 2,
    "low": 1,
}


def _require_business(db: Session, business_id: str) -> None:
    if not db.get(Business, business_id):
        raise HTTPException(status_code=404, detail="business not found")


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
    return start, end


def _message_checksum(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _recent_daily_brief_rows(db: Session, business_id: str, target_date: str) -> List[AssistantMessage]:
    rows = (
        db.execute(
            select(AssistantMessage)
            .where(
                AssistantMessage.business_id == business_id,
                AssistantMessage.kind == "daily_brief",
            )
            .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        )
        .scalars()
        .all()
    )
    return [row for row in rows if isinstance(row.content_json, dict) and str(row.content_json.get("date")) == target_date]


def _last_brief_before(db: Session, business_id: str, target_day_start: datetime) -> Optional[AssistantMessage]:
    rows = (
        db.execute(
            select(AssistantMessage)
            .where(
                AssistantMessage.business_id == business_id,
                AssistantMessage.kind == "daily_brief",
                AssistantMessage.created_at < target_day_start,
            )
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            .limit(1)
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


def _changes_since(db: Session, business_id: str, since_dt: datetime) -> List[Dict[str, Any]]:
    all_changes = changes_service.list_changes(db, business_id=business_id, limit=200)
    scoped: List[Dict[str, Any]] = []
    for change in all_changes:
        occurred_at = change.get("occurred_at")
        if not occurred_at:
            continue
        try:
            ts = datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if ts >= since_dt:
            scoped.append(change)
    return scoped


def _priority_sort_key(state: HealthSignalState) -> tuple:
    severity = _SEVERITY_ORDER.get((state.severity or "").lower(), 0)
    status_open = 1 if state.status == "open" else 0
    last_seen = _to_utc(state.last_seen_at).timestamp() if state.last_seen_at else 0
    return (-severity, -status_open, -last_seen, str(state.signal_id))


def build_daily_brief(db: Session, business_id: str, as_of_dt_utc: datetime) -> DailyBriefOut:
    _require_business(db, business_id)
    as_of = _to_utc(as_of_dt_utc)
    target_date = as_of.date()
    day_start, _ = _day_bounds(target_date)

    previous_brief = _last_brief_before(db, business_id, day_start)
    if previous_brief and previous_brief.created_at:
        since_dt = _to_utc(previous_brief.created_at)
    else:
        since_dt = as_of - timedelta(hours=24)

    recent_changes = _changes_since(db, business_id, since_dt)

    score = health_score_service.compute_health_score(db, business_id)
    delta_7d: Optional[float] = None
    try:
        explain_7d = health_score_service.explain_health_score_change(db, business_id, since_hours=168, limit=20)
        delta_7d = float(explain_7d.get("summary", {}).get("net_estimated_delta"))
    except Exception:
        delta_7d = None

    states = (
        db.execute(
            select(HealthSignalState)
            .where(HealthSignalState.business_id == business_id, HealthSignalState.status != "resolved")
        )
        .scalars()
        .all()
    )
    ordered_states = sorted(states, key=_priority_sort_key)

    priorities: List[DailyBriefPriority] = []
    for state in ordered_states[:10]:
        explain = signals_service.get_signal_explain(db, business_id, state.signal_id)
        playbooks = [
            {
                "id": str(item.get("id", "")),
                "title": str(item.get("title", "")),
                "deep_link": item.get("deep_link"),
            }
            for item in explain.get("playbooks", [])[:3]
        ]
        clear_condition = explain.get("clear_condition") or {}
        clear_summary = str(clear_condition.get("summary") or "No explicit clear condition available.")
        severity = str(state.severity or "warning")
        status = str(state.status or "open")
        title = str(state.title or state.signal_id)

        why_now = f"{title} is {status.replace('_', ' ')} with {severity} severity."
        priorities.append(
            {
                "signal_id": state.signal_id,
                "title": title,
                "severity": severity,
                "status": status,
                "why_now": why_now,
                "recommended_playbooks": playbooks,
                "clear_condition_summary": clear_summary,
            }
        )

    priorities = priorities[:5]

    health_score = float(score.get("score", 0.0))
    headline = f"Daily brief for {target_date.isoformat()}: health score {round(health_score, 2)} with {len(priorities)} active priorities."

    summary_bullets = [
        f"Health score is {round(health_score, 2)}.",
        f"Open signals: {len(ordered_states)}.",
        f"Recent changes since window start: {len(recent_changes)}.",
    ]
    if delta_7d is not None:
        summary_bullets.append(f"Estimated 7-day score delta: {round(delta_7d, 2)}.")
    if priorities:
        summary_bullets.append(f"Top priority: {priorities[0]['title']} ({priorities[0]['severity']}).")
    summary_bullets = summary_bullets[:5]

    return {
        "business_id": business_id,
        "date": target_date.isoformat(),
        "generated_at": as_of.isoformat(),
        "headline": headline,
        "summary_bullets": summary_bullets,
        "priorities": priorities,
        "metrics": {
            "health_score": round(health_score, 2),
            "delta_7d": round(delta_7d, 2) if delta_7d is not None else None,
            "open_signals_count": len(ordered_states),
            "new_changes_count": len(recent_changes),
        },
        "links": {
            "assistant": f"/app/{business_id}/assistant",
            "signals": f"/app/{business_id}/signals",
            "health_score": f"/app/{business_id}/assistant?view=health_score",
            "changes": f"/app/{business_id}/assistant?view=changes",
        },
    }


def get_daily_brief_for_date(db: Session, business_id: str, target_date: date, as_of_dt_utc: datetime) -> DailyBriefOut:
    _require_business(db, business_id)
    rows = _recent_daily_brief_rows(db, business_id, target_date.isoformat())
    if rows:
        payload = rows[0].content_json
        if isinstance(payload, dict):
            return payload  # type: ignore[return-value]
    as_of = _to_utc(as_of_dt_utc)
    return build_daily_brief(db, business_id, as_of)


def publish_daily_brief(db: Session, business_id: str, target_date: date, as_of_dt_utc: datetime) -> tuple[AssistantMessage, DailyBriefOut]:
    _require_business(db, business_id)
    as_of = _to_utc(as_of_dt_utc)
    brief = build_daily_brief(db, business_id, as_of)
    brief["date"] = target_date.isoformat()

    payload = dict(brief)
    checksum_payload = {
        "author": "system",
        "kind": "daily_brief",
        "signal_id": None,
        "audit_id": None,
        "content_json": payload,
    }
    checksum = _message_checksum(checksum_payload)

    same_day = _recent_daily_brief_rows(db, business_id, target_date.isoformat())
    primary = same_day[0] if same_day else None

    if primary is None:
        primary = AssistantMessage(
            business_id=business_id,
            created_at=as_of,
            author="system",
            kind="daily_brief",
            signal_id=None,
            audit_id=None,
            content_json=payload,
            checksum=checksum,
        )
        db.add(primary)
        db.flush()
    else:
        primary.created_at = as_of
        primary.author = "system"
        primary.kind = "daily_brief"
        primary.content_json = payload
        primary.checksum = checksum
        db.flush()

    if len(same_day) > 1:
        duplicate_ids = [row.id for row in same_day[1:]]
        db.execute(delete(AssistantMessage).where(AssistantMessage.id.in_(duplicate_ids)))

    db.commit()
    db.refresh(primary)
    return primary, brief
