import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assistant_summary.db")

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


def _create_business(db_session):
    org = Organization(name="Assistant Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Assistant Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_assistant_summary_empty(client, db_session):
    biz = _create_business(db_session)
    resp = client.get(f"/api/assistant/summary/{biz.id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["business_id"] == biz.id
    assert payload["open_signals"] == 0
    assert payload["uncategorized_count"] == 0
    assert payload["integrations"] == []
    assert payload["recent_signal_resolutions"] == []
