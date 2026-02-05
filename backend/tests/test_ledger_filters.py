import os
import sys
from datetime import datetime, date, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import Organization, Business, Account, Category, RawEvent, TxnCategorization
from backend.app.services import ledger_service


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed(db):
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    db.flush()
    acct = Account(business_id=biz.id, name="Operating", type="asset", subtype="cash")
    db.add(acct)
    db.flush()
    cat = Category(business_id=biz.id, name="Sales", account_id=acct.id)
    db.add(cat)
    db.flush()

    def add(evt_id: str, when: datetime, amount: float, desc: str):
        payload = {"type": "transaction.posted", "transaction": {"amount": amount, "name": desc, "merchant_name": desc}}
        db.add(RawEvent(business_id=biz.id, source="bank", source_event_id=evt_id, occurred_at=when, payload=payload))
        db.add(TxnCategorization(business_id=biz.id, source_event_id=evt_id, category_id=cat.id, source="manual", confidence=1.0))

    add("evt_1", datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "Alpha")
    add("evt_2", datetime(2024, 1, 2, tzinfo=timezone.utc), -30.0, "Bravo Vendor")
    add("evt_3", datetime(2024, 1, 2, tzinfo=timezone.utc), -10.0, "Bravo Vendor")
    db.commit()
    return biz.id


def test_ledger_filters_and_ordering_and_balance_math():
    db = _session()
    biz_id = _seed(db)

    res = ledger_service.ledger_query(
        db,
        biz_id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 3),
        search="bravo",
        limit=10,
        offset=0,
    )

    ids = [row["source_event_id"] for row in res["rows"]]
    assert ids == ["evt_2", "evt_3"]
    assert res["summary"]["row_count"] == 2
    assert res["summary"]["start_balance"] == 0.0
    assert res["summary"]["end_balance"] == -40.0
    assert res["rows"][0]["balance"] == -30.0
    assert res["rows"][1]["balance"] == -40.0
