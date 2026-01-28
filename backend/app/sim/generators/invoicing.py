from __future__ import annotations

import uuid
import random
from datetime import datetime, timezone

def make_invoice_paid_event(*, business_id: str, occurred_at: datetime | None = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    inv_id = f"inv_{uuid.uuid4().hex[:10]}"
    amount = round(random.uniform(150, 9000), 2)

    payload = {
        "type": "invoicing.invoice.paid",
        "invoice": {
            "invoice_id": inv_id,
            "paid_at": occurred_at.isoformat(),
            "amount": amount,
            "currency": "USD",
            "customer_name": random.choice(["Acme Co", "North Ridge", "Sunset Cafe", "Evergreen"]),
        },
        "meta": {"integration": "qbo_like"},
    }

    return {
        "source": "invoicing",
        "source_event_id": inv_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
