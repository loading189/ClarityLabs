from __future__ import annotations

from datetime import date
import hashlib
from typing import Dict, List, Tuple

Merchant = Tuple[str, str]

MERCHANT_SETS: Dict[str, List[Merchant]] = {
    "deposits": [
        ("Stripe Payouts", "Income"),
        ("Square Deposits", "Income"),
        ("Toast Payments", "Income"),
        ("Clover Deposits", "Income"),
    ],
    "payroll": [
        ("Gusto Payroll", "Payroll"),
        ("ADP Workforce", "Payroll"),
        ("Paychex Payroll", "Payroll"),
    ],
    "suppliers": [
        ("Sysco Foods", "Supplies"),
        ("US Foods", "Supplies"),
        ("Restaurant Depot", "Supplies"),
        ("Gordon Food Service", "Supplies"),
    ],
    "rent": [
        ("Main Street Properties", "Rent"),
        ("City Center Realty", "Rent"),
        ("Market Square Holdings", "Rent"),
    ],
    "utilities": [
        ("City Water Utility", "Utilities"),
        ("State Gas & Electric", "Utilities"),
        ("Comcast Business", "Utilities"),
    ],
    "software": [
        ("Toast POS", "Software"),
        ("Square POS", "Software"),
        ("Lightspeed", "Software"),
    ],
    "misc": [
        ("Amazon Business", "Misc"),
        ("Office Depot", "Misc"),
        ("Home Depot", "Misc"),
        ("Ace Hardware", "Misc"),
    ],
}


def _stable_index(seed: int, stream: str, when: date, size: int) -> int:
    key = f"{seed}:{stream}:{when.isoformat()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % size


def pick_merchant(stream: str, seed: int, when: date) -> Merchant:
    pool = MERCHANT_SETS.get(stream)
    if not pool:
        raise ValueError(f"unknown merchant stream '{stream}'")
    idx = _stable_index(seed, stream, when, len(pool))
    return pool[idx]
