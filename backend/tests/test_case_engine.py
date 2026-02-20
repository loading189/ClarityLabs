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
    Plan,
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

    response = case_engine_service.list_cases(sqlite_session, business_id=biz.id, status=None, severity=None, domain=None, q=None, sort="activity", sla_breached=None, no_plan=None, plan_overdue=None, opened_since=None, severity_gte=None, page=1, page_size=10)
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


def test_compute_case_state_is_deterministic(sqlite_session):
    biz, user = _seed_business(sqlite_session)
    now = datetime.now(timezone.utc)
    _seed_signal(sqlite_session, biz.id, "sig-det-1")
    case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-det-1",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="high",
        occurred_at=now,
    )
    sqlite_session.add(Plan(business_id=biz.id, case_id=case_id, created_by_user_id=user.id, title="Plan", intent="intent", status="active", created_at=now - timedelta(days=20)))
    sqlite_session.commit()

    t = datetime(2026, 1, 20, tzinfo=timezone.utc)
    first = case_engine_service.compute_case_state(sqlite_session, case_id, now=t)
    second = case_engine_service.compute_case_state(sqlite_session, case_id, now=t)
    assert first == second


def test_recompute_diff_and_apply_emits_single_event(sqlite_session):
    biz, user = _seed_business(sqlite_session)
    now = datetime.now(timezone.utc)
    for idx in range(3):
        sid = f"sig-rec-{idx}"
        _seed_signal(sqlite_session, biz.id, sid)
        case_engine_service.aggregate_signal_into_case(
            sqlite_session,
            business_id=biz.id,
            signal_id=sid,
            signal_type="liquidity.runway_low",
            domain="liquidity",
            severity="medium",
            occurred_at=now - timedelta(days=idx),
        )
    case_id = sqlite_session.query(Case).filter(Case.business_id == biz.id).first().id
    sqlite_session.add(Plan(business_id=biz.id, case_id=case_id, created_by_user_id=user.id, title="Plan", intent="intent", status="active", created_at=now - timedelta(days=20)))
    sqlite_session.commit()

    diff_only = case_engine_service.recompute_case(sqlite_session, case_id, apply=False)
    assert diff_only["applied"] is False
    assert diff_only["diff"]["is_match"] is False
    before = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "CASE_RECOMPUTE_APPLIED").count()

    applied = case_engine_service.recompute_case(sqlite_session, case_id, apply=True)
    sqlite_session.commit()
    assert applied["applied"] is True
    after = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "CASE_RECOMPUTE_APPLIED").count()
    assert after == before + 1


def test_governance_endpoints_emit_one_event(api_client, sqlite_session):
    biz, user = _seed_business(sqlite_session)
    _seed_signal(sqlite_session, biz.id, "sig-gov")
    case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-gov",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="warning",
        occurred_at=datetime.now(timezone.utc),
    )
    sqlite_session.commit()

    headers = {"X-User-Email": user.email}
    assign_resp = api_client.post(f"/api/cases/{case_id}/assign?business_id={biz.id}", json={"assigned_to": "advisor-a", "reason": "ownership"}, headers=headers)
    assert assign_resp.status_code == 200
    review_resp = api_client.post(f"/api/cases/{case_id}/schedule-review?business_id={biz.id}", json={"next_review_at": "2026-01-10T00:00:00Z"}, headers=headers)
    assert review_resp.status_code == 200

    events = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id).all()
    assert len([event for event in events if event.event_type == "CASE_ASSIGNED"]) == 1
    assert len([event for event in events if event.event_type == "CASE_REVIEW_SCHEDULED"]) == 1


def test_list_cases_includes_computed_fields(api_client, sqlite_session):
    biz, user = _seed_business(sqlite_session)
    now = datetime.now(timezone.utc)
    _seed_signal(sqlite_session, biz.id, "sig-list")
    case_id = case_engine_service.aggregate_signal_into_case(
        sqlite_session,
        business_id=biz.id,
        signal_id="sig-list",
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity="critical",
        occurred_at=now - timedelta(days=10),
    )
    sqlite_session.query(Case).filter(Case.id == case_id).update({"opened_at": now - timedelta(days=10)})
    sqlite_session.commit()

    headers = {"X-User-Email": user.email}
    resp = api_client.get(f"/api/cases?business_id={biz.id}&sort=sla", headers=headers)
    assert resp.status_code == 200
    first = resp.json()["items"][0]
    assert "age_days" in first
    assert "sla_breached" in first
