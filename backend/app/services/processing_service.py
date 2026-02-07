from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models import RawEvent, TxnCategorization
from backend.app.services.integration_connection_service import list_connections, update_status, require_business
from backend.app.services.integration_run_service import start_run, finish_run
from backend.app.services.posted_txn_service import posted_txns


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_dev() -> bool:
    return os.environ.get("ENV", "dev").lower() != "production"


def _count_raw_events(db: Session, business_id: str) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)
        ).scalar_one()
    )


def _count_categorized(db: Session, business_id: str) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(TxnCategorization).where(TxnCategorization.business_id == business_id)
        ).scalar_one()
    )


def reprocess_pipeline(
    db: Session,
    *,
    business_id: str,
    mode: str = "from_last_cursor",
    from_source_event_id: Optional[str] = None,
) -> dict:
    require_business(db, business_id)
    if mode == "from_beginning" and not _is_dev():
        return {"status": "error", "detail": "from_beginning is only allowed in dev mode"}

    before_counts = {
        "raw_events": _count_raw_events(db, business_id),
        "posted_txns": len(posted_txns(db, business_id)),
        "categorized_txns": _count_categorized(db, business_id),
    }
    run = start_run(db, business_id=business_id, run_type="reprocess", before_counts=before_counts)
    db.commit()

    processed = 0
    for posted in posted_txns(db, business_id):
        processed += 1
        _ = posted.txn

    connections = list_connections(db, business_id)
    for conn in connections:
        if mode == "from_beginning":
            conn.last_processed_source_event_id = conn.last_ingested_source_event_id
        elif mode == "from_source_event_id" and from_source_event_id:
            conn.last_processed_source_event_id = from_source_event_id
        else:
            conn.last_processed_source_event_id = conn.last_ingested_source_event_id
        update_status(conn)

    after_counts = {
        "raw_events": _count_raw_events(db, business_id),
        "posted_txns": len(posted_txns(db, business_id)),
        "categorized_txns": _count_categorized(db, business_id),
        "processed": processed,
    }
    finish_run(db, run, status="ok", after_counts=after_counts)
    db.commit()

    return {"status": "ok", "processed": processed, "counts": after_counts}
