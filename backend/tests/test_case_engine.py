import backend.app.sim.models  # noqa: F401
from datetime import datetime, timedelta, timezone

from backend.app.models import (
    Business,
    BusinessMembership,
    Case,
    CaseEvent,
    CaseSignal,
    HealthSignalState,
    Organization,
    User,
)
from fastapi import HTTPException

from backend.app.services import case_engine_service
from backend.app.services.plan_service import create_plan


def _seed_business(db):
    suffix = datetime.now(timezone.utc).timestamp()
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    user = User(email=f"case{suffix}@test.com", name="case")
    db.add(user)
    db.flush()
    db.add(BusinessMembership(business_id=biz.id, user_id=user.id, role="owner"))
    db.commit()
    return biz, user


def _seed_signal(db, business_id: str, signal_id: str, signal_type: str = "liquidity.runway_low", severity: str = "warning"):
    now = datetime.now(timezone.utc)
    db.add(
        HealthSignalState(
            business_id=business_id,
            signal_id=signal_id,
            signal_type=signal_type,
            status="open",
            severity=severity,
            title=signal_type,
            summary="summary",
            payload_json={},
            detected_at=now,
            last_seen_at=now,
            updated_at=now,
        )
    )
    db.commit()


def test_case_aggregation_idempotent(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    _seed_signal(sqlite_session, biz.id, "sig-1")

    case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-1",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="warning",
        occurred_at=datetime.now(timezone.utc),
    )
    same_case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-1",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="warning",
        occurred_at=datetime.now(timezone.utc),
    )
    sqlite_session.commit()

    assert case_id == same_case_id
    assert sqlite_session.query(CaseSignal).filter(CaseSignal.business_id == biz.id, CaseSignal.signal_id == "sig-1").count() == 1
    assert sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "SIGNAL_ATTACHED").count() == 1


def test_case_escalation_by_signal_volume(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    now = datetime.now(timezone.utc)
    for idx in range(3):
        signal_id = f"sig-{idx}"
        _seed_signal(sqlite_session, biz.id, signal_id)
        case_engine_service.aggregate_signal_into_case(
            sqlite_session,
            business_id=biz.id,
            signal_id=signal_id,
            signal_type="liquidity.runway_low",
            domain="liquidity",
            severity="medium",
            occurred_at=now - timedelta(days=idx),
        )
    sqlite_session.commit()

    response = case_engine_service.list_cases(sqlite_session, business_id=biz.id, status=None, severity=None, domain=None, q=None, sort="activity", page=1, page_size=10)
    case_id = response["items"][0]["id"]
    events = case_engine_service.case_timeline(sqlite_session, case_id)
    escalations = [event for event in events if event["event_type"] == "CASE_ESCALATED"]
    assert len(escalations) == 1


def test_cases_api_list_and_timeline(api_client, sqlite_session):
    biz, user = _seed_business(sqlite_session)
    _seed_signal(sqlite_session, biz.id, "sig-api")
    case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-api",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="warning",
        occurred_at=datetime.now(timezone.utc),
    )
    sqlite_session.commit()

    headers = {"X-User-Email": user.email}
    list_resp = api_client.get(f"/api/cases?business_id={biz.id}", headers=headers)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["items"][0]["id"] == case_id

    timeline_resp = api_client.get(f"/api/cases/{case_id}/timeline?business_id={biz.id}", headers=headers)
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()
    assert timeline == sorted(timeline, key=lambda row: (row["created_at"], row["id"]))


def test_plan_requires_case(sqlite_session):
    biz, user = _seed_business(sqlite_session)
    try:
        create_plan(
            sqlite_session,
            business_id=biz.id,
            created_by_user_id=user.id,
            title="Plan",
            intent="intent",
            case_id=None,
            source_action_id=None,
            primary_signal_id=None,
            assigned_to_user_id=None,
            idempotency_key=None,
            conditions=[
                {
                    "type": "metric_delta",
                    "metric_key": "health_score",
                    "baseline_window_days": 7,
                    "evaluation_window_days": 7,
                    "threshold": 1.0,
                    "direction": "improve",
                }
            ],
        )
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400


def test_attach_signal_to_different_case_raises_invariant(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    now = datetime.now(timezone.utc)
    _seed_signal(sqlite_session, biz.id, "sig-1")

    case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-1",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="warning",
        occurred_at=now,
    )
    other_case = Case(
        business_id=biz.id,
        domain="liquidity",
        primary_signal_type="liquidity.runway_low",
        severity="warning",
        status="open",
        opened_at=now,
        last_activity_at=now,
    )
    sqlite_session.add(other_case)
    sqlite_session.flush()

    event_count_before = sqlite_session.query(CaseEvent).filter(CaseEvent.event_type == "SIGNAL_ATTACHED").count()

    try:
        case_engine_service._attach_signal_to_case(
            sqlite_session,
            case=other_case,
            business_id=biz.id,
            signal_id="sig-1",
            signal_type="liquidity.runway_low",
            domain="liquidity",
            severity="warning",
            occurred_at=now,
        )
        assert False, "expected CaseSignalInvariantError"
    except case_engine_service.CaseSignalInvariantError as exc:
        assert "Invariant violation" in str(exc)

    assert sqlite_session.query(CaseSignal).filter(CaseSignal.business_id == biz.id, CaseSignal.signal_id == "sig-1").count() == 1
    assert sqlite_session.query(CaseSignal).filter(CaseSignal.case_id == case_id).count() == 1
    assert sqlite_session.query(CaseSignal).filter(CaseSignal.case_id == other_case.id).count() == 0
    event_count_after = sqlite_session.query(CaseEvent).filter(CaseEvent.event_type == "SIGNAL_ATTACHED").count()
    assert event_count_after == event_count_before
