from __future__ import annotations

from datetime import date, datetime
import logging
from typing import List, Optional, Literal, Dict, Iterable, Any

from fastapi import HTTPException
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.app.models import Business, RawEvent, TxnCategorization, Category, Account
from backend.app.norma.from_events import raw_event_to_txn

Direction = Literal["inflow", "outflow"]

logger = logging.getLogger(__name__)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _date_range_filter(occurred_at: datetime, start: Optional[date], end: Optional[date]) -> bool:
    d = occurred_at.date()
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def is_inflow(direction: str) -> bool:
    return direction == "inflow"


def signed_amount(amount: float, direction: str) -> float:
    amt = float(amount or 0.0)
    if amt < 0:
        logger.warning("Invariant guard: normalized transaction amount is negative: %s", amt)
    return amt if is_inflow(direction) else -amt


def _build_cash_series(
    txns: Iterable,
    starting_cash: float,
) -> List[Dict[str, Any]]:
    bal = float(starting_cash or 0.0)
    out: List[Dict[str, Any]] = []
    for txn in txns:
        bal += signed_amount(txn.amount or 0.0, txn.direction)
        out.append({"occurred_at": txn.occurred_at, "balance": round(bal, 2)})
    return out


def ledger_lines(
    db: Session,
    business_id: str,
    start_date: Optional[date],
    end_date: Optional[date],
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Posted ledger lines only (i.e., events with TxnCategorization).
    """
    require_business(db, business_id)

    # join: categorizations -> events -> category -> account
    stmt = (
        select(TxnCategorization, RawEvent, Category, Account)
        .join(RawEvent, and_(
            RawEvent.business_id == TxnCategorization.business_id,
            RawEvent.source_event_id == TxnCategorization.source_event_id,
        ))
        .join(Category, Category.id == TxnCategorization.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.desc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()

    out: List[Dict[str, Any]] = []
    for txncat, ev, cat, acct in rows:
        if not _date_range_filter(ev.occurred_at, start_date, end_date):
            continue

        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)

        direction: Direction = txn.direction

        out.append(
            {
                "occurred_at": ev.occurred_at,
                "source_event_id": ev.source_event_id,
                "description": txn.description,
                "direction": direction,
                "signed_amount": signed_amount(txn.amount or 0.0, direction),
                "display_amount": float(txn.amount or 0.0),
                "category_id": cat.id,
                "category_name": cat.name,
                "account_id": acct.id,
                "account_name": acct.name,
                "account_type": (acct.type or "").lower(),
                "account_subtype": (acct.subtype or None),
            }
        )

    return out


def income_statement(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    MVP income statement from posted ledger lines:
    - revenue = sum amounts where account.type == 'revenue'
    - expenses = sum absolute value of amounts where account.type == 'expense' OR acct.subtype == 'cogs'
    """
    require_business(db, business_id)

    # pull posted lines for range (we reuse same join but no limit)
    stmt = (
        select(TxnCategorization, RawEvent, Category, Account)
        .join(RawEvent, and_(
            RawEvent.business_id == TxnCategorization.business_id,
            RawEvent.source_event_id == TxnCategorization.source_event_id,
        ))
        .join(Category, Category.id == TxnCategorization.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc())
    )

    rows = db.execute(stmt).all()

    rev_by_name: Dict[str, float] = {}
    exp_by_name: Dict[str, float] = {}

    rev_total = 0.0
    exp_total = 0.0

    for _, ev, cat, acct in rows:
        if not _date_range_filter(ev.occurred_at, start_date, end_date):
            continue

        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        amt = signed_amount(txn.amount or 0.0, txn.direction)
        t = (acct.type or "").strip().lower()
        st = (acct.subtype or "").strip().lower()

        if t == "revenue":
            # revenue should be positive; if negative (refund), it reduces revenue
            rev_total += amt
            rev_by_name[cat.name] = rev_by_name.get(cat.name, 0.0) + amt
        elif t == "expense" or st == "cogs":
            # expenses we report as positive numbers; rebates reduce expense
            exp = -amt
            exp_total += exp
            exp_by_name[cat.name] = exp_by_name.get(cat.name, 0.0) + exp

    revenue_lines = [
        {"name": k, "amount": round(v, 2)} for k, v in sorted(rev_by_name.items())
    ]
    expense_lines = [
        {"name": k, "amount": round(v, 2)} for k, v in sorted(exp_by_name.items())
    ]

    net_income = rev_total - exp_total

    return {
        "start_date": start_date,
        "end_date": end_date,
        "revenue_total": round(rev_total, 2),
        "expense_total": round(exp_total, 2),
        "net_income": round(net_income, 2),
        "revenue": revenue_lines,
        "expenses": expense_lines,
    }


def cash_flow(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Direct-method cashflow MVP:
    cash_in = sum of inflow amounts across posted lines in range
    cash_out = sum of outflow amounts across posted lines in range
    """
    require_business(db, business_id)

    # reuse ledger_lines join; compute totals
    stmt = (
        select(TxnCategorization, RawEvent)
        .join(RawEvent, and_(
            RawEvent.business_id == TxnCategorization.business_id,
            RawEvent.source_event_id == TxnCategorization.source_event_id,
        ))
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc())
    )
    rows = db.execute(stmt).all()

    cash_in = 0.0
    cash_out = 0.0

    for _, ev in rows:
        if not _date_range_filter(ev.occurred_at, start_date, end_date):
            continue
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        signed = signed_amount(txn.amount or 0.0, txn.direction)
        if is_inflow(txn.direction):
            cash_in += abs(signed)
        else:
            cash_out += abs(signed)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "cash_in": round(cash_in, 2),
        "cash_out": round(cash_out, 2),
        "net_cash_flow": round(cash_in - cash_out, 2),
    }


def cash_series(
    db: Session,
    business_id: str,
    start_date: Optional[date],
    end_date: Optional[date],
    starting_cash: float,
) -> List[Dict[str, Any]]:
    """
    Running cash balance series (for signals / bollinger bands).
    MVP = cumulative sum of posted signed amounts.

    NOTE: This assumes your posted lines represent cash-impacting events.
    """
    require_business(db, business_id)

    stmt = (
        select(TxnCategorization, RawEvent)
        .join(RawEvent, and_(
            RawEvent.business_id == TxnCategorization.business_id,
            RawEvent.source_event_id == TxnCategorization.source_event_id,
        ))
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc())
    )
    rows = db.execute(stmt).all()

    txns = []

    for _, ev in rows:
        if not _date_range_filter(ev.occurred_at, start_date, end_date):
            continue
        txns.append(raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id))

    return _build_cash_series(txns, starting_cash)


def balance_sheet_v1(
    db: Session,
    business_id: str,
    as_of: date,
    starting_cash: float,
) -> Dict[str, Any]:
    """
    Balance Sheet MVP (cash-only):
      cash = starting_cash + cumulative signed amounts up to as_of (posted lines)
      assets_total = cash
      liabilities_total = 0
      equity_total = assets - liabilities
    """
    require_business(db, business_id)

    stmt = (
        select(TxnCategorization, RawEvent)
        .join(RawEvent, and_(
            RawEvent.business_id == TxnCategorization.business_id,
            RawEvent.source_event_id == TxnCategorization.source_event_id,
        ))
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc())
    )
    rows = db.execute(stmt).all()

    bal = float(starting_cash or 0.0)
    for _, ev in rows:
        if ev.occurred_at.date() <= as_of:
            txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
            bal += signed_amount(txn.amount or 0.0, txn.direction)

    assets = bal
    liabilities = 0.0
    equity = assets - liabilities

    return {
        "as_of": as_of,
        "cash": round(bal, 2),
        "assets_total": round(assets, 2),
        "liabilities_total": round(liabilities, 2),
        "equity_total": round(equity, 2),
    }
