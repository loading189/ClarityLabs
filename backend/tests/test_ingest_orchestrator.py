import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ingest_orchestrator.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Business, Organization, AuditLog
from backend.app.services.ingest_orchestrator import process_ingested_events


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
    org = Organization(name="Ingest Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Ingest Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_ingest_orchestrator_creates_audit(db_session):
    biz = _create_business(db_session)

    result = process_ingested_events(db_session, business_id=biz.id, source_event_ids=["ev-1", "ev-2"])
    assert result["events_inserted"] == 2

    audit_rows = db_session.execute(
        select(AuditLog).where(AuditLog.business_id == biz.id, AuditLog.event_type == "ingest_processed")
    ).scalars().all()
    assert len(audit_rows) == 1
