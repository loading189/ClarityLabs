from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from backend.app.models import RawEvent
from backend.app.services.integration_connection_service import get_or_create_connection, mark_sync_error, mark_sync_success, update_status
from backend.app.services.integration_run_service import start_run, finish_run
from backend.app.services.posted_txn_service import current_raw_events
from backend.app.services.raw_event_service import insert_raw_event_idempotent


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlaidSyncClient(Protocol):
    def sync_transactions(
        self,
        *,
        cursor: Optional[str],
        since: Optional[str] = None,
        last_n: Optional[int] = None,
    ) -> dict[str, Any]:
        ...


def get_plaid_client() -> PlaidSyncClient:
    raise RuntimeError("Plaid client not configured")


@dataclass(frozen=True)
class SyncCounts:
    added: int
    modified: int
    removed: int
    inserted: int
    duplicates: int


def _build_payload(transaction: dict, event_type: str, *, canonical_id: str, version: int, supersedes: Optional[str]) -> dict:
    payload = {
        "type": "transaction.posted",
        "transaction": transaction,
        "meta": {
            "canonical_source_event_id": canonical_id,
            "event_type": event_type,
            "event_version": version,
            "supersedes_source_event_id": supersedes,
            "is_removed": event_type == "removed",
        },
    }
    if event_type == "removed":
        payload["meta"]["removed_at"] = _now().isoformat()
    return payload


def _next_version(existing: list[RawEvent]) -> int:
    if not existing:
        return 1
    versions = []
    for ev in existing:
        meta = ev.payload.get("meta") if isinstance(ev.payload, dict) else {}
        if isinstance(meta, dict):
            v = meta.get("event_version")
            if isinstance(v, int):
                versions.append(v)
            elif isinstance(v, str) and v.isdigit():
                versions.append(int(v))
    return (max(versions) if versions else 0) + 1


def sync_plaid_transactions(
    db: Session,
    *,
    business_id: str,
    provider: str = "plaid",
    since: Optional[str] = None,
    last_n: Optional[int] = None,
    mode: str = "sync",
) -> dict[str, Any]:
    conn = get_or_create_connection(db, business_id, provider)
    run = start_run(
        db,
        business_id=business_id,
        provider=provider,
        run_type="replay" if mode == "replay" else "sync",
        before_counts={
            "raw_events": int(
                db.execute(
                    select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)
                ).scalar_one()
            )
        },
    )
    db.commit()

    client = get_plaid_client()
    response = client.sync_transactions(cursor=conn.provider_cursor, since=since, last_n=last_n)

    added = response.get("added", []) or []
    modified = response.get("modified", []) or []
    removed = response.get("removed", []) or []
    next_cursor = response.get("next_cursor")

    inserted = 0
    duplicates = 0

    def handle_event(event_type: str, event: dict) -> None:
        nonlocal inserted, duplicates
        transaction = event.get("transaction") if isinstance(event.get("transaction"), dict) else event
        txn_id = transaction.get("transaction_id")
        if not txn_id:
            return
        canonical_id = str(txn_id)
        event_suffix = event.get("event_id") or event.get("update_id") or (next_cursor or "cursor")
        source_event_id = f"{canonical_id}:{event_type}:{event_suffix}"

        existing = db.execute(
            select(RawEvent).where(
                RawEvent.business_id == business_id,
                RawEvent.source == provider,
                or_(
                    RawEvent.canonical_source_event_id == canonical_id,
                    RawEvent.source_event_id == canonical_id,
                ),
            )
        ).scalars().all()
        supersedes = None
        if existing:
            latest = max(existing, key=lambda ev: (ev.occurred_at, ev.source_event_id))
            supersedes = latest.source_event_id
        version = _next_version(existing)

        payload = _build_payload(
            transaction,
            event_type,
            canonical_id=canonical_id,
            version=version,
            supersedes=supersedes,
        )

        created = insert_raw_event_idempotent(
            db,
            business_id=business_id,
            source=provider,
            source_event_id=source_event_id,
            canonical_source_event_id=canonical_id,
            occurred_at=_now(),
            payload=payload,
        )
        if created:
            inserted += 1
            conn.last_ingested_source_event_id = source_event_id
        else:
            duplicates += 1

    try:
        for event in added:
            handle_event("added", event)
        for event in modified:
            handle_event("modified", event)
        for event in removed:
            handle_event("removed", event)

        conn.provider_cursor = next_cursor
        mark_sync_success(conn)
        update_status(conn)
        finish_run(
            db,
            run,
            status="ok",
            after_counts={
                "raw_events": int(
                    db.execute(
                        select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)
                    ).scalar_one()
                ),
                "posted_txns": len(current_raw_events(db, business_id)),
            },
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - want to capture any sync failure
        db.rollback()
        mark_sync_error(conn, {"message": str(exc)})
        finish_run(db, run, status="error", detail={"message": str(exc)})
        db.commit()
        raise

    return {
        "status": "ok",
        "provider": provider,
        "cursor": next_cursor,
        "counts": SyncCounts(
            added=len(added),
            modified=len(modified),
            removed=len(removed),
            inserted=inserted,
            duplicates=duplicates,
        ).__dict__,
    }
