from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Keep your merchant list (we’ll just weight it a bit by profile)
MERCHANTS = [
    ("SHELL OIL", "Fuel"),
    ("WALMART", "Retail"),
    ("AMAZON", "Retail"),
    ("PAYROLL", "Payroll"),
    ("SQUARE", "Income"),
    ("STRIPE PAYOUT", "Income"),
    ("COMCAST", "Utilities"),
    ("OFFICE DEPOT", "Office"),
]

# Simple profile knobs (you can tune later)
PROFILE_MULTIPLIER = {
    "quiet": 0.6,
    "normal": 1.0,
    "busy": 1.6,
    "chaos": 2.4,
}

def make_plaid_transaction_event(
    *,
    business_id: str,
    occurred_at: datetime | None = None,
    cfg: Optional[Any] = None,  # cfg is SimulatorConfig; Optional keeps it backwards-compatible
) -> dict[str, Any]:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    profile = getattr(cfg, "profile", "normal") if cfg else "normal"
    ticket_cents = int(getattr(cfg, "typical_ticket_cents", 6500)) if cfg else 6500

    mult = PROFILE_MULTIPLIER.get(profile, 1.0)

    # Choose merchant; optionally bias by profile
    # (chaos = more variety, quiet = more retail/utility)
    if profile == "quiet":
        pool = [m for m in MERCHANTS if m[1] in {"Retail", "Utilities", "Office", "Fuel"}]
    elif profile == "chaos":
        pool = MERCHANTS * 2  # more variety; simple trick
    else:
        pool = MERCHANTS

    name, hint = random.choice(pool)

    # Amount distribution:
    # Center around typical_ticket, add noise, apply profile multiplier
    base = ticket_cents / 100.0
    noise = random.uniform(0.25, 2.25)  # widen distribution
    amount = round(base * noise * mult, 2)

    # Bank convention: expenses positive, income negative
    if hint != "Income":
        amount = -amount

    source_event_id = f"sim_{uuid.uuid4().hex}"

    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": source_event_id,
            "amount": amount,
            "iso_currency_code": "USD",
            "date": occurred_at.date().isoformat(),
            "name": name,
            "merchant_name": name.title(),
            "payment_channel": "in_store",
            "pending": False,
        },
        "sim_meta": {
            "generator": "plaid",
            "hint": hint,
            "profile": profile,
            "typical_ticket_cents": ticket_cents,
        },
    }

    return {
        "source": "plaid",
        "source_event_id": source_event_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
