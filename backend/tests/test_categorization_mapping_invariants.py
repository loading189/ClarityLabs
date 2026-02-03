from datetime import datetime, timezone
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.db import Base
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import Organization, Business, RawEvent, TxnCategorization
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.categorize import categorize_txn
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings
from backend.app.services.categorize_service import (
    list_txns_to_categorize,
    upsert_categorization,
    system_key_for_category,
)
from backend.app.api.routes.categorize import CategorizationUpsertIn


def _make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _create_business(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Test Biz", industry="test")
    db_session.add(biz)
    db_session.flush()
    return biz


def _event_payload(description: str, amount: float):
    return {
        "type": "transaction.posted",
        "transaction": {
            "description": description,
            "amount": amount,
            "account": "bank",
        },
    }


def test_categorization_mapping_from_seeded_categories():
    db_session = _make_session()
    biz = _create_business(db_session)
    seed_coa_and_categories_and_mappings(db_session, biz.id)

    event = RawEvent(
        business_id=biz.id,
        source="test",
        source_event_id="evt_1",
        occurred_at=datetime(2024, 1, 5, tzinfo=timezone.utc),
        payload=_event_payload("Comcast", -120.0),
    )
    db_session.add(event)
    db_session.commit()

    txns = list_txns_to_categorize(db_session, biz.id, limit=10, only_uncategorized=True)
    assert txns
    suggested = txns[0].get("suggested_category_id")
    if suggested:
        assert system_key_for_category(db_session, biz.id, suggested)


def test_upsert_categorization_requires_mapping():
    db_session = _make_session()
    biz = _create_business(db_session)
    seed_coa_and_categories_and_mappings(db_session, biz.id)

    event = RawEvent(
        business_id=biz.id,
        source="test",
        source_event_id="evt_2",
        occurred_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
        payload=_event_payload("Payroll", -5000.0),
    )
    db_session.add(event)
    db_session.commit()

    txn = raw_event_to_txn(event.payload, event.occurred_at, event.source_event_id)
    enriched = categorize_txn(txn)
    assert enriched.category in {"payroll", "uncategorized"}

    categories = db_session.execute(
        text("SELECT id FROM categories WHERE business_id = :biz_id ORDER BY name ASC"),
        {"biz_id": biz.id},
    ).fetchall()
    assert categories
    category_id = categories[0][0]

    res = upsert_categorization(
        db_session,
        biz.id,
        CategorizationUpsertIn(
            source_event_id=event.source_event_id,
            category_id=category_id,
            source="manual",
            confidence=1.0,
            note=None,
        ),
    )
    assert res["status"] == "ok"
    stored = db_session.query(TxnCategorization).filter_by(source_event_id=event.source_event_id).one()
    assert stored.category_id == category_id
