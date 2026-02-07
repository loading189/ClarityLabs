from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import RawEvent


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upsert_raw_event(
    db: Session,
    *,
    business_id: str,
    source: str,
    source_event_id: str,
    occurred_at: Optional[datetime],
    payload: dict,
) -> bool:
    existing = db.execute(
        select(RawEvent.id).where(
            RawEvent.business_id == business_id,
            RawEvent.source == source,
            RawEvent.source_event_id == source_event_id,
        )
    ).scalar_one_or_none()
    if existing:
        return False

    try:
        with db.begin_nested():
            db.add(
                RawEvent(
                    business_id=business_id,
                    source=source,
                    source_event_id=source_event_id,
                    occurred_at=occurred_at or utcnow(),
                    payload=payload,
                )
            )
            db.flush()
    except IntegrityError:
        return False
    return True
