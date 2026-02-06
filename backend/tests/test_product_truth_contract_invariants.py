from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.db import Base
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import (
    Account,
    Business,
    Category,
    HealthSignalState,
    Organization,
    RawEvent,
    TxnCategorization,
)
from backend.app.services import categorize_service, ledger_service, monitoring_service
from backend.app.services.health_signal_service import update_signal_status
from backend.app.services.posted_txn_service import fetch_posted_transactions
from backend.app.signals.v2 import DetectedSignal


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _create_business(db):
    org = Organization(name="Truth Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Truth Biz")
    db.add(biz)
    db.flush()
    return biz


def _create_category(db, business_id: str):
    account = Account(
        business_id=business_id,
        name="Operating",
        type="asset",
        subtype="cash",
    )
    db.add(account)
    db.flush()
    category = Category(business_id=business_id, name="Sales", account_id=account.id)
    db.add(category)
    db.flush()
    return category


def _add_posted_event(db, business_id: str, category_id: str, source_event_id: str, amount: float, when: datetime):
    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": source_event_id,
            "amount": amount,
            "name": f"Vendor {source_event_id}",
            "merchant_name": f"Vendor {source_event_id}",
        },
    }
    db.add(
        RawEvent(
            business_id=business_id,
            source="bank",
            source_event_id=source_event_id,
            occurred_at=when,
            payload=payload,
        )
    )
    db.add(
        TxnCategorization(
            business_id=business_id,
            source_event_id=source_event_id,
            category_id=category_id,
            source="manual",
            confidence=1.0,
        )
    )


def test_product_truth_contract_posted_ledger_invariants():
    db = _session()
    biz = _create_business(db)
    category = _create_category(db, biz.id)

    _add_posted_event(db, biz.id, category.id, "evt-1", 120.0, datetime(2024, 1, 1, tzinfo=timezone.utc))
    _add_posted_event(db, biz.id, category.id, "evt-2", -30.0, datetime(2024, 1, 2, tzinfo=timezone.utc))
    _add_posted_event(db, biz.id, category.id, "evt-3", -10.0, datetime(2024, 1, 3, tzinfo=timezone.utc))
    db.commit()

    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 3)
    ledger = ledger_service.ledger_query(
        db,
        biz.id,
        start_date=start_date,
        end_date=end_date,
        limit=50,
        offset=0,
    )

    row_total = round(sum(row["amount"] for row in ledger["rows"]), 2)
    assert ledger["summary"]["start_balance"] == 0.0
    assert ledger["summary"]["end_balance"] == row_total

    for row in ledger["rows"]:
        count = db.execute(
            select(func.count())
            .select_from(RawEvent)
            .where(
                RawEvent.business_id == biz.id,
                RawEvent.source_event_id == row["source_event_id"],
            )
        ).scalar_one()
        assert count == 1

    posted = fetch_posted_transactions(db, biz.id, start_date=start_date, end_date=end_date)
    assert [row["source_event_id"] for row in ledger["rows"]] == [txn.source_event_id for txn in posted]


def test_product_truth_contract_uncategorized_window_excludes_posted():
    db = _session()
    biz = _create_business(db)
    category = _create_category(db, biz.id)

    _add_posted_event(db, biz.id, category.id, "evt-1", -25.0, datetime(2024, 2, 1, tzinfo=timezone.utc))
    db.add(
        RawEvent(
            business_id=biz.id,
            source="bank",
            source_event_id="evt-2",
            occurred_at=datetime(2024, 2, 2, tzinfo=timezone.utc),
            payload={
                "type": "transaction.posted",
                "transaction": {
                    "transaction_id": "evt-2",
                    "amount": -42.0,
                    "name": "Vendor evt-2",
                    "merchant_name": "Vendor evt-2",
                },
            },
        )
    )
    db.add(
        RawEvent(
            business_id=biz.id,
            source="bank",
            source_event_id="evt-3",
            occurred_at=datetime(2024, 3, 15, tzinfo=timezone.utc),
            payload={
                "type": "transaction.posted",
                "transaction": {
                    "transaction_id": "evt-3",
                    "amount": -55.0,
                    "name": "Vendor evt-3",
                    "merchant_name": "Vendor evt-3",
                },
            },
        )
    )
    db.commit()

    rows = categorize_service.list_txns_to_categorize(
        db,
        biz.id,
        limit=10,
        only_uncategorized=True,
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 29),
    )

    assert [row["source_event_id"] for row in rows] == ["evt-2"]


def test_product_truth_contract_signal_state_semantics():
    db = _session()
    biz = _create_business(db)

    now = datetime(2024, 1, 5, tzinfo=timezone.utc)
    signal = DetectedSignal(
        signal_id="expense.spike_vs_baseline:fp-1",
        signal_type="expense.spike_vs_baseline",
        fingerprint="fp-1",
        severity="warning",
        title="Expense spike",
        summary="Spend spiked",
        payload={"delta": 1.2},
    )

    monitoring_service._upsert_signal_states(db, biz.id, [signal], now)
    state = db.get(HealthSignalState, (biz.id, signal.signal_id))
    assert state is not None
    assert state.signal_type == signal.signal_type
    assert state.fingerprint == signal.fingerprint
    assert state.detected_at is not None
    assert state.detected_at.replace(tzinfo=timezone.utc) == now
    assert state.updated_at is not None

    update_signal_status(db, biz.id, signal.signal_id, status="ignored", reason="not relevant")
    ignored_state = db.get(HealthSignalState, (biz.id, signal.signal_id))
    assert ignored_state.status == "ignored"

    later = now + timedelta(hours=6)
    monitoring_service._upsert_signal_states(db, biz.id, [signal], later)
    db.refresh(ignored_state)
    assert ignored_state.status == "ignored"
    assert ignored_state.resolved_at is None
    assert ignored_state.detected_at is not None
    assert ignored_state.detected_at.replace(tzinfo=timezone.utc) == now

    monitoring_service._upsert_signal_states(db, biz.id, [], later + timedelta(hours=1))
    db.refresh(ignored_state)
    assert ignored_state.status == "ignored"


def test_product_truth_contract_signal_reopen_from_resolved():
    db = _session()
    biz = _create_business(db)

    now = datetime(2024, 2, 10, tzinfo=timezone.utc)
    signal = DetectedSignal(
        signal_id="liquidity.runway_low:fp-2",
        signal_type="liquidity.runway_low",
        fingerprint="fp-2",
        severity="critical",
        title="Runway low",
        summary="Runway fell below threshold",
        payload={"runway_days": 12},
    )

    monitoring_service._upsert_signal_states(db, biz.id, [signal], now)
    update_signal_status(db, biz.id, signal.signal_id, status="resolved", reason="recovered")

    state = db.get(HealthSignalState, (biz.id, signal.signal_id))
    resolved_at = state.resolved_at
    assert state.status == "resolved"

    later = now + timedelta(days=2)
    monitoring_service._upsert_signal_states(db, biz.id, [signal], later)
    db.refresh(state)
    assert state.status == "open"
    assert state.resolved_at is None
    assert state.detected_at is not None
    assert state.detected_at.replace(tzinfo=timezone.utc) == now
    assert state.last_seen_at is not None
    assert state.last_seen_at.replace(tzinfo=timezone.utc) == later
    assert resolved_at is not None
