# backend/app/api/ledger.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import ledger_service

router = APIRouter(prefix="/ledger", tags=["ledger"])

Direction = Literal["inflow", "outflow"]


# -------------------------
# Schemas
# -------------------------

class LedgerLineOut(BaseModel):
    occurred_at: datetime
    source_event_id: str
    description: str
    direction: Direction

    signed_amount: float
    display_amount: float

    category_id: str
    category_name: str

    account_id: str
    account_name: str
    account_type: str
    account_subtype: Optional[str] = None


class IncomeStatementLine(BaseModel):
    name: str
    amount: float


class IncomeStatementOut(BaseModel):
    start_date: date
    end_date: date
    revenue_total: float
    expense_total: float
    net_income: float
    revenue: List[IncomeStatementLine]
    expenses: List[IncomeStatementLine]


class CashFlowOut(BaseModel):
    start_date: date
    end_date: date
    cash_in: float
    cash_out: float
    net_cash_flow: float


class BalanceSheetV1Out(BaseModel):
    as_of: date
    cash: float
    assets_total: float
    liabilities_total: float
    equity_total: float


class CashPointOut(BaseModel):
    occurred_at: datetime
    balance: float


class LedgerTraceTxnOut(BaseModel):
    occurred_at: datetime
    source_event_id: str
    description: str
    direction: Direction
    signed_amount: float
    display_amount: float
    category_name: Optional[str] = None
    account_name: Optional[str] = None
    counterparty_hint: Optional[str] = None


# -------------------------
# Endpoints
# -------------------------

@router.get("/business/{business_id}/lines", response_model=List[LedgerLineOut])
def ledger_lines(
    business_id: str,
    start_date: date = Query(..., description="Inclusive start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Inclusive end date (YYYY-MM-DD)"),
    limit: int = Query(2000, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    # NOTE: limit defaults to 2000 for UI convenience.
    return ledger_service.ledger_lines(db, business_id, start_date, end_date, limit)


@router.get("/business/{business_id}/transactions", response_model=List[LedgerTraceTxnOut])
def ledger_transactions(
    business_id: str,
    txn_ids: Optional[str] = Query(None, description="Comma-separated source_event_ids"),
    date_start: Optional[date] = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    date_end: Optional[date] = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    ids_list = [item.strip() for item in txn_ids.split(",")] if txn_ids else None
    ids_list = [item for item in ids_list or [] if item]
    return ledger_service.ledger_trace_transactions(
        db,
        business_id,
        txn_ids=ids_list or None,
        start_date=date_start,
        end_date=date_end,
        limit=limit,
    )


@router.get("/business/{business_id}/income_statement", response_model=IncomeStatementOut)
def income_statement(
    business_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    return ledger_service.income_statement(db, business_id, start_date, end_date)


@router.get("/business/{business_id}/cash_flow", response_model=CashFlowOut)
def cash_flow(
    business_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    return ledger_service.cash_flow(db, business_id, start_date, end_date)


@router.get("/business/{business_id}/cash_series", response_model=List[CashPointOut])
def cash_series(
    business_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    starting_cash: float = Query(0.0),
    db: Session = Depends(get_db),
):
    return ledger_service.cash_series(db, business_id, start_date, end_date, starting_cash)


@router.get("/business/{business_id}/balance_sheet_v1", response_model=BalanceSheetV1Out)
def balance_sheet_v1(
    business_id: str,
    as_of: date = Query(...),
    starting_cash: float = Query(0.0),
    db: Session = Depends(get_db),
):
    return ledger_service.balance_sheet_v1(db, business_id, as_of, starting_cash)
