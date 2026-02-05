from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assistant_thread.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, Organization
from backend.app.services.assistant_thread_service import AssistantMessageIn, append_message, list_messages


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


def _create_business(db_session, name: str):
    org = Organization(name=f"Org {name}")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name=f"Biz {name}")
    db_session.add(biz)
    db_session.commit()
    return biz


def test_append_list_deterministic_ordering(db_session):
    biz = _create_business(db_session, "a")
    append_message(db_session, biz.id, AssistantMessageIn(author="system", kind="summary", content_json={"text": "one"}), dedupe=False)
    append_message(db_session, biz.id, AssistantMessageIn(author="assistant", kind="note", content_json={"text": "two"}), dedupe=False)

    messages = list_messages(db_session, biz.id, limit=200)
    assert [row.content_json["text"] for row in messages] == ["one", "two"]
    assert messages[0].business_id == biz.id
    assert messages[0].id < messages[1].id or messages[0].created_at <= messages[1].created_at


def test_retention_enforced(db_session):
    biz = _create_business(db_session, "ret")
    for i in range(205):
        append_message(db_session, biz.id, AssistantMessageIn(author="assistant", kind="note", content_json={"i": i}), dedupe=False)

    messages = list_messages(db_session, biz.id, limit=200)
    assert len(messages) == 200
    assert messages[0].content_json["i"] == 5


def test_validation_rejects_invalid_author_and_kind(db_session):
    biz = _create_business(db_session, "invalid")
    with pytest.raises(Exception):
        append_message(db_session, biz.id, AssistantMessageIn(author="bad", kind="summary", content_json={}), dedupe=False)
    with pytest.raises(Exception):
        append_message(db_session, biz.id, AssistantMessageIn(author="system", kind="bad", content_json={}), dedupe=False)


def test_thread_is_business_isolated(db_session):
    a = _create_business(db_session, "a")
    b = _create_business(db_session, "b")
    append_message(db_session, a.id, AssistantMessageIn(author="system", kind="summary", content_json={"text": "A"}), dedupe=False)
    append_message(db_session, b.id, AssistantMessageIn(author="system", kind="summary", content_json={"text": "B"}), dedupe=False)

    a_rows = list_messages(db_session, a.id)
    b_rows = list_messages(db_session, b.id)
    assert [row.content_json["text"] for row in a_rows] == ["A"]
    assert [row.content_json["text"] for row in b_rows] == ["B"]
