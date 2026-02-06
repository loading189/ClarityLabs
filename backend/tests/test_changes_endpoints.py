from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_changes_endpoints.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Business, Organization


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


def _seed_business(db_session):
    org = Organization(name="Changes Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Changes Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_changes_endpoint_returns_empty_list_when_no_data(client, db_session):
    biz = _seed_business(db_session)
    response = client.get("/api/changes", params={"business_id": biz.id, "limit": 10})
    assert response.status_code == 200
    assert response.json() == []


def test_explain_change_endpoint_returns_empty_payload_when_no_data(client, db_session):
    biz = _seed_business(db_session)
    response = client.get(
        "/api/health_score/explain_change",
        params={"business_id": biz.id, "since_hours": 72, "limit": 20},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["changes"] == []
    assert payload["impacts"] == []


def test_changes_endpoint_rejects_invalid_business_id(client):
    response = client.get("/api/changes", params={"business_id": "not-a-uuid", "limit": 10})
    assert response.status_code == 422


def test_explain_change_endpoint_rejects_invalid_business_id(client):
    response = client.get(
        "/api/health_score/explain_change",
        params={"business_id": "not-a-uuid", "since_hours": 72, "limit": 20},
    )
    assert response.status_code == 422
