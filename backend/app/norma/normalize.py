"""
Norma - normalization layer.

Responsibility:
- Convert RawTransaction records into canonical, downstream-safe objects.
- Apply lightweight, explainable normalization rules (MVP):
  - direction inferred from the sign of amount
  - category mapped from raw labels into our normalized taxonomy

Design notes:
- This module must be PURE:
  - no file IO
  - no network calls
  - no global state mutation
- Keep transformations deterministic and single-purpose.
- Any "learning" or "agentic" behavior belongs in a separate enrichment step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from .ingest import RawTransaction

# -------------------------
# Types
# -------------------------

Direction = Literal["inflow", "outflow"]

# Where a category decision came from (useful for audit + UI review later)
CategorySource = Literal["raw", "rule", "memory", "human", "model"]


# -------------------------
# Core normalized record
# -------------------------

@dataclass(frozen=True)
class NormalizedTransaction:
    id: Optional[str]                 # optional (if you have it)
    source_event_id: str              # REQUIRED for attribution
    occurred_at: datetime             # REQUIRED if you want ordering / windows

    date: date
    description: str
    amount: float
    direction: Direction
    account: str
    category: str
    counterparty_hint: Optional[str] = None


# -------------------------
# Optional enrichment metadata (NOT required for Facts/Ledger)
# -------------------------

@dataclass(frozen=True)
class Categorization:
    """
    Audit-friendly metadata about how a category was chosen.
    """
    category: str
    source: CategorySource
    confidence: float
    reason: str
    candidates: Optional[List[Dict[str, Any]]] = None  # [{category, confidence, reason}, ...]


@dataclass(frozen=True)
class EnrichedTransaction(NormalizedTransaction):
    """
    A NormalizedTransaction + optional categorization metadata.
    Use this only when you need explainability / human review.
    """
    categorization: Optional[Categorization] = None


# -------------------------
# Category mapping (MVP)
# -------------------------

CATEGORY_MAP: Dict[str, str] = {
    "sales income": "revenue",
    "refunds": "contra_revenue",
    "payroll": "payroll",
    "rent": "rent",
    "software": "software",
    "advertising": "marketing",
    "hosting": "hosting",
    "card payment": "debt_payment",
}


def normalize_category(raw: str) -> str:
    """
    Map raw category text into our internal taxonomy.

    Unknown / blank categories fall back to "uncategorized".
    """
    key = (raw or "").strip().lower()
    return CATEGORY_MAP.get(key, "uncategorized")


def infer_direction(amount: float) -> Direction:
    """
    Derive direction from the sign of amount.
    """
    return "inflow" if amount >= 0 else "outflow"


def normalize_txn(t: RawTransaction) -> NormalizedTransaction:
    return NormalizedTransaction(
        id=getattr(t, "id", None),
        source_event_id=t.source_event_id,
        occurred_at=t.occurred_at,

        date=t.date,
        description=t.description,
        amount=float(t.amount or 0.0),
        direction=infer_direction(t.amount),
        account=t.source_account,
        category=normalize_category(t.raw_category),
        counterparty_hint=None,
    )

