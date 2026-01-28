from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Account, Category


def utcnow() -> datetime:
    return datetime.utcnow()


def uuid_str() -> str:
    return str(uuid.uuid4())


def _pick_default_expense_account(db: Session, business_id: str) -> Optional[Account]:
    """
    Pick a reasonable default expense account for auto-created categories.
    Preference order:
      1) An expense account with code '6000' if present
      2) Any expense account
      3) Any account at all (last resort)
      4) None
    """
    a = db.execute(
        select(Account)
        .where(Account.business_id == business_id, Account.type == "expense")
        .order_by(Account.code.asc().nulls_last(), Account.name.asc())
        .limit(1)
    ).scalar_one_or_none()
    if a:
        return a

    a = db.execute(
        select(Account)
        .where(Account.business_id == business_id)
        .order_by(Account.code.asc().nulls_last(), Account.name.asc())
        .limit(1)
    ).scalar_one_or_none()
    return a


def ensure_category_for_system_key(db: Session, business_id: str, system_key: str) -> Category:
    """
    Ensures the business has a Category row for this system_key.
    If missing, creates it with a best-effort default account_id.

    Requires:
      - categories.account_id exists in DB (alembic migration)
      - business has at least one Account row (apply COA template), or we fallback safely
    """
    system_key = (system_key or "").strip().lower()
    if not system_key:
        raise ValueError("system_key required")

    existing = db.execute(
        select(Category).where(
            Category.business_id == business_id,
            Category.system_key == system_key,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    # nice names (MVP)
    pretty = {
        "payroll": "Payroll",
        "rent": "Rent",
        "hosting": "Hosting",
        "marketing": "Marketing",
        "cogs": "Cost of Goods Sold",
        "office_supplies": "Office Supplies",
        "utilities": "Utilities",
        "insurance": "Insurance",
        "meals": "Meals",
        "travel": "Travel",
        "taxes": "Taxes & Licenses",
        "software": "Software & Subscriptions",
        "sales": "Sales",
        "contra": "Refunds / Returns",
        "uncategorized": "Uncategorized",
    }.get(system_key, system_key.replace("_", " ").title())

    # pick a default account_id so your dropdown can show COA details
    acct = _pick_default_expense_account(db, business_id)
    if not acct:
        raise ValueError(
            "No accounts exist for this business yet. Apply the COA template first."
        )

    c = Category(
        id=uuid_str(),
        business_id=business_id,
        name=pretty,
        system_key=system_key,
        account_id=acct.id,
        created_at=utcnow(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
