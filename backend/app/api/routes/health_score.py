from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import health_score_service
from backend.app.api.routes.changes import ChangeEventOut

router = APIRouter(prefix="/api/health_score", tags=["health_score"])


class HealthScoreContributorOut(BaseModel):
    signal_id: str
    domain: str
    status: str
    severity: str
    penalty: float
    rationale: str


class HealthScoreDomainOut(BaseModel):
    domain: Literal[
        "liquidity",
        "revenue",
        "expense",
        "timing",
        "concentration",
        "hygiene",
        "unknown",
    ]
    score: float
    penalty: float
    contributors: List[HealthScoreContributorOut]


class HealthScoreMetaOut(BaseModel):
    model_version: str
    weights: Dict[str, Any]




class HealthScoreImpactOut(BaseModel):
    signal_id: str
    domain: Optional[str] = None
    severity: Optional[str] = None
    change_type: Literal["signal_detected", "signal_resolved", "signal_status_updated"]
    estimated_penalty_delta: float
    rationale: str


class HealthScoreChangeWindowOut(BaseModel):
    since_hours: int


class HealthScoreChangeSummaryOut(BaseModel):
    headline: str
    net_estimated_delta: float
    top_drivers: List[str]


class HealthScoreChangeExplainOut(BaseModel):
    business_id: str
    computed_at: datetime
    window: HealthScoreChangeWindowOut
    changes: List[ChangeEventOut]
    impacts: List[HealthScoreImpactOut]
    summary: HealthScoreChangeSummaryOut


class HealthScoreOut(BaseModel):
    business_id: str
    score: float
    risk_score: Optional[float] = None
    attention_score: Optional[float] = None
    generated_at: datetime
    domains: List[HealthScoreDomainOut]
    contributors: List[HealthScoreContributorOut]
    meta: HealthScoreMetaOut


@router.get("", response_model=HealthScoreOut)
def get_health_score(
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        UUID(business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="business_id must be a valid UUID") from exc
    return health_score_service.compute_health_score(db, business_id)


@router.get("/explain_change", response_model=HealthScoreChangeExplainOut)
def get_health_score_change_explain(
    business_id: str = Query(...),
    since_hours: int = Query(72, ge=1, le=720),
    limit: int = Query(20, ge=1, le=20),
    db: Session = Depends(get_db),
):
    try:
        UUID(business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="business_id must be a valid UUID") from exc
    return health_score_service.explain_health_score_change(
        db,
        business_id=business_id,
        since_hours=since_hours,
        limit=limit,
    )
