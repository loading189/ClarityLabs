from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assistant_work_queue.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Business, HealthSignalState, Organization
from backend.app.services.assistant_plan_service import PlanCreateIn, create_plan
from backend.app.services.assistant_work_queue_service import list_work_queue
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.sim_v2.engine import seed
from backend.app.sim_v2.models import SimV2SeedRequest


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
    org = Organization(name="Work Queue Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Work Queue Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def _add_warning_signal(db, business_id: str, signal_id: str):
    now = datetime.now(timezone.utc)
    db.add(
        HealthSignalState(
            business_id=business_id,
            signal_id=signal_id,
            signal_type="expense_creep_by_vendor",
            status="open",
            severity="warning",
            title=signal_id,
            summary=f"Summary {signal_id}",
            payload_json={},
            detected_at=now,
            last_seen_at=now,
            updated_at=now,
        )
    )


def test_work_queue_deterministic_priorities(db_session):
    biz = _biz(db_session)
    anchor = datetime.now(timezone.utc).date()
    seed(
        db_session,
        SimV2SeedRequest(
            business_id=biz.id,
            preset_id="cash_strained",
            anchor_date=anchor,
            mode="replace",
        ),
    )

    baseline = list_work_queue(db_session, biz.id, 50)
    top_signal = next(item for item in baseline.items if item.kind == "signal")
    create_plan(db_session, PlanCreateIn(business_id=biz.id, title="Top plan", signal_ids=[top_signal.id]))

    _add_warning_signal(db_session, biz.id, "sig-warning-planned")
    _add_warning_signal(db_session, biz.id, "sig-warning-unplanned")
    db_session.commit()
    create_plan(db_session, PlanCreateIn(business_id=biz.id, title="Warn plan", signal_ids=["sig-warning-planned"]))

    queue = list_work_queue(db_session, biz.id, 50)

    first_plan_index = next(index for index, item in enumerate(queue.items) if item.kind == "plan")
    assert first_plan_index < len(queue.items) - 1
    assert queue.items[first_plan_index].score >= 90

    planned_signal = next(item for item in queue.items if item.kind == "signal" and item.id == "sig-warning-planned")
    unplanned_signal = next(item for item in queue.items if item.kind == "signal" and item.id == "sig-warning-unplanned")
    assert unplanned_signal.score > planned_signal.score

    sorted_expected = sorted(queue.items, key=lambda item: (-item.score, str(item.domain or ""), item.id))
    assert [item.id for item in queue.items] == [item.id for item in sorted_expected]
