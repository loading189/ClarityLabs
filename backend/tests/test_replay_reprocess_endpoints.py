import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_replay_reprocess.db")
os.environ.setdefault("PLAID_USE_STUB", "true")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Business, IntegrationConnection, Organization


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


def _create_business_with_connection(db_session):
    org = Organization(name="Replay Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Replay Biz")
    db_session.add(biz)
    db_session.flush()
    connection = IntegrationConnection(
        business_id=biz.id,
        provider="plaid",
        status="connected",
        is_enabled=True,
    )
    db_session.add(connection)
    db_session.commit()
    return biz


def test_replay_and_reprocess_endpoints(client, db_session):
    biz = _create_business_with_connection(db_session)

    replay = client.post(f"/api/integrations/{biz.id}/plaid/replay", json={"last_n": 10})
    assert replay.status_code == 200
    payload = replay.json()
    assert payload["provider"] == "plaid"
    assert payload["inserted"] >= 1

    reconcile = client.get(f"/api/diagnostics/reconcile/{biz.id}")
    assert reconcile.status_code == 200
    data = reconcile.json()
    assert data["counts"]["raw_events"] >= payload["inserted"]

    reprocess = client.post(f"/processing/reprocess/{biz.id}", json={"mode": "from_last_cursor"})
    assert reprocess.status_code == 200
    assert reprocess.json()["mode"] == "from_last_cursor"
