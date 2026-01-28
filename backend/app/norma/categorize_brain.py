from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backend.app.norma.normalize import NormalizedTransaction, EnrichedTransaction, Categorization
from backend.app.norma.merchant import merchant_key
from backend.app.norma.brain_store import BrainStore

BRAIN_PATH = Path(__file__).resolve().parent / "data" / "brain.json"
brain = BrainStore(BRAIN_PATH)


def _as_enriched(txn: NormalizedTransaction) -> EnrichedTransaction:
    return txn if isinstance(txn, EnrichedTransaction) else EnrichedTransaction(**vars(txn))


def categorize_txn_with_brain(txn: NormalizedTransaction, *, business_id: str) -> NormalizedTransaction:
    # only act when uncategorized
    if (txn.category or "").strip().lower() != "uncategorized":
        return txn

    mk = merchant_key(txn.description)
    lbl = brain.lookup_label(business_id=business_id, alias_key=mk)
    if lbl:
        base = _as_enriched(txn)
        return replace(
            base,
            category=lbl.system_key,  # NOTE: category field carries system_key in suggestion stage
            categorization=Categorization(
                category=lbl.system_key,
                source="memory",
                confidence=lbl.confidence,
                reason="Matched vendor memory for this business",
                candidates=[{"merchant_key": mk, "system_key": lbl.system_key}],
            ),
        )

    return txn
