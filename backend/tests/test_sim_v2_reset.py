from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import func, select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sim_v2_reset.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, Organization, RawEvent
from backend.app.sim_v2.engine import reset, seed
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
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def test_reset_removes_sim_v2_events(db_session):
    biz = _biz(db_session)
    seed(db_session, SimV2SeedRequest(business_id=biz.id, preset_id="healthy", anchor_date=date(2025, 1, 15)))

    before = db_session.execute(
        select(func.count()).select_from(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "sim_v2")
    ).scalar_one()
    assert before > 0

    out = reset(db_session, biz.id)
    assert out["deleted_raw_events"] == before

    after = db_session.execute(
        select(func.count()).select_from(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "sim_v2")
    ).scalar_one()
    assert after == 0
