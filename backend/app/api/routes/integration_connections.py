from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.integrations import get_adapter
from backend.app.models import Business, IntegrationConnection, RawEvent
from backend.app.services import audit_service
from backend.app.services.ingest_orchestrator import process_ingested_events
from backend.app.services import integration_connection_service


router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


class IntegrationConnectIn(BaseModel):
    config_json: Optional[dict] = None


class IntegrationConnectionOut(BaseModel):
    id: str
    business_id: str
    provider: str
    status: str
    is_enabled: bool
    connected_at: Optional[datetime]
    disconnected_at: Optional[datetime]
    last_sync_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_error_at: Optional[datetime]
    last_cursor: Optional[str] = None
    last_cursor_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None
    last_ingested_source_event_id: Optional[str] = None
    last_processed_at: Optional[datetime] = None
    last_processed_source_event_id: Optional[str] = None
    last_webhook_at: Optional[datetime] = None
    last_ingest_counts: Optional[dict] = None
    last_error: Optional[str]
    config_json: Optional[dict]

    class Config:
        from_attributes = True


class IntegrationSyncOut(BaseModel):
    provider: str
    inserted: int
    skipped: int
    source_event_ids: list[str]
    ingest_processed: dict


class IntegrationReplayIn(BaseModel):
    since: Optional[datetime] = None
    last_n: Optional[int] = None


def _dev_ops_allowed() -> bool:
    return os.getenv("DEV_INTEGRATION_OPS", "true").lower() == "true"


def _require_dev_ops() -> None:
    if not _dev_ops_allowed():
        raise HTTPException(403, "dev integration ops disabled")


@router.post("/{business_id}/{provider}/connect", response_model=IntegrationConnectionOut)
def connect_integration(
    business_id: str,
    provider: str,
    req: IntegrationConnectIn,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    provider_key = provider.strip().lower()
    existing = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider_key,
        )
    ).scalar_one_or_none()

    before = None
    if existing:
        before = {
            "status": existing.status,
            "config_json": existing.config_json,
        }
        existing.is_enabled = True
        existing.disconnected_at = None
        existing.status = "connected"
        existing.connected_at = existing.connected_at or utcnow()
        existing.config_json = req.config_json
        existing.last_error = None
        existing.last_error_at = None
        integration_connection_service.refresh_connection_status(existing)
        db.add(existing)
        row = existing
    else:
        row = IntegrationConnection(
            business_id=business_id,
            provider=provider_key,
            status="connected",
            is_enabled=True,
            connected_at=utcnow(),
            config_json=req.config_json,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(row)

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="integration_connected",
        actor="system",
        reason="dev_connect",
        before=before,
        after={
            "provider": provider_key,
            "status": "connected",
        },
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/{business_id}/{provider}/disconnect", response_model=IntegrationConnectionOut)
def disconnect_integration(
    business_id: str,
    provider: str,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    provider_key = provider.strip().lower()
    row = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider_key,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "integration not found")

    before = {"status": row.status}
    row.status = "disconnected"
    row.disconnected_at = utcnow()
    row.is_enabled = False
    row.updated_at = utcnow()
    integration_connection_service.refresh_connection_status(row)
    db.add(row)

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="integration_disconnected",
        actor="system",
        reason="dev_disconnect",
        before=before,
        after={"status": row.status},
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/{business_id}/{provider}/disable", response_model=IntegrationConnectionOut)
def disable_integration(
    business_id: str,
    provider: str,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    provider_key = provider.strip().lower()
    row = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider_key,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "integration not found")
    row.is_enabled = False
    row.updated_at = utcnow()
    integration_connection_service.refresh_connection_status(row)
    db.add(row)
    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="integration_disabled",
        actor="system",
        reason="dev_disable",
        before=None,
        after={"provider": provider_key, "status": row.status},
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/{business_id}/{provider}/enable", response_model=IntegrationConnectionOut)
def enable_integration(
    business_id: str,
    provider: str,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    provider_key = provider.strip().lower()
    row = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider_key,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "integration not found")
    row.is_enabled = True
    row.disconnected_at = None
    row.updated_at = utcnow()
    integration_connection_service.refresh_connection_status(row)
    db.add(row)
    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="integration_enabled",
        actor="system",
        reason="dev_enable",
        before=None,
        after={"provider": provider_key, "status": row.status},
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/{business_id}", response_model=list[IntegrationConnectionOut])
def list_connections(business_id: str, db: Session = Depends(get_db)):
    require_business(db, business_id)
    rows = db.execute(
        select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
    ).scalars().all()
    for row in rows:
        integration_connection_service.refresh_connection_status(row)
        db.add(row)
    db.commit()
    return rows


@router.post("/{business_id}/{provider}/sync", response_model=IntegrationSyncOut)
def sync_integration(
    business_id: str,
    provider: str,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    provider_key = provider.strip().lower()
    adapter = get_adapter(provider_key)

    connection = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider_key,
        )
    ).scalar_one_or_none()

    if connection and (not connection.is_enabled or connection.status == "disconnected"):
        raise HTTPException(400, "integration disabled or disconnected")

    since = connection.last_sync_at if connection else None
    try:
        result = adapter.ingest_pull(business_id=business_id, since=since, db=db)
        db.flush()
        ingest_processed = process_ingested_events(
            db,
            business_id=business_id,
            source_event_ids=list(result.source_event_ids),
        )
        if connection:
            integration_connection_service.mark_sync_success(connection)
            connection.last_ingest_counts = {
                "inserted": result.inserted_count,
                "skipped": result.skipped_count,
            }
            if result.source_event_ids:
                latest = db.execute(
                    select(RawEvent.occurred_at, RawEvent.source_event_id)
                    .where(
                        RawEvent.business_id == business_id,
                        RawEvent.source == provider_key,
                        RawEvent.source_event_id.in_(list(result.source_event_ids)),
                    )
                    .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
                    .limit(1)
                ).first()
                if latest:
                    connection.last_ingested_at = latest[0]
                    connection.last_ingested_source_event_id = latest[1]
            connection.updated_at = utcnow()
            db.add(connection)
        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="integration_sync",
            actor="system",
            reason="dev_sync",
            before={"provider": provider_key, "since": since.isoformat() if since else None},
            after={
                "provider": provider_key,
                "inserted": result.inserted_count,
                "skipped": result.skipped_count,
            },
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        if connection:
            integration_connection_service.mark_sync_error(connection, error=str(exc))
            connection.updated_at = utcnow()
            db.add(connection)
            db.commit()
        raise

    return IntegrationSyncOut(
        provider=provider_key,
        inserted=result.inserted_count,
        skipped=result.skipped_count,
        source_event_ids=list(result.source_event_ids),
        ingest_processed=ingest_processed,
    )


