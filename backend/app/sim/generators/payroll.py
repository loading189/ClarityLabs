from __future__ import annotations

import uuid
import random
from datetime import datetime, timezone

def make_payroll_run_event(*, business_id: str, occurred_at: datetime | None = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)

    run_id = f"payroll_{uuid.uuid4().hex[:12]}"
    gross = round(random.uniform(1200, 18000), 2)
    taxes = round(gross * random.uniform(0.12, 0.22), 2)
    net = round(gross - taxes, 2)

    payload = {
        "type": "payroll.run.posted",
        "payroll": {
            "run_id": run_id,
            "processed_at": occurred_at.isoformat(),
            "gross_pay": gross,
            "taxes": taxes,
            "net_pay": net,
            "currency": "USD",
        },
        "meta": {"integration": "gusto_like"},
    }

    return {
        "source": "payroll",
        "source_event_id": run_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }
