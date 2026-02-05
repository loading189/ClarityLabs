from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_health_score_explain_change.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import AuditLog, Business, HealthSignalState, Organization
from backend.app.services import health_score_service


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
    org = Organization(name="Explain Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Explain Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_explain_change_deterministic_order_and_summary(db_session):
    biz = _seed_business(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="sig-a",
            signal_type="liquidity.runway_low",
            status="in_progress",
            severity="critical",
            detected_at=now - timedelta(days=2),
            last_seen_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        AuditLog(
            business_id=biz.id,
            event_type="signal_status_changed",
            actor="analyst",
            reason="reviewed",
            before_state={"signal_id": "sig-a", "status": "open"},
            after_state={"signal_id": "sig-a", "signal_type": "liquidity.runway_low", "status": "in_progress", "severity": "critical"},
            created_at=now,
        )
    )
    db_session.commit()

    first = health_score_service.explain_health_score_change(db_session, biz.id, since_hours=72, limit=20)
    second = health_score_service.explain_health_score_change(db_session, biz.id, since_hours=72, limit=20)
    first.pop("computed_at", None)
    second.pop("computed_at", None)
    assert first == second
    assert first["summary"]["headline"].startswith("Health score")


def test_explain_change_bounded_results(db_session):
    biz = _seed_business(db_session)
    now = datetime.now(timezone.utc)
    for i in range(30):
        db_session.add(
            AuditLog(
                business_id=biz.id,
                event_type="signal_detected",
                actor="system",
                reason="detected",
                after_state={"signal_id": f"sig-{i}", "signal_type": "expense.spike_vs_baseline", "status": "open", "severity": "warning"},
                created_at=now - timedelta(minutes=i),
            )
        )
    db_session.commit()

    payload = health_score_service.explain_health_score_change(db_session, biz.id, since_hours=72, limit=20)
    assert len(payload["impacts"]) <= 20
    assert len(payload["changes"]) <= 20


def test_explain_change_uses_changes_and_weights_only(db_session, monkeypatch):
    biz = _seed_business(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        AuditLog(
            business_id=biz.id,
            event_type="signal_detected",
            actor="system",
            reason="detected",
            after_state={"signal_id": "sig-z", "signal_type": "expense.spike_vs_baseline", "status": "open", "severity": "warning"},
            created_at=now,
        )
    )
    db_session.commit()

    called = {"changes": 0}

    original = health_score_service.changes_service.list_changes_window

    def _wrapped(*args, **kwargs):
        called["changes"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(health_score_service.changes_service, "list_changes_window", _wrapped)
    payload = health_score_service.explain_health_score_change(db_session, biz.id, since_hours=72, limit=20)
    assert called["changes"] == 1
    assert isinstance(payload["summary"]["top_drivers"], list)
