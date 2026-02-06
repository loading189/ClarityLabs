from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_uncategorized_window.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Business, Organization, RawEvent, TxnCategorization
from backend.app.services.posted_txn_service import count_uncategorized_raw_events


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
    org = Organization(name="Window Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Window Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_uncategorized_count_uses_anti_join(db_session):
    biz = _create_business(db_session)
    ev = RawEvent(
        business_id=biz.id,
        source="bank",
        source_event_id="ev-1",
        occurred_at=datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc),
        payload={
            "type": "transaction.posted",
            "transaction": {
                "transaction_id": "ev-1",
                "amount": -12.0,
                "name": "Coffee",
                "merchant_name": "Coffee",
            },
        },
    )
    db_session.add(ev)
    db_session.commit()

    assert count_uncategorized_raw_events(db_session, biz.id) == 1

    existing = db_session.execute(
        select(TxnCategorization).where(TxnCategorization.business_id == biz.id)
    ).scalars().all()
    assert existing == []
