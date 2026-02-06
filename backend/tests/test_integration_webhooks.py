from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_integration_webhooks.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Business, Organization, RawEvent


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
    org = Organization(name="Webhook Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Webhook Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_stripe_webhook_idempotency(client, db_session):
    biz = _create_business(db_session)
    payload = {
        "id": "evt_123",
        "created": int(datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc).timestamp()),
        "type": "payment_intent.succeeded",
        "business_id": biz.id,
        "data": {"object": {"id": "pi_123"}},
    }

    first = client.post("/api/webhooks/stripe", json=payload)
    assert first.status_code == 200
    assert first.json()["inserted"] == 1

    second = client.post("/api/webhooks/stripe", json=payload)
    assert second.status_code == 200
    assert second.json()["inserted"] == 0

    rows = db_session.execute(
        select(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "stripe")
    ).scalars().all()
    assert len(rows) == 1
