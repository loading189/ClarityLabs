from __future__ import annotations

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


@router.get("", dependencies=[Depends(require_membership_dep())])
def list_cases(
    business_id: str = Query(...),
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    sort: str = Query(default="activity"),
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
