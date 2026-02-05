from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_health_score.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Business, HealthSignalState, Organization
from backend.app.services import health_score_service, health_signal_service


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
    org = Organization(name="Score Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Score Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _add_state(
    db_session,
    business_id: str,
    signal_id: str,
    signal_type: str,
    domain: str,
    severity: str,
    status: str,
    detected_at: datetime,
    last_seen_at: datetime,
):
    state = HealthSignalState(
        business_id=business_id,
        signal_id=signal_id,
        signal_type=signal_type,
        status=status,
        severity=severity,
        title=f"{domain} signal",
        summary="summary",
        payload_json={},
        detected_at=detected_at,
        last_seen_at=last_seen_at,
        updated_at=last_seen_at,
    )
    db_session.add(state)
    db_session.commit()


def test_health_score_determinism(db_session):
    biz = _create_business(db_session)
    now = datetime(2024, 7, 1, tzinfo=timezone.utc)
    _add_state(
        db_session,
        biz.id,
        "sig-1",
        "liquidity.runway_low",
        "liquidity",
        "critical",
        "open",
        now - timedelta(days=7),
        now,
    )
    _add_state(
        db_session,
        biz.id,
        "sig-2",
        "expense.spike_vs_baseline",
        "expense",
        "warning",
        "open",
        now - timedelta(days=3),
        now,
    )

    first = health_score_service.compute_health_score(db_session, biz.id)
    second = health_score_service.compute_health_score(db_session, biz.id)
    first.pop("generated_at", None)
    second.pop("generated_at", None)
    assert first == second


def test_health_score_contributor_ordering(db_session):
    biz = _create_business(db_session)
    now = datetime(2024, 7, 1, tzinfo=timezone.utc)
    _add_state(
        db_session,
        biz.id,
        "sig-a",
        "liquidity.runway_low",
        "liquidity",
        "critical",
        "open",
        now - timedelta(days=10),
        now,
    )
    _add_state(
        db_session,
        biz.id,
        "sig-b",
        "expense.spike_vs_baseline",
        "expense",
        "warning",
        "open",
        now - timedelta(days=2),
        now,
    )

    payload = health_score_service.compute_health_score(db_session, biz.id)
    contributors = payload["contributors"]
    penalties = [item["penalty"] for item in contributors]
    assert penalties == sorted(penalties, reverse=True)
    assert contributors[0]["signal_id"] == "sig-a"


def test_health_score_status_sensitivity(db_session):
    biz = _create_business(db_session)
    now = datetime(2024, 7, 1, tzinfo=timezone.utc)
    _add_state(
        db_session,
        biz.id,
        "sig-1",
        "liquidity.runway_low",
        "liquidity",
        "critical",
        "open",
        now - timedelta(days=5),
        now,
    )

    before = health_score_service.compute_health_score(db_session, biz.id)["score"]

    health_signal_service.update_signal_status(
        db_session,
        biz.id,
        "sig-1",
        status="resolved",
        reason="handled",
        actor="tester",
    )

    after = health_score_service.compute_health_score(db_session, biz.id)["score"]
    assert after > before


def test_health_score_domain_grouping(db_session):
    biz = _create_business(db_session)
    now = datetime(2024, 7, 1, tzinfo=timezone.utc)
    _add_state(
        db_session,
        biz.id,
        "sig-1",
        "revenue.decline_vs_baseline",
        "revenue",
        "warning",
        "open",
        now - timedelta(days=4),
        now,
    )

    payload = health_score_service.compute_health_score(db_session, biz.id)
    revenue_domain = next(domain for domain in payload["domains"] if domain["domain"] == "revenue")
    assert revenue_domain["contributors"]
    penalty_sum = round(sum(item["penalty"] for item in revenue_domain["contributors"]), 2)
    assert penalty_sum == revenue_domain["penalty"]
    assert revenue_domain["score"] == max(0.0, round(100.0 - penalty_sum, 2))
