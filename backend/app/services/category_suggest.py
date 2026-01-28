from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Dict

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models import Category, CategoryRule, TxnCategorization, RawEvent


# Treat these as "never suggest" buckets
NEVER_SUGGEST_NAMES = {"uncategorized"}


@dataclass
class Suggestion:
    category_id: str
    confidence: float
    source: str  # history|rule|vendor_map


def _normalize_vendor(v: str) -> str:
    return (v or "").strip().lower()


def _extract_vendor_and_text(raw_event_payload: dict) -> tuple[str, str]:
    """
    Adjust this to your payload shape.
    Common: payload["merchant_name"], payload["name"], payload["description"]
    """
    vendor = (
        raw_event_payload.get("merchant_name")
        or raw_event_payload.get("name")
        or raw_event_payload.get("vendor")
        or ""
    )
    text = (
        raw_event_payload.get("description")
        or raw_event_payload.get("name")
        or raw_event_payload.get("raw_description")
        or ""
    )
    return vendor, text


def _get_uncategorized_category_id(db: Session, business_id: str) -> Optional[str]:
    row = db.execute(
        select(Category.id).where(
            Category.business_id == business_id,
            func.lower(Category.name).in_(NEVER_SUGGEST_NAMES),
        )
    ).first()
    return row[0] if row else None


def suggest_category_for_event(
    db: Session,
    business_id: str,
    source_event_id: str,
    min_confidence: float = 0.70,
) -> Optional[Suggestion]:
    """
    Returns a real suggestion or None.
    Never returns Uncategorized.
    """

    uncategorized_id = _get_uncategorized_category_id(db, business_id)

    # --- 0) Load the raw event so we can read vendor/text ---
    ev = db.execute(
        select(RawEvent).where(
            RawEvent.business_id == business_id,
            RawEvent.source_event_id == source_event_id,
        )
    ).scalar_one_or_none()

    if not ev:
        return None

    vendor, text = _extract_vendor_and_text(ev.payload)
    vendor_n = _normalize_vendor(vendor)
    text_n = (text or "").lower()

    # --- 1) HISTORY: vendor -> most common prior category ---
    # (MVP heuristic: for same vendor, count categories)
    hist_rows = db.execute(
        select(TxnCategorization.category_id, func.count())
        .where(
            TxnCategorization.business_id == business_id,
            TxnCategorization.source_event_id != source_event_id,
        )
        .join(RawEvent, (RawEvent.source_event_id == TxnCategorization.source_event_id) & (RawEvent.business_id == TxnCategorization.business_id))
        .where(func.lower(RawEvent.payload["merchant_name"].astext) == vendor_n)  # may need payload key adjustment
        .group_by(TxnCategorization.category_id)
        .order_by(func.count().desc())
        .limit(1)
    ).first()

    if hist_rows:
        cat_id, cnt = hist_rows[0], hist_rows[1]
        if cat_id and cat_id != uncategorized_id:
            # Simple confidence: grows with count, capped
            conf = min(0.95, 0.60 + (0.10 * min(cnt, 4)))
            if conf >= min_confidence:
                return Suggestion(category_id=cat_id, confidence=conf, source="history")

    # --- 2) RULES: contains_text match ---
    # Priority: smaller number = more important if you ever use it
    rules = db.execute(
        select(CategoryRule)
        .where(CategoryRule.business_id == business_id)
        .where(CategoryRule.active == True)  # noqa: E712
        .order_by(CategoryRule.priority.asc())
    ).scalars().all()

    for r in rules:
        if r.contains_text.lower() in text_n:
            if r.category_id and r.category_id != uncategorized_id:
                # Rules are high confidence
                conf = 0.90
                if conf >= min_confidence:
                    return Suggestion(category_id=r.category_id, confidence=conf, source="rule")

    # --- 3) VENDOR MAP (MVP dictionary) ---
    # You can expand this list quickly
    vendor_map: Dict[str, str] = {
        "comcast": "Utilities",
        "xfinity": "Utilities",
        "att": "Utilities",
        "verizon": "Utilities",
        "centurylink": "Utilities",
        "adobe": "Software & Subscriptions",
        "microsoft": "Software & Subscriptions",
        "google": "Software & Subscriptions",
        "aws": "Software & Subscriptions",
        "amazon web services": "Software & Subscriptions",
        "uber": "Travel",
        "lyft": "Travel",
        "doordash": "Meals",
        "grubhub": "Meals",
        "stripe": "Bank Fees",
        "square": "Bank Fees",
    }

    # find first matching vendor key (substring match)
    target_category_name: Optional[str] = None
    for key, cat_name in vendor_map.items():
        if key in vendor_n or key in text_n:
            target_category_name = cat_name
            break

    if target_category_name:
        cat_row = db.execute(
            select(Category.id)
            .where(Category.business_id == business_id)
            .where(func.lower(Category.name) == target_category_name.lower())
        ).first()

        if cat_row:
            cat_id = cat_row[0]
            if cat_id != uncategorized_id:
                conf = 0.80
                if conf >= min_confidence:
                    return Suggestion(category_id=cat_id, confidence=conf, source="vendor_map")

    # --- 4) No suggestion ---
    return None
