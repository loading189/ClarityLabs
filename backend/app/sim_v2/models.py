from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ScenarioInput(BaseModel):
    id: str
    intensity: int = Field(default=1, ge=1, le=3)


class SimV2SeedRequest(BaseModel):
    business_id: str
    preset_id: Optional[str] = None
    scenarios: Optional[List[ScenarioInput]] = None
    anchor_date: Optional[date] = None
    lookback_days: int = Field(default=120, ge=30, le=365)
    forward_days: int = Field(default=14, ge=0, le=60)
    mode: Literal["replace", "append"] = "replace"
    seed: Optional[int] = None


class SimV2ResetRequest(BaseModel):
    business_id: str


class SimClockOut(BaseModel):
    anchor_date: date
    start_date: date
    end_date: date
    lookback_days: int
    forward_days: int


class SimV2SeedResponse(BaseModel):
    business_id: str
    window: SimClockOut
    preset_id: Optional[str] = None
    scenarios_applied: List[Dict[str, int | str]]
    stats: Dict[str, int | bool]
    signals: Dict[str, object]

