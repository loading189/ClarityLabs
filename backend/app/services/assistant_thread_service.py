from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models import AssistantMessage, Business

ALLOWED_AUTHORS = {"system", "assistant", "user"}
ALLOWED_KINDS = {"summary", "changes", "priority", "explain", "action_result", "note"}
MAX_MESSAGE_BYTES = 16_000
MAX_THREAD_LIMIT = 200


class AssistantMessageIn(BaseModel):
    author: str
    kind: str
    signal_id: Optional[str] = None
    audit_id: Optional[str] = None
    content_json: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("author")
    @classmethod
    def validate_author(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in ALLOWED_AUTHORS:
            raise ValueError("author must be one of system|assistant|user")
        return normalized

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in ALLOWED_KINDS:
            raise ValueError("kind must be one of summary|changes|priority|explain|action_result|note")
        return normalized

    @field_validator("content_json")
    @classmethod
    def validate_content_json(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        try:
            serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
        except TypeError as exc:
            raise ValueError("content_json must be JSON-serializable") from exc
        if len(serialized.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("content_json too large")
        return value


class AssistantMessageOut(BaseModel):
    id: str
    business_id: str
    created_at: datetime
    author: str
    kind: str
    signal_id: Optional[str] = None
    audit_id: Optional[str] = None
    content_json: Dict[str, Any]



def _require_business(db: Session, business_id: str) -> None:
    if not db.get(Business, business_id):
        raise HTTPException(status_code=404, detail="business not found")



def _checksum(message: AssistantMessageIn) -> str:
    payload = {
        "author": message.author,
        "kind": message.kind,
        "signal_id": message.signal_id,
        "audit_id": message.audit_id,
        "content_json": message.content_json,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()



def _to_out(row: AssistantMessage) -> AssistantMessageOut:
    return AssistantMessageOut(
        id=row.id,
        business_id=row.business_id,
        created_at=row.created_at,
        author=row.author,
        kind=row.kind,
        signal_id=row.signal_id,
        audit_id=row.audit_id,
        content_json=row.content_json or {},
    )



def list_messages(
    db: Session,
    business_id: str,
    limit: int = MAX_THREAD_LIMIT,
    before_id: Optional[str] = None,
) -> List[AssistantMessageOut]:
    _require_business(db, business_id)
    bounded = max(1, min(limit, MAX_THREAD_LIMIT))
    stmt = select(AssistantMessage).where(AssistantMessage.business_id == business_id)
    if before_id:
        before = db.get(AssistantMessage, before_id)
        if before and before.business_id == business_id:
            stmt = stmt.where(
                (AssistantMessage.created_at < before.created_at)
                | ((AssistantMessage.created_at == before.created_at) & (AssistantMessage.id < before.id))
            )
    rows = (
        db.execute(
            stmt.order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc()).limit(bounded)
        )
        .scalars()
        .all()
    )
    return [_to_out(row) for row in rows]



def _enforce_retention(db: Session, business_id: str, keep: int = MAX_THREAD_LIMIT) -> None:
    keep = max(1, min(keep, MAX_THREAD_LIMIT))
    keep_ids = (
        db.execute(
            select(AssistantMessage.id)
            .where(AssistantMessage.business_id == business_id)
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            .limit(keep)
        )
        .scalars()
        .all()
    )
    if not keep_ids:
        return
    db.execute(
        delete(AssistantMessage).where(
            AssistantMessage.business_id == business_id,
            AssistantMessage.id.not_in(keep_ids),
        )
    )



def append_message(
    db: Session,
    business_id: str,
    msg_in: AssistantMessageIn,
    *,
    dedupe: bool = True,
) -> AssistantMessageOut:
    _require_business(db, business_id)
    normalized = AssistantMessageIn.model_validate(msg_in)
    checksum = _checksum(normalized)

    if dedupe:
        existing = (
            db.execute(
                select(AssistantMessage)
                .where(
                    AssistantMessage.business_id == business_id,
                    AssistantMessage.checksum == checksum,
                )
                .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing:
            return _to_out(existing)

    row = AssistantMessage(
        business_id=business_id,
        created_at=datetime.now(timezone.utc),
        author=normalized.author,
        kind=normalized.kind,
        signal_id=normalized.signal_id,
        audit_id=normalized.audit_id,
        content_json=normalized.content_json,
        checksum=checksum,
    )
    db.add(row)
    db.flush()
    _enforce_retention(db, business_id, keep=MAX_THREAD_LIMIT)
    db.commit()
    db.refresh(row)
    return _to_out(row)



def prune_messages(db: Session, business_id: str, keep: int = MAX_THREAD_LIMIT) -> int:
    _require_business(db, business_id)
    before_count = (
        db.execute(select(AssistantMessage).where(AssistantMessage.business_id == business_id))
        .scalars()
        .all()
    )
    _enforce_retention(db, business_id, keep=keep)
    db.commit()
    after_count = (
        db.execute(select(AssistantMessage).where(AssistantMessage.business_id == business_id))
        .scalars()
        .all()
    )
    return max(0, len(before_count) - len(after_count))
