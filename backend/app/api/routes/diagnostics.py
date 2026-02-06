from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import diagnostics_service

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


@router.get("/{business_id}", response_model=Union[DiagnosticsOut, DiagnosticsErrorOut])
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


@router.get("/ingestion/{business_id}", response_model=Union[IngestionDiagnosticsOut, DiagnosticsErrorOut])
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
