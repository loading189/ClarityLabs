from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_signal_explain_verification.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, HealthSignalState, Organization
from backend.app.services import signals_service


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


def test_signal_explain_verification_exists_and_deterministic_ordering():
    db = SessionLocal()
    try:
        biz = _create_business(db)
        state = HealthSignalState(
            business_id=biz.id,
            signal_id="sig-1",
            signal_type="liquidity.runway_low",
            status="open",
            severity="critical",
            title="Low cash runway",
            payload_json={"runway_days": 20, "thresholds": {"medium": 30}, "burn_window_days": 30, "current_cash": 1000},
        )
        db.add(state)
        db.commit()

        explain = signals_service.get_signal_explain(db, biz.id, "sig-1")
        assert "verification" in explain
        verification = explain["verification"]
        assert verification["status"] in {"met", "not_met", "unknown"}
        keys = [item["key"] for item in verification["facts"]]
        assert keys == sorted(keys)
        assert len(verification["facts"]) <= 6
    finally:
        db.close()
