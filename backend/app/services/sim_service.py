from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Optional, Dict, Any, List, Literal

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from backend.app.models import Business, RawEvent, BusinessIntegrationProfile
from backend.app.services.raw_event_service import insert_raw_event_idempotent, canonical_source_event_id
from backend.app.sim.models import SimulatorConfig
from backend.app.sim.profiles import PROFILES
from backend.app.sim.generators.plaid import make_plaid_transaction_event
from backend.app.sim.generators.stripe import make_stripe_payout_event, make_stripe_fee_event
from backend.app.sim.generators.shopify import make_shopify_order_paid_event, make_shopify_refund_event
from backend.app.sim.generators.payroll import make_payroll_run_event
from backend.app.sim.generators.invoicing import make_invoice_paid_event
from backend.app.sim.generators.restaurant_v1 import generate_restaurant_v1_events


# ============================================================
# Scenario catalog (v0) — hardcoded starter set
# ============================================================

SCENARIO_CATALOG: Dict[str, Any] = {
    "version": 1,
    "scenarios": [
        {
            "id": "restaurant_v1",
            "name": "Restaurant (v1)",
            "summary": "Daily deposits, weekly suppliers, biweekly payroll, monthly fixed costs, occasional misc spend.",
            "defaults": {
                "plan": {
                    "business_hours": {"open_hour": 11, "close_hour": 22, "business_hours_only": True},
                    "volume": {"events_per_day": 55},
                    "ticket": {"typical_ticket_cents": 2800},
                    "mix": {"bank": True, "card_processor": True, "ecommerce": False, "payroll": True, "invoicing": False},
                    "seasonality": {"enabled": True, "strength": 0.12},
                }
            },
        },
        {
            "id": "service_v1",
            "name": "Service Business (v1)",
            "summary": "Invoicing + bank deposits, fewer daily transactions, payroll biweekly.",
            "defaults": {
                "plan": {
                    "business_hours": {"open_hour": 9, "close_hour": 17, "business_hours_only": True},
                    "volume": {"events_per_day": 12},
                    "ticket": {"typical_ticket_cents": 6500},
                    "mix": {"bank": True, "card_processor": False, "ecommerce": False, "payroll": True, "invoicing": True},
                    "seasonality": {"enabled": False, "strength": 0.0},
                }
            },
        },
        {
            "id": "ecommerce_v1",
            "name": "E-commerce (v1)",
            "summary": "Shopify orders daily, refunds occasionally, card payouts, light payroll.",
            "defaults": {
                "plan": {
                    "business_hours": {"open_hour": 8, "close_hour": 22, "business_hours_only": False},
                    "volume": {"events_per_day": 35},
                    "ticket": {"typical_ticket_cents": 4200},
                    "mix": {"bank": True, "card_processor": True, "ecommerce": True, "payroll": False, "invoicing": False},
                    "seasonality": {"enabled": True, "strength": 0.18},
                }
            },
        },
    ],
}


# ============================================================
# Helpers
# ============================================================


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _intervention_active(iv: Dict[str, Any], day: date) -> bool:
    if not iv.get("enabled", True):
        return False
    try:
        start = date.fromisoformat(iv["start_date"])
    except Exception:
        return False
    dur = iv.get("duration_days")
    if dur is None:
        return day >= start
    end = start + timedelta(days=int(dur) - 1)
    return start <= day <= end


def _parse_yyyy_mm_dd(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid date '{s}'. Expected YYYY-MM-DD.")


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _default_config_for(business_id: str) -> SimulatorConfig:
    now = utcnow()
    return SimulatorConfig(
        business_id=business_id,
        enabled=True,
        profile="normal",
        avg_events_per_day=12,
        typical_ticket_cents=6500,
        payroll_every_n_days=14,
        next_emit_at=now,
        last_emit_at=None,
        max_backfill_events=250,
        seed=1337,
        lock_owner=None,
        lock_expires_at=None,
        updated_at=now,
    )


def _to_out(cfg: SimulatorConfig) -> Dict[str, Any]:
    return {
        "business_id": cfg.business_id,
        "enabled": cfg.enabled,
        "profile": cfg.profile,
        "avg_events_per_day": cfg.avg_events_per_day,
        "typical_ticket_cents": cfg.typical_ticket_cents,
        "payroll_every_n_days": cfg.payroll_every_n_days,
        "updated_at": cfg.updated_at,
    }


def _get_or_create_integration_profile(db: Session, business_id: str) -> BusinessIntegrationProfile:
    prof = db.get(BusinessIntegrationProfile, business_id)
    if prof:
        if prof.simulation_params is None or not isinstance(prof.simulation_params, dict):
            prof.simulation_params = {}
        prof.simulation_params.setdefault("volume_level", "medium")
        prof.simulation_params.setdefault("volatility", "normal")
        prof.simulation_params.setdefault("seasonality", False)
        return prof

    prof = BusinessIntegrationProfile(business_id=business_id)
    prof.simulation_params = {"volume_level": "medium", "volatility": "normal", "seasonality": False}
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def _safe_sim_params(prof: BusinessIntegrationProfile) -> Dict[str, Any]:
    sp = getattr(prof, "simulation_params", None)
    return sp if isinstance(sp, dict) else {"volume_level": "medium", "volatility": "normal", "seasonality": False}


def _get_simulator_blob(prof: BusinessIntegrationProfile) -> Dict[str, Any]:
    sp = _safe_sim_params(prof)
    sim = sp.get("simulator")
    if not isinstance(sim, dict):
        sim = {}
        sp["simulator"] = sim
        prof.simulation_params = sp
    return sim


def _mods_from_interventions(
    ivs: List[Dict[str, Any]],
    day: date,
) -> Dict[str, Any]:
    mods = {"revenue_mult": 1.0, "expense_mult": 1.0, "deposit_delay_days": 0, "refund_rate_mult": 1.0}

    for iv in ivs:
        if not isinstance(iv, dict):
            continue
        if not _intervention_active(iv, day):
            continue

        kind = iv.get("kind")
        params = iv.get("params") or {}

        if kind == "revenue_drop":
            pct = float(params.get("pct", 0.30))
            mods["revenue_mult"] *= max(0.05, 1.0 - pct)

        elif kind == "expense_spike":
            pct = float(params.get("pct", 0.25))
            mods["expense_mult"] *= (1.0 + pct)

        elif kind == "deposit_delay":
            days = int(params.get("days", 3))
            mods["deposit_delay_days"] = max(mods["deposit_delay_days"], days)

        elif kind == "refund_spike":
            rr = float(params.get("refund_rate", 0.08))
            # This is a multiplier; actual generator decides base refund probability
            mods["refund_rate_mult"] *= max(0.1, rr / 0.02)  # 0.02 base -> 1.0
    return mods


def _scenario_defaults(scenario_id: str) -> Dict[str, Any]:
    s = next((x for x in SCENARIO_CATALOG["scenarios"] if x["id"] == scenario_id), None)
    if not s:
        s = next(x for x in SCENARIO_CATALOG["scenarios"] if x["id"] == "restaurant_v1")
    return (s.get("defaults") or {}).get("plan") or {}


def _merge_plan(defaults: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(defaults)
    for k, v in (plan or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def _render_story(
    business_id: str,
    scenario_id: str,
    story_version: int,
    plan: Dict[str, Any],
    interventions: List[Dict[str, Any]],
) -> str:
    mix = plan.get("mix", {}) or {}
    hours = plan.get("business_hours", {}) or {}
    vol = plan.get("volume", {}) or {}
    ticket = plan.get("ticket", {}) or {}

    sources = []
    if mix.get("bank", True):
        sources.append("Bank feed")
    if mix.get("card_processor"):
        sources.append("Card processor")
    if mix.get("ecommerce"):
        sources.append("E-commerce")
    if mix.get("payroll"):
        sources.append("Payroll")
    if mix.get("invoicing"):
        sources.append("Invoicing")

    open_hour = hours.get("open_hour", 9)
    close_hour = hours.get("close_hour", 17)
    bho = hours.get("business_hours_only", True)

    events_per_day = vol.get("events_per_day", 12)
    typical_ticket_cents = ticket.get("typical_ticket_cents", 6500)

    lines = []
    lines.append(f"Story v{story_version} · scenario={scenario_id}")
    lines.append("")
    lines.append("What this business looks like:")
    lines.append(f"- It runs on: {', '.join(sources) if sources else 'Bank feed'}")
    if bho:
        lines.append(f"- Most activity happens during business hours ({open_hour}:00–{close_hour}:00).")
    else:
        lines.append("- Activity can happen at any time of day.")
    lines.append(f"- On a normal day, it produces about {events_per_day} events.")
    lines.append(f"- A typical transaction is around ${typical_ticket_cents/100:.2f}.")
    lines.append("")
    if interventions:
        enabled = [iv for iv in interventions if iv.get("enabled")]
        lines.append(f"History changes (interventions): {len(enabled)} enabled / {len(interventions)} total")
        for iv in enabled[:8]:
            dur = iv.get("duration_days")
            dur_txt = f"{dur} days" if dur else "ongoing"
            lines.append(f"- {iv.get('start_date')}: {iv.get('name')} ({iv.get('kind')}, {dur_txt})")
        if len(enabled) > 8:
            lines.append(f"- …and {len(enabled)-8} more")
    else:
        lines.append("History changes (interventions): none yet.")
    lines.append("")
    lines.append("Goal: generate a realistic timeline, and time-lock the story events so signals appear where expected.")
    return "\n".join(lines)


def _rng(seed: int) -> random.Random:
    r = random.Random()
    r.seed(seed)
    return r


def _rand_time_in_day(r: random.Random, day_start: datetime, business_hours_only: bool, open_hour: int, close_hour: int) -> datetime:
    if not business_hours_only:
        minutes = r.randint(0, 23 * 60 + 59)
        return day_start + timedelta(minutes=minutes)

    span = max(1, (close_hour - open_hour) * 60)
    minutes = r.randint(0, span - 1)
    return day_start.replace(hour=open_hour, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)


def _apply_random_shocks(
    *,
    r: random.Random,
    dt: datetime,
    shock_start: datetime,
    shock_end: datetime,
    revenue_drop_pct: float,
    expense_spike_pct: float,
) -> dict:
    if not (shock_start <= dt < shock_end):
        return {"revenue_mult": 1.0, "expense_mult": 1.0, "deposit_delay_days": 0, "refund_rate": None, "deposit_delay_pct": 0.0}

    shock_kind = r.choices(["revenue_drop", "expense_spike", "deposit_delay"], weights=[45, 45, 10])[0]
    if shock_kind == "revenue_drop":
        return {"revenue_mult": max(0.05, 1.0 - revenue_drop_pct), "expense_mult": 1.0, "deposit_delay_days": 0, "refund_rate": None, "deposit_delay_pct": 0.0}
    if shock_kind == "expense_spike":
        return {"revenue_mult": 1.0, "expense_mult": 1.0 + expense_spike_pct, "deposit_delay_days": 0, "refund_rate": None, "deposit_delay_pct": 0.0}
    return {"revenue_mult": 1.0, "expense_mult": 1.0, "deposit_delay_days": r.choice([2, 3, 5]), "refund_rate": None, "deposit_delay_pct": 1.0}


def _insert_raw_event(db: Session, business_id: str, ev: dict) -> int:
    created = insert_raw_event_idempotent(
        db,
        business_id=business_id,
        source=ev["source"],
        source_event_id=ev["source_event_id"],
        canonical_source_event_id=canonical_source_event_id(ev["payload"], ev["source_event_id"]),
        occurred_at=ev["occurred_at"],
        payload=ev["payload"],
    )
    return 1 if created else 0


# ============================================================
# Interventions: compute modifiers by day / datetime
# ============================================================


def _iv_active_on(iv: Dict[str, Any], d: date) -> bool:
    if not iv.get("enabled", True):
        return False
    sd_raw = iv.get("start_date")
    if not isinstance(sd_raw, str):
        return False
    sd = _parse_yyyy_mm_dd(sd_raw)
    if d < sd:
        return False
    dur = iv.get("duration_days")
    if dur is None:
        return True
    try:
        dur_int = int(dur)
    except Exception:
        return True
    return d < (sd + timedelta(days=dur_int))


def _mods_for_day(ivs: List[Dict[str, Any]], d: date) -> Dict[str, Any]:
    volume_mult = 1.0
    ticket_mult = 1.0
    revenue_mult = 1.0
    expense_mult = 1.0
    deposit_delay_days = 0
    deposit_delay_pct = 0.0
    refund_rate: Optional[float] = None

    for iv in ivs:
        if not isinstance(iv, dict):
            continue
        if not _iv_active_on(iv, d):
            continue

        kind = str(iv.get("kind") or "")
        params = iv.get("params") if isinstance(iv.get("params"), dict) else {}

        if kind == "revenue_drop":
            pct = float(params.get("pct", 0.30))
            pct = max(0.0, min(pct, 0.99))
            mode = str(params.get("mode", "volume")).lower()
            mult = max(0.05, 1.0 - pct)

            if mode == "ticket":
                ticket_mult *= mult
                revenue_mult *= mult
            else:
                volume_mult *= mult

        elif kind in ("expense_spike", "supplier_cost_increase"):
            pct = float(params.get("pct", 0.25))
            pct = max(0.0, min(pct, 10.0))
            expense_mult *= (1.0 + pct)

        elif kind == "deposit_delay":
            days = int(params.get("days", 3))
            days = max(0, min(days, 30))
            pct_aff = float(params.get("pct_affected", 0.8))
            pct_aff = max(0.0, min(pct_aff, 1.0))
            deposit_delay_days = max(deposit_delay_days, days)
            deposit_delay_pct = max(deposit_delay_pct, pct_aff)

        elif kind == "refund_spike":
            rr = float(params.get("refund_rate", 0.08))
            rr = max(0.0, min(rr, 1.0))
            refund_rate = rr if refund_rate is None else max(refund_rate, rr)

    return {
        "volume_mult": volume_mult,
        "ticket_mult": ticket_mult,
        "revenue_mult": revenue_mult,
        "expense_mult": expense_mult,
        "deposit_delay_days": deposit_delay_days,
        "deposit_delay_pct": deposit_delay_pct,
        "refund_rate": refund_rate,
    }


# ============================================================
# Library and catalog
# ============================================================


def _intervention_library() -> List[Dict[str, Any]]:
    return [
        {
            "kind": "revenue_drop",
            "label": "Revenue drop",
            "description": "Sustained drop in demand (volume or ticket).",
            "defaults": {"pct": 0.30, "mode": "volume"},
            "fields": [
                {"key": "pct", "label": "Drop (%)", "type": "percent", "default": 0.30, "min": 0.05, "max": 0.95, "step": 0.01},
                {"key": "mode", "label": "Affects", "type": "text", "default": "volume"},
            ],
        },
        {
            "kind": "expense_spike",
            "label": "Expense spike",
            "description": "Costs increase for a period (COGS, rent, etc.).",
            "defaults": {"pct": 0.25, "category": "cogs"},
            "fields": [
                {"key": "pct", "label": "Increase (%)", "type": "percent", "default": 0.25, "min": 0.05, "max": 5.0, "step": 0.01},
                {"key": "category", "label": "Category", "type": "text", "default": "cogs"},
            ],
        },
        {
            "kind": "deposit_delay",
            "label": "Deposit delay",
            "description": "Card deposits arrive late (cash timing stress).",
            "defaults": {"days": 3, "pct_affected": 0.8},
            "fields": [
                {"key": "days", "label": "Days delayed", "type": "days", "default": 3, "min": 1, "max": 14, "step": 1},
                {"key": "pct_affected", "label": "Share affected (%)", "type": "percent", "default": 0.8, "min": 0.1, "max": 1.0, "step": 0.05},
            ],
        },
        {
            "kind": "refund_spike",
            "label": "Refund spike",
            "description": "Refunds rise for a short window.",
            "defaults": {"refund_rate": 0.08},
            "fields": [
                {"key": "refund_rate", "label": "Refund rate (%)", "type": "percent", "default": 0.08, "min": 0.0, "max": 0.5, "step": 0.01},
            ],
        },
        {
            "kind": "supplier_cost_increase",
            "label": "Supplier cost increase",
            "description": "COGS increases (inputs more expensive).",
            "defaults": {"pct": 0.15},
            "fields": [
                {"key": "pct", "label": "Increase (%)", "type": "percent", "default": 0.15, "min": 0.01, "max": 1.0, "step": 0.01},
            ],
        },
    ]


def get_intervention_library() -> List[Dict[str, Any]]:
    return _intervention_library()


def get_scenario_catalog() -> Dict[str, Any]:
    return SCENARIO_CATALOG


def get_sim_truth(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)

    scenario_id = str(sim.get("scenario_id") or "restaurant_v1")
    story_version = int(sim.get("story_version") or 1)

    truth = sim.get("truth_events")
    truth_events = truth if isinstance(truth, list) else []

    return {
        "business_id": business_id,
        "scenario_id": scenario_id,
        "story_version": story_version,
        "truth_events": truth_events,
    }


def get_sim_plan(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)

    sim = _get_simulator_blob(prof)
    scenario_id = str(sim.get("scenario_id") or "restaurant_v1")
    story_version = int(sim.get("story_version") or 1)

    defaults = _scenario_defaults(scenario_id)
    plan = _merge_plan(defaults, sim.get("plan") if isinstance(sim.get("plan"), dict) else {})

    interventions = sim.get("interventions")
    ivs = interventions if isinstance(interventions, list) else []

    story_text = _render_story(business_id, scenario_id, story_version, plan, ivs)

    sim["scenario_id"] = scenario_id
    sim["story_version"] = story_version
    sim["plan"] = plan
    sim.setdefault("interventions", ivs)
    prof.simulation_params["simulator"] = sim  # type: ignore[index]
    db.add(prof)
    db.commit()

    return {
        "business_id": business_id,
        "scenario_id": scenario_id,
        "story_version": story_version,
        "plan": plan,
        "story_text": story_text,
    }


def put_sim_plan(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)

    scenario_id = req.scenario_id or "restaurant_v1"
    story_version = req.story_version or 1

    defaults = _scenario_defaults(scenario_id)
    merged_plan = _merge_plan(defaults, req.plan or {})

    sim["scenario_id"] = scenario_id
    sim["story_version"] = story_version
    sim["plan"] = merged_plan
    sim.setdefault("interventions", [])
    prof.simulation_params["simulator"] = sim  # type: ignore[index]

    db.add(prof)
    db.commit()

    story_text = _render_story(business_id, scenario_id, story_version, merged_plan, sim.get("interventions") or [])
    return {
        "business_id": business_id,
        "scenario_id": scenario_id,
        "story_version": story_version,
        "plan": merged_plan,
        "story_text": story_text,
    }


def list_sim_interventions(db: Session, business_id: str) -> List[Dict[str, Any]]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)
    ivs = sim.get("interventions")
    if not isinstance(ivs, list):
        ivs = []
        sim["interventions"] = ivs
        prof.simulation_params["simulator"] = sim  # type: ignore[index]
        db.add(prof)
        db.commit()
    return [iv for iv in ivs if isinstance(iv, dict)]


def create_sim_intervention(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)

    _parse_yyyy_mm_dd(req.start_date)

    ivs = sim.get("interventions")
    if not isinstance(ivs, list):
        ivs = []
        sim["interventions"] = ivs

    now = utcnow().isoformat()
    iv = {
        "id": uuid.uuid4().hex,
        "business_id": business_id,
        "kind": req.kind,
        "name": req.name,
        "start_date": req.start_date,
        "duration_days": req.duration_days,
        "params": req.params or {},
        "enabled": bool(req.enabled),
        "updated_at": now,
    }
    ivs.append(iv)

    prof.simulation_params["simulator"] = sim  # type: ignore[index]
    db.add(prof)
    db.commit()

    return iv


def update_sim_intervention(db: Session, business_id: str, intervention_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)

    ivs = sim.get("interventions")
    if not isinstance(ivs, list):
        raise HTTPException(status_code=404, detail="no interventions")

    target = next((iv for iv in ivs if isinstance(iv, dict) and iv.get("id") == intervention_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="intervention not found")

    if req.start_date is not None:
        _parse_yyyy_mm_dd(req.start_date)
        target["start_date"] = req.start_date
    if req.kind is not None:
        target["kind"] = req.kind
    if req.name is not None:
        target["name"] = req.name
    if req.duration_days is not None:
        target["duration_days"] = req.duration_days
    if req.params is not None:
        target["params"] = req.params
    if req.enabled is not None:
        target["enabled"] = bool(req.enabled)

    target["updated_at"] = utcnow().isoformat()

    prof.simulation_params["simulator"] = sim  # type: ignore[index]
    db.add(prof)
    db.commit()

    return target


def delete_sim_intervention(db: Session, business_id: str, intervention_id: str) -> Dict[str, Any]:
    require_business(db, business_id)
    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)

    ivs = sim.get("interventions")
    if not isinstance(ivs, list):
        return {"status": "ok", "deleted": 0}

    before = len(ivs)
    sim["interventions"] = [iv for iv in ivs if not (isinstance(iv, dict) and iv.get("id") == intervention_id)]
    deleted_n = before - len(sim["interventions"])

    prof.simulation_params["simulator"] = sim  # type: ignore[index]
    db.add(prof)
    db.commit()

    return {"status": "ok", "deleted": deleted_n}


def generate_history(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)

    cfg = db.execute(
        select(SimulatorConfig).where(SimulatorConfig.business_id == business_id)
    ).scalar_one_or_none()
    if not cfg:
        cfg = _default_config_for(business_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    if not cfg.enabled:
        return {
            "status": "disabled",
            "business_id": business_id,
            "start_date": req.start_date,
            "days": req.days,
            "inserted": 0,
            "deleted": 0,
            "shock_window": None,
        }

    prof = _get_or_create_integration_profile(db, business_id)
    sim = _get_simulator_blob(prof)

    scenario_id = str(sim.get("scenario_id") or "restaurant_v1")
    defaults = _scenario_defaults(scenario_id)
    plan = _merge_plan(defaults, sim.get("plan") if isinstance(sim.get("plan"), dict) else {})

    interventions_raw = sim.get("interventions")
    ivs = interventions_raw if isinstance(interventions_raw, list) else []

    start_d = _parse_yyyy_mm_dd(req.start_date)
    start_at = datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc)

    plan_hours = plan.get("business_hours", {}) or {}
    plan_vol = plan.get("volume", {}) or {}
    plan_ticket = plan.get("ticket", {}) or {}
    plan_mix = plan.get("mix", {}) or {}

    business_hours_only = (
        req.business_hours_only
        if req.business_hours_only is not None
        else bool(plan_hours.get("business_hours_only", True))
    )
    open_hour = req.open_hour if req.open_hour is not None else int(plan_hours.get("open_hour", 9))
    close_hour = req.close_hour if req.close_hour is not None else int(plan_hours.get("close_hour", 17))

    base_events_per_day = (
        req.events_per_day
        if req.events_per_day is not None
        else int(plan_vol.get("events_per_day", cfg.avg_events_per_day or 12))
    )
    base_events_per_day = max(1, min(int(base_events_per_day), 10000))

    typical_ticket_cents = int(plan_ticket.get("typical_ticket_cents", cfg.typical_ticket_cents or 6500))
    typical_ticket_cents = max(100, typical_ticket_cents)

    # Sync integration toggles to generation mix (v0)
    prof.bank = bool(plan_mix.get("bank", True))
    prof.card_processor = bool(plan_mix.get("card_processor", False))
    prof.ecommerce = bool(plan_mix.get("ecommerce", False))
    prof.payroll = bool(plan_mix.get("payroll", False))
    prof.invoicing = bool(plan_mix.get("invoicing", False))
    db.add(prof)

    deleted_count = 0
    if req.mode == "replace_from_start":
        res = db.execute(
            delete(RawEvent).where(
                RawEvent.business_id == business_id,
                RawEvent.occurred_at >= start_at,
            )
        )
        deleted_count = int(getattr(res, "rowcount", 0) or 0)

    end_d = start_d + timedelta(days=req.days)

    if scenario_id == "restaurant_v1":
        mods_by_day: Dict[date, Dict[str, Any]] = {}
        truth_events: List[Dict[str, Any]] = []

        for d in range(req.days):
            day_date = start_d + timedelta(days=d)
            mods_day = _mods_for_day(ivs, day_date)
            mods_by_day[day_date] = mods_day

            active_iv = []
            for iv in ivs:
                if isinstance(iv, dict) and _iv_active_on(iv, day_date):
                    active_iv.append({"kind": iv.get("kind"), "name": iv.get("name"), "id": iv.get("id")})
            if active_iv:
                truth_events.append(
                    {
                        "type": "interventions_active",
                        "date": day_date.isoformat(),
                        "active": active_iv,
                        "mods": {
                            "volume_mult": float(mods_day["volume_mult"]),
                            "revenue_mult": float(mods_day["revenue_mult"]),
                            "expense_mult": float(mods_day["expense_mult"]),
                            "deposit_delay_days": int(mods_day["deposit_delay_days"]),
                            "deposit_delay_pct": float(mods_day["deposit_delay_pct"]),
                            "refund_rate": mods_day["refund_rate"],
                        },
                    }
                )

        events = generate_restaurant_v1_events(
            business_id=business_id,
            start_date=start_d,
            end_date=end_d,
            seed=req.seed,
            mods_by_day=mods_by_day,
        )

        inserted = 0
        for ev in events:
            inserted += _insert_raw_event(db, business_id, ev)

        sim.setdefault("truth_events", [])
        sim["truth_events"] = truth_events

        prof.simulation_params["simulator"] = sim  # type: ignore[index]
        db.add(prof)
        db.commit()

        return {
            "status": "ok",
            "business_id": business_id,
            "start_date": req.start_date,
            "days": req.days,
            "inserted": inserted,
            "deleted": deleted_count,
            "shock_window": None,
        }

    r = _rng(req.seed)

    # Optional random shock window (secondary layer). Interventions are primary.
    gen_end = start_at + timedelta(days=req.days)
    shock_start = start_at + timedelta(days=int(req.days * 0.55))
    shock_end = min(gen_end, shock_start + timedelta(days=req.shock_days))

    inserted = 0

    # def _mods_for_day(ivs_list: List[Any], day: date) -> Dict[str, Any]:
    #     """
    #     Deterministic day-level modifiers derived from enabled interventions.
    #     This is the "puppet strings" layer.

    #     Returns:
    #       volume_mult: affects event count
    #       revenue_mult: affects revenue magnitude
    #       expense_mult: affects expense magnitude
    #       deposit_delay_days: integer delay days for payouts
    #       deposit_delay_pct: fraction of payouts affected
    #       refund_rate: probability for refund per ecommerce order (None => baseline)
    #     """
    #     mods = {
    #         "volume_mult": 1.0,
    #         "revenue_mult": 1.0,
    #         "expense_mult": 1.0,
    #         "deposit_delay_days": 0,
    #         "deposit_delay_pct": 0.0,
    #         "refund_rate": None,  # None means "baseline behavior"
    #     }

    #     for raw in ivs_list:
    #         if not isinstance(raw, dict):
    #             continue
    #         if not _iv_active_on(raw, day):
    #             continue

    #         kind = str(raw.get("kind") or "")
    #         params = raw.get("params") or {}

    #         if kind == "revenue_drop":
    #             pct = float(params.get("pct", 0.35))
    #             mods["revenue_mult"] *= max(0.05, 1.0 - pct)

    #         elif kind == "expense_spike":
    #             pct = float(params.get("pct", 0.22))
    #             mods["expense_mult"] *= (1.0 + max(0.0, pct))

    #         elif kind == "volume_change":
    #             pct = float(params.get("pct", 0.0))  # +0.2 => +20%, -0.3 => -30%
    #             mods["volume_mult"] *= max(0.0, 1.0 + pct)

    #         elif kind == "deposit_delay":
    #             days = int(params.get("days", 2))
    #             pct_aff = float(params.get("pct", 0.5))
    #             mods["deposit_delay_days"] = max(int(mods["deposit_delay_days"]), max(0, days))
    #             mods["deposit_delay_pct"] = max(float(mods["deposit_delay_pct"]), max(0.0, min(1.0, pct_aff)))

    #         elif kind == "refund_spike":
    #             # explicit probability (0..1)
    #             rr = float(params.get("refund_rate", 0.08))
    #             mods["refund_rate"] = max(0.0, min(1.0, rr))

    #     return mods

    def _time_bucketed(day_start: datetime, buckets: List[tuple[int, int]]) -> datetime:
        start_h, end_h = r.choice(buckets)
        start_min = start_h * 60
        end_min = end_h * 60 - 1
        m = r.randint(start_min, max(start_min, end_min))
        return day_start + timedelta(minutes=m)

    def _occurred_at_for_stream(stream: str, day_start: datetime) -> datetime:
        # More realistic intraday timing per stream
        if stream == "bank":
            return _time_bucketed(day_start, [(6, 10), (12, 16)])
        if stream == "card_processor":
            return _time_bucketed(day_start, [(6, 9)])
        if stream == "ecommerce":
            return _time_bucketed(day_start, [(8, 22)])
        if stream == "invoicing":
            return _time_bucketed(day_start, [(9, 17)])
        if stream == "payroll":
            return _time_bucketed(day_start, [(8, 11)])
        return _rand_time_in_day(r, day_start, business_hours_only, open_hour, close_hour)

    # helper cfg shim for plaid generator ticket sizing
    class _CfgShim:
        def __init__(self, typical_ticket_cents: int, profile: str):
            self.typical_ticket_cents = typical_ticket_cents
            self.profile = profile

    enabled_streams: List[str] = []
    if prof.bank:
        enabled_streams.append("bank")
    if prof.card_processor:
        enabled_streams.append("card_processor")
    if prof.ecommerce:
        enabled_streams.append("ecommerce")
    if prof.payroll:
        enabled_streams.append("payroll")
    if prof.invoicing:
        enabled_streams.append("invoicing")
    if not enabled_streams:
        enabled_streams = ["bank"]

    weights = {
        "bank": 0.55,
        "card_processor": 0.20,
        "ecommerce": 0.15,
        "payroll": 0.05,
        "invoicing": 0.05,
    }
    total_w = sum(weights.get(s, 0.0) for s in enabled_streams) or 1.0
    norm = {s: weights.get(s, 0.0) / total_w for s in enabled_streams}

    # Track “truth” timeline for UI/debugging
    truth_events: List[Dict[str, Any]] = []

    for d in range(req.days):
        day_date = (start_d + timedelta(days=d))
        day_start = (start_at + timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)

        # 1) Interventions drive the day (primary layer)
        mods_day = _mods_for_day(ivs, day_date)

        # 2) Daily volume scaling
        day_events = int(round(base_events_per_day * float(mods_day["volume_mult"])))
        day_events = max(0, min(day_events, 10000))

        # allocate counts by enabled stream weights
        counts = {s: int(round(day_events * norm[s])) for s in enabled_streams}
        allocated = sum(counts.values())
        if allocated != day_events and enabled_streams:
            counts[enabled_streams[0]] += (day_events - allocated)

        # payroll once per payroll cycle day (still deterministic)
        if "payroll" in enabled_streams and (d % int(cfg.payroll_every_n_days or 14)) == 0:
            occurred_at_payroll = _occurred_at_for_stream("payroll", day_start)
            ev = make_payroll_run_event(business_id=business_id, occurred_at=occurred_at_payroll)
            inserted += _insert_raw_event(db, business_id, ev)

        # Truth markers: which interventions are active + their computed mods
        active_iv = []
        for iv in ivs:
            if isinstance(iv, dict) and _iv_active_on(iv, day_date):
                active_iv.append({"kind": iv.get("kind"), "name": iv.get("name"), "id": iv.get("id")})
        if active_iv:
            truth_events.append(
                {
                    "type": "interventions_active",
                    "date": day_date.isoformat(),
                    "active": active_iv,
                    "mods": {
                        "volume_mult": float(mods_day["volume_mult"]),
                        "revenue_mult": float(mods_day["revenue_mult"]),
                        "expense_mult": float(mods_day["expense_mult"]),
                        "deposit_delay_days": int(mods_day["deposit_delay_days"]),
                        "deposit_delay_pct": float(mods_day["deposit_delay_pct"]),
                        "refund_rate": mods_day["refund_rate"],
                    },
                }
            )

        # Generate per-stream events
        for stream, c in counts.items():
            if stream == "payroll":
                continue

            for i in range(c):
                occurred_at = _occurred_at_for_stream(stream, day_start)

                # event-level modifiers = day interventions + optional random shocks
                ev_mods = dict(mods_day)

                if req.enable_shocks:
                    shock_mods = _apply_random_shocks(
                        r=r,
                        dt=occurred_at,
                        shock_start=shock_start,
                        shock_end=shock_end,
                        revenue_drop_pct=req.revenue_drop_pct,
                        expense_spike_pct=req.expense_spike_pct,
                    )
                    # Merge shocks conservatively
                    ev_mods["revenue_mult"] = float(ev_mods["revenue_mult"]) * float(shock_mods.get("revenue_mult", 1.0))
                    ev_mods["expense_mult"] = max(float(ev_mods["expense_mult"]), float(shock_mods.get("expense_mult", 1.0)))
                    ev_mods["deposit_delay_days"] = max(int(ev_mods.get("deposit_delay_days", 0)), int(shock_mods.get("deposit_delay_days", 0)))
                    ev_mods["deposit_delay_pct"] = max(float(ev_mods.get("deposit_delay_pct", 0.0)), float(shock_mods.get("deposit_delay_pct", 0.0)))
                    if ev_mods.get("refund_rate") is None:
                        ev_mods["refund_rate"] = shock_mods.get("refund_rate")

                # Stream-specific ticket sizing proxy (keep it simple + deterministic)
                # - revenue streams scale by revenue_mult
                # - expense-heavy streams scale by expense_mult
                    if stream in ("card_processor", "ecommerce", "invoicing"):
                        ticket_mult = float(ev_mods.get("revenue_mult", 1.0)) * float(ev_mods.get("ticket_mult", 1.0))
                    else:
                         ticket_mult = float(ev_mods.get("expense_mult", 1.0))


                ticket_adj = int(max(100, typical_ticket_cents * ticket_mult))
                shim = _CfgShim(ticket_adj, cfg.profile)

                if stream == "bank":
                    ev = make_plaid_transaction_event(business_id=business_id, occurred_at=occurred_at, cfg=shim)
                    inserted += _insert_raw_event(db, business_id, ev)

                elif stream == "card_processor":
                    delay_days = int(ev_mods.get("deposit_delay_days", 0))
                    pct_aff = float(ev_mods.get("deposit_delay_pct", 0.0))
                    delayed = (delay_days > 0) and (pct_aff > 0.0) and (r.random() < pct_aff)
                    dt2 = occurred_at + timedelta(days=delay_days) if delayed else occurred_at

                    ev = make_stripe_payout_event(business_id=business_id, occurred_at=dt2, cfg=cfg)
                    inserted += _insert_raw_event(db, business_id, ev)

                    if i % 3 == 0:
                        inserted += _insert_raw_event(
                            db, business_id, make_stripe_fee_event(business_id=business_id, occurred_at=dt2)
                        )

                elif stream == "ecommerce":
                    ev = make_shopify_order_paid_event(business_id=business_id, occurred_at=occurred_at)
                    inserted += _insert_raw_event(db, business_id, ev)

                    rr = ev_mods.get("refund_rate")
                    if rr is None:
                        # baseline: occasional refunds
                        if i % 10 == 0:
                            inserted += _insert_raw_event(
                                db, business_id, make_shopify_refund_event(business_id=business_id, occurred_at=occurred_at)
                            )
                    else:
                        if r.random() < float(rr):
                            inserted += _insert_raw_event(
                                db, business_id, make_shopify_refund_event(business_id=business_id, occurred_at=occurred_at)
                            )

                elif stream == "invoicing":
                    ev = make_invoice_paid_event(business_id=business_id, occurred_at=occurred_at)
                    # Best-effort: scale invoice amount by revenue_mult if payload supports it
                    rm = float(ev_mods.get("revenue_mult", 1.0))
                    if rm != 1.0:
                        try:
                            amt = float(ev["payload"]["invoice"]["amount"])
                            ev["payload"]["invoice"]["amount"] = round(amt * rm, 2)
                        except Exception:
                            pass
                    inserted += _insert_raw_event(db, business_id, ev)

    # Store “truth” for debugging/UI (temporary but useful)
    sim.setdefault("truth_events", [])
    sim["truth_events"] = truth_events

    if req.enable_shocks:
        sim["truth_events"].append(
            {
                "type": "shock_window",
                "start_at": shock_start.isoformat(),
                "end_at": shock_end.isoformat(),
                "note": "Random shocks also applied in this window (secondary layer).",
            }
        )

    prof.simulation_params["simulator"] = sim  # type: ignore[index]
    db.add(prof)
    db.commit()

    return {
        "status": "ok",
        "business_id": business_id,
        "start_date": req.start_date,
        "days": req.days,
        "inserted": inserted,
        "deleted": deleted_count,
        "shock_window": None
        if not req.enable_shocks
        else {"start": shock_start.isoformat(), "end": shock_end.isoformat()},
    }


# ============================================================
# LEGACY ENDPOINTS: /sim/*
# (keep so existing screens still work)
# ============================================================


def get_or_create_sim_config(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)

    cfg = db.execute(select(SimulatorConfig).where(SimulatorConfig.business_id == business_id)).scalar_one_or_none()
    if not cfg:
        cfg = _default_config_for(business_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return _to_out(cfg)


def upsert_sim_config(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)

    if req.profile is not None and req.profile not in PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown profile '{req.profile}'. Choose from: {list(PROFILES.keys())}")

    cfg = db.execute(select(SimulatorConfig).where(SimulatorConfig.business_id == business_id)).scalar_one_or_none()
    if not cfg:
        cfg = _default_config_for(business_id)
        db.add(cfg)
        db.flush()

    if req.enabled is not None:
        cfg.enabled = req.enabled
    if req.profile is not None:
        cfg.profile = req.profile
    if req.avg_events_per_day is not None:
        cfg.avg_events_per_day = req.avg_events_per_day
    if req.typical_ticket_cents is not None:
        cfg.typical_ticket_cents = req.typical_ticket_cents
    if req.payroll_every_n_days is not None:
        cfg.payroll_every_n_days = req.payroll_every_n_days

    cfg.updated_at = utcnow()
    db.commit()
    db.refresh(cfg)
    return _to_out(cfg)


def pulse(db: Session, business_id: str, n: int) -> Dict[str, Any]:
    require_business(db, business_id)

    cfg = db.execute(select(SimulatorConfig).where(SimulatorConfig.business_id == business_id)).scalar_one_or_none()
    if not cfg:
        cfg = _default_config_for(business_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    if not cfg.enabled:
        return {"status": "disabled", "business_id": business_id, "inserted": 0}

    prof = _get_or_create_integration_profile(db, business_id)

    enabled_streams = []
    if prof.bank:
        enabled_streams.append("bank")
    if prof.card_processor:
        enabled_streams.append("card_processor")
    if prof.ecommerce:
        enabled_streams.append("ecommerce")
    if prof.payroll:
        enabled_streams.append("payroll")
    if prof.invoicing:
        enabled_streams.append("invoicing")
    if not enabled_streams:
        enabled_streams = ["bank"]

    weights = {"bank": 0.55, "card_processor": 0.20, "ecommerce": 0.15, "payroll": 0.05, "invoicing": 0.05}
    total_w = sum(weights.get(s, 0.0) for s in enabled_streams) or 1.0
    norm = {s: weights.get(s, 0.0) / total_w for s in enabled_streams}
    counts = {s: int(round(n * norm[s])) for s in enabled_streams}
    allocated = sum(counts.values())
    if allocated != n:
        counts[enabled_streams[0]] += (n - allocated)

    now = utcnow()
    created = 0

    for _ in range(counts.get("bank", 0)):
        created += _insert_raw_event(db, business_id, make_plaid_transaction_event(business_id=business_id, occurred_at=now, cfg=cfg))

    for i in range(counts.get("card_processor", 0)):
        created += _insert_raw_event(db, business_id, make_stripe_payout_event(business_id=business_id, occurred_at=now, cfg=cfg))
        if i % 3 == 0:
            created += _insert_raw_event(db, business_id, make_stripe_fee_event(business_id=business_id, occurred_at=now))

    for i in range(counts.get("ecommerce", 0)):
        created += _insert_raw_event(db, business_id, make_shopify_order_paid_event(business_id=business_id, occurred_at=now))
        if i % 8 == 0:
            created += _insert_raw_event(db, business_id, make_shopify_refund_event(business_id=business_id, occurred_at=now))

    for _ in range(counts.get("payroll", 0)):
        created += _insert_raw_event(db, business_id, make_payroll_run_event(business_id=business_id, occurred_at=now))

    for _ in range(counts.get("invoicing", 0)):
        created += _insert_raw_event(db, business_id, make_invoice_paid_event(business_id=business_id, occurred_at=now))

    db.commit()
    return {"status": "ok", "business_id": business_id, "inserted": created, "streams": enabled_streams, "counts": counts}
