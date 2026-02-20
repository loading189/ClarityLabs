from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services import case_engine_service

router = APIRouter(prefix="/api/cases", tags=["cases"])


class CaseStatusIn(BaseModel):
    status: str
    reason: Optional[str] = None
    actor: Optional[str] = None


class CaseNoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    actor: Optional[str] = None


class LedgerAnchorIn(BaseModel):
    anchor_key: str
    payload_json: Optional[Dict[str, Any]] = None


class RecomputeIn(BaseModel):
    apply: bool = False
    limit: Optional[int] = Field(default=None, ge=1)


class AssignCaseIn(BaseModel):
    assigned_to: Optional[str] = None
    reason: Optional[str] = None


class ScheduleReviewIn(BaseModel):
    next_review_at: Optional[datetime] = None


@router.get("", dependencies=[Depends(require_membership_dep())])
def list_cases(
    business_id: str = Query(...),
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    sort: str = Query(default="activity"),
    sla_breached: Optional[bool] = Query(default=None),
    no_plan: Optional[bool] = Query(default=None),
    plan_overdue: Optional[bool] = Query(default=None),
    opened_since: Optional[datetime] = Query(default=None),
    severity_gte: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return case_engine_service.list_cases(
        db,
        business_id=business_id,
        status=status,
        severity=severity,
        domain=domain,
        q=q,
        sort=sort,
        sla_breached=sla_breached,
        no_plan=no_plan,
        plan_overdue=plan_overdue,
        opened_since=opened_since,
        severity_gte=severity_gte,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}", dependencies=[Depends(require_membership_dep())])
def get_case(case_id: str, business_id: str = Query(...), db: Session = Depends(get_db)):
    return case_engine_service.get_case_detail(db, case_id)


@router.get("/{case_id}/timeline", dependencies=[Depends(require_membership_dep())])
def get_case_timeline(case_id: str, business_id: str = Query(...), db: Session = Depends(get_db)) -> List[dict]:
    return case_engine_service.case_timeline(db, case_id)


@router.post("/{case_id}/status", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_case_status(case_id: str, req: CaseStatusIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    case_engine_service.update_case_status(db, case_id, status=req.status, reason=req.reason, actor=req.actor)
    db.commit()
    return case_engine_service.get_case_detail(db, case_id)


@router.post("/{case_id}/recompute", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_case_recompute(case_id: str, req: RecomputeIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    payload = case_engine_service.recompute_case(db, case_id, apply=req.apply)
    if req.apply:
        db.commit()
    return payload


@router.post("/recompute", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_cases_recompute(req: RecomputeIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    payload = case_engine_service.recompute_cases_for_business(db, business_id, apply=req.apply, limit=req.limit)
    if req.apply:
        db.commit()
    return payload


@router.post("/{case_id}/assign", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_case_assign(case_id: str, req: AssignCaseIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    case_engine_service.assign_case(db, case_id, assigned_to=req.assigned_to, reason=req.reason)
    db.commit()
    return case_engine_service.get_case_detail(db, case_id)


@router.post("/{case_id}/schedule-review", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_case_schedule_review(case_id: str, req: ScheduleReviewIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    case_engine_service.schedule_case_review(db, case_id, next_review_at=req.next_review_at)
    db.commit()
    return case_engine_service.get_case_detail(db, case_id)


@router.post("/{case_id}/note", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_case_note(case_id: str, req: CaseNoteIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    case_engine_service.add_case_note(db, case_id, req.text, req.actor)
    db.commit()
    return {"ok": True}


@router.post("/{case_id}/attach-ledger-anchor", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_attach_ledger_anchor(case_id: str, req: LedgerAnchorIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    case_engine_service.attach_ledger_anchor(db, case_id, req.anchor_key, req.payload_json)
    db.commit()
    return {"ok": True}


@router.post("/{case_id}/detach-ledger-anchor", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_detach_ledger_anchor(case_id: str, req: LedgerAnchorIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    case_engine_service.detach_ledger_anchor(db, case_id, req.anchor_key)
    db.commit()
    return {"ok": True}
