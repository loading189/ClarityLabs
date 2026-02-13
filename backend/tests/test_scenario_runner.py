from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import func, select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_scenario_runner.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Business, Organization, RawEvent
from backend.app.scenarios.runner import ScenarioRunner
from backend.app.sim import models as sim_models  # noqa: F401


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
    org = Organization(name="Scenario Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Scenario Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def test_catalog_contains_required_scenarios(db_session):
    runner = ScenarioRunner()
    ids = {item.id for item in runner.list_scenarios()}
    assert {
        "baseline_stable",
        "persistent_deterioration",
        "flickering_threshold",
        "hygiene_missing_uncategorized",
        "plan_success_story",
        "plan_failure_story",
    }.issubset(ids)


def test_seed_is_deterministic_for_same_inputs(db_session):
    biz = _biz(db_session)
    runner = ScenarioRunner()
    params = {"anchor_date": date(2025, 1, 15).isoformat(), "refresh_actions": True}

    first = runner.seed_business(db_session, biz.id, "baseline_stable", params)
    second = runner.seed_business(db_session, biz.id, "baseline_stable", params)

    assert first["seed_key"] == second["seed_key"]
    assert first["summary"] == second["summary"]


def test_reset_clears_and_reseed_works(db_session):
    biz = _biz(db_session)
    runner = ScenarioRunner()

    first = runner.seed_business(db_session, biz.id, "plan_failure_story", {"anchor_date": "2025-01-15"})
    assert first["summary"]["txns_created"] > 0

    reset_out = runner.reset_business(db_session, biz.id)
    assert reset_out["remaining_sim_events"] == 0

    raw_count = db_session.execute(
        select(func.count()).select_from(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "sim_v2")
    ).scalar_one()
    assert raw_count == 0

    reseed = runner.seed_business(db_session, biz.id, "plan_failure_story", {"anchor_date": "2025-01-15"})
    assert reseed["summary"]["txns_created"] > 0
