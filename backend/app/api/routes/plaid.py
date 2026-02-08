from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.integrations.plaid import PlaidAdapter, plaid_environment, plaid_is_configured
from backend.app.models import IntegrationConnection
from backend.app.services import audit_service, integration_connection_service
from backend.app.services.ingest_orchestrator import process_ingested_events


router = APIRouter(prefix="/integrations/plaid", tags=["integrations"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_plaid_configured() -> None:
    if not plaid_is_configured():
        raise HTTPException(400, "Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET.")


class LinkTokenOut(BaseModel):
    link_token: str
    expiration: Optional[str] = None
    request_id: Optional[str] = None


class ExchangeTokenIn(BaseModel):
    public_token: str


class PlaidConnectionOut(BaseModel):
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
    last_ingest_counts: Optional[dict] = None
    last_error: Optional[str] = None
    plaid_item_id: Optional[str] = None
    plaid_environment: Optional[str] = None

    class Config:
        from_attributes = True


class PlaidExchangeOut(BaseModel):
    connection: PlaidConnectionOut


class PlaidSyncOut(BaseModel):
    provider: str
    inserted: int
    skipped: int
    cursor: Optional[str]
    ingest_processed: dict


@router.post(
    "/link_token/{business_id}",
    response_model=LinkTokenOut,
    dependencies=[Depends(require_membership_dep())],
)
def create_link_token(business_id: str, db: Session = Depends(get_db)):
    require_plaid_configured()
    adapter = PlaidAdapter()
    response = adapter.create_link_token(business_id=business_id)
    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="plaid_link_token_created",
        actor="system",
        reason="plaid_link",
        before=None,
        after={"environment": plaid_environment()},
    )
    db.commit()
    return LinkTokenOut(
        link_token=response.get("link_token"),
        expiration=response.get("expiration"),
        request_id=response.get("request_id"),
    )


@router.post(
    "/exchange/{business_id}",
    response_model=PlaidExchangeOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def exchange_public_token(
    business_id: str,
    req: ExchangeTokenIn,
    db: Session = Depends(get_db),
):
    require_plaid_configured()
    adapter = PlaidAdapter()
    response = adapter.exchange_public_token(public_token=req.public_token)
    access_token = response.get("access_token")
    item_id = response.get("item_id")
    if not access_token or not item_id:
        raise HTTPException(400, "Plaid exchange failed to return access_token/item_id.")

    allow_plaintext = os.getenv("PLAID_ALLOW_PLAINTEXT_TOKENS", "true").lower() == "true"
    if not allow_plaintext:
        raise HTTPException(400, "PLAID_ALLOW_PLAINTEXT_TOKENS must be true for dev storage.")

    existing = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "plaid",
        )
    ).scalar_one_or_none()

    before = None
    if existing:
        before = {
            "status": existing.status,
            "plaid_item_id": existing.plaid_item_id,
            "plaid_environment": existing.plaid_environment,
        }
        existing.status = "connected"
        existing.is_enabled = True
        existing.disconnected_at = None
        existing.connected_at = existing.connected_at or utcnow()
        existing.plaid_access_token = access_token
        existing.plaid_item_id = item_id
        existing.plaid_environment = plaid_environment()
        existing.last_cursor = None
        existing.last_cursor_at = None
        existing.last_error = None
        existing.last_error_at = None
        existing.updated_at = utcnow()
        integration_connection_service.refresh_connection_status(existing)
        row = existing
    else:
        row = IntegrationConnection(
            business_id=business_id,
            provider="plaid",
            status="connected",
            is_enabled=True,
            connected_at=utcnow(),
            plaid_access_token=access_token,
            plaid_item_id=item_id,
            plaid_environment=plaid_environment(),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    db.add(row)

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="plaid_token_exchanged",
        actor="system",
        reason="plaid_exchange",
        before=before,
        after={"plaid_item_id": item_id, "environment": plaid_environment()},
    )
    db.commit()
    db.refresh(row)
    return PlaidExchangeOut(connection=row)


@router.post(
    "/sync/{business_id}",
    response_model=PlaidSyncOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def sync_plaid(business_id: str, db: Session = Depends(get_db)):
    require_plaid_configured()
    adapter = PlaidAdapter()

    connection = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "plaid",
        )
    ).scalar_one_or_none()
    if not connection or not connection.plaid_access_token:
        raise HTTPException(404, "Plaid connection not found.")
    if not connection.is_enabled or connection.status == "disconnected":
        raise HTTPException(400, "Plaid connection disabled or disconnected.")

    before_cursor = connection.last_cursor
    try:
        result = adapter.ingest_pull(business_id=business_id, since=None, db=db)
        db.flush()
        ingest_processed = process_ingested_events(
            db,
            business_id=business_id,
            source_event_ids=list(result.source_event_ids),
        )
        integration_connection_service.mark_sync_success(connection)
        connection.last_ingest_counts = {
            "inserted": result.inserted_count,
            "skipped": result.skipped_count,
        }
        connection.updated_at = utcnow()
        db.add(connection)
        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="integration_sync",
            actor="system",
            reason="plaid_sync",
            before={"cursor": before_cursor},
            after={
                "inserted": result.inserted_count,
                "skipped": result.skipped_count,
                "cursor": connection.last_cursor,
            },
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        integration_connection_service.mark_sync_error(connection, error=str(exc))
        connection.updated_at = utcnow()
        db.add(connection)
        db.commit()
        raise

    return PlaidSyncOut(
        provider="plaid",
        inserted=result.inserted_count,
        skipped=result.skipped_count,
        cursor=connection.last_cursor,
        ingest_processed=ingest_processed,
    )
