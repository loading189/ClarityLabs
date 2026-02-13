from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_membership_dep
from backend.app.db import get_db
from backend.app.models import BusinessMembership, User
from backend.app.services.plan_service import (
    PLAN_CONDITION_DIRECTIONS,
    PLAN_CONDITION_TYPES,
    PLAN_OBSERVATION_VERDICTS,
    PLAN_STATUSES,
    activate_plan,
    add_plan_note,
    assign_plan,
    close_plan,
    create_plan_from_action,
    create_plan,
    get_plan_detail,
    list_plans,
    list_plan_summaries,
    refresh_plan,
)


router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanConditionIn(BaseModel):
    type: str
    signal_id: Optional[str] = None
    metric_key: Optional[str] = None
    baseline_window_days: int = Field(..., ge=0)
    evaluation_window_days: int = Field(..., ge=1)
    threshold: Optional[float] = None
    direction: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in PLAN_CONDITION_TYPES:
            raise ValueError("invalid condition type")
        return value

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, value: str) -> str:
        if value not in PLAN_CONDITION_DIRECTIONS:
            raise ValueError("invalid condition direction")
        return value


class PlanCreateIn(BaseModel):
    business_id: str
    title: str = Field(..., min_length=1, max_length=200)
    intent: str = Field(..., min_length=1, max_length=4000)
    source_action_id: Optional[str] = None
    primary_signal_id: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    conditions: List[PlanConditionIn] = Field(default_factory=list, min_length=1)


class PlanAssignIn(BaseModel):
    assigned_to_user_id: Optional[str] = None


class PlanNoteIn(BaseModel):
    note: str = Field(..., min_length=1, max_length=4000)


class PlanCloseIn(BaseModel):
    outcome: str
    note: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, value: str) -> str:
        if value not in {"succeeded", "failed", "canceled"}:
            raise ValueError("invalid outcome")
        return value


class PlanConditionOut(BaseModel):
    id: str
    plan_id: str
    type: str
    signal_id: Optional[str]
    metric_key: Optional[str]
    baseline_window_days: int
    evaluation_window_days: int
    threshold: Optional[float]
    direction: str
    created_at: datetime

    class Config:
        from_attributes = True


class PlanObservationOut(BaseModel):
    id: str
    plan_id: str
    observed_at: datetime
    evaluation_start: date
    evaluation_end: date
    signal_state: Optional[str]
    metric_value: Optional[float]
    metric_baseline: Optional[float]
    metric_delta: Optional[float]
    verdict: str
    evidence_json: dict
    created_at: datetime

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, value: str) -> str:
        if value not in PLAN_OBSERVATION_VERDICTS:
            raise ValueError("invalid verdict")
        return value

    class Config:
        from_attributes = True


class PlanStateEventOut(BaseModel):
    id: str
    plan_id: str
    actor_user_id: str
    event_type: str
    from_status: Optional[str]
    to_status: Optional[str]
    note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PlanOut(BaseModel):
    id: str
    business_id: str
    created_by_user_id: str
    assigned_to_user_id: Optional[str]
    title: str
    intent: str
    status: str
    created_at: datetime
    updated_at: datetime
    activated_at: Optional[datetime]
    closed_at: Optional[datetime]
    source_action_id: Optional[str]
    primary_signal_id: Optional[str]
    idempotency_key: Optional[str]

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in PLAN_STATUSES:
            raise ValueError("invalid plan status")
        return value

    class Config:
        from_attributes = True


class PlanDetailOut(BaseModel):
    plan: PlanOut
    conditions: List[PlanConditionOut]
    latest_observation: Optional[PlanObservationOut]
    observations: List[PlanObservationOut]
    state_events: List[PlanStateEventOut]


class PlanRefreshOut(BaseModel):
    observation: PlanObservationOut
    success_candidate: bool


class PlanSummaryIn(BaseModel):
    plan_ids: List[str] = Field(default_factory=list)


class PlanSummaryOut(BaseModel):
    id: str
    business_id: str
    title: str
    status: str
    assigned_to_user_id: Optional[str]
    latest_observation: Optional[PlanObservationOut]

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in PLAN_STATUSES:
            raise ValueError("invalid plan status")
        return value


class PlanFromActionIn(BaseModel):
    action_id: str


class PlanFromActionOut(BaseModel):
    plan_id: str
    created: bool


