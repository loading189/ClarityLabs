# backend/app/api/sim.py (DROP-IN)
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import sim_service

router = APIRouter(tags=["simulator"])


# ============================================================
# Schemas
# ============================================================

# ---- Legacy sim config (keep for now)
class SimulatorConfigOut(BaseModel):
    business_id: str
    enabled: bool
    profile: str
    avg_events_per_day: int
    typical_ticket_cents: int
    payroll_every_n_days: int
    updated_at: datetime


class SimulatorConfigUpsert(BaseModel):
    enabled: Optional[bool] = None
    profile: Optional[str] = Field(default=None, max_length=40)
    avg_events_per_day: Optional[int] = Field(default=None, ge=0, le=5000)
    typical_ticket_cents: Optional[int] = Field(default=None, ge=0, le=5_000_000)
    payroll_every_n_days: Optional[int] = Field(default=None, ge=1, le=365)


# ---- New simulator control-plane (plan / interventions)
class SimPlanOut(BaseModel):
    business_id: str
    scenario_id: str
    story_version: int
    plan: Dict[str, Any]
    story_text: str


class SimPlanUpsert(BaseModel):
    scenario_id: str = Field(default="restaurant_v1", max_length=80)
    story_version: int = Field(default=1, ge=1, le=9999)
    plan: Dict[str, Any] = Field(default_factory=dict)


class InterventionOut(BaseModel):
    id: str
    business_id: str
    kind: str
    name: str
    start_date: str  # YYYY-MM-DD
    duration_days: Optional[int] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    updated_at: Optional[str] = None


class InterventionCreate(BaseModel):
    kind: str = Field(..., max_length=80)
    name: str = Field(..., max_length=200)
    start_date: str  # YYYY-MM-DD
    duration_days: Optional[int] = Field(default=None, ge=1, le=3650)
    params: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class InterventionPatch(BaseModel):
    kind: Optional[str] = Field(default=None, max_length=80)
    name: Optional[str] = Field(default=None, max_length=200)
    start_date: Optional[str] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=3650)
    params: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class GenerateIn(BaseModel):
    # UI wants: start_date + days + mode
    start_date: str  # YYYY-MM-DD
    days: int = Field(default=365, ge=1, le=3650)
    seed: int = Field(default=1337)
    events_per_day: Optional[int] = Field(default=None, ge=1, le=10000)

    business_hours_only: Optional[bool] = None
    open_hour: Optional[int] = Field(default=None, ge=0, le=23)
    close_hour: Optional[int] = Field(default=None, ge=0, le=23)

    # Keep “random shock window” available, but interventions are now the primary driver.
    enable_shocks: bool = True
    shock_days: int = Field(default=10, ge=1, le=365)
    revenue_drop_pct: float = Field(default=0.30, ge=0.05, le=0.90)
    expense_spike_pct: float = Field(default=0.50, ge=0.05, le=5.00)

    mode: Literal["append", "replace_from_start"] = "replace_from_start"


class TruthOut(BaseModel):
    business_id: str
    scenario_id: str
    story_version: int
    truth_events: List[Dict[str, Any]]


class GenerateOut(BaseModel):
    status: str
    business_id: str
    start_date: str
    days: int
    inserted: int
    deleted: int
    shock_window: Optional[Dict[str, str]]


FieldType = Literal["number", "percent", "text", "days"]


class InterventionTemplateField(BaseModel):
    key: str
    label: str
    type: FieldType
    default: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None


class InterventionTemplate(BaseModel):
    kind: str
    label: str
    description: str
    defaults: Dict[str, Any] = Field(default_factory=dict)
    fields: List[InterventionTemplateField] = Field(default_factory=list)


# ============================================================
# NEW UI ENDPOINTS: /simulator/*
# ============================================================

@router.get("/simulator/intervention-library", response_model=List[InterventionTemplate])
def get_intervention_library():
    return sim_service.get_intervention_library()


