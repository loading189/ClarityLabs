from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Business, Organization, RawEvent, TxnCategorization
from backend.app.services import monitoring_service
from backend.app.services.category_resolver import require_system_key_mapping
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings

DEMO_ORG_NAME = "Clarity Labs Demo Org"
DEMO_BUSINESS_NAME = "Clarity Labs Demo Business"
DEMO_SOURCE = "demo_seed"


@dataclass(frozen=True)
class DemoEventSpec:
    key: str
    day_offset: int
    amount: float
    direction: str
    description: str
    counterparty: str
    category_key: str
    categorize: bool


def _is_dev_env() -> bool:
    return (
        os.getenv("ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("APP_ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("NODE_ENV", "").lower() in {"dev", "development"}
    )


def _anchor_date(now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).date()


def _occurred_at(anchor: date, day_offset: int, direction: str) -> datetime:
    hour = 12 if direction == "inflow" else 16
    return datetime.combine(anchor + timedelta(days=day_offset), time(hour=hour, tzinfo=timezone.utc))


def _event_payload(spec: DemoEventSpec, *, source_event_id: str) -> Dict[str, Any]:
    return {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": source_event_id,
            "amount": spec.amount,
            "name": spec.description,
            "merchant_name": spec.counterparty,
        },
        "description": spec.description,
        "amount": spec.amount,
        "direction": spec.direction,
        "category": spec.category_key,
        "counterparty_hint": spec.counterparty,
        "demo_meta": {"seed": True, "version": 1},
    }


def _demo_event_specs() -> List[DemoEventSpec]:
    return [
        # Posted transactions (ledger + monitoring source-of-truth)
        DemoEventSpec(
            "sales_001",
            -20,
            5000.0,
            "inflow",
            "Card sales payout",
            "Stripe",
            "sales",
            True,
        ),
        DemoEventSpec(
            "supplies_001",
            -15,
            400.0,
            "outflow",
            "Office supplies",
            "Staples",
            "office_supplies",
            True,
        ),
        DemoEventSpec(
            "rent_001",
            -10,
            2500.0,
            "outflow",
            "Monthly rent",
            "Landlord",
            "rent",
            True,
        ),
        DemoEventSpec(
            "supplies_002",
            -5,
            300.0,
            "outflow",
            "Shipping supplies",
            "Uline",
            "office_supplies",
            True,
        ),
        DemoEventSpec(
            "inventory_spike",
            0,
            30000.0,
            "outflow",
            "Emergency inventory purchase",
            "Acme Vendor",
            "cogs",
            True,
        ),
        # Posted uncategorized transactions (drives hygiene signal)
        DemoEventSpec(
            "uncat_posted_01",
            -9,
            110.0,
            "outflow",
            "Unknown charge",
            "Unknown",
            "uncategorized",
            True,
        ),
        DemoEventSpec(
            "uncat_posted_02",
            -8,
            95.0,
            "outflow",
            "Unknown fee",
            "Unknown",
            "uncategorized",
            True,
        ),
        DemoEventSpec(
            "uncat_posted_03",
            -7,
            125.0,
            "outflow",
            "Unknown adjustment",
            "Unknown",
            "uncategorized",
            True,
        ),
        DemoEventSpec(
            "uncat_posted_04",
            -6,
            140.0,
            "outflow",
            "Unknown service",
            "Unknown",
            "uncategorized",
            True,
        ),
        DemoEventSpec(
            "uncat_posted_05",
            -4,
            115.0,
            "outflow",
            "Unknown transfer",
            "Unknown",
            "uncategorized",
            True,
        ),
        # Uncategorized transactions kept for the Categorize queue
        DemoEventSpec(
            "uncat_review_01",
            -3,
            130.0,
            "outflow",
            "Misc charge",
            "Unknown",
            "uncategorized",
            False,
        ),
        DemoEventSpec(
            "uncat_review_02",
            -2,
            160.0,
            "outflow",
            "Misc fee",
            "Unknown",
            "uncategorized",
            False,
        ),
    ]


def _source_event_id(business_id: str, key: str) -> str:
    return f"{DEMO_SOURCE}:{business_id}:{key}"


def _ensure_demo_business(db: Session) -> Tuple[Organization, Business]:
    org = db.execute(select(Organization).where(Organization.name == DEMO_ORG_NAME)).scalars().first()
    if not org:
        org = Organization(name=DEMO_ORG_NAME)
        db.add(org)
        db.flush()

    biz = (
        db.execute(
            select(Business).where(
                Business.org_id == org.id,
                Business.name == DEMO_BUSINESS_NAME,
            )
        )
        .scalars()
        .first()
    )
    if not biz:
        biz = Business(org_id=org.id, name=DEMO_BUSINESS_NAME, industry="restaurant")
        db.add(biz)
        db.flush()
    return org, biz


# Golden-path flow: seed deterministic raw events -> ensure posted categorizations -> run monitoring
# so the same inputs always yield the same ledger rows, signals, and transaction evidence.
# This is the single entry point for demo seeding to keep the workflow reproducible.

def seed_demo(db: Session, *, run_monitoring: bool = True) -> Dict[str, Any]:
    if not _is_dev_env():
        raise HTTPException(status_code=404, detail="demo seed is only available in dev")

    org, biz = _ensure_demo_business(db)
    seed_coa_and_categories_and_mappings(db, biz.id)

    anchor = _anchor_date()
    specs = _demo_event_specs()

    existing_source_ids = set(
        db.execute(
            select(RawEvent.source_event_id).where(
                RawEvent.business_id == biz.id,
                RawEvent.source == DEMO_SOURCE,
            )
        )
        .scalars()
        .all()
    )
    existing_categorizations = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == biz.id)
        )
        .scalars()
        .all()
    )

    inserted_events = 0
    inserted_categorizations = 0

    for spec in specs:
        source_event_id = _source_event_id(biz.id, spec.key)
        occurred_at = _occurred_at(anchor, spec.day_offset, spec.direction)
        if source_event_id not in existing_source_ids:
            db.add(
                RawEvent(
                    business_id=biz.id,
                    source=DEMO_SOURCE,
                    source_event_id=source_event_id,
                    occurred_at=occurred_at,
                    processed_at=occurred_at + timedelta(minutes=5),
                    payload=_event_payload(spec, source_event_id=source_event_id),
                )
            )
            inserted_events += 1

        if spec.categorize and source_event_id not in existing_categorizations:
            mapping = require_system_key_mapping(
                db,
                biz.id,
                spec.category_key,
                context="demo_seed",
            )
            db.add(
                TxnCategorization(
                    business_id=biz.id,
                    source_event_id=source_event_id,
                    category_id=mapping["category_id"],
                    confidence=1.0,
                    source=DEMO_SOURCE,
                    note="demo_seed",
                )
            )
            inserted_categorizations += 1

    db.commit()

    monitor_result = None
    if run_monitoring:
        monitor_result = monitoring_service.pulse(db, biz.id, force_run=True)

    window_start = anchor - timedelta(days=29)
    window_end = anchor

    return {
        "organization_id": org.id,
        "business_id": biz.id,
        "seeded": inserted_events > 0 or inserted_categorizations > 0,
        "window": {
            "start_date": window_start.isoformat(),
            "end_date": window_end.isoformat(),
            "anchor_date": anchor.isoformat(),
        },
        "stats": {
            "raw_events_inserted": inserted_events,
            "categorizations_inserted": inserted_categorizations,
        },
        "monitoring": monitor_result,
    }
