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


def test_ledger_dimensions_stable_ordering():
    db = _session()
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    db.flush()

    acct_a = Account(business_id=biz.id, name="Alpha", type="asset", subtype="cash")
    acct_b = Account(business_id=biz.id, name="Beta", type="asset", subtype="cash")
    db.add_all([acct_a, acct_b])
    db.flush()
    cat_a = Category(business_id=biz.id, name="Sales", account_id=acct_a.id)
    cat_b = Category(business_id=biz.id, name="Ops", account_id=acct_b.id)
    db.add_all([cat_a, cat_b])
    db.flush()

    entries = [
        ("evt_1", acct_a, cat_a, "Acme", 10.0),
        ("evt_2", acct_a, cat_a, "Acme", 11.0),
        ("evt_3", acct_b, cat_b, "Bravo", -5.0),
    ]
    for idx, (eid, _acct, cat, vendor, amount) in enumerate(entries):
        payload = {"type": "transaction.posted", "transaction": {"amount": amount, "name": vendor, "merchant_name": vendor}}
        db.add(RawEvent(business_id=biz.id, source="bank", source_event_id=eid, occurred_at=datetime(2024, 1, idx + 1, tzinfo=timezone.utc), payload=payload))
        db.add(TxnCategorization(business_id=biz.id, source_event_id=eid, category_id=cat.id, source="manual", confidence=1.0))
    db.commit()

    accounts = ledger_service.ledger_dimensions(db, biz.id, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31), dimension="accounts")
    vendors = ledger_service.ledger_dimensions(db, biz.id, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31), dimension="vendors")

    assert [row["label"] for row in accounts] == ["Alpha", "Beta"]
    assert [row["vendor"] for row in vendors] == ["Acme", "Bravo"]
    assert accounts[0]["count"] == 2
    assert vendors[0]["total"] == 21.0
