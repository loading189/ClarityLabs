from datetime import datetime, timezone
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.api.ledger import signed_amount
from backend.app.norma.from_events import raw_event_to_txn


def test_normalization_outputs_absolute_amount():
    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": "txn_100",
            "amount": -125.50,
            "name": "Comcast Cable",
            "merchant_name": "Comcast Cable",
        },
    }
    occurred_at = datetime(2024, 2, 5, 12, 0, tzinfo=timezone.utc)
    txn = raw_event_to_txn(payload, occurred_at, "evt_100")

    assert txn.amount == 125.50
    assert txn.amount >= 0
    assert txn.direction == "outflow"


def test_signed_amount_uses_direction():
    assert signed_amount(80.0, "inflow") == 80.0
    assert signed_amount(80.0, "outflow") == -80.0
