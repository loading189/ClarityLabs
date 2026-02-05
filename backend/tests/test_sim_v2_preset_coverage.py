from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sim_v2_preset_coverage.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.models import Business, Organization
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.sim_v2.engine import seed
from backend.app.sim_v2.models import SimV2SeedRequest


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


def _biz(db_session):
    org = Organization(name="Sim V2 Coverage Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Coverage Biz")
    db_session.add(biz)
    db_session.commit()
    db_session.refresh(biz)
    return biz


def _seed_preset(db_session, business_id: str, preset_id: str) -> dict:
    return seed(
        db_session,
        SimV2SeedRequest(
            business_id=business_id,
            preset_id=preset_id,
            anchor_date=date(2025, 1, 15),
            mode="replace",
        ),
    )


def _assert_detector_coverage(payload: dict) -> None:
    detectors = payload["coverage"]["detectors"]
    assert detectors
    assert any(bool(row["ran"]) for row in detectors)
    expected = sorted(
        detectors,
        key=lambda row: (str(row.get("domain", "")), str(row.get("signal_id", "")), str(row.get("detector_id", ""))),
    )
    assert detectors == expected


def test_cash_strained_has_liquidity_warning_coverage(db_session):
    biz = _biz(db_session)
    payload = _seed_preset(db_session, biz.id, "cash_strained")

    assert int(payload["signals"]["total"]) >= 6
    detectors = payload["coverage"]["detectors"]
    assert any(
        row["domain"] == "liquidity" and row["fired"] and row["severity"] in {"warning", "critical"}
        for row in detectors
    )
    _assert_detector_coverage(payload)


def test_revenue_decline_has_revenue_warning_coverage(db_session):
    biz = _biz(db_session)
    payload = _seed_preset(db_session, biz.id, "revenue_decline")

    assert int(payload["signals"]["total"]) >= 6
    detectors = payload["coverage"]["detectors"]
    assert any(
        row["domain"] == "revenue" and row["fired"] and row["severity"] in {"warning", "critical"}
        for row in detectors
    )
    _assert_detector_coverage(payload)


def test_messy_books_has_hygiene_signals(db_session):
    biz = _biz(db_session)
    payload = _seed_preset(db_session, biz.id, "messy_books")

    assert int(payload["signals"]["total"]) >= 4
    detector_ids = {row["signal_id"] for row in payload["coverage"]["detectors"] if row["fired"]}
    assert any(signal_id.startswith("hygiene.") for signal_id in detector_ids)
    _assert_detector_coverage(payload)
