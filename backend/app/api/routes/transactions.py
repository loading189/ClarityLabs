from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services.transaction_service import transaction_detail

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class RawEventOut(BaseModel):
    source: str
    source_event_id: str
    payload: Dict[str, Any]
    occurred_at: datetime
    created_at: datetime
    processed_at: Optional[datetime] = None


class NormalizedTxnOut(BaseModel):
    source_event_id: str
    occurred_at: datetime
    date: date
    description: str
    amount: float
    direction: str
    account: str
    category_hint: str
    counterparty_hint: Optional[str] = None
    merchant_key: Optional[str] = None


class VendorNormalizationOut(BaseModel):
    canonical_name: str
    source: str


class CategorizationOut(BaseModel):
    category_id: str
    category_name: str
    system_key: Optional[str] = None
    account_id: str
    account_name: str
    source: str
    confidence: float
    note: Optional[str] = None
    rule_id: Optional[str] = None
    created_at: datetime


class LedgerContextRowOut(BaseModel):
    source_event_id: str
    occurred_at: datetime
    date: date
    description: str
    vendor: str
    amount: float
    category: str
    account: str
    balance: float


class LedgerContextOut(BaseModel):
    row: LedgerContextRowOut
    balance: float
    running_total_in: float
    running_total_out: float


class AuditLogOut(BaseModel):
    id: str
    event_type: str
    actor: str
    reason: Optional[str] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    rule_id: Optional[str] = None
    created_at: datetime


class RelatedSignalOut(BaseModel):
    signal_id: str
    title: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    domain: Optional[str] = None
    updated_at: Optional[datetime] = None
    matched_on: Optional[str] = None
    window: Optional[Dict[str, Any]] = None
    facts: Optional[Dict[str, Any]] = None
    recommended_actions: List[Dict[str, Any]] = []


class SuggestedCategoryOut(BaseModel):
    system_key: str
    category_id: str
    category_name: str
    source: str
    confidence: float
    reason: str


class RuleSuggestionOut(BaseModel):
    contains_text: str
    category_id: str
    category_name: str
    direction: Optional[str] = None
    account: Optional[str] = None


class TransactionDetailOut(BaseModel):
    business_id: str
    source_event_id: str
    raw_event: RawEventOut
    normalized_txn: NormalizedTxnOut
    vendor_normalization: VendorNormalizationOut
    categorization: Optional[CategorizationOut] = None
    suggested_category: Optional[SuggestedCategoryOut] = None
    rule_suggestion: Optional[RuleSuggestionOut] = None
    processing_assumptions: List[Dict[str, str]]
    ledger_context: Optional[LedgerContextOut] = None
    audit_history: List[AuditLogOut]
    related_signals: List[RelatedSignalOut]


@router.get("/{business_id}/{source_event_id}", response_model=TransactionDetailOut)
def get_transaction_detail(
    business_id: str,
    source_event_id: str,
    db: Session = Depends(get_db),
):
    """
    Audit-grade transaction detail by source_event_id.
    Includes raw ingestion, normalization assumptions, and audit log history tied to the event.
    """
    return transaction_detail(db, business_id, source_event_id)
