from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Case, Plan, WorkItem
from backend.app.services import case_engine_service

WORK_ITEM_TYPES = {
    "REVIEW_DUE",
    "SLA_BREACH",
    "NO_PLAN",
    "PLAN_OVERDUE",
    "HIGH_SEVERITY_TRIAGE",
    "UNASSIGNED_CASE",
}
WORK_ITEM_STATUSES = {"open", "snoozed", "completed"}
SEVERITY_ORDER = ["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class ComputedWorkItem:
    case_id: str
    business_id: str
    type: str
    priority: int
    due_at: Optional[datetime]
    idempotency_key: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_work_item(db: Session, work_item_id: str) -> WorkItem:
    row = db.get(WorkItem, work_item_id)
    if not row:
        raise HTTPException(status_code=404, detail="work item not found")
    return row


def _review_date_bucket(review_at: datetime) -> str:
    return _as_utc(review_at).date().isoformat()


def _active_plan_for_case(db: Session, case_id: str) -> Optional[Plan]:
    return (
        db.execute(
            select(Plan)
            .where(Plan.case_id == case_id, Plan.status.in_(["draft", "active"]))
            .order_by(Plan.created_at.asc(), Plan.id.asc())
        )
        .scalars()
        .first()
    )


def generate_work_items_for_case(db: Session, case_id: str, *, now: Optional[datetime] = None) -> List[ComputedWorkItem]:
    case = case_engine_service._require_case(db, case_id)
    current = _as_utc(now or _now())
    computed = case_engine_service.compute_case_state(db, case_id, now=current)
    active_plan = _active_plan_for_case(db, case_id)

    items: List[ComputedWorkItem] = []

    if computed.computed_sla_breached and case.status != "resolved":
        items.append(
            ComputedWorkItem(
                case_id=case.id,
                business_id=case.business_id,
                type="SLA_BREACH",
                priority=100,
                due_at=current,
                idempotency_key=f"{case.id}:SLA_BREACH",
            )
        )

    if computed.computed_plan_overdue:
        due_at = _as_utc(active_plan.created_at) + timedelta(days=14) if active_plan else current
        items.append(
            ComputedWorkItem(
                case_id=case.id,
                business_id=case.business_id,
                type="PLAN_OVERDUE",
                priority=90,
                due_at=due_at,
                idempotency_key=f"{case.id}:PLAN_OVERDUE",
            )
        )

    if computed.computed_open_signal_count_30d > 0 and active_plan is None:
        items.append(
            ComputedWorkItem(
                case_id=case.id,
                business_id=case.business_id,
                type="NO_PLAN",
                priority=70,
                due_at=_as_utc(case.opened_at) + timedelta(days=3),
                idempotency_key=f"{case.id}:NO_PLAN",
            )
        )

    if case.severity in {"high", "critical"} and case.status == "open":
        items.append(
            ComputedWorkItem(
                case_id=case.id,
                business_id=case.business_id,
                type="HIGH_SEVERITY_TRIAGE",
                priority=80,
                due_at=_as_utc(case.opened_at) + timedelta(days=1),
                idempotency_key=f"{case.id}:HIGH_SEVERITY_TRIAGE",
            )
        )

    if case.next_review_at and current >= _as_utc(case.next_review_at):
        items.append(
            ComputedWorkItem(
                case_id=case.id,
                business_id=case.business_id,
                type="REVIEW_DUE",
                priority=60,
                due_at=_as_utc(case.next_review_at),
                idempotency_key=f"{case.id}:REVIEW_DUE:{_review_date_bucket(case.next_review_at)}",
            )
        )

    if case.assigned_to is None and case.status != "resolved":
        items.append(
            ComputedWorkItem(
                case_id=case.id,
                business_id=case.business_id,
                type="UNASSIGNED_CASE",
                priority=50,
                due_at=None,
                idempotency_key=f"{case.id}:UNASSIGNED",
            )
        )

    return sorted(items, key=lambda row: (-row.priority, row.due_at or datetime.max.replace(tzinfo=timezone.utc), row.type, row.idempotency_key))


def materialize_work_items_for_case(db: Session, case_id: str, *, now: Optional[datetime] = None) -> List[WorkItem]:
    current = _as_utc(now or _now())
    computed_items = generate_work_items_for_case(db, case_id, now=current)
    computed_by_key = {item.idempotency_key: item for item in computed_items}

    existing_items = (
        db.execute(select(WorkItem).where(WorkItem.case_id == case_id).order_by(WorkItem.created_at.asc(), WorkItem.id.asc()))
        .scalars()
        .all()
    )
    existing_by_key = {item.idempotency_key: item for item in existing_items}

    for key, computed in computed_by_key.items():
        existing = existing_by_key.get(key)
        if existing is None:
            row = WorkItem(
                case_id=computed.case_id,
                business_id=computed.business_id,
                type=computed.type,
                priority=computed.priority,
                status="open",
                due_at=computed.due_at,
                idempotency_key=computed.idempotency_key,
            )
            db.add(row)
            case_engine_service._emit_case_event(db, computed.case_id, "WORK_ITEM_CREATED", {"work_item_type": computed.type, "idempotency_key": computed.idempotency_key})
            continue

        if existing.status in {"open", "snoozed"}:
            existing.priority = computed.priority
            existing.due_at = computed.due_at

    for key, existing in existing_by_key.items():
        if key in computed_by_key:
            continue
        if existing.status in {"open", "snoozed"}:
            existing.status = "completed"
            existing.resolved_at = current
            case_engine_service._emit_case_event(
                db,
                existing.case_id,
                "WORK_ITEM_AUTO_RESOLVED",
                {"work_item_id": existing.id, "idempotency_key": existing.idempotency_key, "reason": "AUTO_RESOLVED"},
            )

    db.flush()
    return (
        db.execute(select(WorkItem).where(WorkItem.case_id == case_id).order_by(WorkItem.created_at.asc(), WorkItem.id.asc()))
        .scalars()
        .all()
    )


def list_work_items(
    db: Session,
    *,
    business_id: str,
    status: Optional[str],
    priority_gte: Optional[int],
    due_before: Optional[datetime],
    assigned_only: bool,
    case_severity_gte: Optional[str],
    sort: str,
) -> List[dict]:
    case_engine_service._require_business(db, business_id)
    stmt = select(WorkItem, Case).join(Case, Case.id == WorkItem.case_id).where(WorkItem.business_id == business_id)

    if status:
        stmt = stmt.where(WorkItem.status == status)
    if priority_gte is not None:
        stmt = stmt.where(WorkItem.priority >= priority_gte)
    if due_before is not None:
        stmt = stmt.where(WorkItem.due_at.is_not(None), WorkItem.due_at <= due_before)
    if assigned_only:
        stmt = stmt.where(Case.assigned_to.is_not(None))
    if case_severity_gte:
        rank = SEVERITY_ORDER.index(case_severity_gte) if case_severity_gte in SEVERITY_ORDER else 0
        allowed = SEVERITY_ORDER[rank:]
        stmt = stmt.where(Case.severity.in_(allowed))

    if sort == "due_at":
        stmt = stmt.order_by(WorkItem.due_at.is_(None).asc(), WorkItem.due_at.asc(), WorkItem.priority.desc(), WorkItem.created_at.asc(), WorkItem.id.asc())
    elif sort == "created_at":
        stmt = stmt.order_by(WorkItem.created_at.asc(), WorkItem.priority.desc(), WorkItem.due_at.is_(None).asc(), WorkItem.due_at.asc(), WorkItem.id.asc())
    else:
        stmt = stmt.order_by(WorkItem.priority.desc(), WorkItem.due_at.is_(None).asc(), WorkItem.due_at.asc(), WorkItem.created_at.asc(), WorkItem.id.asc())

    rows = db.execute(stmt).all()
    return [
        {
            "id": work.id,
            "case_id": work.case_id,
            "business_id": work.business_id,
            "type": work.type,
            "priority": work.priority,
            "status": work.status,
            "due_at": work.due_at,
            "snoozed_until": work.snoozed_until,
            "created_at": work.created_at,
            "updated_at": work.updated_at,
            "resolved_at": work.resolved_at,
            "idempotency_key": work.idempotency_key,
            "case_severity": case.severity,
            "case_domain": case.domain,
            "assigned_to": case.assigned_to,
        }
        for work, case in rows
    ]


def complete_work_item(db: Session, work_item_id: str) -> WorkItem:
    row = _require_work_item(db, work_item_id)
    if row.status == "completed":
        return row
    row.status = "completed"
    row.resolved_at = _now()
    case_engine_service._emit_case_event(db, row.case_id, "WORK_ITEM_COMPLETED", {"work_item_id": row.id, "type": row.type})
    return row


def snooze_work_item(db: Session, work_item_id: str, *, snoozed_until: datetime) -> WorkItem:
    row = _require_work_item(db, work_item_id)
    row.status = "snoozed"
    row.snoozed_until = _as_utc(snoozed_until)
    case_engine_service._emit_case_event(
        db,
        row.case_id,
        "WORK_ITEM_SNOOZED",
        {"work_item_id": row.id, "type": row.type, "snoozed_until": row.snoozed_until.isoformat()},
    )
    return row
