from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.models import ActionItem, HealthSignalState, IntegrationConnection, RawEvent
from backend.app.services import diagnostics_service
from backend.app.services.posted_txn_service import count_uncategorized_raw_events

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class OrphanCategoryOut(BaseModel):
    category_id: str
    name: str
    account_id: Optional[str] = None


class InvalidRuleOut(BaseModel):
    rule_id: str
    category_id: str
    issue: str


class InvalidVendorDefaultOut(BaseModel):
    merchant_id: str
    system_key: str
    issue: str


class LedgerIntegrityOut(BaseModel):
    status: str
    detail: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None


class DiagnosticsOut(BaseModel):
    orphan_categories: List[OrphanCategoryOut]
    invalid_rule_outputs: List[InvalidRuleOut]
    invalid_vendor_defaults: List[InvalidVendorDefaultOut]
    ledger_integrity: LedgerIntegrityOut


class DiagnosticsErrorOut(BaseModel):
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ProcessingErrorOut(BaseModel):
    source_event_id: str
    provider: str
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    updated_at: Optional[datetime] = None


class IngestionConnectionOut(BaseModel):
    provider: str
    status: str
    last_sync_at: Optional[datetime] = None
    last_cursor: Optional[str] = None
    last_cursor_at: Optional[datetime] = None
    last_webhook_at: Optional[datetime] = None
    last_ingest_counts: Optional[dict] = None
    last_error: Optional[str] = None


class IngestionDiagnosticsOut(BaseModel):
    status_counts: Dict[str, int]
    errors: List[ProcessingErrorOut]
    connections: List[IngestionConnectionOut]
    monitor_status: Dict[str, Any]


class ReconcileConnectionOut(BaseModel):
    provider: str
    status: str
    provider_cursor: Optional[str] = None
    provider_cursor_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None
    last_ingested_source_event_id: Optional[str] = None
    last_processed_at: Optional[datetime] = None
    last_processed_source_event_id: Optional[str] = None
    mismatch_flags: Dict[str, bool]


class ReconcileLatestMarkersOut(BaseModel):
    raw_event_occurred_at: Optional[datetime] = None
    raw_event_source_event_id: Optional[str] = None
    connections: List[ReconcileConnectionOut]


class ReconcileCountsOut(BaseModel):
    raw_events: int
    posted_transactions: int
    categorized_transactions: int


class ReconcileOut(BaseModel):
    counts: ReconcileCountsOut
    latest_markers: ReconcileLatestMarkersOut



class DataStatusLatestEventOut(BaseModel):
    source: Optional[str] = None
    occurred_at: Optional[datetime] = None


class DataStatusOut(BaseModel):
    latest_event: DataStatusLatestEventOut
    open_signals: int
    open_actions: int
    ledger_rows: int
    uncategorized_txns: int
    last_sync_at: Optional[datetime] = None


@router.get(
    "/{business_id}",
    response_model=Union[DiagnosticsOut, DiagnosticsErrorOut],
    dependencies=[Depends(require_membership_dep())],
)
def get_diagnostics(business_id: str, db: Session = Depends(get_db)):
    try:
        payload = diagnostics_service.collect_diagnostics(db, business_id)
        return DiagnosticsOut(**payload)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return DiagnosticsErrorOut(
            status="error",
            message=str(exc),
            details={"type": exc.__class__.__name__},
        )


@router.get(
    "/ingestion/{business_id}",
    response_model=Union[IngestionDiagnosticsOut, DiagnosticsErrorOut],
    dependencies=[Depends(require_membership_dep())],
)
def get_ingestion_diagnostics(business_id: str, db: Session = Depends(get_db)):
    try:
        payload = diagnostics_service.collect_ingestion_diagnostics(db, business_id)
        return IngestionDiagnosticsOut(**payload)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return DiagnosticsErrorOut(
            status="error",
            message=str(exc),
            details={"type": exc.__class__.__name__},
        )


@router.get(
    "/reconcile/{business_id}",
    response_model=Union[ReconcileOut, DiagnosticsErrorOut],
    dependencies=[Depends(require_membership_dep())],
)
def get_reconcile_report(business_id: str, db: Session = Depends(get_db)):
    try:
        payload = diagnostics_service.collect_reconcile_report(db, business_id)
        return ReconcileOut(**payload)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return DiagnosticsErrorOut(
            status="error",
            message=str(exc),
            details={"type": exc.__class__.__name__},
        )


@router.get(
    "/status/{business_id}",
    response_model=DataStatusOut,
    dependencies=[Depends(require_membership_dep())],
)
def get_data_status(business_id: str, db: Session = Depends(get_db)):
    latest_event = (
        db.execute(
            select(RawEvent.source, RawEvent.occurred_at)
            .where(RawEvent.business_id == business_id)
            .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
            .limit(1)
        )
        .first()
    )
    open_signals = int(
        db.execute(
            select(func.count())
            .select_from(HealthSignalState)
            .where(HealthSignalState.business_id == business_id, HealthSignalState.status == "open")
        ).scalar_one()
    )
    open_actions = int(
        db.execute(
            select(func.count())
            .select_from(ActionItem)
            .where(ActionItem.business_id == business_id, ActionItem.status == "open")
        ).scalar_one()
    )
    ledger_rows = int(
        db.execute(
            select(func.count())
            .select_from(RawEvent)
            .where(RawEvent.business_id == business_id)
        ).scalar_one()
    )
    uncategorized = count_uncategorized_raw_events(db, business_id)
    last_sync_at = db.execute(
        select(func.max(IntegrationConnection.last_sync_at)).where(IntegrationConnection.business_id == business_id)
    ).scalar_one()

    return DataStatusOut(
        latest_event=DataStatusLatestEventOut(
            source=latest_event[0] if latest_event else None,
            occurred_at=latest_event[1] if latest_event else None,
        ),
        open_signals=open_signals,
        open_actions=open_actions,
        ledger_rows=ledger_rows,
        uncategorized_txns=int(uncategorized),
        last_sync_at=last_sync_at,
    )
