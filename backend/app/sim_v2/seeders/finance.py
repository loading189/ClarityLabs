from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import random
from typing import Dict, Iterable, List, Tuple

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from backend.app.models import Business, BusinessCategoryMap, Category, RawEvent, TxnCategorization


@dataclass
class SeedEvent:
    day: date
    amount: float
    direction: str
    description: str
    counterparty_hint: str
    category_key: str


def _dt(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=0, tzinfo=timezone.utc))


def delete_sim_v2_rows(db: Session, business_id: str) -> int:
    source_ids = db.execute(
        select(RawEvent.source_event_id).where(
            RawEvent.business_id == business_id,
            RawEvent.source == "sim_v2",
        )
    ).scalars().all()
    if source_ids:
        db.execute(
            delete(TxnCategorization).where(
                and_(
                    TxnCategorization.business_id == business_id,
                    TxnCategorization.source_event_id.in_(source_ids),
                )
            )
        )
    res = db.execute(
        delete(RawEvent).where(
            RawEvent.business_id == business_id,
            RawEvent.source == "sim_v2",
        )
    )
    return int(getattr(res, "rowcount", 0) or 0)


def category_ids_by_key(db: Session, business_id: str) -> Dict[str, str]:
    rows = db.execute(
        select(BusinessCategoryMap.system_key, Category.id)
        .join(Category, Category.id == BusinessCategoryMap.category_id)
        .where(BusinessCategoryMap.business_id == business_id)
    ).all()
    return {str(k): str(v) for k, v in rows}


def insert_seed_events(
    db: Session,
    business_id: str,
    seed: int,
    events: Iterable[SeedEvent],
) -> int:
    inserted = 0
    cat_map = category_ids_by_key(db, business_id)
    for idx, ev in enumerate(sorted(events, key=lambda x: (x.day, x.description, x.counterparty_hint, x.amount, x.direction))):
        source_event_id = f"sim_v2:{business_id}:{seed}:{idx:06d}"
        payload = {
            "type": "plaid.transaction",
            "description": ev.description,
            "amount": round(ev.amount, 2),
            "direction": ev.direction,
            "category": ev.category_key,
            "counterparty_hint": ev.counterparty_hint,
            "sim_meta": {"v": 2},
        }
        db.add(
            RawEvent(
                business_id=business_id,
                source="sim_v2",
                source_event_id=source_event_id,
                occurred_at=_dt(ev.day, 12 if ev.direction == "inflow" else 16),
                payload=payload,
            )
        )
        cat_id = cat_map.get(ev.category_key) or cat_map.get("uncategorized")
        if cat_id:
            db.add(
                TxnCategorization(
                    business_id=business_id,
                    source_event_id=source_event_id,
                    category_id=cat_id,
                    confidence=1.0,
                    source="sim_v2",
                    note="sim_v2",
                )
            )
        inserted += 1
    return inserted


def baseline_events(
    *,
    rng: random.Random,
    start_date: date,
    end_date: date,
) -> List[SeedEvent]:
    events: List[SeedEvent] = []
    day = start_date
    while day <= end_date:
        # Revenue cadence (daily weekdays)
        if day.weekday() < 5:
            events.append(SeedEvent(day, rng.uniform(1200, 1800), "inflow", "Daily card deposit", "stripe", "sales"))

        # Payroll (biweekly Fridays)
        if day.weekday() == 4 and ((day - start_date).days % 14 == 0):
            events.append(SeedEvent(day, rng.uniform(1200, 1700), "outflow", "Payroll run", "payroll", "payroll"))

        # Weekly vendors
        if day.weekday() in {1, 3}:
            events.append(SeedEvent(day, rng.uniform(180, 360), "outflow", "Office supplies", "Staples", "office_supplies"))
        if day.weekday() == 2:
            events.append(SeedEvent(day, rng.uniform(240, 430), "outflow", "Food inventory", "Sysco", "cogs"))

        # Monthly recurring
        if day.day == 1:
            events.append(SeedEvent(day, 2600.0, "outflow", "Rent", "Landlord", "rent"))
        if day.day in {5, 20}:
            events.append(SeedEvent(day, 220.0, "outflow", "SaaS Subscription", "Notion", "software"))

        day += timedelta(days=1)
    return events


def apply_cash_crunch(events: List[SeedEvent], *, anchor_date: date, intensity: int) -> None:
    for d in range(0, 21):
        day = anchor_date - timedelta(days=d)
        events.append(SeedEvent(day, 1300.0 + (200 * intensity), "outflow", "Emergency vendor payment", "Acme Vendor", "cogs"))
        if d % 3 == 0:
            events.append(SeedEvent(day, 500.0 + (120 * intensity), "outflow", "Short-term debt service", "Lender", "taxes"))
    for d in range(0, 14):
        day = anchor_date - timedelta(days=d)
        events.append(SeedEvent(day, 450.0 - (40 * intensity), "inflow", "Reduced card deposit", "stripe", "sales"))


def apply_revenue_drop(events: List[SeedEvent], *, anchor_date: date, intensity: int) -> None:
    for d in range(0, 45):
        day = anchor_date - timedelta(days=d)
        if day.weekday() < 5:
            events.append(SeedEvent(day, max(120.0, 900.0 - 120 * intensity), "inflow", "Revenue slump deposit", "stripe", "sales"))


def apply_expense_spike(events: List[SeedEvent], *, anchor_date: date, intensity: int) -> None:
    for d in range(0, 30):
        day = anchor_date - timedelta(days=d)
        if day.weekday() in {1, 3, 4}:
            events.append(SeedEvent(day, 500 + (220 * intensity), "outflow", "Supplier surge", "Acme Vendor", "cogs"))


def apply_vendor_concentration(events: List[SeedEvent], *, anchor_date: date, intensity: int) -> None:
    for d in range(0, 30):
        day = anchor_date - timedelta(days=d)
        if day.weekday() < 5:
            events.append(SeedEvent(day, 650 + 120 * intensity, "outflow", "Single vendor dependency", "Acme Vendor", "cogs"))


def apply_messy_books(events: List[SeedEvent], *, anchor_date: date, intensity: int) -> None:
    for d in range(0, 20):
        day = anchor_date - timedelta(days=d)
        events.append(SeedEvent(day, 80 + 30 * intensity, "outflow", "Unknown charge", "Unknown", "uncategorized"))


def apply_timing_mismatch(events: List[SeedEvent], *, anchor_date: date, intensity: int) -> None:
    for d in range(0, 21):
        day = anchor_date - timedelta(days=d)
        if d % 2 == 0:
            events.append(SeedEvent(day, 120 + (20 * intensity), "inflow", "Delayed payout", "stripe", "sales"))
        events.append(SeedEvent(day, 550 + (80 * intensity), "outflow", "Payroll advance", "payroll", "payroll"))
