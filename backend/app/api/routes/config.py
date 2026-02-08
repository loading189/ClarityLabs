from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.api.config import allow_business_delete, pilot_mode_enabled

router = APIRouter(prefix="/api", tags=["config"])


class ConfigOut(BaseModel):
    pilot_mode_enabled: bool
    allow_business_delete: bool


@router.get("/config", response_model=ConfigOut)
def get_config() -> ConfigOut:
    return ConfigOut(
        pilot_mode_enabled=pilot_mode_enabled(),
        allow_business_delete=allow_business_delete(),
    )
