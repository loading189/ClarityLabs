from __future__ import annotations

import uuid
import random
from datetime import datetime, timezone

PRODUCTS = ["Tee", "Mug", "Sticker Pack", "Hat", "Notebook"]

def make_shopify_order_paid_event(*, business_id: str, occurred_at: datetime | None = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    order_id = random.randint(10000, 99999)
    total = round(random.uniform(20, 280), 2)

    payload = {
        "type": "shopify.order.paid",
        "order": {
            "id": order_id,
            "name": f"#{order_id}",
            "processed_at": occurred_at.isoformat(),
            "total_price": total,
            "currency": "USD",
            "line_items": [{"title": random.choice(PRODUCTS), "quantity": random.randint(1, 3)}],
        },
        "meta": {"integration": "shopify"},
    }

    return {
        "source": "shopify",
        "source_event_id": f"order_{order_id}",
        "occurred_at": occurred_at,
        "payload": payload,
    }

def make_shopify_refund_event(*, business_id: str, occurred_at: datetime | None = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    refund_id = f"refund_{uuid.uuid4().hex[:10]}"
    amount = round(random.uniform(10, 120), 2)

    payload = {
        "type": "shopify.refund",
        "refund": {
            "id": refund_id,
            "created_at": occurred_at.isoformat(),
            "amount": amount,
            "currency": "USD",
            "note": "Customer refund",
        },
        "meta": {"integration": "shopify"},
    }

    return {
        "source": "shopify",
        "source_event_id": refund_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
