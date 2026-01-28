from __future__ import annotations

from dataclasses import replace
from typing import Optional

from backend.app.norma.normalize import NormalizedTransaction, EnrichedTransaction, Categorization




def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _contains(hay: str, *needles: str) -> bool:
    h = _norm(hay)
    return any(_norm(n) in h for n in needles)


def _enrich(
    txn: NormalizedTransaction,
    *,
    category: str,
    source: str,
    confidence: float,
    reason: str,
) -> EnrichedTransaction:
    # Start from txn data (works whether txn is NormalizedTransaction or EnrichedTransaction)
    base = txn if isinstance(txn, EnrichedTransaction) else EnrichedTransaction(**vars(txn))
    return replace(
        base,
        category=category,
        categorization=Categorization(
            category=category,
            source=source,          # "rule" etc.
            confidence=confidence,
            reason=reason,
            candidates=None,
        ),
    )


def categorize_txn(txn: NormalizedTransaction) -> NormalizedTransaction:
    """
    Returns an EnrichedTransaction when we categorize/review,
    but it's still a NormalizedTransaction subtype so downstream code works.
    Only acts when category is 'uncategorized'.
    """
    if _norm(txn.category) != "uncategorized":
        return txn

    desc = _norm(txn.description)

    # --- Payroll rules ---
    if _contains(desc, "gusto", "adp", "payroll", "paychex", "intuit payroll"):
        return _enrich(
            txn,
            category="payroll",
            source="rule",
            confidence=0.92,
            reason="Matched payroll keyword/merchant in description",
        )

    # --- Hosting rules ---
    if _contains(desc, "aws", "amazon web services", "digitalocean", "heroku", "render", "vercel", "netlify"):
        return _enrich(
            txn,
            category="hosting",
            source="rule",
            confidence=0.88,
            reason="Matched hosting keyword/merchant in description",
        )

    # --- Rent rules ---
    if _contains(desc, "rent", "lease"):
        return _enrich(
            txn,
            category="rent",
            source="rule",
            confidence=0.80,
            reason="Matched rent/lease keyword in description",
        )

    # No match: mark reviewed but keep uncategorized
    return _enrich(
        txn,
        category="uncategorized",
        source="rule",
        confidence=0.40,
        reason="No rule match; needs review",
    )
