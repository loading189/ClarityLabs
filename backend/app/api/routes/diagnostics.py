from __future__ import annotations

from typing import Any, Dict, List, Optional

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


@router.get("/{business_id}", response_model=DiagnosticsOut)
def get_diagnostics(business_id: str, db: Session = Depends(get_db)):
    payload = diagnostics_service.collect_diagnostics(db, business_id)
    return DiagnosticsOut(**payload)
