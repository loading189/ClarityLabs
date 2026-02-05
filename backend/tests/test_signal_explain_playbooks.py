from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import event

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_signal_explain_playbooks.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Account, Business, Category, Organization, RawEvent, TxnCategorization
from backend.app.services import monitoring_service, signals_service


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


def _seed_signal(db_session):
    org = Organization(name="Explain Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Explain Biz")
    db_session.add(biz)
    db_session.flush()

    acct = Account(business_id=biz.id, name="Operating Expense", type="expense")
    db_session.add(acct)
    db_session.flush()
    cat = Category(business_id=biz.id, account_id=acct.id, name="General")
    db_session.add(cat)
    db_session.flush()

    now = datetime(2024, 6, 30, tzinfo=timezone.utc)
    for source_event_id, days, amount in (("prior", 20, 300.0), ("current", 5, 600.0)):
        event_row = RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id=source_event_id,
            occurred_at=now - timedelta(days=days),
            payload={
                "type": "plaid.transaction",
                "description": "Acme",
                "amount": amount,
                "direction": "outflow",
                "counterparty_hint": "Acme",
            },
        )
        db_session.add(event_row)
        db_session.add(
            TxnCategorization(
                business_id=biz.id,
                source_event_id=source_event_id,
                category_id=cat.id,
                confidence=1.0,
                source="manual",
            )
        )
    db_session.commit()
    monitoring_service.pulse(db_session, biz.id)
    signal_id = signals_service.list_signal_states(db_session, biz.id)[0][0]["id"]
    return biz.id, signal_id


def test_explain_includes_clear_condition_and_playbooks(db_session):
    business_id, signal_id = _seed_signal(db_session)

    explain = signals_service.get_signal_explain(db_session, business_id, signal_id)

    assert explain["clear_condition"]
    assert explain["clear_condition"]["summary"]
    assert isinstance(explain["playbooks"], list)
    assert explain["playbooks"]
    assert [p["id"] for p in explain["playbooks"]] == sorted(p["id"] for p in explain["playbooks"])


def test_explain_does_not_introduce_new_query_pattern(db_session):
    business_id, signal_id = _seed_signal(db_session)

    statements: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        signals_service.get_signal_explain(db_session, business_id, signal_id)
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)

    assert len(statements) <= 5
