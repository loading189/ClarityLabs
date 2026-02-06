import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_golden_path_smoke.db")
os.environ.setdefault("ENV", "dev")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import HealthSignalState, TxnCategorization
from backend.app.services import monitoring_service
from backend.app.services.category_resolver import require_system_key_mapping


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


# Golden path: seed -> pulse -> validate ledger, signals, transaction evidence, and deterministic recategorization.

def test_golden_path_smoke(client, db_session):
    seed_resp = client.post("/demo/seed")
    assert seed_resp.status_code == 200
    payload = seed_resp.json()
    business_id = payload["business_id"]
    window = payload["window"]

    pulse = monitoring_service.pulse(db_session, business_id, force_run=True)
    assert pulse["ran"] is True

    ledger_resp = client.get(
        f"/ledger/business/{business_id}/lines",
        params={
            "start_date": window["start_date"],
            "end_date": window["end_date"],
            "limit": 200,
        },
    )
    assert ledger_resp.status_code == 200
    ledger_rows = ledger_resp.json()
    assert len(ledger_rows) > 0

    signals_resp = client.get(f"/api/signals?business_id={business_id}")
    assert signals_resp.status_code == 200
    signals_payload = signals_resp.json()
    assert len(signals_payload.get("signals", [])) > 0

    signal_states = (
        db_session.execute(
            select(HealthSignalState).where(HealthSignalState.business_id == business_id)
        )
        .scalars()
        .all()
    )
    target_state = next(
        (
            state
            for state in signal_states
            if isinstance(state.payload_json, dict)
            and state.payload_json.get("evidence_source_event_ids")
        ),
        None,
    )
    assert target_state is not None

    signal_detail_resp = client.get(f"/api/signals/{business_id}/{target_state.signal_id}")
    assert signal_detail_resp.status_code == 200
    signal_detail = signal_detail_resp.json()
    payload_json = signal_detail.get("payload_json") or {}
    evidence_ids = payload_json.get("evidence_source_event_ids")
    assert isinstance(evidence_ids, list) and evidence_ids

    source_event_id = evidence_ids[0]
    txn_detail_resp = client.get(f"/api/transactions/{business_id}/{source_event_id}")
    assert txn_detail_resp.status_code == 200
    txn_detail = txn_detail_resp.json()
    assert txn_detail["raw_event"]["payload"]
    assert txn_detail["raw_event"]["processed_at"] is not None
    assert txn_detail["related_signals"]
    assert txn_detail["audit_history"]

    hygiene_state = next(
        (
            state
            for state in signal_states
            if state.signal_type == "hygiene.uncategorized_high"
        ),
        None,
    )
    assert hygiene_state is not None

    uncat_map = require_system_key_mapping(db_session, business_id, "uncategorized", context="golden_path_test")
    replacement_map = require_system_key_mapping(
        db_session,
        business_id,
        "office_supplies",
        context="golden_path_test",
    )
    uncat_rows = (
        db_session.execute(
            select(TxnCategorization).where(
                TxnCategorization.business_id == business_id,
                TxnCategorization.category_id == uncat_map["category_id"],
            )
        )
        .scalars()
        .all()
    )
    assert len(uncat_rows) >= 5
    for row in uncat_rows:
        row.category_id = replacement_map["category_id"]
    db_session.commit()

    monitoring_service.pulse(db_session, business_id, force_run=True)
    updated_hygiene = (
        db_session.execute(
            select(HealthSignalState).where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.signal_type == "hygiene.uncategorized_high",
            )
        )
        .scalars()
        .first()
    )
    assert updated_hygiene is None or updated_hygiene.status == "resolved"
