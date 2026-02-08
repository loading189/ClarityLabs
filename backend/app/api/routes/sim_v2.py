from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_membership
from backend.app.db import get_db
from backend.app.models import User
from backend.app.sim_v2 import catalog, engine
from backend.app.sim_v2.models import SimV2ResetRequest, SimV2SeedRequest

router = APIRouter(prefix="/api/sim_v2", tags=["sim_v2"])


@router.get("/catalog")
def get_catalog():
    return catalog.catalog_payload()


@router.post("/seed")
def seed(
    req: SimV2SeedRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_membership(db, req.business_id, user, min_role="staff")
    try:
        return engine.seed(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reset")
def reset(
    req: SimV2ResetRequest | None = None,
    business_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = business_id or (req.business_id if req else None)
    if not target:
        raise HTTPException(status_code=400, detail="business_id is required")
    require_membership(db, target, user, min_role="staff")
    try:
        return engine.reset(db, target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
