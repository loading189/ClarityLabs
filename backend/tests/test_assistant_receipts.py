from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assistant_receipts.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, Organization
from backend.app.services.assistant_thread_service import append_receipt, list_messages


def _create_business(db):
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    db.commit()
    return biz


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def test_receipts_appended_deterministically_and_include_audit_id():
    db = SessionLocal()
    try:
        biz = _create_business(db)
        append_receipt(
            db,
            biz.id,
            {
                "receipt_id": "r-1",
                "action": "signal_status_updated",
                "signal_id": "sig-1",
                "audit_id": "audit-1",
                "created_at": "2025-01-01T00:00:00+00:00",
                "links": {"audit": "/audit/audit-1", "signal": "/signal/sig-1"},
            },
            dedupe=False,
        )
        append_receipt(
            db,
            biz.id,
            {
                "receipt_id": "r-2",
                "action": "plan_done",
                "plan_id": "plan-1",
                "created_at": "2025-01-01T00:00:01+00:00",
                "links": {"plan": "/plan/plan-1"},
            },
            dedupe=False,
        )

        rows = list_messages(db, biz.id)
        assert [row.kind for row in rows] == ["receipt_signal_status_updated", "receipt_plan_done"]
        assert rows[0].audit_id == "audit-1"
        assert rows[0].content_json["audit_id"] == "audit-1"
    finally:
        db.close()
