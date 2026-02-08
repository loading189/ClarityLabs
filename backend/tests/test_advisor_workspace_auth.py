from datetime import datetime, timezone

import pytest

pytest.importorskip("httpx")

from backend.app.models import ActionItem, ActionStateEvent, Business, BusinessMembership, Organization, RawEvent, User


def _create_business(session) -> Business:
    org = Organization(name="Advisor Org")
    session.add(org)
    session.flush()
    biz = Business(org_id=org.id, name="Advisor Biz")
    session.add(biz)
    session.flush()
    return biz


def _create_user(session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def _add_membership(session, business_id: str, user_id: str, role: str):
    membership = BusinessMembership(business_id=business_id, user_id=user_id, role=role)
    session.add(membership)
    session.flush()
    return membership


def _seed_action(session, business_id: str) -> ActionItem:
    now = datetime.now(timezone.utc)
    action = ActionItem(
        business_id=business_id,
        action_type="fix_mapping",
        title="Categorize new transactions",
        summary="Summary",
        priority=3,
        status="open",
        created_at=now,
        updated_at=now,
        idempotency_key=f"{business_id}:fix_mapping:none:all:{now.date().isoformat()}:uncategorized",
    )
    session.add(action)
    session.flush()
    return action


def test_user_auto_create_via_header(api_client, sqlite_session):
    resp = api_client.get("/api/me", headers={"X-User-Email": "new-user@example.com"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["email"] == "new-user@example.com"
    user = sqlite_session.query(User).filter(User.email == "new-user@example.com").first()
    assert user is not None


def test_missing_header_returns_401(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    sqlite_session.commit()

    resp = api_client.get(f"/api/actions/{biz.id}")
    assert resp.status_code == 401


def test_membership_enforced(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "viewer@example.com")
    sqlite_session.commit()

    resp = api_client.get(f"/api/actions/{biz.id}", headers={"X-User-Email": user.email})
    assert resp.status_code == 403


def test_viewer_cannot_resolve_or_assign(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    viewer = _create_user(sqlite_session, "viewer@example.com")
    _add_membership(sqlite_session, biz.id, viewer.id, role="viewer")
    action = _seed_action(sqlite_session, biz.id)
    sqlite_session.commit()

    resolve = api_client.post(
        f"/api/actions/{biz.id}/{action.id}/resolve",
        json={"status": "done", "resolution_reason": "Reviewed"},
        headers={"X-User-Email": viewer.email},
    )
    assert resolve.status_code == 403

    assign = api_client.post(
        f"/api/actions/{biz.id}/{action.id}/assign",
        json={"assigned_to_user_id": viewer.id},
        headers={"X-User-Email": viewer.email},
    )
    assert assign.status_code == 403


def test_advisor_can_resolve_and_assign(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    advisor = _create_user(sqlite_session, "advisor@example.com")
    _add_membership(sqlite_session, biz.id, advisor.id, role="advisor")
    action = _seed_action(sqlite_session, biz.id)
    sqlite_session.commit()

    assign = api_client.post(
        f"/api/actions/{biz.id}/{action.id}/assign",
        json={"assigned_to_user_id": advisor.id},
        headers={"X-User-Email": advisor.email},
    )
    assert assign.status_code == 200
    assert assign.json()["assigned_to_user_id"] == advisor.id

    resolve = api_client.post(
        f"/api/actions/{biz.id}/{action.id}/resolve",
        json={"status": "done", "resolution_reason": "Reviewed", "resolution_note": "Checked docs"},
        headers={"X-User-Email": advisor.email},
    )
    assert resolve.status_code == 200
    payload = resolve.json()
    assert payload["status"] == "done"
    assert payload["resolved_by_user_id"] == advisor.id

    events = sqlite_session.query(ActionStateEvent).filter(ActionStateEvent.action_id == action.id).all()
    assert len(events) == 1
    assert events[0].from_status == "open"
    assert events[0].to_status == "done"


def test_triage_filters(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    advisor = _create_user(sqlite_session, "advisor@example.com")
    staff = _create_user(sqlite_session, "staff@example.com")
    _add_membership(sqlite_session, biz.id, advisor.id, role="advisor")
    _add_membership(sqlite_session, biz.id, staff.id, role="staff")
    action_assigned = _seed_action(sqlite_session, biz.id)
    action_assigned.assigned_to_user_id = advisor.id
    action_unassigned = _seed_action(sqlite_session, biz.id)
    sqlite_session.commit()

    resp_me = api_client.get(
        f"/api/actions/{biz.id}/triage?assigned=me",
        headers={"X-User-Email": advisor.email},
    )
    assert resp_me.status_code == 200
    actions_me = resp_me.json()["actions"]
    assert len(actions_me) == 1
    assert actions_me[0]["id"] == action_assigned.id

    resp_unassigned = api_client.get(
        f"/api/actions/{biz.id}/triage?assigned=unassigned",
        headers={"X-User-Email": staff.email},
    )
    assert resp_unassigned.status_code == 200
    actions_unassigned = resp_unassigned.json()["actions"]
    assert len(actions_unassigned) == 1
    assert actions_unassigned[0]["id"] == action_unassigned.id


def test_action_refresh_determinism(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    advisor = _create_user(sqlite_session, "advisor@example.com")
    owner = _create_user(sqlite_session, "owner@example.com")
    _add_membership(sqlite_session, biz.id, advisor.id, role="advisor")
    _add_membership(sqlite_session, biz.id, owner.id, role="owner")
    sqlite_session.add(
        RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id="uncat-1",
            occurred_at=datetime.now(timezone.utc),
            payload={"amount": -12.0, "description": "Uncategorized Vendor"},
        )
    )
    sqlite_session.commit()

    first = api_client.post(
        f"/api/actions/{biz.id}/refresh",
        headers={"X-User-Email": advisor.email},
    )
    second = api_client.post(
        f"/api/actions/{biz.id}/refresh",
        headers={"X-User-Email": owner.email},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_ids = sorted(item["idempotency_key"] for item in first.json()["actions"])
    second_ids = sorted(item["idempotency_key"] for item in second.json()["actions"])
    assert first_ids == second_ids
