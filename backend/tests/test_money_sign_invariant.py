from datetime import datetime, timezone
from pathlib import Path
import os
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.api import ledger
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.normalize import NormalizedTransaction


def test_raw_event_to_txn_stripe_payout_inflow_amount_positive():
    payload = {
        "type": "stripe.payout.paid",
        "data": {"object": {"amount": 125.50}},
    }
    occurred_at = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    txn = raw_event_to_txn(payload, occurred_at, "evt_stripe_payout")

    assert txn.direction == "inflow"
    assert txn.amount == 125.50


def test_raw_event_to_txn_payroll_outflow_amount_positive():
    payload = {
        "type": "payroll.run.posted",
        "payroll": {"net_pay": 2200.00},
    }
    occurred_at = datetime(2024, 1, 20, 12, 0, tzinfo=timezone.utc)
    txn = raw_event_to_txn(payload, occurred_at, "evt_payroll_run")

    assert txn.direction == "outflow"
    assert txn.amount == 2200.00


def test_raw_event_to_txn_vendor_purchase_outflow_amount_positive():
    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": "txn_vendor",
            "amount": -48.75,
            "name": "US Foods",
            "merchant_name": "US Foods",
        },
    }
    occurred_at = datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)
    txn = raw_event_to_txn(payload, occurred_at, "evt_vendor")

    assert txn.direction == "outflow"
    assert txn.amount == 48.75


def test_cash_series_starting_cash_zero():
    occurred_at = datetime(2024, 2, 1, 12, 0, tzinfo=timezone.utc)
    txns = [
        NormalizedTransaction(
            id=None,
            source_event_id="evt_1",
            occurred_at=occurred_at,
            date=occurred_at.date(),
            description="Deposit",
            amount=100.0,
            direction="inflow",
            account="bank",
            category="sales",
            counterparty_hint=None,
        ),
        NormalizedTransaction(
            id=None,
            source_event_id="evt_2",
            occurred_at=occurred_at,
            date=occurred_at.date(),
            description="Vendor",
            amount=30.0,
            direction="outflow",
            account="bank",
            category="cogs",
            counterparty_hint=None,
        ),
        NormalizedTransaction(
            id=None,
            source_event_id="evt_3",
            occurred_at=occurred_at,
            date=occurred_at.date(),
            description="Deposit",
            amount=20.0,
            direction="inflow",
            account="bank",
            category="sales",
            counterparty_hint=None,
        ),
    ]

    series = ledger._build_cash_series(txns, starting_cash=0.0)

    assert [point.balance for point in series] == [100.0, 70.0, 90.0]
