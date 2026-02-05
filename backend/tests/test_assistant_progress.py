from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest
sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assistant_progress.db")

from backend.app.db import Base, SessionLocal, engine
from sqlalchemy import select

from backend.app.models import Business, HealthSignalState, Organization
from backend.app.api.routes.assistant_progress import get_assistant_progress
from backend.app.services.assistant_plan_service import PlanCreateIn, PlanStatusIn, create_plan, update_plan_status
from backend.app.services.daily_brief_service import publish_daily_brief
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
    org = Organization(name="Progress Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Progress Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def test_assistant_progress_and_plan_outcome(db_session):
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

    # Create consecutive daily briefs for a deterministic streak.
    for offset in range(0, 4):
        current_day = anchor - timedelta(days=offset)
        as_of = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
        publish_daily_brief(db_session, biz.id, current_day, as_of)

    signal_id = db_session.execute(select(HealthSignalState.signal_id).where(HealthSignalState.business_id == biz.id).order_by(HealthSignalState.signal_id.asc())).scalars().first()
    plan = create_plan(db_session, PlanCreateIn(business_id=biz.id, title="Liquidity plan", signal_ids=[signal_id]))

    done_plan = update_plan_status(
        db_session,
        biz.id,
        plan.plan_id,
        PlanStatusIn(actor="analyst", status="done"),
    )

    assert done_plan.completed_at
    assert done_plan.outcome
    assert done_plan.outcome["signals_total"] == 1
    assert done_plan.outcome["signals_resolved_count"] in {0, 1}
    assert done_plan.outcome["signals_still_open_count"] in {0, 1}
    assert done_plan.outcome["summary_bullets"] == [
        f"Signals resolved: {done_plan.outcome['signals_resolved_count']}/1.",
        f"Signals still open: {done_plan.outcome['signals_still_open_count']}.",
        f"Health score changed by {float(done_plan.outcome['health_score_delta']):+.2f}.",
        "Clear-condition checks met: 0/1.",
    ]

    payload = get_assistant_progress(business_id=biz.id, window_days=3, db=db_session).model_dump()

    assert payload["business_id"] == biz.id
    assert payload["window_days"] == 3
    assert "generated_at" in payload
    assert "health_score" in payload and "current" in payload["health_score"]
    assert "open_signals" in payload and "current" in payload["open_signals"]
    assert payload["plans"]["completed_count_window"] == 1
    assert payload["streak_days"] == 4

    domains = payload["top_domains_open"]
    assert domains == sorted(domains, key=lambda row: (-row["count"], row["domain"]))
