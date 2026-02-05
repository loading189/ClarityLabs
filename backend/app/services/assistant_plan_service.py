from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AssistantMessage, Business
from backend.app.services import signals_service
from backend.app.services.assistant_thread_service import AssistantMessageIn, append_message

ALLOWED_PLAN_STATUS = {"open", "in_progress", "done"}
ALLOWED_STEP_STATUS = {"todo", "done"}


class PlanStep(BaseModel):
    step_id: str
    title: str
    playbook_id: Optional[str] = None
    status: str = "todo"

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_STEP_STATUS:
            raise ValueError("step status must be todo|done")
        return value


class PlanNoteIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=40)
    text: str = Field(..., min_length=1, max_length=2000)


class PlanCreateIn(BaseModel):
    business_id: str
    title: Optional[str] = Field(default=None, max_length=200)
    signal_ids: List[str] = Field(default_factory=list, min_length=1)


class PlanStepDoneIn(BaseModel):
    step_id: str
    actor: str = Field(..., min_length=1, max_length=40)
    note: Optional[str] = Field(default=None, max_length=2000)


class PlanStatusIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=40)
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_PLAN_STATUS:
            raise ValueError("status must be open|in_progress|done")
        return value


class PlanOut(BaseModel):
    plan_id: str
    business_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    signal_ids: List[str]
    steps: List[Dict[str, Any]]
    notes: List[Dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_business(db: Session, business_id: str) -> None:
    if not db.get(Business, business_id):
        raise HTTPException(status_code=404, detail="business not found")


def _plan_sort_key(plan: Dict[str, Any]):
    status = str(plan.get("status") or "open")
    rank = 0 if status in {"open", "in_progress"} else 1
    updated = str(plan.get("updated_at") or "")
    plan_id = str(plan.get("plan_id") or "")
    return (rank, -int(datetime.fromisoformat(updated).timestamp()) if updated else 0, plan_id)


def _parse_plan_row(row: AssistantMessage) -> Optional[Dict[str, Any]]:
    content = row.content_json if isinstance(row.content_json, dict) else {}
    if not content.get("plan_id"):
        return None
    return {
        "plan_id": str(content.get("plan_id")),
        "business_id": row.business_id,
        "title": str(content.get("title") or "Untitled plan"),
        "status": str(content.get("status") or "open"),
        "created_at": str(content.get("created_at") or row.created_at.isoformat()),
        "updated_at": str(content.get("updated_at") or row.created_at.isoformat()),
        "signal_ids": [str(signal_id) for signal_id in (content.get("signal_ids") or [])],
        "steps": list(content.get("steps") or []),
        "notes": list(content.get("notes") or []),
    }


def _list_plan_rows(db: Session, business_id: str) -> List[AssistantMessage]:
    return (
        db.execute(
            select(AssistantMessage)
            .where(AssistantMessage.business_id == business_id, AssistantMessage.kind == "plan")
            .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        )
        .scalars()
        .all()
    )


def list_plans(db: Session, business_id: str) -> List[PlanOut]:
    _require_business(db, business_id)
    plans = [p for row in _list_plan_rows(db, business_id) if (p := _parse_plan_row(row)) is not None]
    plans.sort(key=_plan_sort_key)
    return [PlanOut.model_validate(plan) for plan in plans]


def _deterministic_steps(db: Session, business_id: str, signal_ids: List[str]) -> List[Dict[str, Any]]:
    unique_signal_ids = sorted({signal_id.strip() for signal_id in signal_ids if signal_id and signal_id.strip()})
    steps: List[Dict[str, Any]] = []
    seen_playbook_ids: set[str] = set()
    for signal_id in unique_signal_ids:
        explain = signals_service.get_signal_explain(db, business_id, signal_id)
        playbooks = sorted(explain.get("playbooks") or [], key=lambda item: str(item.get("id") or ""))
        for playbook in playbooks:
            playbook_id = str(playbook.get("id") or "")
            if not playbook_id or playbook_id in seen_playbook_ids:
                continue
            seen_playbook_ids.add(playbook_id)
            steps.append(
                {
                    "step_id": str(uuid4()),
                    "title": str(playbook.get("title") or playbook_id),
                    "playbook_id": playbook_id,
                    "status": "todo",
                }
            )
    steps.sort(key=lambda row: (str(row.get("playbook_id") or ""), str(row.get("title") or ""), str(row.get("step_id") or "")))
    return steps


def create_plan(db: Session, req: PlanCreateIn) -> PlanOut:
    _require_business(db, req.business_id)
    signal_ids = sorted({signal_id.strip() for signal_id in req.signal_ids if signal_id and signal_id.strip()})
    if not signal_ids:
        raise HTTPException(status_code=400, detail="signal_ids required")

    now_iso = _now_iso()
    plan_id = str(uuid4())
    plan_content = {
        "plan_id": plan_id,
        "title": req.title.strip() if req.title and req.title.strip() else f"Resolution plan {plan_id[:8]}",
        "status": "open",
        "created_at": now_iso,
        "updated_at": now_iso,
        "signal_ids": signal_ids,
        "steps": _deterministic_steps(db, req.business_id, signal_ids),
        "notes": [],
    }

    plan_msg = append_message(
        db,
        req.business_id,
        AssistantMessageIn(author="system", kind="plan", content_json=plan_content),
        dedupe=False,
    )
    append_message(
        db,
        req.business_id,
        AssistantMessageIn(author="system", kind="plan_created", content_json={"plan_id": plan_id, "signal_ids": signal_ids}),
        dedupe=False,
    )
    row = db.get(AssistantMessage, plan_msg.id)
    parsed = _parse_plan_row(row) if row else None
    if not parsed:
        raise HTTPException(status_code=500, detail="failed to create plan")
    return PlanOut.model_validate(parsed)


def _get_plan_row_by_plan_id(db: Session, business_id: str, plan_id: str) -> AssistantMessage:
    for row in _list_plan_rows(db, business_id):
        content = row.content_json if isinstance(row.content_json, dict) else {}
        if str(content.get("plan_id") or "") == plan_id:
            return row
    raise HTTPException(status_code=404, detail="plan not found")


def mark_plan_step_done(db: Session, business_id: str, plan_id: str, req: PlanStepDoneIn) -> PlanOut:
    row = _get_plan_row_by_plan_id(db, business_id, plan_id)
    content = dict(row.content_json or {})
    steps = list(content.get("steps") or [])
    found = False
    for step in steps:
        if str(step.get("step_id") or "") == req.step_id:
            step["status"] = "done"
            found = True
    if not found:
        raise HTTPException(status_code=404, detail="step not found")
    content["steps"] = sorted(steps, key=lambda item: (str(item.get("playbook_id") or ""), str(item.get("title") or ""), str(item.get("step_id") or "")))
    content["updated_at"] = _now_iso()
    row.content_json = content
    db.add(row)
    db.commit()
    db.refresh(row)
    append_message(
        db,
        business_id,
        AssistantMessageIn(author="system", kind="plan_step_done", content_json={"plan_id": plan_id, "step_id": req.step_id, "actor": req.actor, "note": req.note}),
        dedupe=False,
    )
    parsed = _parse_plan_row(row)
    return PlanOut.model_validate(parsed)


def add_plan_note(db: Session, business_id: str, plan_id: str, req: PlanNoteIn) -> PlanOut:
    row = _get_plan_row_by_plan_id(db, business_id, plan_id)
    content = dict(row.content_json or {})
    notes = list(content.get("notes") or [])
    note = {"id": str(uuid4()), "created_at": _now_iso(), "text": req.text, "actor": req.actor}
    notes.append(note)
    content["notes"] = notes
    content["updated_at"] = _now_iso()
    row.content_json = content
    db.add(row)
    db.commit()
    db.refresh(row)
    append_message(
        db,
        business_id,
        AssistantMessageIn(author="system", kind="plan_note_added", content_json={"plan_id": plan_id, "note_id": note["id"], "actor": req.actor}),
        dedupe=False,
    )
    return PlanOut.model_validate(_parse_plan_row(row))


def update_plan_status(db: Session, business_id: str, plan_id: str, req: PlanStatusIn) -> PlanOut:
    row = _get_plan_row_by_plan_id(db, business_id, plan_id)
    content = dict(row.content_json or {})
    content["status"] = req.status
    content["updated_at"] = _now_iso()
    row.content_json = content
    db.add(row)
    db.commit()
    db.refresh(row)
    append_message(
        db,
        business_id,
        AssistantMessageIn(author="system", kind="plan_status_updated", content_json={"plan_id": plan_id, "status": req.status, "actor": req.actor}),
        dedupe=False,
    )
    return PlanOut.model_validate(_parse_plan_row(row))
