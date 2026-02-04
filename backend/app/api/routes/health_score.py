from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import health_score_service

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
    return health_score_service.compute_health_score(db, business_id)
