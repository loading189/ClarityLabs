from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AuditLog, Business, HealthSignalState
from backend.app.services import signals_service
from backend.app.services.assistant_plan_service import list_plans

SEVERITY_WEIGHTS = {
    "critical": 100,
    "warn": 60,
    "warning": 60,
    "info": 20,
}


class WorkQueuePrimaryAction(BaseModel):
    label: str
    type: Literal["open_explain", "open_plan", "start_playbook"]
    payload: Dict[str, Any]


class WorkQueueLinks(BaseModel):
    assistant: str
    signals: Optional[str] = None


class WorkQueueItem(BaseModel):
    kind: Literal["signal", "plan"]
    id: str
    title: str
    severity: Optional[str] = None
    status: str
    domain: Optional[str] = None
    score: int
    why_now: str
    primary_action: WorkQueuePrimaryAction
    links: WorkQueueLinks


class WorkQueueOut(BaseModel):
    business_id: str
    generated_at: str
    items: List[WorkQueueItem]


class _ScoredItem(BaseModel):
    item: WorkQueueItem

    @property
    def sort_key(self) -> tuple[int, str, str]:
        return (-self.item.score, str(self.item.domain or ""), self.item.id)


def _require_business(db: Session, business_id: str) -> None:
    if not db.get(Business, business_id):
        raise HTTPException(status_code=404, detail="business not found")


def _active_plans_by_signal(db: Session, business_id: str) -> Dict[str, List[Dict[str, Any]]]:
    plans = [plan.model_dump() for plan in list_plans(db, business_id)]
    active = [plan for plan in plans if plan.get("status") in {"open", "in_progress"}]
    by_signal: Dict[str, List[Dict[str, Any]]] = {}
    for plan in active:
        for signal_id in sorted({str(signal_id) for signal_id in (plan.get("signal_ids") or []) if str(signal_id)}):
            by_signal.setdefault(signal_id, []).append(plan)
    for signal_id, rows in by_signal.items():
        rows.sort(key=lambda plan: (str(plan.get("updated_at") or ""), str(plan.get("plan_id") or "")), reverse=True)
    return by_signal


def _signals_with_recent_changes(db: Session, business_id: str, since: datetime) -> set[str]:
    rows = (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.business_id == business_id,
                AuditLog.created_at >= since,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        )
        .scalars()
        .all()
    )
    signal_ids: set[str] = set()
    for row in rows:
        if row.event_type not in {"signal_detected", "signal_resolved", "signal_status_changed", "signal_status_updated"}:
            continue
        for payload in (row.after_state, row.before_state):
            if isinstance(payload, dict) and payload.get("signal_id"):
                signal_ids.add(str(payload["signal_id"]))
                break
    return signal_ids


def _signal_score(row: HealthSignalState, *, has_recent_change: bool, has_active_plan: bool) -> int:
    severity = str(row.severity or "info").lower()
    base = SEVERITY_WEIGHTS.get(severity, 20)
    detected_at = row.detected_at or row.updated_at or row.last_seen_at
    open_days = 0
    if detected_at:
        open_days = max(0, (datetime.now(timezone.utc).date() - detected_at.date()).days)
    score = base + min(20, open_days)
    if has_recent_change:
        score += 10
    if not has_active_plan:
        score += 15
    return score


def list_work_queue(db: Session, business_id: str, limit: int = 50) -> WorkQueueOut:
    _require_business(db, business_id)
    bounded_limit = max(1, min(limit, 200))
    now = datetime.now(timezone.utc)
    active_plans_by_signal = _active_plans_by_signal(db, business_id)
    signals_with_changes = _signals_with_recent_changes(db, business_id, now - timedelta(days=7))

    signal_rows = (
        db.execute(
            select(HealthSignalState)
            .where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.status.not_in(["resolved", "closed"]),
            )
            .order_by(HealthSignalState.signal_id.asc())
        )
        .scalars()
        .all()
    )

    scored_items: List[_ScoredItem] = []

    added_plan_ids: set[str] = set()
    for plan_rows in active_plans_by_signal.values():
        for plan in plan_rows:
            plan_id = str(plan.get("plan_id") or "")
            if not plan_id or plan_id in added_plan_ids:
                continue
            added_plan_ids.add(plan_id)
            unfinished = sum(1 for step in (plan.get("steps") or []) if str(step.get("status") or "todo") != "done")
            score = 90 + unfinished
            scored_items.append(
                _ScoredItem(
                    item=WorkQueueItem(
                        kind="plan",
                        id=plan_id,
                        title=str(plan.get("title") or f"Plan {plan_id[:8]}"),
                        status=str(plan.get("status") or "open"),
                        domain="assistant",
                        score=score,
                        why_now=f"Active plan with {unfinished} unfinished step{'s' if unfinished != 1 else ''}.",
                        primary_action=WorkQueuePrimaryAction(
                            label="Open Plan",
                            type="open_plan",
                            payload={"plan_id": plan_id},
                        ),
                        links=WorkQueueLinks(assistant=f"/app/{business_id}/assistant?planId={plan_id}"),
                    )
                )
            )

    for row in signal_rows:
        signal_id = str(row.signal_id)
        signal_type = str(row.signal_type or "")
        domain = signals_service.SIGNAL_CATALOG.get(signal_type, {}).get("domain")
        active_plan = (active_plans_by_signal.get(signal_id) or [None])[0]
        has_plan = active_plan is not None
        has_change = signal_id in signals_with_changes
        score = _signal_score(row, has_recent_change=has_change, has_active_plan=has_plan)

        playbooks = sorted(
            signals_service.get_signal_explain(db, business_id, signal_id).get("playbooks") or [],
            key=lambda item: str(item.get("id") or ""),
        )
        primary_action: WorkQueuePrimaryAction
        if has_plan and active_plan:
            primary_action = WorkQueuePrimaryAction(
                label="Open Plan",
                type="open_plan",
                payload={"plan_id": str(active_plan.get("plan_id"))},
            )
        elif playbooks:
            playbook = playbooks[0]
            primary_action = WorkQueuePrimaryAction(
                label="Start Playbook",
                type="start_playbook",
                payload={
                    "signal_id": signal_id,
                    "playbook_id": str(playbook.get("id") or ""),
                    "title": str(playbook.get("title") or "Start playbook"),
                    "deep_link": playbook.get("deep_link"),
                },
            )
        else:
            primary_action = WorkQueuePrimaryAction(
                label="Open Explain",
                type="open_explain",
                payload={"signal_id": signal_id},
            )

        why_bits = [f"{str(row.severity or 'info').lower()} signal"]
        if has_change:
            why_bits.append("recent change in last 7d")
        if has_plan:
            why_bits.append("active plan linked")
        else:
            why_bits.append("no active plan")
        scored_items.append(
            _ScoredItem(
                item=WorkQueueItem(
                    kind="signal",
                    id=signal_id,
                    title=str(row.title or signal_id),
                    severity=row.severity,
                    status=str(row.status or "open"),
                    domain=domain,
                    score=score,
                    why_now="; ".join(why_bits) + ".",
                    primary_action=primary_action,
                    links=WorkQueueLinks(
                        assistant=f"/app/{business_id}/assistant?signalId={signal_id}",
                        signals=f"/app/{business_id}/signals?signalId={signal_id}",
                    ),
                )
            )
        )

    scored_items.sort(key=lambda row: row.sort_key)
    return WorkQueueOut(
        business_id=business_id,
        generated_at=now.isoformat(),
        items=[row.item for row in scored_items[:bounded_limit]],
    )
