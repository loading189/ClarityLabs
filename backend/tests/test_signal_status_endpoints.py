import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_signal_status_endpoints.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.api.routes.demo import HealthSignalStatusIn, update_health_signal_status
from backend.app.api.routes.signals import SignalStatusUpdateIn, update_signal_status
from backend.app.models import Organization, Business


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


def _create_business(db_session, business_id: str | None = None):
    org = Organization(name="Signals Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(id=business_id, org_id=org.id, name="Signals Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_demo_and_real_signal_status_match(db_session):
    biz = _create_business(db_session)
    payload = {"status": "resolved", "reason": "handled", "actor": "tester"}

    demo_payload = update_health_signal_status(
        biz.id,
        "sample_signal",
        HealthSignalStatusIn(**payload),
        db_session,
    )
    real_payload = update_signal_status(
        biz.id,
        "sample_signal",
        SignalStatusUpdateIn(**payload),
        db_session,
    )
    demo_payload.pop("audit_id", None)
    real_payload.pop("audit_id", None)
    demo_payload.pop("resolved_at", None)
    real_payload.pop("resolved_at", None)
    demo_payload.pop("last_seen_at", None)
    real_payload.pop("last_seen_at", None)

    assert demo_payload == real_payload
