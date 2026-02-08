from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("httpx")

from backend.app.models import (
    ActionItem,
    AssistantMessage,
    Business,
    BusinessMembership,
    HealthSignalState,
    Organization,
    Plan,
    PlanStateEvent,
    User,
)


def _create_business(session) -> Business:
    org = Organization(name="Plan Org")
    session.add(org)
    session.flush()
    biz = Business(org_id=org.id, name="Plan Biz")
    session.add(biz)
    session.flush()
    return biz


def _create_user(session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def _add_membership(session, business_id: str, user_id: str, role: str = "staff"):
    membership = BusinessMembership(business_id=business_id, user_id=user_id, role=role)
    session.add(membership)
    session.flush()
    return membership


def _seed_daily_brief(session, business_id: str, target_date: datetime, health_score: float):
    session.add(
        AssistantMessage(
            business_id=business_id,
            author="system",
            kind="daily_brief",
            content_json={
                "business_id": business_id,
                "date": target_date.date().isoformat(),
                "generated_at": target_date.isoformat(),
                "headline": "Daily brief",
                "summary_bullets": [],
                "priorities": [],
                "metrics": {
                    "health_score": health_score,
                },
                "links": {},
            },
        )
    )


def _plan_payload(business_id: str, signal_id: str | None = None):
    condition = {
        "type": "signal_resolved",
        "signal_id": signal_id,
        "baseline_window_days": 0,
        "evaluation_window_days": 3,
        "direction": "resolve",
    }
    return {
        "business_id": business_id,
        "title": "Stabilize cash",
        "intent": "Reduce variance in weekly cash flow.",
        "conditions": [condition],
    }


def test_plan_create_requires_membership(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "viewer@example.com")
    sqlite_session.commit()

    resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": user.email},
        json=_plan_payload(biz.id, "signal-1"),
    )
    assert resp.status_code == 403


