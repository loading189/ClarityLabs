from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from backend.app.models import Business, IntegrationConnection, ProcessingEventState, RawEvent, TxnCategorization
from backend.app.norma.adapters import normalized_to_contract
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.services import audit_service, monitoring_service


PROCESSING_STATUSES = ("ingested", "normalized", "categorized", "posted", "ignored", "error")
REPROCESS_MODES = ("from_last_cursor", "from_beginning", "from_source_event_id")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


def _candidate_events_query(
    business_id: str,
    source_event_ids: Optional[Sequence[str]],
) -> Any:
    state = ProcessingEventState
    stmt = (
        select(RawEvent)
        .outerjoin(
            state,
            and_(
                RawEvent.business_id == state.business_id,
                RawEvent.source_event_id == state.source_event_id,
            ),
        )
        .where(RawEvent.business_id == business_id)
    )
    if source_event_ids:
        stmt = stmt.where(RawEvent.source_event_id.in_(list(source_event_ids)))
    else:
        stmt = stmt.where(
            or_(
                state.source_event_id.is_(None),
                state.status.in_(["ingested", "normalized", "error", "ignored"]),
            )
        )
    return stmt


def process_new_events(
    db: Session,
    business_id: str,
    source_event_ids: Optional[Sequence[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    require_business(db, business_id)

    stmt = _candidate_events_query(business_id, source_event_ids)
    events = (
        db.execute(
            stmt.order_by(RawEvent.occurred_at.asc(), RawEvent.source_event_id.asc()).limit(limit)
        )
        .scalars()
        .all()
    )
    event_ids = [event.source_event_id for event in events]

    start_audit = audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="processing_started",
        actor="system",
        reason="processing_service",
        before=None,
        after={
            "candidate_events": len(event_ids),
            "source_event_ids": list(event_ids),
        },
    )

    if not events:
        completed_audit = audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="processing_completed",
            actor="system",
            reason="processing_service",
            before=None,
            after={
                "events_total": 0,
                "processed": 0,
                "normalized": 0,
                "categorized": 0,
                "errors": 0,
                "skipped": 0,
            },
        )
        db.flush()
        return {
            "events_total": 0,
            "processed": 0,
            "normalized": 0,
            "categorized": 0,
            "errors": 0,
            "skipped": 0,
            "audit_ids": {
                "processing_started": start_audit.id,
                "processing_completed": completed_audit.id,
            },
        }

    states = (
        db.execute(
            select(ProcessingEventState).where(
                ProcessingEventState.business_id == business_id,
                ProcessingEventState.source_event_id.in_(event_ids),
            )
        )
        .scalars()
        .all()
    )
    states_by_id = {row.source_event_id: row for row in states}

    categorized_ids = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(
                TxnCategorization.business_id == business_id,
                TxnCategorization.source_event_id.in_(event_ids),
            )
        )
        .scalars()
        .all()
    )

    counts = {
        "events_total": len(event_ids),
        "processed": 0,
        "normalized": 0,
        "categorized": 0,
        "errors": 0,
        "skipped": 0,
    }

    now = utcnow()
    for event in events:
        state = states_by_id.get(event.source_event_id)
        if not state:
            state = ProcessingEventState(
                business_id=business_id,
                source_event_id=event.source_event_id,
                provider=event.source,
                status="ingested",
                first_seen_at=now,
                updated_at=now,
            )
            db.add(state)
            states_by_id[event.source_event_id] = state

        payload = event.payload if isinstance(event.payload, dict) else {}
        meta = payload.get("meta") if isinstance(payload, dict) else None
        is_removed = False
        if isinstance(meta, dict) and meta.get("is_removed") is True:
            is_removed = True
        if payload.get("type") == "plaid.transaction.removed":
            is_removed = True
        if is_removed:
            state.status = "ignored"
            state.last_processed_at = now
            state.updated_at = now
            db.add(state)
            counts["skipped"] += 1
            continue

        already_categorized = event.source_event_id in categorized_ids
        if state.status in ("categorized", "posted") and already_categorized:
            counts["skipped"] += 1
            continue
        if state.status == "normalized" and state.normalized_json and not already_categorized:
            counts["skipped"] += 1
            continue

        try:
            txn = raw_event_to_txn(event.payload, event.occurred_at, event.source_event_id)
            normalized_contract = normalized_to_contract(txn).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            state.status = "error"
            state.error_code = exc.__class__.__name__
            state.error_detail = str(exc)
            state.last_processed_at = now
            state.updated_at = now
            db.add(state)
            counts["errors"] += 1
            audit_service.log_audit_event(
                db,
                business_id=business_id,
                event_type="processing_error",
                actor="system",
                reason="raw_event_error",
                before=None,
                after={
                    "source_event_id": event.source_event_id,
                    "error_code": state.error_code,
                    "error_detail": state.error_detail,
                },
                source_event_id=event.source_event_id,
            )
            continue

        state.normalized_json = normalized_contract
        state.error_code = None
        state.error_detail = None
        if already_categorized:
            state.status = "categorized"
            counts["categorized"] += 1
        else:
            supersedes = None
            if isinstance(meta, dict):
                supersedes = meta.get("supersedes")
            if supersedes:
                existing_cat = db.execute(
                    select(TxnCategorization).where(
                        TxnCategorization.business_id == business_id,
                        TxnCategorization.source_event_id == supersedes,
                    )
                ).scalar_one_or_none()
                if existing_cat:
                    db.add(
                        TxnCategorization(
                            business_id=business_id,
                            source_event_id=event.source_event_id,
                            category_id=existing_cat.category_id,
                            confidence=existing_cat.confidence,
                            source="supersede",
                            note=f"supersedes {supersedes}",
                        )
                    )
                    categorized_ids.add(event.source_event_id)
                    state.status = "categorized"
                    counts["categorized"] += 1
                else:
                    state.status = "normalized"
                    counts["normalized"] += 1
            else:
                state.status = "normalized"
                counts["normalized"] += 1
        state.last_processed_at = now
        state.updated_at = now
        db.add(state)
        counts["processed"] += 1

    completed_audit = audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="processing_completed",
        actor="system",
        reason="processing_service",
        before=None,
        after=dict(counts),
    )
    db.flush()

    providers = {event.source for event in events}
    for provider in providers:
        latest_event = max(
            (event for event in events if event.source == provider),
            key=lambda ev: (ev.occurred_at, ev.source_event_id),
        )
        connection = db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.business_id == business_id,
                IntegrationConnection.provider == provider,
            )
        ).scalar_one_or_none()
        if connection:
            connection.last_processed_at = latest_event.occurred_at
            connection.last_processed_source_event_id = latest_event.source_event_id
            connection.updated_at = now
            db.add(connection)

    return {
        **counts,
        "audit_ids": {
            "processing_started": start_audit.id,
            "processing_completed": completed_audit.id,
        },
    }


