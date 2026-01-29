from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def stable_stripe_object_id(prefix: str, source_event_id: str, length: int = 16) -> str:
    """
    Deterministic Stripe-like object id derived from the event's stable identity.
    Example: stable_stripe_object_id("po", "stripe_abcd...") -> "po_<hashprefix>"
    """
    digest = hashlib.sha256(source_event_id.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def make_stripe_payout_event(
    *,
    business_id: str,
    occurred_at: datetime | None = None,
    cfg: Optional[Any] = None,
    source_event_id: str,  # ✅ REQUIRED: caller/engine provides stable event id
) -> dict:
    """
    Stripe payout event.

    Determinism note:
    - payout 'data.object.id' is derived from source_event_id so it won't change between runs.
    - 'source_event_id' itself must be stable/deterministic upstream if you're doing golden runs.
    """
    occurred_at = occurred_at or datetime.now(timezone.utc)

    payout_object_id = stable_stripe_object_id("po", source_event_id)

    # payout is usually POSITIVE cash movement into bank
    amount = round(random.uniform(150, 4500), 2)

    payload = {
        "type": "stripe.payout.paid",
        "data": {
            "object": {
                "id": payout_object_id,
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
        "source_event_id": source_event_id,  # ✅ was payout_id (undefined)
        "occurred_at": occurred_at,
        "payload": payload,
    }


def make_stripe_fee_event(
    *,
    business_id: str,
    occurred_at: datetime | None = None,
    source_event_id: str | None = None,  # ✅ optional override for deterministic mode
) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)
    amount = round(random.uniform(2, 120), 2)

    # If you care about deterministic golden runs, pass source_event_id in from engine.
    fee_event_id = source_event_id or f"fee_{uuid.uuid4().hex[:16]}"

    payload = {
        "type": "stripe.balance.fee",
        "data": {"amount": amount, "currency": "usd", "description": "Stripe processing fees"},
        "meta": {"integration": "stripe"},
    }

    return {
        "source": "stripe",
        "source_event_id": fee_event_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
