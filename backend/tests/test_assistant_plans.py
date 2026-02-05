from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assistant_plans.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import AssistantMessage, Business, HealthSignalState, Organization
from backend.app.services.assistant_plan_service import (
    PlanCreateIn,
    PlanNoteIn,
    PlanStatusIn,
    PlanStepDoneIn,
    create_plan,
    list_plans,
    mark_plan_step_done,
    add_plan_note,
    update_plan_status,
)


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _biz(db):
    org = Organization(name="Plans Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Plans Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def _seed_signal(db, biz_id: str, signal_id: str, signal_type: str):
    now = datetime.now(timezone.utc)
    db.add(
        HealthSignalState(
            business_id=biz_id,
            signal_id=signal_id,
            signal_type=signal_type,
            status="open",
            severity="warning",
            title=signal_id,
            summary=f"Summary {signal_id}",
            payload_json={"window_days": 30},
            detected_at=now,
            last_seen_at=now,
            updated_at=now,
        )
    )


def test_create_plan_deterministic_steps_and_order(db_session):
    biz = _biz(db_session)
    _seed_signal(db_session, biz.id, "sig-expense", "expense_creep_by_vendor")
    _seed_signal(db_session, biz.id, "sig-runway", "low_cash_runway")
    db_session.commit()

    plan = create_plan(db_session, PlanCreateIn(business_id=biz.id, title="Plan A", signal_ids=["sig-runway", "sig-expense"]))

    assert plan.title == "Plan A"
    assert plan.signal_ids == ["sig-expense", "sig-runway"]
    playbook_ids = [str(step.get("playbook_id")) for step in plan.steps]
    assert playbook_ids == sorted(playbook_ids)
    assert len(playbook_ids) == len(set(playbook_ids))


def test_step_done_updates_plan_and_emits_activity(db_session):
    biz = _biz(db_session)
    _seed_signal(db_session, biz.id, "sig-expense", "expense_creep_by_vendor")
    db_session.commit()
    plan = create_plan(db_session, PlanCreateIn(business_id=biz.id, signal_ids=["sig-expense"]))

    first_step_id = str(plan.steps[0]["step_id"])
    updated = mark_plan_step_done(db_session, biz.id, plan.plan_id, PlanStepDoneIn(step_id=first_step_id, actor="analyst", note="completed"))

    assert any(step["step_id"] == first_step_id and step["status"] == "done" for step in updated.steps)
    rows = db_session.execute(select(AssistantMessage).where(AssistantMessage.business_id == biz.id, AssistantMessage.kind == "plan_step_done")).scalars().all()
    assert len(rows) == 1
    assert rows[0].content_json.get("plan_id") == plan.plan_id


def test_add_note_updates_plan_and_emits_activity(db_session):
    biz = _biz(db_session)
    _seed_signal(db_session, biz.id, "sig-expense", "expense_creep_by_vendor")
    db_session.commit()
    plan = create_plan(db_session, PlanCreateIn(business_id=biz.id, signal_ids=["sig-expense"]))

    updated = add_plan_note(db_session, biz.id, plan.plan_id, PlanNoteIn(actor="owner", text="Track invoices"))

    assert len(updated.notes) == 1
    assert updated.notes[0]["text"] == "Track invoices"
    rows = db_session.execute(select(AssistantMessage).where(AssistantMessage.business_id == biz.id, AssistantMessage.kind == "plan_note_added")).scalars().all()
    assert len(rows) == 1


def test_plan_list_deterministic_ordering(db_session):
    biz = _biz(db_session)
    _seed_signal(db_session, biz.id, "sig-expense", "expense_creep_by_vendor")
    db_session.commit()
    p1 = create_plan(db_session, PlanCreateIn(business_id=biz.id, title="A", signal_ids=["sig-expense"]))
    p2 = create_plan(db_session, PlanCreateIn(business_id=biz.id, title="B", signal_ids=["sig-expense"]))

    update_plan_status(db_session, biz.id, p1.plan_id, PlanStatusIn(actor="user", status="done"))

    plans = list_plans(db_session, biz.id)
    assert plans[0].plan_id == p2.plan_id
    assert plans[-1].plan_id == p1.plan_id