def test_plan_lifecycle_activate_refresh_close(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "staff@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="staff")
    sqlite_session.commit()

    create_resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": user.email},
        json=_plan_payload(biz.id, "signal-1"),
    )
    assert create_resp.status_code == 200
    plan_id = create_resp.json()["plan"]["id"]
    assert create_resp.json()["plan"]["status"] == "draft"

    activate_resp = api_client.post(
        f"/api/plans/{plan_id}/activate",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["plan"]["status"] == "active"

    refresh_resp = api_client.post(
        f"/api/plans/{plan_id}/refresh",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["observation"]["verdict"] in {"success", "no_change"}

    close_resp = api_client.post(
        f"/api/plans/{plan_id}/close",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
        json={"outcome": "succeeded", "note": "Completed"},
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["plan"]["status"] == "succeeded"


def test_plan_refresh_signal_resolved_success_candidate(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "staff2@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="staff")
    sqlite_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="signal-2",
            signal_type="cash_low",
            status="resolved",
            resolved_at=now - timedelta(days=4),
            updated_at=now - timedelta(days=4),
        )
    )
    sqlite_session.commit()

    create_resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": user.email},
        json=_plan_payload(biz.id, "signal-2"),
    )
    plan_id = create_resp.json()["plan"]["id"]

    api_client.post(
        f"/api/plans/{plan_id}/activate",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )

    plan = sqlite_session.get(Plan, plan_id)
    plan.activated_at = now - timedelta(days=4)
    sqlite_session.commit()

    refresh_resp = api_client.post(
        f"/api/plans/{plan_id}/refresh",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )
    assert refresh_resp.status_code == 200
    payload = refresh_resp.json()
    assert payload["success_candidate"] is True
    assert payload["observation"]["verdict"] == "success"


def test_plan_refresh_metric_delta_improves(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "staff3@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="staff")
    sqlite_session.commit()

    create_resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": user.email},
        json={
            "business_id": biz.id,
            "title": "Improve score",
            "intent": "Increase health score",
            "conditions": [
                {
                    "type": "metric_delta",
                    "metric_key": "health_score",
                    "baseline_window_days": 3,
                    "evaluation_window_days": 3,
                    "threshold": 2.0,
                    "direction": "improve",
                }
            ],
        },
    )
    plan_id = create_resp.json()["plan"]["id"]

    api_client.post(
        f"/api/plans/{plan_id}/activate",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )

    activated_at = now - timedelta(days=3)
    plan = sqlite_session.get(Plan, plan_id)
    plan.activated_at = activated_at

    baseline_dates = [activated_at - timedelta(days=3), activated_at - timedelta(days=2), activated_at - timedelta(days=1)]
    evaluation_dates = [activated_at, activated_at + timedelta(days=1), activated_at + timedelta(days=2)]
    for dt in baseline_dates:
        _seed_daily_brief(sqlite_session, biz.id, dt, 10.0)
    for dt in evaluation_dates:
        _seed_daily_brief(sqlite_session, biz.id, dt, 15.0)
    sqlite_session.commit()

    refresh_resp = api_client.post(
        f"/api/plans/{plan_id}/refresh",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )
    assert refresh_resp.status_code == 200
    payload = refresh_resp.json()
    assert payload["success_candidate"] is True
    assert payload["observation"]["metric_delta"] > 0


def test_plan_state_events_logged(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "staff4@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="staff")
    sqlite_session.commit()

    create_resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": user.email},
        json=_plan_payload(biz.id, "signal-3"),
    )
    plan_id = create_resp.json()["plan"]["id"]

    api_client.post(
        f"/api/plans/{plan_id}/activate",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
    )
    api_client.post(
        f"/api/plans/{plan_id}/note",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
        json={"note": "Reviewed baseline"},
    )
    api_client.post(
        f"/api/plans/{plan_id}/assign",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
        json={"assigned_to_user_id": user.id},
    )
    api_client.post(
        f"/api/plans/{plan_id}/close",
        headers={"X-User-Email": user.email},
        params={"business_id": biz.id},
        json={"outcome": "canceled"},
    )

    events = sqlite_session.query(PlanStateEvent).filter(PlanStateEvent.plan_id == plan_id).all()
    event_types = {event.event_type for event in events}
    assert {"created", "activated", "note_added", "assigned", "canceled"}.issubset(event_types)


def test_action_to_plan_linkage(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "staff5@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="staff")
    action = ActionItem(
        business_id=biz.id,
        action_type="fix_mapping",
        title="Categorize",
        summary="Needs work",
        priority=3,
        status="open",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        idempotency_key="plan-link",
    )
    sqlite_session.add(action)
    sqlite_session.commit()

    create_resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": user.email},
        json={
            "business_id": biz.id,
            "title": "Link plan",
            "intent": "Tie to action",
            "source_action_id": action.id,
            "conditions": [
                {
                    "type": "metric_delta",
                    "metric_key": "health_score",
                    "baseline_window_days": 1,
                    "evaluation_window_days": 1,
                    "threshold": 0.0,
                    "direction": "improve",
                }
            ],
        },
    )
    assert create_resp.status_code == 200

    list_resp = api_client.get(
        f"/api/actions/{biz.id}",
        headers={"X-User-Email": user.email},
    )
    assert list_resp.status_code == 200
    actions = list_resp.json()["actions"]
    matched = next(item for item in actions if item["id"] == action.id)
    assert matched["plan_id"] == create_resp.json()["plan"]["id"]


def test_plan_rbac_viewer_can_read(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    staff_user = _create_user(sqlite_session, "staff6@example.com")
    viewer_user = _create_user(sqlite_session, "viewer6@example.com")
    _add_membership(sqlite_session, biz.id, staff_user.id, role="staff")
    _add_membership(sqlite_session, biz.id, viewer_user.id, role="viewer")
    sqlite_session.commit()

    create_resp = api_client.post(
        "/api/plans",
        headers={"X-User-Email": staff_user.email},
        json=_plan_payload(biz.id, "signal-4"),
    )
    plan_id = create_resp.json()["plan"]["id"]

    list_resp = api_client.get(
        "/api/plans",
        headers={"X-User-Email": viewer_user.email},
        params={"business_id": biz.id},
    )
    assert list_resp.status_code == 200

    detail_resp = api_client.get(
        f"/api/plans/{plan_id}",
        headers={"X-User-Email": viewer_user.email},
        params={"business_id": biz.id},
    )
    assert detail_resp.status_code == 200

    activate_resp = api_client.post(
        f"/api/plans/{plan_id}/activate",
        headers={"X-User-Email": viewer_user.email},
        params={"business_id": biz.id},
    )
    assert activate_resp.status_code == 403
