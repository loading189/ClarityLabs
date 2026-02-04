from __future__ import annotations

from dataclasses import asdict
from datetime import date
import logging
import os
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models import Account, Business, Category, RawEvent, TxnCategorization
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.ledger import LedgerIntegrityError, build_cash_ledger
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.signals.core import generate_core_signals


logger = logging.getLogger(__name__)


def _is_dev_env() -> bool:
    return (
        os.getenv("ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("APP_ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("NODE_ENV", "").lower() in {"dev", "development"}
    )


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _date_range_filter(occurred_at: date, start: date, end: date) -> bool:
    return start <= occurred_at <= end


def _fetch_posted_transactions(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> List[NormalizedTransaction]:
    stmt = (
        select(TxnCategorization, RawEvent, Category, Account)
        .join(
            RawEvent,
            and_(
                RawEvent.business_id == TxnCategorization.business_id,
                RawEvent.source_event_id == TxnCategorization.source_event_id,
            ),
        )
        .join(Category, Category.id == TxnCategorization.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc(), RawEvent.source_event_id.asc())
    )

    rows = db.execute(stmt).all()
    txns: List[NormalizedTransaction] = []
    for _, ev, cat, acct in rows:
        if not _date_range_filter(ev.occurred_at.date(), start_date, end_date):
            continue
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        txns.append(
            NormalizedTransaction(
                id=txn.id,
                source_event_id=txn.source_event_id,
                occurred_at=txn.occurred_at,
                date=txn.date,
                description=txn.description,
                amount=txn.amount,
                direction=txn.direction,
                account=acct.name,
                category=(cat.name or cat.system_key or "uncategorized"),
                counterparty_hint=txn.counterparty_hint,
            )
        )

    return txns


def fetch_signals(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: {start_date} → {end_date}",
        )

    _require_business(db, business_id)

    txns = _fetch_posted_transactions(db, business_id, start_date, end_date)
    if not txns:
        return [], {
            "reason": "not_enough_data",
            "detail": "No posted transactions in the selected date range.",
        }

    try:
        ledger = build_cash_ledger(txns, opening_balance=0.0)
        signals = generate_core_signals(txns, ledger)
    except LedgerIntegrityError as exc:
        if _is_dev_env():
            logger.warning(
                "[signals] ledger integrity failed business=%s error=%s",
                business_id,
                str(exc),
            )
        return [], {
            "reason": "integrity_error",
            "detail": str(exc),
        }

    return [asdict(signal) for signal in signals], {"count": len(signals)}


def available_signal_types() -> List[Dict[str, Any]]:
    return [
        {
            "type": "cash_runway_trend",
            "window_days": 30,
            "required_inputs": ["transactions", "ledger", "outflow", "cash_balance"],
        },
        {
            "type": "expense_creep",
            "window_days": 30,
            "required_inputs": ["transactions", "outflow", "category"],
        },
        {
            "type": "revenue_volatility",
            "window_days": 60,
            "required_inputs": ["transactions", "weekly_inflows"],
        },
    ]
