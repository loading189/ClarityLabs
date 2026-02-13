from datetime import datetime, timezone

import pytest

pytest.importorskip("httpx")

from backend.app.models import ActionItem, Business, BusinessMembership, HealthSignalState, Organization, Plan, User


def _create_business(session) -> Business:
    org = Organization(name="Case Org")
    session.add(org)
    session.flush()
    biz = Business(org_id=org.id, name="Case Biz")
    session.add(biz)
    session.flush()
    return biz


def _create_user(session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def _add_membership(session, business_id: str, user_id: str, role: str = "staff"):
    row = BusinessMembership(business_id=business_id, user_id=user_id, role=role)
    session.add(row)
    session.flush()
    return row


def _create_action(session, business_id: str, *, source_signal_id: str | None = "sig-1") -> ActionItem:
    now = datetime.now(timezone.utc)
    action = ActionItem(
        business_id=business_id,
        action_type="investigate_anomaly",
        title="Cash anomaly",
        summary="Investigate a cash anomaly.",
        priority=4,
        status="open",
        created_at=now,
        updated_at=now,
        source_signal_id=source_signal_id,
        evidence_json={"signal_type": "cash_low"},
        idempotency_key=f"{business_id}:action:1",
    )
    session.add(action)
    session.flush()
    return action


def test_plan_from_action_is_idempotent_and_links_action(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "staff@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="staff")
    action = _create_action(sqlite_session, biz.id)
    sqlite_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="sig-1",
            signal_type="cash_low",
            status="open",
            title="Cash low",
            summary="Cash is low.",
        )
    )
    sqlite_session.commit()

    first = api_client.post(
        f"/api/plans/{biz.id}/from_action",
        headers={"X-User-Email": user.email},
        json={"action_id": action.id},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["created"] is True

    second = api_client.post(
        f"/api/plans/{biz.id}/from_action",
        headers={"X-User-Email": user.email},
        json={"action_id": action.id},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["created"] is False
    assert second_payload["plan_id"] == first_payload["plan_id"]

    plan = sqlite_session.get(Plan, first_payload["plan_id"])
    assert plan is not None
    assert plan.business_id == biz.id
    assert plan.source_action_id == action.id
    assert plan.primary_signal_id == "sig-1"
    assert plan.title.startswith("Remediation: ")
    assert plan.intent == "prevent cash shortfall"

    detail = api_client.get(
        f"/api/plans/{first_payload['plan_id']}",
        params={"business_id": biz.id},
        headers={"X-User-Email": user.email},
    )
    assert detail.status_code == 200
    conditions = detail.json()["conditions"]
    assert len(conditions) >= 2

    actions = api_client.get(
        f"/api/actions/{biz.id}",
        headers={"X-User-Email": user.email},
    )
    assert actions.status_code == 200
    linked = next(item for item in actions.json()["actions"] if item["id"] == action.id)
    assert linked["plan_id"] == first_payload["plan_id"]


def test_plan_from_action_requires_membership(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    member = _create_user(sqlite_session, "member@example.com")
    outsider = _create_user(sqlite_session, "outsider@example.com")
    _add_membership(sqlite_session, biz.id, member.id, role="staff")
    action = _create_action(sqlite_session, biz.id)
    sqlite_session.commit()

    ok = api_client.post(
        f"/api/plans/{biz.id}/from_action",
        headers={"X-User-Email": member.email},
        json={"action_id": action.id},
    )
    assert ok.status_code == 200

    denied = api_client.post(
        f"/api/plans/{biz.id}/from_action",
        headers={"X-User-Email": outsider.email},
        json={"action_id": action.id},
    )
    assert denied.status_code == 403
