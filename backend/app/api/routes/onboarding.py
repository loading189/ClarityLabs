# backend/app/api/onboarding.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import (
    Organization,
    Business,
    Account,
    RawEvent,
    BusinessIntegrationProfile,
)
from backend.app.sim.models import SimulatorConfig
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# -------------------------
# Helpers / Defaults
# -------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def uuid_str() -> str:
    return str(uuid.uuid4())

def default_story() -> dict:
    return {
        "scenario_id": "restaurant_v1",
        "timezone": "America/Chicago",
        "hours": {"open_hour": 11, "close_hour": 22, "business_hours_only": True},
        "mix": {
            "bank": True,
            "payroll": True,
            "card_processor": True,
            "ecommerce": False,
            "invoicing": False,
        },
        "rhythm": {"lunch_peak": True, "dinner_peak": True, "weekend_boost": 1.2},
        "payout_behavior": {"deposit_delay_days": [0, 1, 2]},
        "truth": {"shocks": [], "notes": ""},
    }

def default_simulation_params() -> dict:
    return {
        "volume_level": "medium",
        "volatility": "normal",
        "seasonality": False,
        "story": default_story(),
    }


# -------------------------
# COA templates (optional, MVP)
# -------------------------

CoaTemplateName = Literal["service_simple", "retail_simple"]

COA_TEMPLATES: Dict[str, List[Dict[str, Optional[str]]]] = {
    "service_simple": [
        {"code": "1000", "name": "Cash", "type": "asset", "subtype": "cash"},
        {"code": "1200", "name": "Accounts Receivable", "type": "asset", "subtype": "ar"},
        {"code": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "ap"},
        {"code": "3000", "name": "Owner Equity", "type": "equity", "subtype": "owner_equity"},
        {"code": "4000", "name": "Service Revenue", "type": "revenue", "subtype": "service"},
        {"code": "5100", "name": "Payroll Expense", "type": "expense", "subtype": "payroll"},
        {"code": "5200", "name": "Rent Expense", "type": "expense", "subtype": "rent"},
        {"code": "5300", "name": "Software Expense", "type": "expense", "subtype": "software"},
        {"code": "5400", "name": "Marketing Expense", "type": "expense", "subtype": "marketing"},
    ],
    "retail_simple": [
        {"code": "1000", "name": "Cash", "type": "asset", "subtype": "cash"},
        {"code": "1300", "name": "Inventory", "type": "asset", "subtype": "inventory"},
        {"code": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "ap"},
        {"code": "3000", "name": "Owner Equity", "type": "equity", "subtype": "owner_equity"},
        {"code": "4000", "name": "Sales Revenue", "type": "revenue", "subtype": "sales"},
        {"code": "5000", "name": "Cost of Goods Sold", "type": "expense", "subtype": "cogs"},
        {"code": "5400", "name": "Marketing Expense", "type": "expense", "subtype": "marketing"},
    ],
}


# -------------------------
# Schemas
# -------------------------

class CreateOrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class OrgOut(BaseModel):
    id: str
    name: str
    created_at: datetime


class BootstrapBusinessIn(BaseModel):
    org_id: str
    name: str = Field(min_length=1, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=120)

    # Integration mix toggles (also written into story.mix)
    bank: bool = True
    payroll: bool = True
    card_processor: bool = True
    ecommerce: bool = False
    invoicing: bool = False

    # Story knobs
    scenario_id: Optional[str] = Field(default=None, max_length=80)

    # Simulator knobs
    sim_enabled: bool = True
    avg_events_per_day: int = Field(default=12, ge=1, le=10000)
    typical_ticket_cents: int = Field(default=6500, ge=0, le=5_000_000)
    payroll_every_n_days: int = Field(default=14, ge=1, le=365)


class BusinessOut(BaseModel):
    id: str
    org_id: str
    name: str
    industry: Optional[str] = None
    created_at: datetime


class SimulatorConfigOut(BaseModel):
    business_id: str
    enabled: bool
    profile: str
    avg_events_per_day: int
    typical_ticket_cents: int
    payroll_every_n_days: int
    updated_at: datetime


class IntegrationProfileOut(BaseModel):
    business_id: str
    bank: bool
    payroll: bool
    card_processor: bool
    ecommerce: bool
    invoicing: bool
    scenario_id: str
    story_version: int
    simulation_params: Dict[str, Any]
    updated_at: datetime


class BootstrapBusinessOut(BaseModel):
    business: BusinessOut
    sim_config: SimulatorConfigOut
    integration_profile: IntegrationProfileOut


class ApplyCoaIn(BaseModel):
    template: CoaTemplateName
    replace_existing: bool = False

class ApplyCoaOut(BaseModel):
    business_id: str
    template: str
    created: int
    skipped: int


class BusinessStatusOut(BaseModel):
    business_id: str
    has_accounts: bool
    accounts_count: int
    has_events: bool
    events_count: int
    sim_enabled: bool
    ready: bool


# -------------------------
# Endpoints
# -------------------------

@router.post("/orgs", response_model=OrgOut)
def create_org(req: CreateOrgIn, db: Session = Depends(get_db)):
    org = Organization(id=uuid_str(), name=req.name, created_at=utcnow())
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrgOut(id=org.id, name=org.name, created_at=org.created_at)


@router.post("/businesses/bootstrap", response_model=BootstrapBusinessOut)
def bootstrap_business(req: BootstrapBusinessIn, db: Session = Depends(get_db)):
    org = db.get(Organization, req.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="org not found")

    try:
        # 1) Create Business
        biz = Business(
            id=uuid_str(),
            org_id=req.org_id,
            name=req.name,
            industry=req.industry,
            created_at=utcnow(),
            # legacy flags can exist but we do NOT rely on them:
            sim_enabled=False,
            sim_profile="normal",
        )
        db.add(biz)
        db.flush()

        # 2) Seed COA + categories + mappings (canonical)
        seed_coa_and_categories_and_mappings(db, biz.id)

        # 3) Create Integration Profile w/ story
        story = default_story()
        if req.scenario_id:
            story["scenario_id"] = req.scenario_id

        story["mix"] = {
            "bank": req.bank,
            "payroll": req.payroll,
            "card_processor": req.card_processor,
            "ecommerce": req.ecommerce,
            "invoicing": req.invoicing,
        }

        sim_params = default_simulation_params()
        sim_params["story"] = story

        prof = BusinessIntegrationProfile(
            business_id=biz.id,
            bank=req.bank,
            payroll=req.payroll,
            card_processor=req.card_processor,
            ecommerce=req.ecommerce,
            invoicing=req.invoicing,
            scenario_id=story.get("scenario_id", "restaurant_v1"),
            story_version=1,
            simulation_params=sim_params,
            updated_at=utcnow(),
        )
        db.add(prof)

        # 4) Create SimulatorConfig (tick system reads this)
        cfg = SimulatorConfig(
            business_id=biz.id,
            enabled=req.sim_enabled,
            profile="normal",
            avg_events_per_day=req.avg_events_per_day,
            typical_ticket_cents=req.typical_ticket_cents,
            payroll_every_n_days=req.payroll_every_n_days,
            updated_at=utcnow(),
        )
        db.add(cfg)

        db.commit()
        db.refresh(biz)
        db.refresh(cfg)
        db.refresh(prof)

    except Exception:
        db.rollback()
        raise

    return BootstrapBusinessOut(
        business=BusinessOut(
            id=biz.id,
            org_id=biz.org_id,
            name=biz.name,
            industry=biz.industry,
            created_at=biz.created_at,
        ),
        sim_config=SimulatorConfigOut(
            business_id=cfg.business_id,
            enabled=cfg.enabled,
            profile=cfg.profile,
            avg_events_per_day=cfg.avg_events_per_day,
            typical_ticket_cents=cfg.typical_ticket_cents,
            payroll_every_n_days=cfg.payroll_every_n_days,
            updated_at=cfg.updated_at,
        ),
        integration_profile=IntegrationProfileOut(
            business_id=prof.business_id,
            bank=prof.bank,
            payroll=prof.payroll,
            card_processor=prof.card_processor,
            ecommerce=prof.ecommerce,
            invoicing=prof.invoicing,
            scenario_id=prof.scenario_id,
            story_version=prof.story_version,
            simulation_params=prof.simulation_params,
            updated_at=prof.updated_at,
        ),
    )


@router.post("/businesses/{business_id}/coa/apply_template", response_model=ApplyCoaOut)
def apply_coa_template(business_id: str, req: ApplyCoaIn, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    rows = COA_TEMPLATES.get(req.template)
    if not rows:
        raise HTTPException(status_code=400, detail=f"unknown template '{req.template}'")

    # Optional: replace accounts
    if req.replace_existing:
        existing = db.execute(select(Account).where(Account.business_id == business_id)).scalars().all()
        for a in existing:
            db.delete(a)
        db.flush()

    # prevent duplicates by account code
    existing_codes = set(
        r[0] for r in db.execute(select(Account.code).where(Account.business_id == business_id)).all()
        if r[0] is not None
    )

    created = 0
    skipped = 0

    for a in rows:
        code = a.get("code")
        if code and code in existing_codes:
            skipped += 1
            continue

        db.add(
            Account(
                id=uuid_str(),
                business_id=business_id,
                code=code,
                name=a["name"] or "Unnamed",
                type=a["type"] or "expense",
                subtype=a.get("subtype"),
                active=True,
                created_at=utcnow(),
            )
        )
        created += 1

    # IMPORTANT: re-run canonical seeder so categories + mappings stay aligned
    db.flush()
    seed_coa_and_categories_and_mappings(db, business_id)

    db.commit()
    return ApplyCoaOut(business_id=business_id, template=req.template, created=created, skipped=skipped)


@router.get("/businesses/{business_id}/status", response_model=BusinessStatusOut)
def business_status(business_id: str, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    accounts_count = db.execute(
        select(func.count()).select_from(Account).where(Account.business_id == business_id)
    ).scalar_one()

    events_count = db.execute(
        select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)
    ).scalar_one()

    # NEW: sim-enabled should come from SimulatorConfig
    cfg = db.execute(
        select(SimulatorConfig).where(SimulatorConfig.business_id == business_id)
    ).scalar_one_or_none()

    sim_enabled = bool(cfg.enabled) if cfg else False

    has_accounts = int(accounts_count) > 0
    has_events = int(events_count) > 0
    ready = has_accounts and (has_events or sim_enabled)

    return BusinessStatusOut(
        business_id=business_id,
        has_accounts=has_accounts,
        accounts_count=int(accounts_count),
        has_events=has_events,
        events_count=int(events_count),
        sim_enabled=sim_enabled,
        ready=ready,
    )
