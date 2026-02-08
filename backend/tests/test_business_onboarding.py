from __future__ import annotations

import pytest

from backend.app.models import Business, BusinessMembership, Organization, User

pytest.importorskip("httpx")


def _create_business(session, name: str = "Test Biz") -> Business:
    org = Organization(name="Test Org")
    session.add(org)
    session.flush()
    biz = Business(org_id=org.id, name=name)
    session.add(biz)
    session.flush()
    return biz


def _create_user(session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def _add_membership(session, business_id: str, user_id: str, role: str = "owner") -> BusinessMembership:
    membership = BusinessMembership(business_id=business_id, user_id=user_id, role=role)
    session.add(membership)
    session.flush()
    return membership


def test_create_business_creates_owner_membership(api_client, sqlite_session):
    resp = api_client.post(
        "/api/businesses",
        json={"name": "Acme Co"},
        headers={"X-User-Email": "owner@example.com"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["business"]["name"] == "Acme Co"
    assert payload["membership"]["role"] == "owner"

    user = sqlite_session.query(User).filter(User.email == "owner@example.com").first()
    assert user is not None
    membership = (
        sqlite_session.query(BusinessMembership)
        .filter(
            BusinessMembership.user_id == user.id,
            BusinessMembership.business_id == payload["business"]["id"],
        )
        .first()
    )
    assert membership is not None
    assert membership.role == "owner"


def test_list_my_businesses_filters_to_memberships(api_client, sqlite_session):
    biz_one = _create_business(sqlite_session, name="Biz One")
    _create_business(sqlite_session, name="Biz Two")
    user = _create_user(sqlite_session, "member@example.com")
    _add_membership(sqlite_session, biz_one.id, user.id, role="advisor")
    sqlite_session.commit()

    resp = api_client.get("/api/businesses/mine", headers={"X-User-Email": user.email})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["business_id"] == biz_one.id
    assert payload[0]["role"] == "advisor"


def test_membership_required_for_business_scoped(api_client, sqlite_session):
    biz = _create_business(sqlite_session)
    sqlite_session.commit()

    no_header = api_client.get(f"/api/businesses/{biz.id}/members")
    assert no_header.status_code == 401

    non_member = api_client.get(
        f"/api/businesses/{biz.id}/members",
        headers={"X-User-Email": "someone@example.com"},
    )
    assert non_member.status_code == 403


def test_join_business_gated_by_pilot_mode(api_client, sqlite_session, monkeypatch):
    biz = _create_business(sqlite_session)
    sqlite_session.commit()

    resp = api_client.post(
        f"/api/businesses/{biz.id}/join",
        json={},
        headers={"X-User-Email": "joiner@example.com"},
    )
    assert resp.status_code == 404

    monkeypatch.setenv("PILOT_DEV_MODE", "1")
    resp = api_client.post(
        f"/api/businesses/{biz.id}/join",
        json={"role": "staff"},
        headers={"X-User-Email": "joiner@example.com"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["business_id"] == biz.id
    assert payload["role"] == "staff"


def test_delete_business_requires_owner_and_flag(api_client, sqlite_session, monkeypatch):
    biz = _create_business(sqlite_session)
    owner = _create_user(sqlite_session, "owner-delete@example.com")
    _add_membership(sqlite_session, biz.id, owner.id, role="owner")
    sqlite_session.commit()

    disabled = api_client.delete(
        f"/api/businesses/{biz.id}?confirm=true",
        headers={"X-User-Email": owner.email},
    )
    assert disabled.status_code == 403

    monkeypatch.setenv("ALLOW_BUSINESS_DELETE", "1")
    deleted = api_client.delete(
        f"/api/businesses/{biz.id}?confirm=true",
        headers={"X-User-Email": owner.email},
    )
    assert deleted.status_code == 200

    resp = api_client.get("/api/businesses/mine", headers={"X-User-Email": owner.email})
    assert resp.status_code == 200
    assert resp.json() == []
