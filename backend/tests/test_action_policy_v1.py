from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("httpx")

from backend.app.models import ActionItem, AuditLog, Business, BusinessMembership, HealthSignalState, Organization, User
import backend.app.sim.models  # noqa: F401
from backend.app.services.actions_service import generate_actions_for_business


def _create_business(session) -> Business:
    org = Organization(name="Policy Org")
    session.add(org)
    session.flush()
    biz = Business(org_id=org.id, name="Policy Biz")
    session.add(biz)
    session.flush()
    return biz


def _create_user(session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def _add_membership(session, business_id: str, user_id: str, role: str = "advisor"):
    session.add(BusinessMembership(business_id=business_id, user_id=user_id, role=role))
    session.flush()


def _signal_payload() -> dict:
    return {
        "detector_version": "v1",
        "vendor": "Acme",
        "ledger_anchors": [
            {"label": "Anchor", "query": {"source_event_ids": ["e1"], "direction": "outflow"}, "evidence_keys": ["a"]}
        ],
    }


def _seed_open_signal(session, business_id: str, *, now: datetime, signal_id: str = "sig-1", severity: str = "warning"):
    state = HealthSignalState(
        business_id=business_id,
        signal_id=signal_id,
        signal_type="expense.spike_vs_baseline",
        fingerprint="fp-1",
        status="open",
        severity=severity,
        title="Signal",
        summary="Review this signal",
        payload_json=_signal_payload(),
        detected_at=now - timedelta(hours=30),
        last_seen_at=now,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state


def _add_audit(session, business_id: str, *, signal_id: str, status: str, event_type: str, created_at: datetime):
    session.add(
        AuditLog(
            business_id=business_id,
            event_type=event_type,
            actor="system",
            reason="test",
            before_state={"signal_id": signal_id, "status": status},
            after_state={"signal_id": signal_id, "status": status},
            created_at=created_at,
        )
    )


def test_action_policy_idempotency(sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    _seed_open_signal(sqlite_session, biz.id, now=now)
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=30))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_updated", created_at=now - timedelta(hours=2))
    sqlite_session.commit()

    first = generate_actions_for_business(sqlite_session, biz.id, now=now)
    sqlite_session.commit()
    second = generate_actions_for_business(sqlite_session, biz.id, now=now + timedelta(minutes=1))
    sqlite_session.commit()

    open_actions = (
        sqlite_session.query(ActionItem)
        .filter(ActionItem.business_id == biz.id, ActionItem.status == "open", ActionItem.action_type == "investigate_anomaly")
        .all()
    )
    assert len(open_actions) == 1
    assert first.created_count == 1
    assert second.created_count == 0


def test_action_policy_persistence_threshold(sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    state = _seed_open_signal(sqlite_session, biz.id, now=now)
    state.detected_at = now - timedelta(hours=2)
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=2))
    sqlite_session.commit()

    result = generate_actions_for_business(sqlite_session, biz.id, now=now)

    assert result.created_count == 0
    assert result.suppressed_count >= 1
    assert "persistence_min_age" in result.suppression_reasons


def test_action_policy_flap_suppression(sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    _seed_open_signal(sqlite_session, biz.id, now=now)
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=30))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="resolved", event_type="signal_resolved", created_at=now - timedelta(hours=20))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=16))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="resolved", event_type="signal_resolved", created_at=now - timedelta(hours=12))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=8))
    sqlite_session.commit()

    result = generate_actions_for_business(sqlite_session, biz.id, now=now)

    assert result.created_count == 0
    assert result.suppression_reasons.get("flapping", 0) >= 1


def test_action_policy_cooldown_after_resolve(sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    _seed_open_signal(sqlite_session, biz.id, now=now, severity="warning")
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=30))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_updated", created_at=now - timedelta(hours=2))
    sqlite_session.commit()

    created = generate_actions_for_business(sqlite_session, biz.id, now=now)
    sqlite_session.commit()
    action = sqlite_session.query(ActionItem).filter(ActionItem.business_id == biz.id).one()
    action.status = "done"
    action.resolved_at = now - timedelta(hours=1)
    sqlite_session.commit()

    suppressed = generate_actions_for_business(sqlite_session, biz.id, now=now + timedelta(minutes=10))
    sqlite_session.commit()
    refreshed = sqlite_session.query(ActionItem).filter(ActionItem.id == action.id).one()
    assert created.created_count == 1
    assert suppressed.suppression_reasons.get("cooldown_after_resolve", 0) >= 1
    assert refreshed.status == "done"

    state = sqlite_session.query(HealthSignalState).filter(HealthSignalState.business_id == biz.id).one()
    state.severity = "critical"
    state.updated_at = now + timedelta(minutes=20)
    _add_audit(
        sqlite_session,
        biz.id,
        signal_id="sig-1",
        status="open",
        event_type="signal_updated",
        created_at=now + timedelta(minutes=20),
    )
    sqlite_session.commit()

    escalated = generate_actions_for_business(sqlite_session, biz.id, now=now + timedelta(minutes=21))
    sqlite_session.commit()
    reopened = sqlite_session.query(ActionItem).filter(ActionItem.id == action.id).one()
    assert escalated.updated_count >= 1
    assert reopened.status == "open"


def test_refresh_api_returns_policy_counts(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    advisor = _create_user(sqlite_session, "policy-advisor@example.com")
    _add_membership(sqlite_session, biz.id, advisor.id)
    _seed_open_signal(sqlite_session, biz.id, now=now)
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_detected", created_at=now - timedelta(hours=30))
    _add_audit(sqlite_session, biz.id, signal_id="sig-1", status="open", event_type="signal_updated", created_at=now - timedelta(hours=2))
    sqlite_session.commit()

    resp = api_client.post(f"/api/actions/{biz.id}/refresh", headers={"X-User-Email": advisor.email})
    assert resp.status_code == 200
    payload = resp.json()
    assert "created_count" in payload
    assert "updated_count" in payload
    assert "suppressed_count" in payload
    assert isinstance(payload.get("suppression_reasons"), dict)
