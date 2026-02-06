from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.integrations import get_adapter
from backend.app.models import Business, IntegrationConnection
from backend.app.services import audit_service
from backend.app.services.ingest_orchestrator import process_ingested_events


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
    connected_at: Optional[datetime]
    last_sync_at: Optional[datetime]
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
        existing.status = "connected"
        existing.connected_at = existing.connected_at or utcnow()
        existing.config_json = req.config_json
        existing.last_error = None
        db.add(existing)
        row = existing
    else:
        row = IntegrationConnection(
            business_id=business_id,
            provider=provider_key,
            status="connected",
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
    row.updated_at = utcnow()
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


@router.get("/{business_id}", response_model=list[IntegrationConnectionOut])
def list_connections(business_id: str, db: Session = Depends(get_db)):
    require_business(db, business_id)
    rows = db.execute(
        select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
    ).scalars().all()
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
            connection.last_sync_at = utcnow()
            connection.last_error = None
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
            connection.last_error = str(exc)
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
