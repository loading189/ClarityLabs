from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from backend.app.api.deps import get_current_user, require_membership, require_membership_dep
from backend.app.db import get_db
from backend.app.models import ActionItem, ActionStateEvent, Business, BusinessMembership, Plan, User
from backend.app.services.actions_service import (
    assign_action,
    create_action_from_signal,
    generate_actions_for_business,
    list_actions,
    resolve_action,
    snooze_action,
)


router = APIRouter(prefix="/api/actions", tags=["actions"])


class ActionItemOut(BaseModel):
    id: str
    business_id: str
    action_type: str
    title: str
    summary: str
    priority: int
    status: str
    created_at: datetime
    updated_at: datetime
    due_at: Optional[datetime]
    source_signal_id: Optional[str]
    evidence_json: Optional[dict]
    rationale_json: Optional[dict]
    resolution_reason: Optional[str]
    resolution_note: Optional[str]
    resolution_meta_json: Optional[dict]
    resolved_at: Optional[datetime]
    assigned_to_user_id: Optional[str]
    resolved_by_user_id: Optional[str]
    snoozed_until: Optional[datetime]
    idempotency_key: str
    plan_id: Optional[str] = None

    class Config:
        from_attributes = True


class ActionListOut(BaseModel):
    actions: list[ActionItemOut]
    summary: dict


class ActionRefreshOut(ActionListOut):
    created_count: int
    updated_count: int
    suppressed_count: int
    suppression_reasons: dict[str, int]


class ActionResolveIn(BaseModel):
    status: str
    resolution_reason: Optional[str] = None
    resolution_note: Optional[str] = None
    resolution_meta_json: Optional[dict] = None


class ActionSnoozeIn(BaseModel):
    until: datetime
    reason: Optional[str] = None
    note: Optional[str] = None


class ActionAssignIn(BaseModel):
    assigned_to_user_id: Optional[str] = None


class ActionStateEventOut(BaseModel):
    id: str
    action_id: str
    actor_user_id: str
    actor_email: Optional[str]
    actor_name: Optional[str]
    from_status: str
    to_status: str
    reason: Optional[str]
    note: Optional[str]
    created_at: datetime


class ActionFromSignalIn(BaseModel):
    signal_id: str


class ActionFromSignalOut(BaseModel):
    action_id: str
    created: bool
    linked_signal_id: str


class ActionTriageUserOut(BaseModel):
    id: str
    email: str
    name: Optional[str]


class ActionTriageItemOut(BaseModel):
    id: str
    business_id: str
    business_name: str
    action_type: str
    title: str
    summary: str
    priority: int
    status: str
    created_at: datetime
    due_at: Optional[datetime]
    source_signal_id: Optional[str]
    evidence_json: Optional[dict]
    rationale_json: Optional[dict]
    resolution_reason: Optional[str]
    resolution_note: Optional[str]
    resolution_meta_json: Optional[dict]
    resolved_at: Optional[datetime]
    assigned_to_user_id: Optional[str]
    resolved_by_user_id: Optional[str]
    snoozed_until: Optional[datetime]
    assigned_to_user: Optional[ActionTriageUserOut]
    plan_id: Optional[str] = None


class ActionTriageSummaryOut(BaseModel):
    by_status: dict
    by_business: list[dict]


class ActionTriageOut(BaseModel):
    actions: list[ActionTriageItemOut]
    summary: ActionTriageSummaryOut


def _plan_id_map(db: Session, action_ids: list[str]) -> dict[str, str]:
    if not action_ids:
        return {}
    rows = (
        db.execute(
            select(Plan.id, Plan.source_action_id).where(Plan.source_action_id.in_(action_ids))
        )
        .all()
    )
    return {source_action_id: plan_id for plan_id, source_action_id in rows if source_action_id}


def _serialize_actions(db: Session, actions: list[ActionItem]) -> list[ActionItemOut]:
    plan_map = _plan_id_map(db, [action.id for action in actions])
    payloads: list[ActionItemOut] = []
    for action in actions:
        plan_id = plan_map.get(action.id)
        payloads.append(ActionItemOut.model_validate(action).model_copy(update={"plan_id": plan_id}))
    return payloads


