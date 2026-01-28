from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.db import get_db
from backend.app.models import Business, RawEvent
from backend.app.sim.profiles import PROFILES
from backend.app.sim.generators.plaid import make_plaid_transaction_event

router = APIRouter()

class SimConfigIn(BaseModel):
    enabled: bool
    profile: str = "normal"

@router.post("/businesses/{business_id}/config")
def set_sim_config(business_id: uuid.UUID, req: SimConfigIn, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")

    if req.profile not in PROFILES:
        raise HTTPException(400, f"unknown profile '{req.profile}'. Choose from: {list(PROFILES.keys())}")

    biz.sim_enabled = req.enabled
    biz.sim_profile = req.profile
    db.commit()
    return {"status": "ok", "business_id": str(business_id), "sim_enabled": biz.sim_enabled, "sim_profile": biz.sim_profile}

