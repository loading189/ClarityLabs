from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import random
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Business, HealthSignalState, RawEvent, TxnCategorization
from backend.app.services import monitoring_service
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings
from backend.app.sim_v2 import catalog
from backend.app.sim_v2.models import SimV2SeedRequest
from backend.app.sim_v2.seeders.finance import baseline_events, delete_sim_v2_rows, insert_seed_events


@dataclass(frozen=True)
class SimClock:
    anchor_date: date
    lookback_days: int = 120
    forward_days: int = 14

    @property
    def start_date(self) -> date:
        return self.anchor_date - timedelta(days=self.lookback_days)

    @property
    def end_date(self) -> date:
        return self.anchor_date + timedelta(days=self.forward_days)


def _derive_seed(business_id: str, preset_id: str | None, anchor_date: date) -> int:
    digest = hashlib.sha256(f"{business_id}|{preset_id or 'custom'}|{anchor_date.isoformat()}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _scenario_inputs(req: SimV2SeedRequest) -> List[dict]:
    if req.scenarios:
        return [{"id": s.id, "intensity": s.intensity} for s in req.scenarios]
    if req.preset_id:
        preset = catalog.PRESETS.get(req.preset_id)
        if not preset:
            raise ValueError(f"unknown preset_id: {req.preset_id}")
        return list(preset)
    return [{"id": "steady_state", "intensity": 1}]


def _signals_summary(db: Session, business_id: str) -> Dict[str, object]:
    states = db.execute(
        select(HealthSignalState).where(HealthSignalState.business_id == business_id)
        .order_by(HealthSignalState.severity.asc(), HealthSignalState.signal_id.asc())
    ).scalars().all()

    by_severity: Dict[str, int] = {}
    by_domain: Dict[str, int] = {}
    for state in states:
        sev = state.severity or "unknown"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        domain = (state.signal_type or "unknown").split(".", 1)[0]
        by_domain[domain] = by_domain.get(domain, 0) + 1

    top = [
        {
            "signal_id": s.signal_id,
            "status": s.status,
            "severity": s.severity,
            "domain": (s.signal_type or "unknown").split(".", 1)[0],
            "title": s.title,
        }
        for s in states[:5]
    ]
    return {"total": len(states), "by_severity": by_severity, "by_domain": by_domain, "top": top}




def _coverage_inputs(db: Session, business_id: str, anchor_date: date) -> Dict[str, int]:
    window_start = anchor_date - timedelta(days=29)

    raw_events_count = int(
        db.execute(
            select(func.count()).select_from(RawEvent).where(
                RawEvent.business_id == business_id,
                RawEvent.source == "sim_v2",
            )
        ).scalar_one()
    )

    normalized_txns_count = int(
        db.execute(
            select(func.count()).select_from(TxnCategorization).where(
                TxnCategorization.business_id == business_id,
                TxnCategorization.source == "sim_v2",
            )
        ).scalar_one()
    )

    rows = db.execute(
        select(RawEvent.payload).where(
            RawEvent.business_id == business_id,
            RawEvent.source == "sim_v2",
            RawEvent.occurred_at >= datetime.combine(window_start, time.min, tzinfo=timezone.utc),
            RawEvent.occurred_at <= datetime.combine(anchor_date, time.max, tzinfo=timezone.utc),
        )
    ).all()

    deposits_count_last30 = 0
    expenses_count_last30 = 0
    vendors = set()
    for (payload,) in rows:
        if not isinstance(payload, dict):
            continue
        direction = str(payload.get("direction") or "")
        if direction == "inflow":
            deposits_count_last30 += 1
        elif direction == "outflow":
            expenses_count_last30 += 1
        vendor = payload.get("counterparty_hint")
        if isinstance(vendor, str) and vendor.strip():
            vendors.add(vendor.strip().lower())

    return {
        "raw_events_count": raw_events_count,
        "normalized_txns_count": normalized_txns_count,
        "deposits_count_last30": deposits_count_last30,
        "expenses_count_last30": expenses_count_last30,
        "distinct_vendors_last30": len(vendors),
        "balance_series_points": normalized_txns_count,
    }

def seed(db: Session, req: SimV2SeedRequest) -> dict:
    business = db.get(Business, req.business_id)
    if not business:
        raise ValueError("business not found")

    anchor_date = req.anchor_date or datetime.now(timezone.utc).date()
    clock = SimClock(anchor_date=anchor_date, lookback_days=req.lookback_days, forward_days=req.forward_days)
    seed_value = req.seed if req.seed is not None else _derive_seed(req.business_id, req.preset_id, anchor_date)
    rng = random.Random(seed_value)

    seed_coa_and_categories_and_mappings(db, req.business_id)

    deleted = 0
    if req.mode == "replace":
        deleted = delete_sim_v2_rows(db, req.business_id)

    events = baseline_events(rng=rng, start_date=clock.start_date, end_date=clock.end_date)
    scenarios = _scenario_inputs(req)
    for scenario in scenarios:
        definition = catalog.SCENARIOS.get(str(scenario["id"]))
        if not definition:
            raise ValueError(f"unknown scenario id: {scenario['id']}")
        definition.apply(events, {"anchor_date": anchor_date, "intensity": int(scenario.get("intensity", 1))})

    inserted = insert_seed_events(db, req.business_id, seed_value, events)
    db.commit()

    pulse_now = datetime.combine(anchor_date, time(hour=12, tzinfo=timezone.utc))
    pulse_result = monitoring_service.pulse(
        db,
        req.business_id,
        now=pulse_now,
        include_detector_results=True,
        force_run=True,
    )

    signals = _signals_summary(db, req.business_id)
    detector_rows = sorted(
        pulse_result.get("detector_results", []),
        key=lambda row: (str(row.get("domain", "")), str(row.get("signal_id", "")), str(row.get("detector_id", ""))),
    )
    coverage = {
        "window_observed": {"start_date": clock.start_date, "end_date": clock.anchor_date},
        "inputs": _coverage_inputs(db, req.business_id, anchor_date),
        "detectors": detector_rows,
    }
    return {
        "business_id": req.business_id,
        "window": {
            "anchor_date": clock.anchor_date,
            "start_date": clock.start_date,
            "end_date": clock.end_date,
            "lookback_days": clock.lookback_days,
            "forward_days": clock.forward_days,
        },
        "preset_id": req.preset_id,
        "scenarios_applied": scenarios,
        "stats": {
            "raw_events_inserted": inserted,
            "raw_events_deleted": deleted,
            "pulse_ran": True,
        },
        "signals": signals,
        "coverage": coverage,
    }


def reset(db: Session, business_id: str) -> dict:
    business = db.get(Business, business_id)
    if not business:
        raise ValueError("business not found")
    deleted = delete_sim_v2_rows(db, business_id)
    db.commit()
    monitoring_service.pulse(db, business_id)
    return {"business_id": business_id, "deleted_raw_events": deleted, "pulse_ran": True}
