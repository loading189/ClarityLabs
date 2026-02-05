from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_changes_feed.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import AuditLog, Business, Organization
from backend.app.services import changes_service


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


def _seed_business(db_session):
    org = Organization(name="Changes Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Changes Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_changes_feed_is_deterministic_and_bounded(db_session):
    biz = _seed_business(db_session)
    base = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)

    detected = AuditLog(
        business_id=biz.id,
        event_type="signal_detected",
        actor="system",
        reason="detected",
        after_state={
            "signal_id": "sig-a",
            "signal_type": "liquidity.runway_low",
            "status": "open",
            "severity": "critical",
            "title": "Low cash runway",
        },
        created_at=base,
    )
    status_updated = AuditLog(
        business_id=biz.id,
        event_type="signal_status_changed",
        actor="analyst",
        reason="reviewed",
        before_state={"signal_id": "sig-a", "status": "open"},
        after_state={
            "signal_id": "sig-a",
            "signal_type": "liquidity.runway_low",
            "status": "in_progress",
            "severity": "critical",
            "title": "Low cash runway",
        },
        created_at=base + timedelta(minutes=1),
    )
    resolved = AuditLog(
        business_id=biz.id,
        event_type="signal_status_changed",
        actor="analyst",
        reason="resolved",
        before_state={"signal_id": "sig-a", "status": "in_progress"},
        after_state={
            "signal_id": "sig-a",
            "signal_type": "liquidity.runway_low",
            "status": "resolved",
            "severity": "critical",
            "title": "Low cash runway",
        },
        created_at=base + timedelta(minutes=2),
    )
    db_session.add_all([detected, status_updated, resolved])
    db_session.commit()

    events = changes_service.list_changes(db_session, biz.id, limit=2)

    assert len(events) == 2
    assert [event["type"] for event in events] == ["signal_resolved", "signal_status_updated"]
    assert events[0]["occurred_at"] >= events[1]["occurred_at"]
    assert events[0]["business_id"] == biz.id
    assert events[0]["signal_id"] == "sig-a"
    assert events[0]["links"]["assistant"].endswith("signalId=sig-a")
