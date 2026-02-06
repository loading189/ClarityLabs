from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import List, Optional, Sequence

from sqlalchemy import and_, select, func
from sqlalchemy.orm import Session

from backend.app.models import Account, Category, RawEvent, TxnCategorization
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.normalize import NormalizedTransaction


@dataclass(frozen=True)
class PostedTransactionDetail:
    txn: NormalizedTransaction
    category_id: str
    category_name: str
    account_id: str
    account_name: str
    account_type: str
    account_subtype: Optional[str]


def _date_to_bounds(start_date: Optional[date], end_date: Optional[date]) -> tuple[Optional[datetime], Optional[datetime]]:
    start_dt = None
    end_dt = None
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def _posted_txn_stmt(
    business_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    source_event_ids: Optional[Sequence[str]] = None,
    order_desc: bool = False,
    limit: Optional[int] = None,
):
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
    )

    if source_event_ids:
        stmt = stmt.where(RawEvent.source_event_id.in_(source_event_ids))

    start_dt, end_dt = _date_to_bounds(start_date, end_date)
    if start_dt is not None:
        stmt = stmt.where(RawEvent.occurred_at >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(RawEvent.occurred_at <= end_dt)

    if order_desc:
        stmt = stmt.order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
    else:
        stmt = stmt.order_by(RawEvent.occurred_at.asc(), RawEvent.source_event_id.asc())

    if limit:
        stmt = stmt.limit(limit)

    return stmt


def fetch_posted_transaction_rows(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    source_event_ids: Optional[Sequence[str]] = None,
    order_desc: bool = False,
    limit: Optional[int] = None,
):
    stmt = _posted_txn_stmt(
        business_id,
        start_date=start_date,
        end_date=end_date,
        source_event_ids=source_event_ids,
        order_desc=order_desc,
        limit=limit,
    )
    return db.execute(stmt).all()


def fetch_posted_transactions(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[NormalizedTransaction]:
    rows = fetch_posted_transaction_rows(
        db,
        business_id,
        start_date=start_date,
        end_date=end_date,
    )
    txns: List[NormalizedTransaction] = []
    for _, ev, cat, acct in rows:
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
                account=(acct.name or "").strip() or "Unknown",
                category=(cat.name or cat.system_key or "uncategorized"),
                counterparty_hint=txn.counterparty_hint,
            )
        )
    return txns


def fetch_posted_transaction_details(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    source_event_ids: Optional[Sequence[str]] = None,
    order_desc: bool = False,
    limit: Optional[int] = None,
) -> List[PostedTransactionDetail]:
    rows = fetch_posted_transaction_rows(
        db,
        business_id,
        start_date=start_date,
        end_date=end_date,
        source_event_ids=source_event_ids,
        order_desc=order_desc,
        limit=limit,
    )
    details: List[PostedTransactionDetail] = []
    for _, ev, cat, acct in rows:
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        details.append(
            PostedTransactionDetail(
                txn=NormalizedTransaction(
                    id=txn.id,
                    source_event_id=txn.source_event_id,
                    occurred_at=txn.occurred_at,
                    date=txn.date,
                    description=txn.description,
                    amount=txn.amount,
                    direction=txn.direction,
                    account=(acct.name or "").strip() or "Unknown",
                    category=(cat.name or cat.system_key or "uncategorized"),
                    counterparty_hint=txn.counterparty_hint,
                ),
                category_id=cat.id,
                category_name=cat.name,
                account_id=acct.id,
                account_name=acct.name,
                account_type=(acct.type or "").lower(),
                account_subtype=(acct.subtype or None),
            )
        )
    return details


def fetch_uncategorized_raw_events(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: Optional[int] = None,
):
    start_dt, end_dt = _date_to_bounds(start_date, end_date)
    stmt = (
        select(RawEvent)
        .outerjoin(
            TxnCategorization,
            and_(
                RawEvent.business_id == TxnCategorization.business_id,
                RawEvent.source_event_id == TxnCategorization.source_event_id,
            ),
        )
        .where(
            RawEvent.business_id == business_id,
            TxnCategorization.id.is_(None),
        )
    )
    if start_dt is not None:
        stmt = stmt.where(RawEvent.occurred_at >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(RawEvent.occurred_at <= end_dt)
    stmt = stmt.order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
    if limit:
        stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()


def count_uncategorized_raw_events(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> int:
    start_dt, end_dt = _date_to_bounds(start_date, end_date)
    stmt = (
        select(func.count())
        .select_from(RawEvent)
        .outerjoin(
            TxnCategorization,
            and_(
                RawEvent.business_id == TxnCategorization.business_id,
                RawEvent.source_event_id == TxnCategorization.source_event_id,
            ),
        )
        .where(
            RawEvent.business_id == business_id,
            TxnCategorization.id.is_(None),
        )
    )
    if start_dt is not None:
        stmt = stmt.where(RawEvent.occurred_at >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(RawEvent.occurred_at <= end_dt)
    return int(db.execute(stmt).scalar_one())