@router.get("/simulator/catalog")
def get_scenario_catalog():
    return sim_service.get_scenario_catalog()


@router.get("/simulator/truth/{business_id}", response_model=TruthOut)
def get_sim_truth(business_id: str, db: Session = Depends(get_db)):
    return sim_service.get_sim_truth(db, business_id)


@router.get("/simulator/plan/{business_id}", response_model=SimPlanOut)
def get_sim_plan(business_id: str, db: Session = Depends(get_db)):
    return sim_service.get_sim_plan(db, business_id)


@router.put("/simulator/plan/{business_id}", response_model=SimPlanOut)
def put_sim_plan(business_id: str, req: SimPlanUpsert, db: Session = Depends(get_db)):
    return sim_service.put_sim_plan(db, business_id, req)


@router.get("/simulator/interventions/{business_id}", response_model=List[InterventionOut])
def list_sim_interventions(business_id: str, db: Session = Depends(get_db)):
    return sim_service.list_sim_interventions(db, business_id)


@router.post("/simulator/interventions/{business_id}", response_model=InterventionOut)
def create_sim_intervention(business_id: str, req: InterventionCreate, db: Session = Depends(get_db)):
    return sim_service.create_sim_intervention(db, business_id, req)


@router.patch("/simulator/interventions/{business_id}/{intervention_id}", response_model=InterventionOut)
def update_sim_intervention(business_id: str, intervention_id: str, req: InterventionPatch, db: Session = Depends(get_db)):
    return sim_service.update_sim_intervention(db, business_id, intervention_id, req)


@router.delete("/simulator/interventions/{business_id}/{intervention_id}")
def delete_sim_intervention(business_id: str, intervention_id: str, db: Session = Depends(get_db)):
    return sim_service.delete_sim_intervention(db, business_id, intervention_id)


@router.post("/simulator/generate/{business_id}", response_model=GenerateOut)
def generate_history(business_id: str, req: GenerateIn, db: Session = Depends(get_db)):
    return sim_service.generate_history(db, business_id, req)


# ============================================================
# LEGACY ENDPOINTS: /sim/*
# (keep so existing screens still work)
# ============================================================

@router.get("/sim/config/{business_id}", response_model=SimulatorConfigOut)
def get_or_create_sim_config(business_id: str, db: Session = Depends(get_db)):
    return sim_service.get_or_create_sim_config(db, business_id)


@router.put("/sim/config/{business_id}", response_model=SimulatorConfigOut)
def upsert_sim_config(business_id: str, req: SimulatorConfigUpsert, db: Session = Depends(get_db)):
    return sim_service.upsert_sim_config(db, business_id, req)


@router.post("/sim/pulse/{business_id}")
def pulse(
    business_id: str,
    n: int = Query(25, ge=1, le=500),
    run_monitoring: bool = Query(True),
    db: Session = Depends(get_db),
):
    return sim_service.pulse(db, business_id, n, run_monitoring=run_monitoring)


@router.post("/sim/run_history/{business_id}")
def run_history_legacy(business_id: str, req: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Legacy compatibility: call the new generator with a best-effort mapping.
    Prefer /simulator/generate/{business_id} going forward.
    """
    start = (sim_service.utcnow() - timedelta(days=int(req.get("days", 120)))).date().isoformat()
    gen = GenerateIn(
        start_date=start,
        days=int(req.get("days", 120)),
        seed=int(req.get("seed", 1337)),
        events_per_day=req.get("events_per_day"),
        enable_shocks=bool(req.get("enable_shocks", True)),
        shock_days=int(req.get("shock_days", 10)),
        revenue_drop_pct=float(req.get("revenue_drop_pct", 0.30)),
        expense_spike_pct=float(req.get("expense_spike_pct", 0.50)),
        mode="replace_from_start",
    )
    return sim_service.generate_history(db, business_id, gen)