@router.post("", response_model=PlanDetailOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_plan(
    req: PlanCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = create_plan(
        db,
        business_id=req.business_id,
        created_by_user_id=user.id,
        title=req.title,
        intent=req.intent,
        source_action_id=req.source_action_id,
        primary_signal_id=req.primary_signal_id,
        assigned_to_user_id=req.assigned_to_user_id,
        idempotency_key=req.idempotency_key,
        conditions=[condition.model_dump() for condition in req.conditions],
    )
    db.commit()
    plan, conditions, latest_observation, observations, events = get_plan_detail(db, req.business_id, plan.id)
    return PlanDetailOut(
        plan=PlanOut.model_validate(plan),
        conditions=[PlanConditionOut.model_validate(condition) for condition in conditions],
        latest_observation=PlanObservationOut.model_validate(latest_observation) if latest_observation else None,
        observations=[PlanObservationOut.model_validate(observation) for observation in observations],
        state_events=[PlanStateEventOut.model_validate(event) for event in events],
    )


@router.post("/{business_id}/from_action", response_model=PlanFromActionOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_plan_from_action(
    business_id: str,
    req: PlanFromActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan_id, created = create_plan_from_action(
        db,
        business_id=business_id,
        action_id=req.action_id,
        actor_user_id=user.id,
    )
    db.commit()
    return PlanFromActionOut(plan_id=plan_id, created=created)


@router.get("", response_model=List[PlanOut], dependencies=[Depends(require_membership_dep())])
def get_plans(
    business_id: str = Query(...),
    status: Optional[str] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    source_action_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    plans = list_plans(
        db,
        business_id,
        status=status,
        assigned_to_user_id=assigned_to,
        source_action_id=source_action_id,
    )
    return [PlanOut.model_validate(plan) for plan in plans]


@router.get("/{plan_id}", response_model=PlanDetailOut, dependencies=[Depends(require_membership_dep())])
def get_plan(
    plan_id: str,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    plan, conditions, latest_observation, observations, events = get_plan_detail(db, business_id, plan_id)
    return PlanDetailOut(
        plan=PlanOut.model_validate(plan),
        conditions=[PlanConditionOut.model_validate(condition) for condition in conditions],
        latest_observation=PlanObservationOut.model_validate(latest_observation) if latest_observation else None,
        observations=[PlanObservationOut.model_validate(observation) for observation in observations],
        state_events=[PlanStateEventOut.model_validate(event) for event in events],
    )


@router.post("/{plan_id}/activate", response_model=PlanDetailOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_activate_plan(
    plan_id: str,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    activate_plan(db, business_id, plan_id, user.id)
    db.commit()
    plan, conditions, latest_observation, observations, events = get_plan_detail(db, business_id, plan_id)
    return PlanDetailOut(
        plan=PlanOut.model_validate(plan),
        conditions=[PlanConditionOut.model_validate(condition) for condition in conditions],
        latest_observation=PlanObservationOut.model_validate(latest_observation) if latest_observation else None,
        observations=[PlanObservationOut.model_validate(observation) for observation in observations],
        state_events=[PlanStateEventOut.model_validate(event) for event in events],
    )


@router.post("/{plan_id}/assign", response_model=PlanDetailOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_assign_plan(
    plan_id: str,
    req: PlanAssignIn,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assign_plan(db, business_id, plan_id, user.id, req.assigned_to_user_id)
    db.commit()
    plan, conditions, latest_observation, observations, events = get_plan_detail(db, business_id, plan_id)
    return PlanDetailOut(
        plan=PlanOut.model_validate(plan),
        conditions=[PlanConditionOut.model_validate(condition) for condition in conditions],
        latest_observation=PlanObservationOut.model_validate(latest_observation) if latest_observation else None,
        observations=[PlanObservationOut.model_validate(observation) for observation in observations],
        state_events=[PlanStateEventOut.model_validate(event) for event in events],
    )


@router.post("/{plan_id}/note", response_model=PlanDetailOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_note_plan(
    plan_id: str,
    req: PlanNoteIn,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    add_plan_note(db, business_id, plan_id, user.id, req.note)
    db.commit()
    plan, conditions, latest_observation, observations, events = get_plan_detail(db, business_id, plan_id)
    return PlanDetailOut(
        plan=PlanOut.model_validate(plan),
        conditions=[PlanConditionOut.model_validate(condition) for condition in conditions],
        latest_observation=PlanObservationOut.model_validate(latest_observation) if latest_observation else None,
        observations=[PlanObservationOut.model_validate(observation) for observation in observations],
        state_events=[PlanStateEventOut.model_validate(event) for event in events],
    )


@router.post("/{plan_id}/refresh", response_model=PlanRefreshOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_refresh_plan(
    plan_id: str,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    result = refresh_plan(db, business_id, plan_id)
    db.commit()
    db.refresh(result.observation)
    return PlanRefreshOut(
        observation=PlanObservationOut.model_validate(result.observation),
        success_candidate=result.success_candidate,
    )


@router.post("/{plan_id}/close", response_model=PlanDetailOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_close_plan(
    plan_id: str,
    req: PlanCloseIn,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    close_plan(db, business_id, plan_id, user.id, outcome=req.outcome, note=req.note)
    db.commit()
    plan, conditions, latest_observation, observations, events = get_plan_detail(db, business_id, plan_id)
    return PlanDetailOut(
        plan=PlanOut.model_validate(plan),
        conditions=[PlanConditionOut.model_validate(condition) for condition in conditions],
        latest_observation=PlanObservationOut.model_validate(latest_observation) if latest_observation else None,
        observations=[PlanObservationOut.model_validate(observation) for observation in observations],
        state_events=[PlanStateEventOut.model_validate(event) for event in events],
    )


@router.post("/summary", response_model=List[PlanSummaryOut])
def post_plan_summaries(
    req: PlanSummaryIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan_ids = [plan_id for plan_id in req.plan_ids if plan_id]
    if not plan_ids:
        return []
    summaries = list_plan_summaries(db, plan_ids)
    if not summaries:
        return []
    business_ids = {plan.business_id for plan, _ in summaries}
    memberships = (
        db.execute(
            select(BusinessMembership.business_id).where(
                BusinessMembership.user_id == user.id,
                BusinessMembership.business_id.in_(business_ids),
            )
        )
        .scalars()
        .all()
    )
    if business_ids - set(memberships):
        raise HTTPException(status_code=403, detail="membership required")
    return [
        PlanSummaryOut(
            id=plan.id,
            business_id=plan.business_id,
            title=plan.title,
            status=plan.status,
            assigned_to_user_id=plan.assigned_to_user_id,
            latest_observation=PlanObservationOut.model_validate(observation) if observation else None,
        )
        for plan, observation in summaries
    ]
