from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.plaid import PlaidAdapter
from backend.app.models import IntegrationConnection
from backend.app.services import audit_service, integration_connection_service
from backend.app.services.ingest_orchestrator import process_ingested_events


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_plaid_sync(db: Session, business_id: str, *, adapter: PlaidAdapter | None = None) -> dict:
    plaid_adapter = adapter or PlaidAdapter()
    connection = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "plaid",
        )
    ).scalar_one_or_none()
    if not connection or not connection.plaid_access_token:
        raise RuntimeError("Plaid connection not found.")
    if not connection.is_enabled or connection.status == "disconnected":
        raise RuntimeError("Plaid connection disabled or disconnected.")

    before_cursor = connection.last_cursor
    result = plaid_adapter.ingest_pull(business_id=business_id, since=None, db=db)
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
    return {
        "provider": "plaid",
        "inserted": result.inserted_count,
        "skipped": result.skipped_count,
        "cursor": connection.last_cursor,
        "ingest_processed": ingest_processed,
    }

