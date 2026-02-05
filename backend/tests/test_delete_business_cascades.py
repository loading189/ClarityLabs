from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import func, select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_delete_business_cascades.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import AssistantMessage, AuditLog, Business, HealthSignalState, Organization, RawEvent
from backend.app.sim_v2.engine import seed
from backend.app.services.business_service import hard_delete_business
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


def test_delete_business_cascades_rows(db_session):
    org = Organization(name="Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Biz")
    db_session.add(biz)
    db_session.commit()
    db_session.refresh(biz)

    seed(db_session, SimV2SeedRequest(business_id=biz.id, preset_id="cash_strained", anchor_date=date(2025, 1, 15)))
    db_session.add(
        AssistantMessage(
            business_id=biz.id,
            author="assistant",
            kind="note",
            content_json={"text": "hello"},
        )
    )
    db_session.commit()

    assert db_session.execute(select(func.count()).select_from(RawEvent).where(RawEvent.business_id == biz.id)).scalar_one() > 0
    assert db_session.execute(select(func.count()).select_from(HealthSignalState).where(HealthSignalState.business_id == biz.id)).scalar_one() > 0

    assert hard_delete_business(db_session, biz.id) is True

    for model in (RawEvent, HealthSignalState, AssistantMessage, AuditLog):
        count = db_session.execute(select(func.count()).select_from(model).where(model.business_id == biz.id)).scalar_one()
        assert count == 0
