import pytest

pytest.importorskip("httpx")

from datetime import datetime, timedelta, timezone

from backend.app.models import ActionItem, Business, BusinessMembership, HealthSignalState, IntegrationConnection, Organization, RawEvent, User


def test_data_status_endpoint_returns_counts(api_client, sqlite_session):
    org = Organization(name="Org")
    sqlite_session.add(org)
    sqlite_session.flush()
    biz = Business(org_id=org.id, name="Biz")
    sqlite_session.add(biz)
    user = User(email="owner@example.com", name="Owner")
    sqlite_session.add(user)
    sqlite_session.flush()
    sqlite_session.add(BusinessMembership(business_id=biz.id, user_id=user.id, role="owner"))

    now = datetime.now(timezone.utc)
    sqlite_session.add(
        RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id="evt-1",
            occurred_at=now - timedelta(minutes=5),
            payload={"description": "Coffee", "amount": -9.25},
        )
    )
    sqlite_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="sig-1",
            signal_type="cash_low",
            status="open",
            severity="high",
            title="Cash low",
            summary="summary",
            payload_json={},
            detected_at=now,
            last_seen_at=now,
            updated_at=now,
        )
    )
    sqlite_session.add(
        ActionItem(
            business_id=biz.id,
            action_type="investigate_anomaly",
            title="Investigate",
            summary="summary",
            priority=4,
            status="open",
            created_at=now,
            updated_at=now,
            idempotency_key=f"{biz.id}:k",
        )
    )
    sqlite_session.add(
        IntegrationConnection(
            business_id=biz.id,
            provider="plaid",
            status="connected",
            last_sync_at=now,
        )
    )
    sqlite_session.commit()

    resp = api_client.get(f"/api/diagnostics/status/{biz.id}", headers={"X-User-Email": user.email})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["latest_event"]["source"] == "plaid"
    assert payload["open_signals"] == 1
    assert payload["open_actions"] == 1
    assert payload["ledger_rows"] == 1
    assert payload["last_sync_at"]
