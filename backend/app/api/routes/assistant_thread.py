from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services.assistant_thread_service import (
    AssistantMessageIn,
    AssistantMessageOut,
    list_messages,
    append_message,
    prune_messages,
)

router = APIRouter(prefix="/api/assistant/thread", tags=["assistant"])


class AssistantThreadPruneOut(BaseModel):
    pruned_count: int


@router.get("", response_model=List[AssistantMessageOut], dependencies=[Depends(require_membership_dep())])
def get_assistant_thread(
    business_id: str = Query(...),
    limit: int = Query(200, ge=1, le=200),
    before_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return list_messages(db, business_id=business_id, limit=limit, before_id=before_id)


@router.post("", response_model=AssistantMessageOut, dependencies=[Depends(require_membership_dep())])
def post_assistant_thread(
    message: AssistantMessageIn,
    business_id: str = Query(...),
    dedupe: bool = Query(True),
    db: Session = Depends(get_db),
):
    return append_message(db, business_id=business_id, msg_in=message, dedupe=dedupe)


@router.delete(
    "",
    response_model=AssistantThreadPruneOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def delete_assistant_thread(
    business_id: str = Query(...),
    keep: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return AssistantThreadPruneOut(pruned_count=prune_messages(db, business_id=business_id, keep=keep))
