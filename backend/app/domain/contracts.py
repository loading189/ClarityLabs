from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RawEventContract(BaseModel):
    id: Optional[str] = None
    business_id: Optional[str] = None
    source: str
    source_event_id: str
    occurred_at: datetime
    payload: Dict[str, Any]


class NormalizedTransactionContract(BaseModel):
    id: Optional[str] = None
    source_event_id: str
    occurred_at: datetime
    date: date
    description: str
    amount: float
    direction: str
    account: str
    category: str
    counterparty_hint: Optional[str] = None


class CategorizationContract(BaseModel):
    category: str
    source: str
    confidence: float
    reason: str
    candidates: Optional[List[Dict[str, Any]]] = None


class CategorizedTransactionContract(NormalizedTransactionContract):
    categorization: Optional[CategorizationContract] = None


class LedgerRowContract(BaseModel):
    occurred_at: datetime
    source_event_id: str
    date: date
    description: str
    amount: float
    category: str
    balance: float


class SignalResult(BaseModel):
    key: str
    title: str
    severity: str
    dimension: str
    priority: int
    value: Any
    message: str

    inputs: Optional[List[str]] = None
    conditions: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    why: Optional[str] = None
    how_to_fix: Optional[str] = None
    evidence_refs: Optional[List[Dict[str, Any]]] = None

    version: int = 1


class BriefFactsMeta(BaseModel):
    as_of: Optional[str] = None
    txn_count: int
    months_covered: int


class BriefResult(BaseModel):
    business_id: str
    as_of: Optional[str] = None
    window_days: int
    status: str
    headline: str
    bullets: List[str]
    next_best_action: str
    confidence: float
    confidence_reason: str
    top_signals: List[SignalResult]
    facts_meta: BriefFactsMeta
