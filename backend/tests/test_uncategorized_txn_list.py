from __future__ import annotations

import os
from datetime import datetime, timezone, date
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_uncategorized_txn_list.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Organization, Business, RawEvent, TxnCategorization, Account, Category
from backend.app.services import categorize_service


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


def _biz(db):
    org = Organization(name="Categorize Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Categorize Biz")
    db.add(biz)
    db.flush()
    return biz


def _event(business_id: str, source_event_id: str, amount: float, occurred_at: datetime):
    return RawEvent(
        business_id=business_id,
        source="bank",
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        payload={
            "type": "transaction.posted",
            "transaction": {
                "transaction_id": source_event_id,
                "amount": amount,
                "name": f"Vendor {source_event_id}",
                "merchant_name": f"Vendor {source_event_id}",
            },
        },
    )


def test_list_txns_to_categorize_filters_uncategorized(db_session):
    biz = _biz(db_session)
    account = Account(business_id=biz.id, name="Ops", type="expense", subtype="ops")
    db_session.add(account)
    db_session.flush()
    category = Category(business_id=biz.id, name="Ops", account_id=account.id)
    db_session.add(category)
    db_session.flush()
    evt_1 = _event(biz.id, "evt-1", -10.0, datetime(2025, 1, 10, tzinfo=timezone.utc))
    evt_2 = _event(biz.id, "evt-2", -20.0, datetime(2025, 1, 12, tzinfo=timezone.utc))
    db_session.add_all([evt_1, evt_2])
    db_session.flush()

    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt-1",
            category_id=category.id,
            source="manual",
            confidence=1.0,
        )
    )
    db_session.commit()

    rows = categorize_service.list_txns_to_categorize(
        db_session,
        biz.id,
        limit=10,
        only_uncategorized=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert len(rows) == 1
    assert rows[0]["source_event_id"] == "evt-2"


def test_uncategorized_pagination_and_count_updates_after_categorization(db_session):
    biz = _biz(db_session)
    account = Account(business_id=biz.id, name="Ops", type="expense", subtype="ops")
    db_session.add(account)
    db_session.flush()
    category = Category(business_id=biz.id, name="Ops", account_id=account.id)
    db_session.add(category)
    db_session.flush()

    db_session.add_all(
        [
            _event(biz.id, "evt-1", -10.0, datetime(2025, 1, 10, tzinfo=timezone.utc)),
            _event(biz.id, "evt-2", -20.0, datetime(2025, 1, 11, tzinfo=timezone.utc)),
            _event(biz.id, "evt-3", -30.0, datetime(2025, 1, 12, tzinfo=timezone.utc)),
        ]
    )
    db_session.commit()

    page_1 = categorize_service.list_txns_to_categorize_page(
        db_session,
        biz.id,
        limit=2,
        offset=0,
        only_uncategorized=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    page_2 = categorize_service.list_txns_to_categorize_page(
        db_session,
        biz.id,
        limit=2,
        offset=page_1["next_offset"] or 0,
        only_uncategorized=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    ids_1 = [row["source_event_id"] for row in page_1["items"]]
    ids_2 = [row["source_event_id"] for row in page_2["items"]]

    assert page_1["total_count"] == 3
    assert len(page_1["items"]) == 2
    assert page_1["has_more"] is True
    assert len(page_2["items"]) == 1
    assert page_2["has_more"] is False
    assert ids_1 == ["evt-3", "evt-2"]
    assert ids_2 == ["evt-1"]
    assert set(ids_1).isdisjoint(ids_2)

    req = type("Req", (), {"source_event_id": "evt-3", "category_id": category.id, "source": "manual", "confidence": 1.0, "note": None})
    categorize_service.upsert_categorization(db_session, biz.id, req)

    after = categorize_service.list_txns_to_categorize_page(
        db_session,
        biz.id,
        limit=10,
        offset=0,
        only_uncategorized=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    after_ids = [row["source_event_id"] for row in after["items"]]
    assert after["total_count"] == 2
    assert "evt-3" not in after_ids