@router.post("/{business_id}/{provider}/replay", response_model=IntegrationSyncOut)
def replay_integration(
    business_id: str,
    provider: str,
    req: IntegrationReplayIn,
    db: Session = Depends(get_db),
):
    _require_dev_ops()
    require_business(db, business_id)
    provider_key = provider.strip().lower()
    adapter = get_adapter(provider_key)
    connection = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider_key,
        )
    ).scalar_one_or_none()
    if connection and (not connection.is_enabled or connection.status == "disconnected"):
        raise HTTPException(400, "integration disabled or disconnected")

    since = req.since if req.since else None
    try:
        result = adapter.ingest_pull(business_id=business_id, since=since, db=db)
        db.flush()
        ingest_processed = process_ingested_events(
            db,
            business_id=business_id,
            source_event_ids=list(result.source_event_ids),
        )
        if connection:
            integration_connection_service.mark_sync_success(connection)
            connection.last_ingest_counts = {
                "inserted": result.inserted_count,
                "skipped": result.skipped_count,
            }
            if result.source_event_ids:
                latest = db.execute(
                    select(RawEvent.occurred_at, RawEvent.source_event_id)
                    .where(
                        RawEvent.business_id == business_id,
                        RawEvent.source == provider_key,
                        RawEvent.source_event_id.in_(list(result.source_event_ids)),
                    )
                    .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
                    .limit(1)
                ).first()
                if latest:
                    connection.last_ingested_at = latest[0]
                    connection.last_ingested_source_event_id = latest[1]
            connection.updated_at = utcnow()
            db.add(connection)
        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="integration_replay",
            actor="system",
            reason="dev_replay",
            before={"provider": provider_key},
            after={
                "provider": provider_key,
                "inserted": result.inserted_count,
                "skipped": result.skipped_count,
                "since": req.since.isoformat() if req.since else None,
                "last_n": req.last_n,
            },
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        if connection:
            integration_connection_service.mark_sync_error(connection, error=str(exc))
            connection.updated_at = utcnow()
            db.add(connection)
            db.commit()
        raise

    return IntegrationSyncOut(
        provider=provider_key,
        inserted=result.inserted_count,
        skipped=result.skipped_count,
        source_event_ids=list(result.source_event_ids),
        ingest_processed=ingest_processed,
    )
