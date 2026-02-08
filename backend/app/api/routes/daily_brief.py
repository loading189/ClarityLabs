from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services import daily_brief_service
from backend.app.services.assistant_thread_service import AssistantMessageOut

router = APIRouter(prefix="/api/assistant/daily_brief", tags=["assistant"])


class DailyBriefPriorityPlaybookOut(BaseModel):
    id: str
    title: str
    deep_link: Optional[str] = None


class DailyBriefPriorityOut(BaseModel):
    signal_id: str
    title: str
    severity: str
    status: str
    why_now: str
    recommended_playbooks: List[DailyBriefPriorityPlaybookOut] = Field(default_factory=list)
    clear_condition_summary: str


class DailyBriefMetricsOut(BaseModel):
    health_score: float
    delta_7d: Optional[float] = None
    open_signals_count: int
    new_changes_count: int


class DailyBriefOut(BaseModel):
    business_id: str
    date: str
    generated_at: str
    headline: str
    summary_bullets: List[str]
    priorities: List[DailyBriefPriorityOut]
    metrics: DailyBriefMetricsOut
    links: Dict[str, str]


class DailyBriefPublishOut(BaseModel):
    message: AssistantMessageOut
    brief: DailyBriefOut


def _resolve_date(value: Optional[date]) -> date:
    return value or datetime.now(timezone.utc).date()


@router.get("", response_model=DailyBriefOut, dependencies=[Depends(require_membership_dep())])
def get_daily_brief(
    business_id: str = Query(...),
    date_value: Optional[date] = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    target_date = _resolve_date(date_value)
    as_of = datetime.combine(target_date, datetime.now(timezone.utc).timetz())
    brief = daily_brief_service.get_daily_brief_for_date(db, business_id, target_date, as_of)
    return brief


@router.post("/publish", response_model=DailyBriefPublishOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def publish_daily_brief(
    business_id: str = Query(...),
    date_value: Optional[date] = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    target_date = _resolve_date(date_value)
    as_of = datetime.combine(target_date, datetime.now(timezone.utc).timetz())
    row, brief = daily_brief_service.publish_daily_brief(db, business_id, target_date, as_of)
    msg = AssistantMessageOut(
        id=row.id,
        business_id=row.business_id,
        created_at=row.created_at,
        author=row.author,
        kind=row.kind,
        signal_id=row.signal_id,
        audit_id=row.audit_id,
        content_json=row.content_json or {},
    )
    return DailyBriefPublishOut(message=msg, brief=brief)
