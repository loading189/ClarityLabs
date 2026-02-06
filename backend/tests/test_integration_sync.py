from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_integration_sync.db")

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
    org = Organization(name="Sync Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Sync Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_plaid_sync_inserts_events(client, db_session):
    biz = _create_business(db_session)

    connect = client.post(f"/api/integrations/{biz.id}/plaid/connect", json={"config_json": {"mode": "stub"}})
    assert connect.status_code == 200

    sync = client.post(f"/api/integrations/{biz.id}/plaid/sync")
    assert sync.status_code == 200
    payload = sync.json()
    assert payload["inserted"] == 3

    rows = db_session.execute(
        select(RawEvent).where(RawEvent.business_id == biz.id, RawEvent.source == "plaid")
    ).scalars().all()
    assert len(rows) == 3
