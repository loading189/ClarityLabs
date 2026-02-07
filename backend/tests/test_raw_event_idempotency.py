from datetime import datetime, timezone

import pytest

from backend.app.db import Base, SessionLocal, engine
from backend.app.integrations.utils import upsert_raw_event
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


def _create_business(db_session):
    org = Organization(name="Raw Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Raw Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_raw_event_idempotent_insert(db_session):
    biz = _create_business(db_session)
    payload = {"type": "plaid.transaction", "amount": 10.0}

    inserted_first = upsert_raw_event(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="plaid:txn-dup",
        occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        payload=payload,
    )
    inserted_second = upsert_raw_event(
        db_session,
        business_id=biz.id,
        source="plaid",
        source_event_id="plaid:txn-dup",
        occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        payload=payload,
    )
    db_session.commit()

    rows = db_session.query(RawEvent).all()
    assert inserted_first is True
    assert inserted_second is False
    assert len(rows) == 1
