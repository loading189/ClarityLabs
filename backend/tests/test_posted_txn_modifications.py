from datetime import datetime, timezone

import pytest

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Account, Business, Category, Organization, RawEvent, TxnCategorization
from backend.app.services.posted_txn_service import fetch_posted_transactions


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


def _setup_business(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Test Biz")
    db_session.add(biz)
    db_session.flush()
    account = Account(business_id=biz.id, code="1000", name="Cash", type="asset")
    db_session.add(account)
    db_session.flush()
    category = Category(
        business_id=biz.id,
        name="Supplies",
        system_key="office_supplies",
        account_id=account.id,
    )
    db_session.add(category)
    db_session.flush()
    return biz, category


def _plaid_payload(txn_id: str, amount: float, version: int, *, removed: bool = False):
    base_id = f"plaid:{txn_id}"
    payload = {
        "type": "plaid.transaction.removed" if removed else "plaid.transaction",
        "transaction": {
            "transaction_id": txn_id,
            "amount": amount,
            "name": "Test Purchase",
        },
        "direction": "outflow",
        "category": "office_supplies",
        "provider": "plaid",
        "meta": {
            "event_kind": "removed" if removed else "modified",
            "event_version": version,
            "event_fingerprint": f"fingerprint-{version}",
            "source_event_base_id": base_id,
            "is_removed": removed,
        },
    }
    return payload


def test_posted_txn_latest_version_and_removal(db_session):
    biz, category = _setup_business(db_session)

    event_v1 = RawEvent(
        business_id=biz.id,
        source="plaid",
        source_event_id="plaid:txn-1",
        occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        payload=_plaid_payload("txn-1", 50.0, 1),
    )
    event_v2 = RawEvent(
        business_id=biz.id,
        source="plaid",
        source_event_id="plaid:txn-1:v2",
        occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        payload=_plaid_payload("txn-1", 80.0, 2),
    )
    db_session.add_all([event_v1, event_v2])
    db_session.flush()
    db_session.add_all(
        [
            TxnCategorization(
                business_id=biz.id,
                source_event_id=event_v1.source_event_id,
                category_id=category.id,
            ),
            TxnCategorization(
                business_id=biz.id,
                source_event_id=event_v2.source_event_id,
                category_id=category.id,
            ),
        ]
    )
    db_session.commit()

    txns = fetch_posted_transactions(db_session, biz.id)
    assert len(txns) == 1
    assert txns[0].amount == 80.0

    tombstone = RawEvent(
        business_id=biz.id,
        source="plaid",
        source_event_id="plaid:txn-1:v3",
        occurred_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        payload=_plaid_payload("txn-1", 0.0, 3, removed=True),
    )
    db_session.add(tombstone)
    db_session.commit()

    txns_after = fetch_posted_transactions(db_session, biz.id)
    assert txns_after == []


def test_posted_txn_ordering_stable(db_session):
    biz, category = _setup_business(db_session)

    events = [
        RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id="plaid:txn-2",
            occurred_at=datetime(2025, 1, 5, tzinfo=timezone.utc),
            payload=_plaid_payload("txn-2", 30.0, 1),
        ),
        RawEvent(
            business_id=biz.id,
            source="plaid",
            source_event_id="plaid:txn-3",
            occurred_at=datetime(2025, 1, 5, tzinfo=timezone.utc),
            payload=_plaid_payload("txn-3", 20.0, 1),
        ),
    ]
    db_session.add_all(events)
    db_session.flush()
    db_session.add_all(
        [
            TxnCategorization(
                business_id=biz.id,
                source_event_id=events[0].source_event_id,
                category_id=category.id,
            ),
            TxnCategorization(
                business_id=biz.id,
                source_event_id=events[1].source_event_id,
                category_id=category.id,
            ),
        ]
    )
    db_session.commit()

    txns = fetch_posted_transactions(db_session, biz.id)
    assert [txn.source_event_id for txn in txns] == ["plaid:txn-2", "plaid:txn-3"]
