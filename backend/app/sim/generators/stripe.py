from __future__ import annotations

import uuid
import random
from datetime import datetime, timezone
from typing import Any, Optional

def make_stripe_payout_event(*, business_id: str, occurred_at: datetime | None = None, cfg: Optional[Any] = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    # payout is usually POSITIVE cash movement into bank
    amount = round(random.uniform(150, 4500), 2)

    payout_id = f"po_{uuid.uuid4().hex[:16]}"
    payload = {
        "type": "stripe.payout.paid",
        "data": {
            "object": {
                "id": payout_id,
                "amount": amount,
                "currency": "usd",
                "arrival_date": occurred_at.date().isoformat(),
                "status": "paid",
                "destination": "bank_account",
            }
        },
        "meta": {"integration": "stripe"},
    }

    return {
        "source": "stripe",
        "source_event_id": payout_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }

def make_stripe_fee_event(*, business_id: str, occurred_at: datetime | None = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)
    amount = round(random.uniform(2, 120), 2)

    fee_id = f"fee_{uuid.uuid4().hex[:16]}"
    payload = {
        "type": "stripe.balance.fee",
        "data": {"amount": amount, "currency": "usd", "description": "Stripe processing fees"},
        "meta": {"integration": "stripe"},
    }

    return {
        "source": "stripe",
        "source_event_id": fee_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
