from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Business, RawEvent, TxnCategorization
from backend.app.services.integration_connection_service import list_connections
from backend.app.services.integration_run_service import list_runs
from backend.app.services.posted_txn_service import current_raw_events

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class ConnectionDiagOut(BaseModel):
    provider: str
    status: str
    is_enabled: bool
    last_sync_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error: Optional[dict] = None
    provider_cursor: Optional[str] = None
    last_ingested_source_event_id: Optional[str] = None
    last_processed_source_event_id: Optional[str] = None
    processing_stale: bool


class ReconcileOut(BaseModel):
    business_id: str
    counts: dict
    latest_markers: dict
    connections: list[ConnectionDiagOut]


class IntegrationRunOut(BaseModel):
    id: str
    provider: Optional[str] = None
    run_type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    before_counts: Optional[dict] = None
    after_counts: Optional[dict] = None
    detail: Optional[dict] = None

    class Config:
        from_attributes = True


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


@router.get("/reconcile/{business_id}", response_model=ReconcileOut)
def reconcile(business_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)

    raw_total = int(
        db.execute(select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)).scalar_one()
    )
    posted_total = len(current_raw_events(db, business_id))
    categorized_total = int(
        db.execute(
            select(func.count()).select_from(TxnCategorization).where(TxnCategorization.business_id == business_id)
        ).scalar_one()
    )

    latest_event = db.execute(
        select(RawEvent)
        .where(RawEvent.business_id == business_id)
        .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
        .limit(1)
    ).scalar_one_or_none()

    connections = []
    for conn in list_connections(db, business_id):
        processing_stale = bool(
            conn.last_ingested_source_event_id
            and conn.last_processed_source_event_id != conn.last_ingested_source_event_id
        )
        connections.append(
            ConnectionDiagOut(
                provider=conn.provider,
                status=conn.status,
                is_enabled=conn.is_enabled,
                last_sync_at=conn.last_sync_at,
                last_success_at=conn.last_success_at,
                last_error_at=conn.last_error_at,
                last_error=conn.last_error,
                provider_cursor=conn.provider_cursor,
                last_ingested_source_event_id=conn.last_ingested_source_event_id,
                last_processed_source_event_id=conn.last_processed_source_event_id,
                processing_stale=processing_stale,
            )
        )

    return ReconcileOut(
        business_id=business_id,
        counts={
            "raw_events_total": raw_total,
            "posted_txns_total": posted_total,
            "categorized_txns_total": categorized_total,
        },
        latest_markers={
            "raw_event_occurred_at": None if not latest_event else latest_event.occurred_at,
            "raw_event_source_event_id": None if not latest_event else latest_event.source_event_id,
        },
        connections=connections,
    )


@router.get("/audit/{business_id}", response_model=list[IntegrationRunOut])
def audit_runs(business_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    return list_runs(db, business_id, limit=10)
