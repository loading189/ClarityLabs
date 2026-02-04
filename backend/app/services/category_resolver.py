from __future__ import annotations

import logging
import os
from typing import Optional, Dict
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, joinedload

from backend.app.models import BusinessCategoryMap, Category

logger = logging.getLogger(__name__)


def _is_dev_env() -> bool:
    return (
        os.getenv("ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("APP_ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("NODE_ENV", "").lower() in {"dev", "development"}
    )


def resolve_system_key(db: Session, business_id: str, system_key: str) -> Optional[Dict[str, str]]:
    system_key = (system_key or "").strip().lower()
    if not system_key:
        return None

    row = db.execute(
        select(Category)
        .join(BusinessCategoryMap, BusinessCategoryMap.category_id == Category.id)
        .options(joinedload(Category.account))
        .where(
            and_(
                BusinessCategoryMap.business_id == business_id,
                BusinessCategoryMap.system_key == system_key,
                Category.business_id == business_id,
            )
        )
        .limit(1)
    ).scalars().first()

    if not row or not row.account:
        return None

    c = row
    return {
        "category_id": c.id,
        "category_name": c.name,
        "account_id": c.account.id,
        "account_code": c.account.code or "",
        "account_name": c.account.name or "",
    }


def require_system_key_mapping(
    db: Session,
    business_id: str,
    system_key: str,
    *,
    context: str,
) -> Dict[str, str]:
    resolved = resolve_system_key(db, business_id, system_key)
    if not resolved:
        message = (
            f"Invariant violation: {context} system_key '{system_key}' does not map to a valid category + account."
        )
        if _is_dev_env():
            logger.warning(
                "[categorization] invariant failed business=%s context=%s system_key=%s",
                business_id,
                context,
                system_key,
            )
        raise ValueError(message)
    return resolved
