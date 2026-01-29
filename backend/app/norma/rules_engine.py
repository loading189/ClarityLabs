from __future__ import annotations

from dataclasses import replace
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.app.models import CategoryRule, BusinessCategoryMap
from backend.app.norma.normalize import NormalizedTransaction, EnrichedTransaction, Categorization


def _as_enriched(txn: NormalizedTransaction) -> EnrichedTransaction:
    return txn if isinstance(txn, EnrichedTransaction) else EnrichedTransaction(**vars(txn))


def _direction(txn: NormalizedTransaction) -> str:
    return (txn.direction or "").strip().lower()


def _account(txn: NormalizedTransaction) -> str:
    return (txn.account or "").strip().lower()


def _desc(txn: NormalizedTransaction) -> str:
    return (txn.description or "").strip().lower()


def suggest_from_rules(
    db: Session,
    txn: NormalizedTransaction,
    *,
    business_id: str,
) -> Optional[EnrichedTransaction]:
    """
    Business-scoped deterministic rules.

    If a rule matches, we convert its category_id -> system_key
    using BusinessCategoryMap (because the rest of the pipeline uses system_key).

    Conflict policy: first match wins, ordered by priority (asc), created_at (asc), id (asc).
    """
    desc = _desc(txn)
    if not desc:
        return None

    rows = (
        db.execute(
            select(CategoryRule)
            .where(
                and_(
                    CategoryRule.business_id == business_id,
                    CategoryRule.active.is_(True),
                )
            )
            .order_by(
                CategoryRule.priority.asc(),
                CategoryRule.created_at.asc(),
                CategoryRule.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    for r in rows:
        needle = (r.contains_text or "").strip().lower()
        if not needle:
            continue

        if needle not in desc:
            continue

        # optional filters
        if r.direction and r.direction.strip().lower() != _direction(txn):
            continue
        if r.account and r.account.strip().lower() != _account(txn):
            continue

        # Convert category_id -> system_key (so we can resolve consistently)
        m = db.execute(
            select(BusinessCategoryMap).where(
                and_(
                    BusinessCategoryMap.business_id == business_id,
                    BusinessCategoryMap.category_id == r.category_id,
                )
            )
        ).scalar_one_or_none()

        if not m:
            # Rule points to a category that isn't mapped yet; skip.
            continue

        sys_key = (m.system_key or "").strip().lower()
        if not sys_key or sys_key == "uncategorized":
            continue

        base = _as_enriched(txn)
        return replace(
            base,
            category=sys_key,
            categorization=Categorization(
                category=sys_key,
                source="rule",
                confidence=0.92,
                reason=f"Matched rule: contains '{needle}'",
                candidates=None,
            ),
        )

    return None
