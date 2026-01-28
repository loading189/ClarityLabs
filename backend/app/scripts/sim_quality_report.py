from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models import RawEvent
import backend.app.sim.models  # noqa: F401


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _merchant_name(payload: Dict[str, Any]) -> str:
    txn = payload.get("transaction") if isinstance(payload, dict) else None
    if isinstance(txn, dict):
        return str(txn.get("merchant_name") or txn.get("name") or "Unknown")

    payload_type = str(payload.get("type") or "")
    if payload_type.startswith("stripe.payout"):
        return "Stripe Payout"
    if payload_type.startswith("stripe.balance.fee"):
        return "Stripe Fees"
    if payload_type.startswith("payroll.run"):
        sim_meta = payload.get("sim_meta") if isinstance(payload, dict) else None
        if isinstance(sim_meta, dict) and sim_meta.get("merchant"):
            return str(sim_meta["merchant"])
        return "Payroll"

    meta = payload.get("meta") if isinstance(payload, dict) else None
    if isinstance(meta, dict) and meta.get("integration"):
        return str(meta["integration"])

    return payload_type or "Unknown"


def _stream_name(payload: Dict[str, Any]) -> Optional[str]:
    sim_meta = payload.get("sim_meta") if isinstance(payload, dict) else None
    if isinstance(sim_meta, dict):
        stream = sim_meta.get("stream")
        if isinstance(stream, str):
            return stream
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sim quality report for restaurant_v1.")
    parser.add_argument("--business-id", required=True, help="Business UUID")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    if end_date <= start_date:
        raise SystemExit("end-date must be after start-date")

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc)

    with SessionLocal() as session:
        rows = session.execute(
            select(RawEvent).where(
                RawEvent.business_id == args.business_id,
                RawEvent.occurred_at >= start_dt,
                RawEvent.occurred_at < end_dt,
            )
        ).scalars()

        merchant_counts: Counter[str] = Counter()
        stream_counts: Counter[str] = Counter()
        total = 0

        for ev in rows:
            total += 1
            payload = ev.payload
            merchant_counts[_merchant_name(payload)] += 1
            stream = _stream_name(payload)
            if stream:
                stream_counts[stream] += 1

    days = max(1, (end_date - start_date).days)
    deposits = stream_counts.get("daily_deposits", 0)

    print("Sim quality report")
    print(f"Business: {args.business_id}")
    print(f"Range: {start_date.isoformat()} to {end_date.isoformat()} ({days} days)")
    print(f"Total events: {total}")
    print("")
    print("Merchant counts:")
    for name, count in merchant_counts.most_common():
        print(f"  {name}: {count}")

    print("")
    print("Cadence summary:")
    print(f"  deposits/day: {deposits / days:.2f}")
    print(f"  payroll count: {stream_counts.get('payroll', 0)}")
    print(f"  supplier count: {stream_counts.get('suppliers', 0)}")
    print(f"  rent count: {stream_counts.get('rent', 0)}")


if __name__ == "__main__":
    main()
