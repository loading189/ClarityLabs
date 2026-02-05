from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services.assistant_plan_service import (
    PlanCreateIn,
    PlanNoteIn,
    PlanOut,
    PlanStatusIn,
    PlanStepDoneIn,
    PlanVerifyOut,
    add_plan_note,
    create_plan,
    list_plans,
    mark_plan_step_done,
    update_plan_status,
    verify_plan,
)

router = APIRouter(prefix="/api/assistant/plans", tags=["assistant"])


@router.get("", response_model=List[PlanOut])
def get_plans(
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return list_plans(db, business_id)


@router.post("", response_model=PlanOut)
def post_plan(
    req: PlanCreateIn,
    db: Session = Depends(get_db),
):
    return create_plan(db, req)


@router.post("/{plan_id}/step_done", response_model=PlanOut)
def post_plan_step_done(
    plan_id: str,
    req: PlanStepDoneIn,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return mark_plan_step_done(db, business_id, plan_id, req)


@router.post("/{plan_id}/note", response_model=PlanOut)
def post_plan_note(
    plan_id: str,
    req: PlanNoteIn,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return add_plan_note(db, business_id, plan_id, req)


@router.post("/{plan_id}/status", response_model=PlanOut)
def post_plan_status(
    plan_id: str,
    req: PlanStatusIn,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return update_plan_status(db, business_id, plan_id, req)


@router.get("/{plan_id}/verify", response_model=PlanVerifyOut)
def get_plan_verify(
    plan_id: str,
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return verify_plan(db, business_id, plan_id)
