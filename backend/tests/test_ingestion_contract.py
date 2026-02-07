from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ingestion_contract.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Organization, Business, RawEvent
from backend.app.services.posted_txn_service import current_raw_events, posted_txns
from backend.app.services.raw_event_service import insert_raw_event_idempotent
from backend.app.services import plaid_sync_service


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


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _create_business(db_session):
    org = Organization(name="Ingest Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Ingest Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _plaid_payload(transaction_id: str, amount: float, name: str, *, event_type: str, version: int):
    return {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": transaction_id,
            "amount": amount,
            "name": name,
            "merchant_name": name,
        },
        "meta": {
            "canonical_source_event_id": transaction_id,
            "event_type": event_type,
            "event_version": version,
            "is_removed": event_type == "removed",
        },
    }


def test_raw_event_idempotent_insert(db_session):
    biz = _create_business(db_session)
    occurred_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = _plaid_payload("tx_1", 12.0, "Coffee", event_type="added", version=1)

    created = insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:added:v1",
        canonical_source_event_id="tx_1",
        occurred_at=occurred_at,
        payload=payload,
    )
    dup = insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:added:v1",
        canonical_source_event_id="tx_1",
        occurred_at=occurred_at,
        payload=payload,
    )
    db_session.commit()

    assert created is True
    assert dup is False

    rows = db_session.execute(select(RawEvent)).scalars().all()
    assert len(rows) == 1


def test_plaid_sync_added_modified_removed(client, db_session, monkeypatch):
    biz = _create_business(db_session)

    class StubPlaidClient:
        def sync_transactions(self, *, cursor, since=None, last_n=None):
            return {
                "added": [
                    {
                        "event_id": "evt_add",
                        "transaction": {
                            "transaction_id": "tx_1",
                            "amount": -10.0,
                            "name": "Coffee",
                            "merchant_name": "Coffee",
                        },
                    }
                ],
                "modified": [
                    {
                        "event_id": "evt_mod",
                        "transaction": {
                            "transaction_id": "tx_1",
                            "amount": -5.0,
                            "name": "Coffee Adjusted",
                            "merchant_name": "Coffee",
                        },
                    }
                ],
                "removed": [
                    {
                        "event_id": "evt_remove",
                        "transaction": {
                            "transaction_id": "tx_2",
                            "amount": -12.0,
                            "name": "Lunch",
                            "merchant_name": "Lunch",
                        },
                    }
                ],
                "next_cursor": "cursor_1",
            }

    monkeypatch.setattr(plaid_sync_service, "get_plaid_client", lambda: StubPlaidClient())

    resp = client.post(f"/integrations/{biz.id}/plaid/sync")
    assert resp.status_code == 200

    events = db_session.execute(select(RawEvent)).scalars().all()
    assert len(events) == 3

    current = posted_txns(db_session, biz.id)
    assert len(current) == 1
    assert current[0].canonical_source_event_id == "tx_1"
    assert current[0].txn.amount == 5.0

    removed = [ev for ev in events if ev.source_event_id.startswith("tx_2")]
    assert removed
    assert removed[0].payload["meta"]["is_removed"] is True

    resp = client.post(f"/integrations/{biz.id}/plaid/sync")
    assert resp.status_code == 200
    events_after = db_session.execute(select(RawEvent)).scalars().all()
    assert len(events_after) == 3


def test_posted_txn_service_latest_and_removed(db_session):
    biz = _create_business(db_session)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:added:v1",
        canonical_source_event_id="tx_1",
        occurred_at=now,
        payload=_plaid_payload("tx_1", 10.0, "Coffee", event_type="added", version=1),
    )
    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:modified:v2",
        canonical_source_event_id="tx_1",
        occurred_at=now,
        payload=_plaid_payload("tx_1", 15.0, "Coffee", event_type="modified", version=2),
    )
    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_2:added:v1",
        canonical_source_event_id="tx_2",
        occurred_at=now,
        payload=_plaid_payload("tx_2", 20.0, "Lunch", event_type="added", version=1),
    )
    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_2:removed:v2",
        canonical_source_event_id="tx_2",
        occurred_at=now,
        payload=_plaid_payload("tx_2", 20.0, "Lunch", event_type="removed", version=2),
    )
    db_session.commit()

    current = current_raw_events(db_session, biz.id)
    assert [ev.canonical_source_event_id for ev in current] == ["tx_1"]


def test_demo_health_reflects_modifications_and_removals(client, db_session):
    biz = _create_business(db_session)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:added:v1",
        canonical_source_event_id="tx_1",
        occurred_at=now,
        payload=_plaid_payload("tx_1", 10.0, "Coffee", event_type="added", version=1),
    )
    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:modified:v2",
        canonical_source_event_id="tx_1",
        occurred_at=now,
        payload=_plaid_payload("tx_1", 25.0, "Coffee", event_type="modified", version=2),
    )
    db_session.commit()

    resp = client.get(f"/demo/health/{biz.id}")
    assert resp.status_code == 200
    data = resp.json()
    ledger_rows = data["ledger_preview"]
    row = next((r for r in ledger_rows if r["source_event_id"] == "tx_1"), None)
    assert row is not None
    assert row["amount"] == 25.0

    insert_raw_event_idempotent(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="tx_1:removed:v3",
        canonical_source_event_id="tx_1",
        occurred_at=now,
        payload=_plaid_payload("tx_1", 25.0, "Coffee", event_type="removed", version=3),
    )
    db_session.commit()

    resp = client.get(f"/demo/health/{biz.id}")
    assert resp.status_code == 200
    data = resp.json()
    ledger_rows = data["ledger_preview"]
    assert all(r["source_event_id"] != "tx_1" for r in ledger_rows)


def test_replay_and_reprocess_reconcile(client, db_session, monkeypatch):
    biz = _create_business(db_session)

    class StubPlaidClient:
        def sync_transactions(self, *, cursor, since=None, last_n=None):
            return {
                "added": [
                    {
                        "event_id": "evt_replay",
                        "transaction": {
                            "transaction_id": "tx_9",
                            "amount": -33.0,
                            "name": "Supply",
                            "merchant_name": "Supply",
                        },
                    }
                ],
                "modified": [],
                "removed": [],
                "next_cursor": "cursor_replay",
            }

    monkeypatch.setattr(plaid_sync_service, "get_plaid_client", lambda: StubPlaidClient())

    resp = client.post(f"/integrations/{biz.id}/plaid/replay", json={})
    assert resp.status_code == 200

    diag = client.get(f"/diagnostics/reconcile/{biz.id}").json()
    assert diag["counts"]["raw_events_total"] == 1
    assert diag["counts"]["posted_txns_total"] == 1
    conn = diag["connections"][0]
    assert conn["provider_cursor"] == "cursor_replay"
    assert conn["last_ingested_source_event_id"].startswith("tx_9")

    resp = client.post(f"/processing/reprocess/{biz.id}", json={"mode": "from_last_cursor"})
    assert resp.status_code == 200

    diag = client.get(f"/diagnostics/reconcile/{biz.id}").json()
    conn = diag["connections"][0]
    assert conn["last_processed_source_event_id"] == conn["last_ingested_source_event_id"]
