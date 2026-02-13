from __future__ import annotations

import os

from fastapi import HTTPException


def dev_tools_enabled() -> bool:
    return os.getenv("CLARITY_DEV_TOOLS", "0").strip() == "1"


def require_dev_tools() -> None:
    if not dev_tools_enabled():
        raise HTTPException(status_code=404, detail="Dev tools are disabled.")

