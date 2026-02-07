from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Business, BusinessIntegrationProfile
from backend.app.services import integration_connection_service
from backend.app.services.plaid_sync_service import sync_plaid_transactions

router = APIRouter(prefix="/integrations", tags=["integrations"])


def utcnow() -> datetime:
    return datetime.utcnow()


class IntegrationProfileOut(BaseModel):
    business_id: str
    bank: bool
    payroll: bool
    card_processor: bool
    ecommerce: bool
    invoicing: bool
    simulation_params: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # pydantic v2 ORM mode


class IntegrationProfileUpsert(BaseModel):
    bank: Optional[bool] = None
    payroll: Optional[bool] = None
    card_processor: Optional[bool] = None
    ecommerce: Optional[bool] = None
    invoicing: Optional[bool] = None
    # allow null from client, but we will sanitize it before writing to DB
    simulation_params: Optional[dict] = None


class IntegrationConnectionOut(BaseModel):
    id: str
    business_id: str
    provider: str
    is_enabled: bool
    status: str
    disconnected_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error: Optional[dict] = None
    provider_cursor: Optional[str] = None
    last_ingested_source_event_id: Optional[str] = None
    last_processed_source_event_id: Optional[str] = None

    class Config:
        from_attributes = True


class ReplayRequest(BaseModel):
    since: Optional[str] = None
    last_n: Optional[int] = None


class ToggleRequest(BaseModel):
    is_enabled: bool


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _get_or_create_profile(db: Session, business_id: str) -> BusinessIntegrationProfile:
    prof = db.get(BusinessIntegrationProfile, business_id)
    if prof:
        # ensure simulation_params is never null (safety)
        if prof.simulation_params is None:
            prof.simulation_params = {
                        "volume_level": "medium",
                        "volatility": "normal",
                        "seasonality": False,
            }
            prof.updated_at = utcnow()
            db.commit()
            db.refresh(prof)
        return prof

    # rely on model defaults for toggles + simulation_params
    prof = BusinessIntegrationProfile(business_id=business_id, created_at=utcnow(), updated_at=utcnow())
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


@router.get("/business/{business_id}", response_model=IntegrationProfileOut)
def get_profile(business_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    prof = _get_or_create_profile(db, business_id)
    return prof


@router.put("/business/{business_id}", response_model=IntegrationProfileOut)
def update_profile(business_id: str, req: IntegrationProfileUpsert, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    prof = _get_or_create_profile(db, business_id)

    data = req.model_dump(exclude_unset=True)

    # prevent wiping simulation_params
    if "simulation_params" in data and data["simulation_params"] is None:
        data.pop("simulation_params")

    for field, value in data.items():
        # IMPORTANT: don't allow writing NULL into a non-null JSON column
        if field == "simulation_params" and value is None:
            # Option A: ignore null (treat as "not provided")
            continue

            # Option B: convert null to {} (uncomment if you'd rather do that)
            # value = {}

        setattr(prof, field, value)

    prof.updated_at = utcnow()
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


@router.get("/{business_id}/connections", response_model=list[IntegrationConnectionOut])
def list_connections(business_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    return integration_connection_service.list_connections(db, business_id)


@router.post("/{business_id}/{provider}/sync")
def sync_connection(business_id: str, provider: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    if provider != "plaid":
        raise HTTPException(status_code=400, detail="unsupported provider")
    return sync_plaid_transactions(db, business_id=business_id, provider=provider, mode="sync")


@router.post("/{business_id}/{provider}/replay")
def replay_connection(
    business_id: str,
    provider: str,
    req: ReplayRequest,
    db: Session = Depends(get_db),
):
    _require_business(db, business_id)
    if provider != "plaid":
        raise HTTPException(status_code=400, detail="unsupported provider")
    return sync_plaid_transactions(
        db,
        business_id=business_id,
        provider=provider,
        since=req.since,
        last_n=req.last_n,
        mode="replay",
    )


@router.post("/{business_id}/{provider}/toggle", response_model=IntegrationConnectionOut)
def toggle_connection(
    business_id: str,
    provider: str,
    req: ToggleRequest,
    db: Session = Depends(get_db),
):
    _require_business(db, business_id)
    conn = integration_connection_service.get_or_create_connection(db, business_id, provider)
    integration_connection_service.set_enabled(conn, req.is_enabled)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.post("/{business_id}/{provider}/disconnect", response_model=IntegrationConnectionOut)
def disconnect_connection(business_id: str, provider: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    conn = integration_connection_service.get_or_create_connection(db, business_id, provider)
    integration_connection_service.disconnect(conn)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn
