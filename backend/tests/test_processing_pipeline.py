from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_processing_pipeline.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import (
    Account,
    AuditLog,
    Business,
    Category,
    Organization,
    ProcessingEventState,
    RawEvent,
    TxnCategorization,
)
from backend.app.services.ingest_orchestrator import process_ingested_events
from backend.app.services.processing_service import process_new_events


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
    org = Organization(name="Processing Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Processing Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _event(business_id: str, source_event_id: str, amount: float):
    return RawEvent(
        business_id=business_id,
        source="bank",
        source_event_id=source_event_id,
        occurred_at=datetime(2025, 1, 10, tzinfo=timezone.utc),
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


def test_process_new_events_idempotent(db_session):
    biz = _create_business(db_session)
    db_session.add(_event(biz.id, "evt-1", -10.0))
    db_session.commit()

    first = process_new_events(db_session, business_id=biz.id)
    second = process_new_events(db_session, business_id=biz.id)

    assert first["processed"] == 1
    assert second["skipped"] == 1

    rows = db_session.execute(
        select(ProcessingEventState).where(
            ProcessingEventState.business_id == biz.id,
            ProcessingEventState.source_event_id == "evt-1",
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "normalized"


def test_process_new_events_captures_errors(db_session):
    biz = _create_business(db_session)
    db_session.add(
        RawEvent(
            business_id=biz.id,
            source="bank",
            source_event_id="evt-bad",
            occurred_at=datetime(2025, 1, 11, tzinfo=timezone.utc),
            payload={"type": "transaction.posted", "transaction": {}},
        )
    )
    db_session.commit()

    result = process_new_events(db_session, business_id=biz.id)
    assert result["errors"] == 1

    row = db_session.execute(
        select(ProcessingEventState).where(
            ProcessingEventState.business_id == biz.id,
            ProcessingEventState.source_event_id == "evt-bad",
        )
    ).scalar_one()
    assert row.status == "error"
    assert row.error_code == "ValueError"
    assert row.error_detail

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.business_id == biz.id,
            AuditLog.event_type == "processing_error",
            AuditLog.source_event_id == "evt-bad",
        )
    ).scalar_one()
    assert audit.after_state["error_code"] == "ValueError"


def test_categorized_events_marked_posted_eligible(db_session):
    biz = _create_business(db_session)
    account = Account(business_id=biz.id, name="Ops", type="expense", subtype="ops")
    db_session.add(account)
    db_session.flush()
    category = Category(business_id=biz.id, name="Ops", account_id=account.id)
    db_session.add(category)
    db_session.flush()
    db_session.add(_event(biz.id, "evt-cat", -22.0))
    db_session.flush()
    db_session.add(
        TxnCategorization(
            business_id=biz.id,
            source_event_id="evt-cat",
            category_id=category.id,
            source="manual",
            confidence=1.0,
        )
    )
    db_session.commit()

    result = process_new_events(db_session, business_id=biz.id)
    assert result["categorized"] == 1

    state = db_session.execute(
        select(ProcessingEventState).where(
            ProcessingEventState.business_id == biz.id,
            ProcessingEventState.source_event_id == "evt-cat",
        )
    ).scalar_one()
    assert state.status == "categorized"


def test_ingest_orchestrator_returns_processing_summary(db_session):
    biz = _create_business(db_session)
    db_session.add(_event(biz.id, "evt-1", -10.0))
    db_session.add(_event(biz.id, "evt-2", -15.0))
    db_session.commit()

    result = process_ingested_events(db_session, business_id=biz.id, source_event_ids=["evt-1", "evt-2"])
    assert result["events_inserted"] == 2
    assert result["processing"]["events_total"] == 2
    assert "audit_ids" in result

    audit_rows = db_session.execute(
        select(AuditLog).where(AuditLog.business_id == biz.id)
    ).scalars().all()
    event_types = {row.event_type for row in audit_rows}
    assert "processing_started" in event_types
    assert "processing_completed" in event_types
    assert "ingest_processed" in event_types


def test_ingestion_diagnostics_endpoint(client, db_session):
    biz = _create_business(db_session)
    db_session.add(_event(biz.id, "evt-1", -10.0))
    db_session.add(
        RawEvent(
            business_id=biz.id,
            source="bank",
            source_event_id="evt-bad",
            occurred_at=datetime(2025, 1, 12, tzinfo=timezone.utc),
            payload={"type": "transaction.posted", "transaction": {}},
        )
    )
    db_session.commit()

    process_new_events(db_session, business_id=biz.id)

    response = client.get(f"/api/diagnostics/ingestion/{biz.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status_counts"]["normalized"] == 1
    assert payload["status_counts"]["error"] == 1
    assert payload["errors"][0]["source_event_id"] == "evt-bad"
