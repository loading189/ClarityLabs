from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.services import audit_service, categorize_service, monitoring_service, processing_service


def process_ingested_events(
    db: Session,
    *,
    business_id: str,
    source_event_ids: Optional[Sequence[str]] = None,
) -> dict:
    categorize_service.seed_coa_and_categories_and_mappings(db, business_id)

    inserted_count = len(source_event_ids) if source_event_ids else 0
    processing_summary = processing_service.process_new_events(
        db,
        business_id=business_id,
        source_event_ids=source_event_ids,
    )
    pulse_result = monitoring_service.pulse(db, business_id)
    touched = pulse_result.get("touched_signal_ids", []) if pulse_result else []

    audit_row = audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="ingest_processed",
        actor="system",
        reason="ingest_orchestrator",
        before=None,
        after={
            "events_inserted": inserted_count,
            "processing_summary": processing_summary,
            "pulse_ran": bool(pulse_result.get("ran")) if pulse_result else False,
            "touched_signals": len(touched),
            "source_event_ids": list(source_event_ids or []),
        },
    )
    db.commit()

    return {
        "events_inserted": inserted_count,
        "processing": processing_summary,
        "pulse": pulse_result,
        "touched_signal_ids": touched,
        "audit_ids": {
            "ingest_processed": audit_row.id,
            **(processing_summary.get("audit_ids") or {}),
        },
    }
