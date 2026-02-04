from __future__ import annotations

from dataclasses import replace
from typing import Optional, List, Tuple

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.app.models import CategoryRule, BusinessCategoryMap, Category, Account
from backend.app.services.category_resolver import require_system_key_mapping
from backend.app.norma.normalize import NormalizedTransaction, EnrichedTransaction, Categorization
from backend.app.norma.categorize import categorize_txn as heuristic_categorize_txn
from backend.app.norma.categorize_brain import categorize_txn_with_brain


def _as_enriched(txn: NormalizedTransaction) -> EnrichedTransaction:
    return txn if isinstance(txn, EnrichedTransaction) else EnrichedTransaction(**vars(txn))


def _is_uncat(val: Optional[str]) -> bool:
    return (val or "").strip().lower() in ("", "uncategorized", "unknown")


def _contains(haystack: str, needle: str) -> bool:
    return needle in haystack


def _system_key_for_category_id(db: Session, business_id: str, category_id: str) -> Optional[str]:
    """
    Convert category_id -> system_key using BusinessCategoryMap.
    This keeps your "system_key as lingua franca" approach consistent.
    """
    m = db.execute(
        select(BusinessCategoryMap.system_key)
        .join(Category, Category.id == BusinessCategoryMap.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(
            and_(
                BusinessCategoryMap.business_id == business_id,
                BusinessCategoryMap.category_id == category_id,
                Category.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    system_key = (m or "").strip().lower() or None
    if not system_key:
        raise ValueError(
            f"Invariant violation: rule category_id '{category_id}' has no valid system_key mapping."
        )
    return system_key


def suggest_from_rules(
    db: Session,
    txn: NormalizedTransaction,
    *,
    business_id: str,
) -> Optional[EnrichedTransaction]:
    """
    Business-scoped deterministic rules using CategoryRule.
    Returns EnrichedTransaction where `category` == system_key (NOT category name).

    Conflict policy: first match wins, ordered by priority (asc), created_at (asc), id (asc).
    """
    desc = (txn.description or "").strip().lower()
    if not desc:
        return None

    direction = (txn.direction or "").strip().lower()  # "inflow"/"outflow"
    account = (txn.account or "").strip().lower()

    # Pull active rules, most specific first (lower priority number = higher rank)
    rules = db.execute(
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
        .limit(5000)
    ).scalars().all()

    for r in rules:
        needle = (r.contains_text or "").strip().lower()
        if not needle:
            continue

        if r.direction and (r.direction.strip().lower() != direction):
            continue

        if r.account and (r.account.strip().lower() != account):
            continue

        if not _contains(desc, needle):
            continue

        # Map category_id -> system_key (what your downstream expects)
        system_key = _system_key_for_category_id(db, business_id, r.category_id)
        if not system_key or system_key == "uncategorized":
            continue

        base = _as_enriched(txn)
        return replace(
            base,
            category=system_key,
            categorization=Categorization(
                category=system_key,
                source="rule",
                confidence=0.92,  # deterministic business rule
                reason=f"Matched rule contains_text='{needle}'",
                candidates=None,
            ),
        )

    return None


def _vendor_keyword_suggest(description: str) -> Optional[Categorization]:
    """
    Lightweight global keyword heuristics -> system_key.
    Deterministic + cheap.
    """
    d = (description or "").strip().lower()
    if not d:
        return None

    rules: List[Tuple[str, str, float, str]] = [
        # Utilities / telecom
        ("comcast", "utilities", 0.78, "Matched vendor keyword 'comcast'"),
        ("xfinity", "utilities", 0.78, "Matched vendor keyword 'xfinity'"),
        ("verizon", "utilities", 0.70, "Matched vendor keyword 'verizon'"),
        ("at&t", "utilities", 0.70, "Matched vendor keyword 'at&t'"),
        ("t-mobile", "utilities", 0.70, "Matched vendor keyword 't-mobile'"),
        ("tmobile", "utilities", 0.70, "Matched vendor keyword 'tmobile'"),

        # Software / subscriptions
        ("adobe", "software", 0.74, "Matched vendor keyword 'adobe'"),
        ("google workspace", "software", 0.70, "Matched vendor keyword 'google workspace'"),
        ("microsoft", "software", 0.68, "Matched vendor keyword 'microsoft'"),
        ("dropbox", "software", 0.70, "Matched vendor keyword 'dropbox'"),
        ("slack", "software", 0.70, "Matched vendor keyword 'slack'"),
        ("github", "software", 0.65, "Matched vendor keyword 'github'"),
        ("zoom", "software", 0.65, "Matched vendor keyword 'zoom'"),

        # Meals
        ("doordash", "meals", 0.72, "Matched vendor keyword 'doordash'"),
        ("uber eats", "meals", 0.72, "Matched vendor keyword 'uber eats'"),

        # Travel
        ("airbnb", "travel", 0.72, "Matched vendor keyword 'airbnb'"),
        ("delta", "travel", 0.68, "Matched vendor keyword 'delta'"),
        ("united", "travel", 0.66, "Matched vendor keyword 'united'"),
        ("hotel", "travel", 0.60, "Matched keyword 'hotel'"),
        ("lyft", "travel", 0.58, "Matched vendor keyword 'lyft'"),

        # Marketing
        ("facebook", "marketing", 0.70, "Matched vendor keyword 'facebook'"),
        ("meta", "marketing", 0.62, "Matched vendor keyword 'meta'"),
        ("google ads", "marketing", 0.72, "Matched vendor keyword 'google ads'"),
        ("adwords", "marketing", 0.70, "Matched vendor keyword 'adwords'"),

        # Bank fees
        ("bank fee", "bank_fees", 0.72, "Matched keyword 'bank fee'"),
        ("service fee", "bank_fees", 0.64, "Matched keyword 'service fee'"),
        ("overdraft", "bank_fees", 0.78, "Matched keyword 'overdraft'"),
    ]

    for needle, system_key, conf, why in rules:
        if needle in d:
            return Categorization(
                category=system_key,
                source="heuristic",
                confidence=conf,
                reason=why,
                candidates=None,
            )

    return None


def suggest_category(
    db: Session,
    txn: NormalizedTransaction,
    *,
    business_id: str,
) -> NormalizedTransaction:
    """
    Suggestion order:
      1) Brain (business memory)
      2) Rules (business deterministic / bulk-loadable)
      3) Heuristics (global)
      4) No suggestion
    """
    if not _is_uncat(txn.category):
        return txn

    # 1) Brain
    brain_res = categorize_txn_with_brain(txn, business_id=business_id)
    if isinstance(brain_res, EnrichedTransaction) and brain_res.categorization and not _is_uncat(brain_res.category):
        require_system_key_mapping(
            db,
            business_id,
            brain_res.category,
            context="vendor default",
        )
        return brain_res

    # 2) Rules
    rule_res = suggest_from_rules(db, txn, business_id=business_id)
    if rule_res and not _is_uncat(rule_res.category):
        return rule_res

    # 3) Heuristics (your existing global heuristic engine)
    heur = heuristic_categorize_txn(txn)
    if isinstance(heur, EnrichedTransaction) and heur.categorization and not _is_uncat(heur.category):
        return heur

    # 3b) Optional: your tiny keyword list (if you want it as a fallback)
    kw = _vendor_keyword_suggest(txn.description)
    if kw and not _is_uncat(kw.category):
        base = _as_enriched(txn)
        return replace(base, category=kw.category, categorization=kw)

    # 4) No suggestion -> IMPORTANT: do NOT invent “uncategorized” as a suggestion
    base = _as_enriched(txn)
    return replace(
        base,
        categorization=Categorization(
            category="uncategorized",
            source="none",
            confidence=0.0,
            reason="No suggestion available; needs review",
            candidates=None,
        ),
    )
