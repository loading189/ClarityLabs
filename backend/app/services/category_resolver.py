from __future__ import annotations

from typing import Optional, Dict
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, joinedload

from backend.app.models import BusinessCategoryMap, Category


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
