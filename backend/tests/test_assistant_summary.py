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
from backend.app.models import Business, BusinessMembership, Organization, User


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


def _create_user(db_session, email: str) -> User:
    user = User(email=email, name=email.split("@")[0])
    db_session.add(user)
    db_session.flush()
    return user


def _add_membership(db_session, business_id: str, user_id: str, role: str = "viewer"):
    membership = BusinessMembership(business_id=business_id, user_id=user_id, role=role)
    db_session.add(membership)
    db_session.flush()
    return membership


def test_assistant_summary_empty(client, db_session):
    biz = _create_business(db_session)
    user = _create_user(db_session, "viewer@example.com")
    _add_membership(db_session, biz.id, user.id, role="viewer")
    db_session.commit()
    resp = client.get(
        f"/api/assistant/summary/{biz.id}",
        headers={"X-User-Email": user.email},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["business_id"] == biz.id
    assert payload["open_signals"] == 0
    assert payload["open_action_count"] == 0
    assert payload["top_open_actions"] == []
    assert payload["uncategorized_count"] == 0
    assert payload["integrations"] == []
    assert payload["recent_signal_resolutions"] == []
