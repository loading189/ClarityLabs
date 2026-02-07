from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import IntegrationRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_run(
    db: Session,
    *,
    business_id: str,
    run_type: str,
    provider: Optional[str] = None,
    before_counts: Optional[dict] = None,
    detail: Optional[dict] = None,
) -> IntegrationRun:
    run = IntegrationRun(
        business_id=business_id,
        run_type=run_type,
        provider=provider,
        status="in_progress",
        started_at=_now(),
        before_counts=before_counts,
        detail=detail,
    )
    db.add(run)
    db.flush()
    return run


def finish_run(
    db: Session,
    run: IntegrationRun,
    *,
    status: str,
    after_counts: Optional[dict] = None,
    detail: Optional[dict] = None,
) -> None:
    run.status = status
    run.after_counts = after_counts
    if detail:
        run.detail = detail
    run.finished_at = _now()
    db.add(run)


def list_runs(db: Session, business_id: str, limit: int = 10) -> list[IntegrationRun]:
    return db.execute(
        select(IntegrationRun)
        .where(IntegrationRun.business_id == business_id)
        .order_by(IntegrationRun.started_at.desc())
        .limit(limit)
    ).scalars().all()
