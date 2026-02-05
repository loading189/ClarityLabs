from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sim_v2_seed.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, Organization
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
    org = Organization(name="Sim V2 Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def test_sim_v2_seed_deterministic_and_signals(db_session):
    biz = _biz(db_session)
    req = SimV2SeedRequest(
        business_id=biz.id,
        preset_id="cash_strained",
        anchor_date=date(2025, 1, 15),
        mode="replace",
    )
    first = seed(db_session, req)
    assert int(first["signals"]["total"]) > 0
    first_ids = [row["signal_id"] for row in first["signals"]["top"]]

    second = seed(db_session, req)
    second_ids = [row["signal_id"] for row in second["signals"]["top"]]
    assert first_ids == second_ids
