import json
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_plaid_sandbox.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import AuditLog, Business, IntegrationConnection, Organization, ProcessingEventState, RawEvent


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
    org = Organization(name="Plaid Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Plaid Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _transaction(transaction_id: str, amount: float, name: str, date: str):
    return {
        "transaction_id": transaction_id,
        "amount": amount,
        "name": name,
        "merchant_name": name,
        "date": date,
        "datetime": f"{date}T12:00:00",
        "account_id": "acct-1",
        "payment_channel": "online",
    }


def _mock_plaid_transport():
    sync_cursor2_sequence = [
        {
            "added": [],
            "modified": [
                _transaction("txn-002", -250.0, "Daily Sales", "2025-01-03"),
            ],
            "removed": [{"transaction_id": "txn-001"}],
            "next_cursor": "cursor-3",
            "has_more": False,
        },
        {
            "added": [_transaction("txn-004", 25.0, "Late Fees", "2025-01-05")],
            "modified": [],
            "removed": [],
            "next_cursor": "cursor-4",
            "has_more": False,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        payload = json.loads(request.content.decode() or "{}")
        if path == "/link/token/create":
            return httpx.Response(
                200,
                json={"link_token": "link-sandbox", "expiration": "2025-12-31T00:00:00Z"},
            )
        if path == "/item/public_token/exchange":
            return httpx.Response(200, json={"access_token": "access-sandbox", "item_id": "item-1"})
        if path == "/transactions/sync":
            cursor = payload.get("cursor")
            if cursor is None:
                return httpx.Response(
                    200,
                    json={
                        "added": [
                            _transaction("txn-001", 40.0, "Coffee Supply Co", "2025-01-02"),
                            _transaction("txn-002", -200.0, "Daily Sales", "2025-01-03"),
                        ],
                        "modified": [],
                        "removed": [],
                        "next_cursor": "cursor-1",
                        "has_more": True,
                    },
                )
            if cursor == "cursor-1":
                return httpx.Response(
                    200,
                    json={
                        "added": [_transaction("txn-003", 80.0, "Paper Goods", "2025-01-04")],
                        "modified": [],
                        "removed": [],
                        "next_cursor": "cursor-2",
                        "has_more": False,
                    },
                )
            if cursor == "cursor-2":
                return httpx.Response(200, json=sync_cursor2_sequence.pop(0))
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def test_plaid_sandbox_sync_ingest_flow(client, db_session, monkeypatch):
    from backend.app.integrations import plaid as plaid_module

    monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLAID_SECRET", "secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")

    transport = _mock_plaid_transport()

    def _client(base_url: str) -> httpx.Client:
        return httpx.Client(base_url=base_url, transport=transport)

    monkeypatch.setattr(plaid_module, "_build_httpx_client", _client)

    biz = _create_business(db_session)

    link = client.post(f"/integrations/plaid/link_token/{biz.id}")
    assert link.status_code == 200
    assert link.json()["link_token"] == "link-sandbox"

    exchange = client.post(
        f"/integrations/plaid/exchange/{biz.id}",
        json={"public_token": "public-sandbox"},
    )
    assert exchange.status_code == 200

    connection = db_session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == biz.id,
            IntegrationConnection.provider == "plaid",
        )
    ).scalar_one()
    assert connection.plaid_access_token == "access-sandbox"
    assert connection.plaid_item_id == "item-1"

    sync = client.post(f"/integrations/plaid/sync/{biz.id}")
    assert sync.status_code == 200
    payload = sync.json()
    assert payload["inserted"] == 3
    assert payload["cursor"] == "cursor-2"

    rows = db_session.execute(
        select(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "plaid")
    ).scalars().all()
    assert len(rows) == 3

    states = db_session.execute(
        select(ProcessingEventState).where(ProcessingEventState.business_id == biz.id)
    ).scalars().all()
    assert len(states) == 3

    audit = db_session.execute(
        select(AuditLog).where(AuditLog.business_id == biz.id, AuditLog.event_type == "ingest_processed")
    ).scalars().all()
    assert audit

    sync_again = client.post(f"/integrations/plaid/sync/{biz.id}")
    assert sync_again.status_code == 200
    rows = db_session.execute(
        select(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "plaid")
    ).scalars().all()
    assert len(rows) == 5

    sync_third = client.post(f"/integrations/plaid/sync/{biz.id}")
    assert sync_third.status_code == 200
    rows = db_session.execute(
        select(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "plaid")
    ).scalars().all()
    assert len(rows) == 6
