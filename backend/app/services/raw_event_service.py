from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import RawEvent


def insert_raw_event_idempotent(
    db: Session,
    *,
    business_id: str,
    source: str,
    source_event_id: str,
    occurred_at: datetime,
    payload: dict,
    canonical_source_event_id: Optional[str] = None,
) -> bool:
    raw_event = RawEvent(
        business_id=business_id,
        source=source,
        source_event_id=source_event_id,
        canonical_source_event_id=canonical_source_event_id or source_event_id,
        occurred_at=occurred_at,
        payload=payload,
    )
    db.add(raw_event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def canonical_source_event_id(payload: dict, fallback: str) -> str:
    meta = payload.get("meta")
    if isinstance(meta, dict):
        canonical = meta.get("canonical_source_event_id")
        if isinstance(canonical, str) and canonical:
            return canonical
    transaction = payload.get("transaction")
    if isinstance(transaction, dict):
        txn_id = transaction.get("transaction_id")
        if isinstance(txn_id, str) and txn_id:
            return txn_id
    return fallback
