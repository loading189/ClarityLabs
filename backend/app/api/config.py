from __future__ import annotations

import os


def pilot_mode_enabled() -> bool:
    return os.getenv("PILOT_DEV_MODE") == "1" or os.getenv("CLARITY_PILOT_MODE") == "1"


def allow_business_delete() -> bool:
    return os.getenv("ALLOW_BUSINESS_DELETE") == "1"
