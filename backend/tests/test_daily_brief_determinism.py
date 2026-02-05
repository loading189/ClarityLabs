from __future__ import annotations

from datetime import date, datetime, timezone
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_daily_brief.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import AssistantMessage, Business, Organization
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
    org = Organization(name="Brief Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Brief Biz")
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def _severity_rank(severity: str) -> int:
    order = {"critical": 6, "high": 5, "warning": 4, "medium": 3, "info": 2, "low": 1}
    return order.get((severity or "").lower(), 0)


def test_daily_brief_determinism_and_idempotency(db_session):
    biz = _biz(db_session)
    seed(
        db_session,
        SimV2SeedRequest(
            business_id=biz.id,
            preset_id="cash_strained",
            anchor_date=date(2025, 1, 15),
            mode="replace",
        ),
    )

    as_of = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    first_message, first_brief = publish_daily_brief(db_session, biz.id, as_of.date(), as_of)
    second_message, second_brief = publish_daily_brief(db_session, biz.id, as_of.date(), as_of)

    assert first_message.id == second_message.id
    assert first_brief == second_brief

    rows = (
        db_session.execute(
            select(AssistantMessage).where(
                AssistantMessage.business_id == biz.id,
                AssistantMessage.kind == "daily_brief",
            )
        )
        .scalars()
        .all()
    )
    same_day = [row for row in rows if isinstance(row.content_json, dict) and row.content_json.get("date") == "2025-01-15"]
    assert len(same_day) == 1

    priorities = first_brief["priorities"]
    assert priorities

    for idx in range(len(priorities) - 1):
        left = priorities[idx]
        right = priorities[idx + 1]
        left_key = (
            -_severity_rank(str(left.get("severity", ""))),
            0 if left.get("status") == "open" else 1,
            str(left.get("signal_id", "")),
        )
        right_key = (
            -_severity_rank(str(right.get("severity", ""))),
            0 if right.get("status") == "open" else 1,
            str(right.get("signal_id", "")),
        )
        assert left_key <= right_key
