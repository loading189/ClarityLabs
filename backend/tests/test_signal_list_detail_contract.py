from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.db import Base
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Business, HealthSignalState, Organization
from backend.app.services import signals_service


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _create_business(db):
    org = Organization(name="Signals Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Signals Biz")
    db.add(biz)
    db.flush()
    return biz


def test_signal_list_and_detail_contract_fields():
    db = _session()
    biz = _create_business(db)
    now = datetime(2024, 4, 1, tzinfo=timezone.utc)
    state = HealthSignalState(
        business_id=biz.id,
        signal_id="expense.new_recurring:fp-9",
        signal_type="expense.new_recurring",
        fingerprint="fp-9",
        status="open",
        severity="warning",
        title="New recurring expense",
        summary="Recurring expense detected",
        payload_json={"vendor": "Acme"},
        detected_at=now,
        last_seen_at=now,
        updated_at=now,
    )
    db.add(state)
    db.commit()

    items, meta = signals_service.list_signal_states(db, biz.id)
    assert meta["count"] == 1
    assert items[0]["id"] == state.signal_id
    assert items[0]["type"] == state.signal_type
    assert items[0]["severity"] is not None
    assert items[0]["status"] is not None
    assert items[0]["title"] is not None
    assert items[0]["summary"] is not None
    assert items[0]["updated_at"] is not None

    detail = signals_service.get_signal_state_detail(db, biz.id, state.signal_id)
    assert detail["payload_json"] == {"vendor": "Acme"}
    assert detail["fingerprint"] == "fp-9"
    assert detail["detected_at"] is not None
    assert detail["last_seen_at"] is not None
    assert detail["resolved_at"] is None
    assert detail["updated_at"] is not None
