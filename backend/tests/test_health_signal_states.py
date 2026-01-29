from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_health_signal_states.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Organization, Business
from backend.app.services import health_signal_service


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


def _create_business(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Test Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_health_signal_status_persistence(db_session):
    biz = _create_business(db_session)

    signals = [
        {"id": "high_uncategorized_rate", "status": "open"},
        {"id": "rule_coverage_low", "status": "in_progress"},
    ]

    hydrated = health_signal_service.hydrate_signal_states(db_session, biz.id, signals)
    assert hydrated[0]["status"] == "open"
    assert hydrated[0]["last_seen_at"] is not None

    updated = health_signal_service.update_signal_status(
        db_session,
        biz.id,
        "high_uncategorized_rate",
        status="resolved",
        resolution_note="resolved via rule",
    )

    assert updated["status"] == "resolved"
    assert updated["resolved_at"] is not None
    assert updated["resolution_note"] == "resolved via rule"

    second = health_signal_service.hydrate_signal_states(db_session, biz.id, signals)
    by_id = {row["id"]: row for row in second}
    assert by_id["high_uncategorized_rate"]["status"] == "resolved"
    assert by_id["high_uncategorized_rate"]["resolution_note"] == "resolved via rule"
