from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auto_categorize.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import (
    Business,
    Organization,
    RawEvent,
    VendorCategoryMap,
    Category,
    TxnCategorization,
)
from backend.app.norma.merchant import merchant_key
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings


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
    org = Organization(name="AutoCat Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="AutoCat Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def test_auto_categorize_applies_vendor_map(client, db_session):
    biz = _create_business(db_session)
    seed_coa_and_categories_and_mappings(db_session, biz.id)
    category = db_session.execute(
        select(Category).where(Category.business_id == biz.id).order_by(Category.name.asc())
    ).scalars().first()
    assert category is not None

    ev = RawEvent(
        business_id=biz.id,
        source="bank",
        source_event_id="ev-1",
        occurred_at=datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc),
        payload={
            "type": "transaction.posted",
            "transaction": {
                "transaction_id": "ev-1",
                "amount": -20.0,
                "name": "Vendor X",
                "merchant_name": "Vendor X",
            },
        },
    )
    db_session.add(ev)
    db_session.add(
        VendorCategoryMap(
            business_id=biz.id,
            vendor_key=merchant_key("Vendor X"),
            category_id=category.id,
            confidence=0.95,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    resp = client.post(f"/api/categorize/auto/{biz.id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["applied"] == 1

    rows = db_session.execute(
        select(TxnCategorization).where(
            TxnCategorization.business_id == biz.id,
            TxnCategorization.source_event_id == "ev-1",
        )
    ).scalars().all()
    assert len(rows) == 1
