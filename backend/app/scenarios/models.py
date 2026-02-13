from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    name: str
    description: str
    tags: tuple[str, ...]
    parameters: dict[str, Any] | None = None


class ScenarioSeedRequest(BaseModel):
    business_id: str
    scenario_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class ScenarioResetRequest(BaseModel):
    business_id: str


class ScenarioSummary(BaseModel):
    txns_created: int
    ledger_rows: int
    signals_open_count: int
    actions_open_count: int | None = None


class ScenarioSeedResponse(BaseModel):
    business_id: str
    scenario_id: str
    seed_key: int
    summary: ScenarioSummary


def derive_seed_key(business_id: str, scenario_id: str, params: dict[str, Any] | None = None) -> int:
    canonical = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{business_id}|{scenario_id}|{canonical}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def parse_anchor_date(params: dict[str, Any]) -> date | None:
    value = params.get("anchor_date")
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
