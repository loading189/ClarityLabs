from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_plan_verify.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, HealthSignalState, Organization
from backend.app.services.assistant_plan_service import PlanCreateIn, create_plan, verify_plan


def _create_business(db):
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    db.commit()
    return biz


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def test_plan_verify_returns_deterministic_signals_and_totals():
    db = SessionLocal()
    try:
        biz = _create_business(db)
        db.add(HealthSignalState(business_id=biz.id, signal_id="sig-b", signal_type="liquidity.runway_low", status="open", severity="warning", payload_json={"runway_days": 10, "thresholds": {"medium": 30}}))
        db.add(HealthSignalState(business_id=biz.id, signal_id="sig-a", signal_type="liquidity.runway_low", status="open", severity="warning", payload_json={"runway_days": 40, "thresholds": {"medium": 30}}))
        db.commit()

        plan = create_plan(db, PlanCreateIn(business_id=biz.id, title="Plan", signal_ids=["sig-b", "sig-a"]))
        verified = verify_plan(db, biz.id, plan.plan_id)

        assert [row.signal_id for row in verified.signals] == ["sig-a", "sig-b"]
        assert set(verified.totals.keys()) == {"met", "not_met", "unknown"}
        assert sum(verified.totals.values()) == 2
    finally:
        db.close()