def collect_ingestion_diagnostics(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)

    counts = dict.fromkeys(PROCESSING_STATUSES, 0)
    rows = (
        db.execute(
            select(ProcessingEventState.status, func.count())
            .where(ProcessingEventState.business_id == business_id)
            .group_by(ProcessingEventState.status)
        )
        .all()
    )
    for status, count in rows:
        counts[status] = int(count)

    errors = (
        db.execute(
            select(ProcessingEventState)
            .where(
                ProcessingEventState.business_id == business_id,
                ProcessingEventState.status == "error",
            )
            .order_by(ProcessingEventState.updated_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    connections = (
        db.execute(
            select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
        )
        .scalars()
        .all()
    )

    return {
        "status_counts": counts,
        "errors": [
            {
                "source_event_id": row.source_event_id,
                "provider": row.provider,
                "error_code": row.error_code,
                "error_detail": row.error_detail,
                "updated_at": row.updated_at,
            }
            for row in errors
        ],
        "connections": [
            {
                "provider": row.provider,
                "status": row.status,
                "last_sync_at": row.last_sync_at,
                "last_cursor": row.last_cursor,
                "last_cursor_at": row.last_cursor_at,
                "last_webhook_at": row.last_webhook_at,
                "last_ingest_counts": row.last_ingest_counts,
                "last_error": row.last_error,
            }
            for row in connections
        ],
        "monitor_status": monitoring_service.get_monitor_status(db, business_id),
    }


def reprocess_pipeline(
    db: Session,
    *,
    business_id: str,
    mode: str = "from_last_cursor",
    from_source_event_id: Optional[str] = None,
) -> Dict[str, Any]:
    require_business(db, business_id)
    if mode not in REPROCESS_MODES:
        raise HTTPException(400, "invalid reprocess mode")

    before_counts = {
        "raw_events": int(
            db.execute(
                select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)
            ).scalar_one()
        ),
        "categorized": int(
            db.execute(
                select(func.count())
                .select_from(TxnCategorization)
                .where(TxnCategorization.business_id == business_id)
            ).scalar_one()
        ),
    }

    if mode == "from_beginning":
        db.execute(
            delete(ProcessingEventState).where(ProcessingEventState.business_id == business_id)
        )
        db.execute(
            delete(TxnCategorization).where(TxnCategorization.business_id == business_id)
        )
        db.flush()

    source_event_ids = None
    if mode == "from_source_event_id":
        if not from_source_event_id:
            raise HTTPException(400, "from_source_event_id required")
        start_event = db.execute(
            select(RawEvent).where(
                RawEvent.business_id == business_id,
                RawEvent.source_event_id == from_source_event_id,
            )
        ).scalar_one_or_none()
        if not start_event:
            raise HTTPException(404, "source_event_id not found")
        source_event_ids = db.execute(
            select(RawEvent.source_event_id)
            .where(
                RawEvent.business_id == business_id,
                RawEvent.occurred_at >= start_event.occurred_at,
            )
            .order_by(RawEvent.occurred_at.asc(), RawEvent.source_event_id.asc())
        ).scalars().all()

    summary = process_new_events(
        db,
        business_id=business_id,
        source_event_ids=source_event_ids,
        limit=1000,
    )
    pulse_result = monitoring_service.pulse(db, business_id)

    after_counts = {
        "raw_events": before_counts["raw_events"],
        "categorized": int(
            db.execute(
                select(func.count())
                .select_from(TxnCategorization)
                .where(TxnCategorization.business_id == business_id)
            ).scalar_one()
        ),
    }

    audit_row = audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="processing_reprocess",
        actor="system",
        reason="reprocess",
        before=before_counts,
        after={
            "mode": mode,
            "from_source_event_id": from_source_event_id,
            "processing": summary,
            "after_counts": after_counts,
            "pulse": pulse_result,
        },
    )
    db.commit()
    return {
        "mode": mode,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "processing": summary,
        "pulse": pulse_result,
        "audit_id": audit_row.id,
    }