@router.get("/{business_id}", response_model=ActionListOut, dependencies=[Depends(require_membership_dep())])
def get_actions(
    business_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    actions, summary = list_actions(db, business_id, status=status, limit=limit, offset=offset)
    return {"actions": _serialize_actions(db, actions), "summary": summary}


@router.post(
    "/{business_id}/refresh",
    response_model=ActionRefreshOut,
    dependencies=[Depends(require_membership_dep(min_role="advisor"))],
)
def refresh_actions(
    business_id: str,
    db: Session = Depends(get_db),
):
    result = generate_actions_for_business(db, business_id)
    db.commit()
    actions, summary = list_actions(db, business_id, status="open", limit=50, offset=0)
    return {
        "actions": _serialize_actions(db, actions),
        "summary": summary,
        "created_count": result.created_count,
        "updated_count": result.updated_count,
        "suppressed_count": result.suppressed_count,
        "suppression_reasons": result.suppression_reasons,
    }


@router.post(
    "/{business_id}/from_signal",
    response_model=ActionFromSignalOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def create_action_for_signal(
    business_id: str,
    req: ActionFromSignalIn,
    db: Session = Depends(get_db),
):
    try:
        action, created = create_action_from_signal(db, business_id, req.signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    db.refresh(action)
    return ActionFromSignalOut(action_id=action.id, created=created, linked_signal_id=req.signal_id)


@router.post(
    "/{business_id}/{action_id}/resolve",
    response_model=ActionItemOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def resolve_action_item(
    business_id: str,
    action_id: str,
    req: ActionResolveIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = resolve_action(
            db,
            business_id,
            action_id,
            status=req.status,
            resolution_reason=req.resolution_reason,
            resolution_note=req.resolution_note,
            resolution_meta_json=req.resolution_meta_json,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "not found" in message else 400, message) from exc
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/{business_id}/{action_id}/snooze",
    response_model=ActionItemOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def snooze_action_item(
    business_id: str,
    action_id: str,
    req: ActionSnoozeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = snooze_action(
            db,
            business_id,
            action_id,
            until=req.until,
            reason=req.reason,
            note=req.note,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "not found" in message else 400, message) from exc
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/{business_id}/{action_id}/assign",
    response_model=ActionItemOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def assign_action_item(
    business_id: str,
    action_id: str,
    req: ActionAssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = assign_action(
            db,
            business_id,
            action_id,
            assigned_to_user_id=req.assigned_to_user_id,
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "not found" in message else 400, message) from exc
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/{business_id}/{action_id}/events",
    response_model=list[ActionStateEventOut],
    dependencies=[Depends(require_membership_dep())],
)
def list_action_events(
    business_id: str,
    action_id: str,
    db: Session = Depends(get_db),
):
    action = db.get(ActionItem, action_id)
    if not action or action.business_id != business_id:
        raise HTTPException(status_code=404, detail="action not found")
    rows = (
        db.execute(
            select(ActionStateEvent, User)
            .join(User, ActionStateEvent.actor_user_id == User.id)
            .where(ActionStateEvent.action_id == action_id)
            .order_by(ActionStateEvent.created_at.desc(), ActionStateEvent.id.desc())
        )
        .all()
    )
    return [
        ActionStateEventOut(
            id=event.id,
            action_id=event.action_id,
            actor_user_id=event.actor_user_id,
            actor_email=actor.email,
            actor_name=actor.name,
            from_status=event.from_status,
            to_status=event.to_status,
            reason=event.reason,
            note=event.note,
            created_at=event.created_at,
        )
        for event, actor in rows
    ]


@router.get("/{business_id}/triage", response_model=ActionTriageOut)
def triage_actions(
    business_id: str,
    status: Optional[str] = Query(default=None),
    assigned: str = Query(default="any", pattern="^(me|unassigned|any)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if business_id != "all":
        require_membership(db, business_id, user)
        business_ids = [business_id]
    else:
        membership_rows = (
            db.execute(
                select(BusinessMembership.business_id).where(BusinessMembership.user_id == user.id)
            )
            .scalars()
            .all()
        )
        business_ids = membership_rows
    if not business_ids:
        return ActionTriageOut(actions=[], summary=ActionTriageSummaryOut(by_status={}, by_business=[]))

    assigned_user = aliased(User)
    stmt = (
        select(ActionItem, Business, assigned_user)
        .join(Business, ActionItem.business_id == Business.id)
        .outerjoin(assigned_user, ActionItem.assigned_to_user_id == assigned_user.id)
        .where(ActionItem.business_id.in_(business_ids))
    )
    if status:
        stmt = stmt.where(ActionItem.status == status)
    if assigned == "me":
        stmt = stmt.where(ActionItem.assigned_to_user_id == user.id)
    elif assigned == "unassigned":
        stmt = stmt.where(ActionItem.assigned_to_user_id.is_(None))
    stmt = stmt.order_by(ActionItem.priority.desc(), ActionItem.created_at.desc(), ActionItem.id.desc())

    rows = db.execute(stmt).all()
    plan_map = _plan_id_map(db, [row[0].id for row in rows])
    actions = []
    for action, biz, assigned_row in rows:
        plan_id = plan_map.get(action.id)
        assigned_payload = None
        if assigned_row:
            assigned_payload = ActionTriageUserOut(
                id=assigned_row.id,
                email=assigned_row.email,
                name=assigned_row.name,
            )
        actions.append(
            ActionTriageItemOut(
                id=action.id,
                business_id=action.business_id,
                business_name=biz.name,
                action_type=action.action_type,
                title=action.title,
                summary=action.summary,
                priority=action.priority,
                status=action.status,
                created_at=action.created_at,
                due_at=action.due_at,
                source_signal_id=action.source_signal_id,
                evidence_json=action.evidence_json,
                rationale_json=action.rationale_json,
                resolution_reason=action.resolution_reason,
                resolution_note=action.resolution_note,
                resolution_meta_json=action.resolution_meta_json,
                resolved_at=action.resolved_at,
                assigned_to_user_id=action.assigned_to_user_id,
                resolved_by_user_id=action.resolved_by_user_id,
                snoozed_until=action.snoozed_until,
                assigned_to_user=assigned_payload,
                plan_id=plan_id,
            )
        )

    summary_rows = (
        db.execute(
            select(ActionItem.status, func.count())
            .where(ActionItem.business_id.in_(business_ids))
            .group_by(ActionItem.status)
        )
        .all()
    )
    by_status = {row[0]: int(row[1]) for row in summary_rows}
    by_business_rows = (
        db.execute(
            select(Business.id, Business.name, ActionItem.status, func.count())
            .join(ActionItem, ActionItem.business_id == Business.id)
            .where(ActionItem.business_id.in_(business_ids))
            .group_by(Business.id, Business.name, ActionItem.status)
        )
        .all()
    )
    business_map: dict[str, dict] = {}
    for biz_id, biz_name, row_status, count in by_business_rows:
        entry = business_map.setdefault(
            biz_id,
            {"business_id": biz_id, "business_name": biz_name, "counts": {}},
        )
        entry["counts"][row_status] = int(count)
    summary = ActionTriageSummaryOut(by_status=by_status, by_business=list(business_map.values()))
    return ActionTriageOut(actions=actions, summary=summary)
