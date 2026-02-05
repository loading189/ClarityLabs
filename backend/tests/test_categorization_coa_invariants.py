from datetime import datetime, timezone
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.norma.merchant import merchant_key
from backend.app.norma.ledger import build_cash_ledger
from backend.app.norma.normalize import NormalizedTransaction
from backend.tests.test_categorization_mapping_invariants import _make_session, _create_business
from backend.app.models import Account, Category, BusinessCategoryMap


def test_categories_have_account_mapping_or_uncategorized():
    db = _make_session()
    biz = _create_business(db)
    account = Account(business_id=biz.id, name="Ops", type="expense", subtype="ops")
    db.add(account)
    db.flush()
    uncategorized = Category(business_id=biz.id, name="Uncategorized", account_id=account.id)
    db.add(uncategorized)
    db.flush()
    db.add(BusinessCategoryMap(business_id=biz.id, system_key="uncategorized", category_id=uncategorized.id))
    db.commit()

    categories = db.query(Category).filter(Category.business_id == biz.id).all()
    assert categories
    for cat in categories:
        assert cat.account_id is not None


def test_vendor_normalization_deterministic():
    assert merchant_key("ACME COFFEE #123") == merchant_key("acme coffee 123")


def test_ledger_ordering_and_running_balance_deterministic():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    txns = [
        NormalizedTransaction(id=None, source_event_id="b", occurred_at=t0, date=t0.date(), description="B", amount=10.0, direction="inflow", account="bank", category="sales"),
        NormalizedTransaction(id=None, source_event_id="a", occurred_at=t0, date=t0.date(), description="A", amount=3.0, direction="outflow", account="bank", category="ops"),
    ]
    ledger_one = build_cash_ledger(txns, opening_balance=0)
    ledger_two = build_cash_ledger(txns, opening_balance=0)
    assert [r.source_event_id for r in ledger_one] == [r.source_event_id for r in ledger_two]
    assert [r.balance for r in ledger_one] == [r.balance for r in ledger_two]
    assert ledger_one[-1].balance == 7.0
