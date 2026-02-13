from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_membership
from backend.app.db import get_db
from backend.app.models import User
from backend.app.scenarios.runner import ScenarioRunner
from backend.app.scenarios.models import ScenarioResetRequest, ScenarioSeedRequest


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
_runner = ScenarioRunner()


@router.get("/catalog")
def get_catalog():
    return {
        "scenarios": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "tags": list(item.tags),
                "parameters": item.parameters or {},
            }
            for item in _runner.list_scenarios()
        ]
    }


@router.post("/seed")
def seed_scenario(
    req: ScenarioSeedRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_membership(db, req.business_id, user, min_role="staff")
    try:
        return _runner.seed_business(db, req.business_id, req.scenario_id, req.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reset")
def reset_scenario(
    req: ScenarioResetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_membership(db, req.business_id, user, min_role="staff")
    try:
        return _runner.reset_business(db, req.business_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
