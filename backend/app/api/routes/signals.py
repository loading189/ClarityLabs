from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_membership_dep
from backend.app.db import get_db
from backend.app.models import User
from backend.app.services import signals_service
from backend.app.services.assistant_thread_service import append_receipt

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalsResponse(BaseModel):
    signals: List[Dict[str, Any]]
    meta: Dict[str, Any]


class SignalStatusUpdateIn(BaseModel):
    status: str = Field(..., min_length=2, max_length=32)
    reason: Optional[str] = Field(default=None, max_length=500)
    actor: Optional[str] = Field(default=None, max_length=40)


class SignalStatusUpdateOut(BaseModel):
    business_id: str
    signal_id: str
    status: str
    last_seen_at: Optional[str]
    resolved_at: Optional[str]
    resolution_note: Optional[str]
    reason: Optional[str]
    audit_id: str


class SignalExplainStateOut(BaseModel):
    status: str
    severity: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    last_seen_at: Optional[str]
    resolved_at: Optional[str]
    metadata: Optional[Dict[str, Any]]
    resolved_condition_met: bool = False


class SignalExplainClearConditionOut(BaseModel):
    summary: str
    type: Literal["threshold", "trend", "categorical"]
    fields: Optional[List[str]] = None
    window_days: Optional[int] = None
    comparator: Optional[Literal[">=", "<=", "=="]] = None
    target: Optional[Any] = None


class SignalExplainPlaybookOut(BaseModel):
    id: str
    title: str
    description: str
    kind: Literal["inspect", "adjust", "decide"]
    ui_target: Literal["ledger", "vendors", "rules", "categorize", "assistant"]
    deep_link: Optional[str] = None
    requires_confirmation: Optional[bool] = None


class SignalRecommendedActionOut(BaseModel):
    action_id: str
    label: str
    rationale: str
    parameters: Optional[Dict[str, Any]] = None


class SignalExplainDetectorOut(BaseModel):
    type: str
    title: str
    description: str
    domain: str
    default_severity: Optional[str]
    recommended_actions: List[SignalRecommendedActionOut]
    evidence_schema: List[str]
    scoring_profile: Dict[str, Any]


class LedgerAnchorQueryOut(BaseModel):
    source_event_ids: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    accounts: Optional[List[str]] = None
    vendors: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    search: Optional[str] = None
    direction: Optional[Literal["inflow", "outflow"]] = None


class SignalExplainEvidenceAnchorOut(LedgerAnchorQueryOut):
    pass


class SignalExplainEvidenceOut(BaseModel):
    key: str
    label: str
    value: Any
    unit: Optional[str] = None
    as_of: Optional[str] = None
    source: Literal["ledger", "state", "derived", "detector"]
    anchors: Optional[SignalExplainEvidenceAnchorOut] = None


class SignalExplainEvidenceSummaryOut(BaseModel):
    counts: Dict[str, Any] = Field(default_factory=dict)
    deltas: Dict[str, Any] = Field(default_factory=dict)
    rows: List[str] = Field(default_factory=list)


class SignalExplainExplanationOut(BaseModel):
    observation: str
    evidence: SignalExplainEvidenceSummaryOut
    implication: str


class SignalExplainLedgerAnchorOut(BaseModel):
    label: str
    query: LedgerAnchorQueryOut
    evidence_keys: List[str] = Field(default_factory=list)


class SignalExplainVerificationFactOut(BaseModel):
    key: str
    label: str
    value: Any
    source: Literal["ledger", "state", "derived", "detector"]


class SignalExplainVerificationOut(BaseModel):
    status: Literal["met", "not_met", "unknown"]
    checked_at: str
    facts: List[SignalExplainVerificationFactOut] = Field(default_factory=list)


class SignalExplainNextActionOut(BaseModel):
    key: str
    label: str
    action: Optional[Literal["acknowledge", "snooze", "resolve"]]
    suggested_snooze_minutes: Optional[int] = None
    requires_reason: bool
    rationale: str
    guardrails: Optional[List[str]] = None

class SignalExplainAuditOut(BaseModel):
    id: str
    event_type: str
    actor: Optional[str]
    reason: Optional[str]
    status: Optional[str]
    created_at: Optional[str]


class SignalExplainOut(BaseModel):
    business_id: str
    signal_id: str
    state: SignalExplainStateOut
    detector: SignalExplainDetectorOut
    evidence: List[SignalExplainEvidenceOut]
    related_audits: List[SignalExplainAuditOut]
    next_actions: List[SignalExplainNextActionOut]
    clear_condition: Optional[SignalExplainClearConditionOut] = None
    verification: SignalExplainVerificationOut
    playbooks: List[SignalExplainPlaybookOut] = Field(default_factory=list)
    explanation: SignalExplainExplanationOut
    ledger_anchors: List[SignalExplainLedgerAnchorOut] = Field(default_factory=list)
    links: List[str]


@router.get("", response_model=SignalsResponse, dependencies=[Depends(require_membership_dep())])
def list_signals(
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    signals, meta = signals_service.list_signal_states(db, business_id)
    return SignalsResponse(signals=signals, meta=meta)


@router.get("/types", response_model=List[Dict[str, Any]])
def list_signal_types(
    include_inputs: Optional[bool] = Query(True),
):
    types = signals_service.available_signal_types()
    if not include_inputs:
        return [{"type": row["type"], "window_days": row["window_days"]} for row in types]
    return types


@router.get("/v1", response_model=SignalsResponse, dependencies=[Depends(require_membership_dep())])
def list_v1_signals(
    business_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    signals, meta = signals_service.fetch_signals(db, business_id, start_date, end_date)
    return SignalsResponse(signals=signals, meta=meta)


@router.post(
    "/{business_id}/{signal_id}/status",
    response_model=SignalStatusUpdateOut,
    dependencies=[Depends(require_membership_dep(min_role="staff"))],
)
def update_signal_status(
    business_id: str,
    signal_id: str,
    req: SignalStatusUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = signals_service.update_signal_status(
        db,
        business_id,
        signal_id,
        status=req.status,
        reason=req.reason,
        actor=req.actor or user.email,
    )
    append_receipt(
        db,
        business_id,
        {
            "action": "signal_status_updated",
            "actor": req.actor,
            "reason": req.reason,
            "signal_id": signal_id,
            "audit_id": result.get("audit_id"),
            "links": {
                "audit": f"/app/{business_id}/audit/{result.get('audit_id')}",
                "signal": f"/app/{business_id}/assistant?signalId={signal_id}",
            },
        },
        dedupe=False,
    )
    return result


@router.get("/{business_id}/{signal_id}", dependencies=[Depends(require_membership_dep())])
def get_signal_detail(
    business_id: str,
    signal_id: str,
    db: Session = Depends(get_db),
):
    return signals_service.get_signal_state_detail(db, business_id, signal_id)


@router.get(
    "/{business_id}/{signal_id}/explain",
    dependencies=[Depends(require_membership_dep())],
)
def get_signal_explain(
    business_id: str,
    signal_id: str,
    db: Session = Depends(get_db),
):
    return signals_service.get_signal_explain(db, business_id, signal_id)
