from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import RawEvent
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.services.raw_event_service import canonical_source_event_id as resolve_canonical_id


@dataclass(frozen=True)
class PostedTxn:
    raw_event: RawEvent
    canonical_source_event_id: str
    txn: object


def _meta(payload: dict) -> dict:
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}


def _event_version(payload: dict) -> int:
    meta = _meta(payload)
    version = meta.get("event_version")
    if isinstance(version, int):
        return version
    if isinstance(version, str) and version.isdigit():
        return int(version)
    return 0


def _is_removed(payload: dict) -> bool:
    meta = _meta(payload)
    if meta.get("is_removed") is True:
        return True
    event_type = meta.get("event_type")
    return event_type == "removed"


def _latest_event(events: Iterable[RawEvent]) -> RawEvent:
    return max(
        events,
        key=lambda ev: (
            _event_version(ev.payload or {}),
            ev.occurred_at,
            ev.source_event_id,
        ),
    )


def current_raw_events(
    db: Session,
    business_id: str,
    *,
    source: Optional[str] = None,
    include_removed: bool = False,
    limit: Optional[int] = None,
) -> List[RawEvent]:
    stmt = select(RawEvent).where(RawEvent.business_id == business_id)
    if source:
        stmt = stmt.where(RawEvent.source == source)
    stmt = stmt.order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
    if limit:
        stmt = stmt.limit(limit)
    events = db.execute(stmt).scalars().all()

    grouped: dict[str, list[RawEvent]] = {}
    for ev in events:
        canonical_id = ev.canonical_source_event_id or resolve_canonical_id(ev.payload, ev.source_event_id)
        grouped.setdefault(canonical_id, []).append(ev)

    current: List[RawEvent] = []
    for group in grouped.values():
        latest = _latest_event(group)
        if not include_removed and _is_removed(latest.payload or {}):
            continue
        current.append(latest)

    current.sort(key=lambda ev: (ev.occurred_at, ev.source_event_id))
    return current


def posted_txns(
    db: Session,
    business_id: str,
    *,
    source: Optional[str] = None,
    include_removed: bool = False,
    limit: Optional[int] = None,
) -> List[PostedTxn]:
    events = current_raw_events(
        db,
        business_id,
        source=source,
        include_removed=include_removed,
        limit=limit,
    )
    posted: List[PostedTxn] = []
    for ev in events:
        canonical_id = ev.canonical_source_event_id or resolve_canonical_id(ev.payload, ev.source_event_id)
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, source_event_id=canonical_id)
        posted.append(PostedTxn(raw_event=ev, canonical_source_event_id=canonical_id, txn=txn))
    return posted
