from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("httpx")

from backend.app.models import (
    Account,
    ActionItem,
    BusinessMembership,
    Business,
    Category,
    HealthSignalState,
    IntegrationConnection,
    Organization,
    RawEvent,
    TxnCategorization,
    User,
)


def _create_business(session) -> Business:
    org = Organization(name="Action Org")
    session.add(org)
    session.flush()
    biz = Business(org_id=org.id, name="Action Biz")
    session.add(biz)
    session.flush()
    return biz


def _seed_account_and_category(session, business_id: str) -> Category:
    account = Account(
        business_id=business_id,
        name="Operating Cash",
        type="asset",
        subtype="cash",
    )
    session.add(account)
    session.flush()
    category = Category(
        business_id=business_id,
        name="Supplies",
        account_id=account.id,
    )
    session.add(category)
    session.flush()
    return category


def _seed_posted_txn(
    session,
    *,
    business_id: str,
    category_id: str,
    source_event_id: str,
    occurred_at: datetime,
    description: str,
    amount: float,
):
    event = RawEvent(
        business_id=business_id,
        source="plaid",
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        payload={"amount": amount, "description": description},
    )
    session.add(event)
    session.add(
        TxnCategorization(
            business_id=business_id,
            source_event_id=source_event_id,
            category_id=category_id,
            created_at=occurred_at,
        )
    )

def _create_user(session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def _add_membership(session, business_id: str, user_id: str, role: str = "owner"):
    membership = BusinessMembership(business_id=business_id, user_id=user_id, role=role)
    session.add(membership)
    session.flush()
    return membership


def test_refresh_creates_actions(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "owner@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="owner")
    category = _seed_account_and_category(sqlite_session, biz.id)

    sqlite_session.add(
        IntegrationConnection(
            business_id=biz.id,
            provider="plaid",
            status="connected",
            last_sync_at=now - timedelta(hours=24),
        )
    )

    sqlite_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="signal-1",
            signal_type="cash_low",
            status="open",
            severity="high",
            title="Cash balance dipped",
            summary="Cash balance dropped below threshold.",
            payload_json={
                "ledger_anchors": [
                    {
                        "label": "Low cash window",
                        "query": {
                            "start_date": (now - timedelta(days=7)).date().isoformat(),
                            "end_date": now.date().isoformat(),
                            "source_event_ids": ["evt-anchor"],
                        },
                    }
                ]
            },
            detected_at=now - timedelta(days=1),
            last_seen_at=now,
            updated_at=now,
        )
    )

    sqlite_session.add(
        RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id="uncat-1",
            occurred_at=now - timedelta(days=2),
            payload={"amount": -42.0, "description": "Uncategorized Vendor"},
        )
    )

    _seed_posted_txn(
        sqlite_session,
        business_id=biz.id,
        category_id=category.id,
        source_event_id="vendor-baseline",
        occurred_at=now - timedelta(days=30),
        description="Big Vendor",
        amount=-100.0,
    )
    _seed_posted_txn(
        sqlite_session,
        business_id=biz.id,
        category_id=category.id,
        source_event_id="vendor-recent",
        occurred_at=now - timedelta(days=7),
        description="Big Vendor",
        amount=-450.0,
    )

    sqlite_session.commit()

    resp = api_client.post(
        f"/api/actions/{biz.id}/refresh",
        headers={"X-User-Email": user.email},
    )
    assert resp.status_code == 200
    payload = resp.json()
    action_types = {item["action_type"] for item in payload["actions"]}
    assert "fix_mapping" in action_types
    assert "investigate_anomaly" in action_types
    assert "sync_integration" in action_types
    assert "review_vendor" in action_types


def test_refresh_is_idempotent(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "owner@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="owner")
    sqlite_session.add(
        RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id="uncat-1",
            occurred_at=now - timedelta(days=1),
            payload={"amount": -12.0, "description": "Uncategorized Vendor"},
        )
    )
    sqlite_session.commit()

    resp = api_client.post(
        f"/api/actions/{biz.id}/refresh",
        headers={"X-User-Email": user.email},
    )
    assert resp.status_code == 200
    resp = api_client.post(
        f"/api/actions/{biz.id}/refresh",
        headers={"X-User-Email": user.email},
    )
    assert resp.status_code == 200

    count = sqlite_session.query(ActionItem).filter(ActionItem.business_id == biz.id).count()
    assert count == 1


def test_resolve_updates_status(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "advisor@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="advisor")
    sqlite_session.add(
        ActionItem(
            business_id=biz.id,
            action_type="fix_mapping",
            title="Categorize new transactions",
            summary="Summary",
            priority=3,
            status="open",
            created_at=now,
            updated_at=now,
            idempotency_key=f"{biz.id}:fix_mapping:none:all:{now.date().isoformat()}:uncategorized",
        )
    )
    sqlite_session.commit()
    action = sqlite_session.query(ActionItem).first()

    resp = api_client.post(
        f"/api/actions/{biz.id}/{action.id}/resolve",
        json={"status": "done", "resolution_reason": "Reviewed"},
        headers={"X-User-Email": user.email},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "done"
    assert payload["resolution_reason"] == "Reviewed"


def test_create_action_from_signal_is_idempotent(api_client, sqlite_session):
    now = datetime.now(timezone.utc)
    biz = _create_business(sqlite_session)
    user = _create_user(sqlite_session, "advisor@example.com")
    _add_membership(sqlite_session, biz.id, user.id, role="advisor")
    sqlite_session.add(
        HealthSignalState(
            business_id=biz.id,
            signal_id="signal-from-row",
            signal_type="cash_low",
            status="open",
            severity="high",
            title="Cash dropped",
            summary="Cash dropped below target.",
            payload_json={
                "ledger_anchors": [
                    {
                        "label": "Anchor",
                        "query": {
                            "start_date": (now - timedelta(days=3)).date().isoformat(),
                            "end_date": now.date().isoformat(),
                            "source_event_ids": ["evt-a"],
                        },
                    }
                ]
            },
            detected_at=now - timedelta(hours=4),
            last_seen_at=now,
            updated_at=now,
        )
    )
    sqlite_session.commit()

    first = api_client.post(
        f"/api/actions/{biz.id}/from_signal",
        json={"signal_id": "signal-from-row"},
        headers={"X-User-Email": user.email},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["created"] is True
    assert first_payload["action_id"]
    assert first_payload["linked_signal_id"] == "signal-from-row"

    second = api_client.post(
        f"/api/actions/{biz.id}/from_signal",
        json={"signal_id": "signal-from-row"},
        headers={"X-User-Email": user.email},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["created"] is False
    assert second_payload["action_id"] == first_payload["action_id"]

    count = sqlite_session.query(ActionItem).filter(ActionItem.business_id == biz.id).count()
    assert count == 1

    signals = api_client.get(
        f"/api/signals?business_id={biz.id}",
        headers={"X-User-Email": user.email},
    )
    assert signals.status_code == 200
    signal_payload = signals.json()
    signal = next(item for item in signal_payload["signals"] if item["id"] == "signal-from-row")
    assert signal["linked_action_id"] == first_payload["action_id"]
