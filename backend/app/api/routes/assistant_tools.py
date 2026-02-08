from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_membership
from backend.app.db import get_db
from backend.app.integrations import get_adapter
from backend.app.models import ActionItem, AuditLog, HealthSignalState, IntegrationConnection, User
from backend.app.services import audit_service, monitoring_service, integration_connection_service
from backend.app.services.ingest_orchestrator import process_ingested_events
from backend.app.services.posted_txn_service import (
    count_uncategorized_raw_events,
    fetch_posted_transactions,
)


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _top_vendors(db: Session, business_id: str, limit: int = 5):
    start_date = (utcnow() - timedelta(days=30)).date()
    txns = fetch_posted_transactions(db, business_id, start_date=start_date)
    totals: dict[str, float] = {}
    for txn in txns:
        if (txn.direction or "").lower() != "outflow":
            continue
        key = (txn.description or "").strip() or "Unknown"
        totals[key] = totals.get(key, 0.0) + abs(float(txn.amount or 0.0))
    ranked = sorted(totals.items(), key=lambda row: row[1], reverse=True)[:limit]
    return [{"vendor": name, "total_spend": total} for name, total in ranked]


def _open_signals_count(db: Session, business_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(HealthSignalState)
            .where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.status == "open",
            )
        ).scalar_one()
    )


def _open_actions(db: Session, business_id: str, limit: int = 3) -> list[ActionItem]:
    return (
        db.execute(
            select(ActionItem)
            .where(
                ActionItem.business_id == business_id,
                ActionItem.status == "open",
            )
            .order_by(ActionItem.priority.desc(), ActionItem.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def _open_actions_count(db: Session, business_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(ActionItem)
            .where(
                ActionItem.business_id == business_id,
                ActionItem.status == "open",
            )
        ).scalar_one()
    )


def _recent_signal_resolutions(db: Session, business_id: str, limit: int = 5) -> list[dict]:
    rows = (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.business_id == business_id,
                AuditLog.event_type == "signal_status_changed",
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit * 3)
        )
        .scalars()
        .all()
    )
    results: list[dict] = []
    for row in rows:
        after_state = row.after_state if isinstance(row.after_state, dict) else {}
        status = after_state.get("status")
        if status not in {"resolved", "ignored"}:
            continue
        signal_id = after_state.get("signal_id")
        if not signal_id:
            continue
        results.append(
            {
                "id": row.id,
                "signal_id": signal_id,
                "status": status,
                "actor": row.actor,
                "reason": row.reason,
                "created_at": row.created_at,
            }
        )
        if len(results) >= limit:
            break
    return results


class AssistantActionIn(BaseModel):
    action_type: str
    payload: Optional[dict] = None


@router.get("/summary/{business_id}")
def assistant_summary(
    business_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_membership(db, business_id, user)
    integrations = (
        db.execute(
            select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
        )
        .scalars()
        .all()
    )
    audit_rows = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.business_id == business_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(5)
        )
        .scalars()
        .all()
    )
    return {
        "business_id": business_id,
        "integrations": [
            {
                "provider": row.provider,
                "status": row.status,
                "last_sync_at": row.last_sync_at,
                "last_error": row.last_error,
            }
            for row in integrations
        ],
        "monitor_status": monitoring_service.get_monitor_status(db, business_id),
        "open_signals": _open_signals_count(db, business_id),
        "open_action_count": _open_actions_count(db, business_id),
        "top_open_actions": [
            {
                "id": row.id,
                "type": row.action_type,
                "title": row.title,
                "priority": row.priority,
            }
            for row in _open_actions(db, business_id)
        ],
        "uncategorized_count": count_uncategorized_raw_events(db, business_id),
        "recent_signal_resolutions": _recent_signal_resolutions(db, business_id),
        "audit_events": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "actor": row.actor,
                "reason": row.reason,
                "created_at": row.created_at,
            }
            for row in audit_rows
        ],
        "top_vendors": _top_vendors(db, business_id),
    }


@router.post("/action/{business_id}")
def assistant_action(
    business_id: str,
    req: AssistantActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_membership(db, business_id, user, min_role="staff")
    action = (req.action_type or "").strip().lower()
    before = {
        "open_signals": _open_signals_count(db, business_id),
        "uncategorized_count": count_uncategorized_raw_events(db, business_id),
    }

    result: dict = {"ok": True}
    navigation_hint = None

    if action == "run_pulse":
        pulse = monitoring_service.pulse(db, business_id, force_run=True)
        result["result"] = {"pulse": pulse}
    elif action == "sync_integrations":
        connections = (
            db.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.business_id == business_id,
                    IntegrationConnection.is_enabled == True,  # noqa: E712
                    IntegrationConnection.status != "disconnected",
                )
            )
            .scalars()
            .all()
        )
        sync_results = []
        all_source_event_ids: list[str] = []
        for connection in connections:
            adapter = get_adapter(connection.provider)
            pull = adapter.ingest_pull(
                business_id=business_id,
                since=connection.last_sync_at,
                db=db,
            )
            integration_connection_service.mark_sync_success(connection)
            connection.last_ingest_counts = {
                "inserted": pull.inserted_count,
                "skipped": pull.skipped_count,
            }
            connection.updated_at = utcnow()
            db.add(connection)
            sync_results.append(
                {
                    "provider": connection.provider,
                    "inserted": pull.inserted_count,
                    "skipped": pull.skipped_count,
                }
            )
            all_source_event_ids.extend(list(pull.source_event_ids))
        db.flush()
        ingest_processed = process_ingested_events(
            db,
            business_id=business_id,
            source_event_ids=all_source_event_ids,
        )
        result["result"] = {"sync": sync_results, "ingest_processed": ingest_processed}
    elif action == "open_uncategorized":
        navigation_hint = {"path": f"/app/{business_id}/categorize"}
    elif action == "open_signal":
        row = (
            db.execute(
                select(HealthSignalState)
                .where(
                    HealthSignalState.business_id == business_id,
                    HealthSignalState.status == "open",
                )
                .order_by(HealthSignalState.severity.desc().nullslast(), HealthSignalState.detected_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row:
            navigation_hint = {"path": f"/app/{business_id}/signals?signal_id={row.signal_id}"}
        else:
            result["ok"] = False
            result["result"] = {"message": "no_open_signal"}
    else:
        raise HTTPException(400, "unsupported action_type")

    after = {
        "open_signals": _open_signals_count(db, business_id),
        "uncategorized_count": count_uncategorized_raw_events(db, business_id),
        "action": action,
    }
    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="assistant_action",
        actor="assistant",
        reason=action,
        before=before,
        after=after,
    )
    db.commit()

    if navigation_hint:
        result["navigation_hint"] = navigation_hint
    return result
