# backend/app/sim/generators/payroll.py
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any, Optional


def _stable_id(prefix: str, key: str, length: int = 12) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def make_payroll_run_event(
    *,
    business_id: str,
    occurred_at: datetime | None = None,
    source_event_id: str | None = None,
    cfg: Optional[Any] = None,
) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    # Deterministic event id if not provided by engine
    if source_event_id is None:
        source_event_id = _stable_id(
            "payroll",
            f"{business_id}|{occurred_at.isoformat()}|payroll_run",
            length=32,
        )

    # IMPORTANT: run_id must also be deterministic (derive from source_event_id)
    run_id = _stable_id("payroll", source_event_id, length=12)

    # If you use randomness here, it must be deterministic too.
    # Seed a local RNG from the source_event_id so the same event always has same amounts.
    seed_int = int(hashlib.sha256(source_event_id.encode("utf-8")).hexdigest()[:16], 16)
    r = random.Random(seed_int)

    gross_pay = round(r.uniform(6000, 12000), 2)
    taxes = round(gross_pay * r.uniform(0.12, 0.20), 2)
    net_pay = round(gross_pay - taxes, 2)

    payload = {
        "type": "payroll.run.posted",
        "meta": {"integration": "gusto_like"},
        "payroll": {
            "run_id": run_id,
            "currency": "USD",
            "gross_pay": gross_pay,
            "taxes": taxes,
            "net_pay": net_pay,
            "processed_at": occurred_at.isoformat(),
        },
    }

    return {
        "source": "payroll",
        "source_event_id": source_event_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
