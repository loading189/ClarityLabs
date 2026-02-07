from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.clarity.brief import build_brief
from backend.app.clarity.signals import compute_signals
from backend.app.db import get_db
from backend.app.models import Business, RawEvent
from backend.app.norma.facts import compute_facts
from backend.app.norma.ledger import build_cash_ledger
from backend.app.services.posted_txn_service import posted_txns

router = APIRouter(prefix="/brief", tags=["brief"])


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _load_event_txn_pairs_from_db(
    db: Session,
    biz_db_id: str,
    limit_events: int = 2000,
    chronological: bool = True,
) -> Tuple[List[Tuple[RawEvent, Any]], Optional[datetime]]:
    items = posted_txns(db, biz_db_id, limit=limit_events)
    pairs: List[Tuple[RawEvent, Any]] = []
    iterable = reversed(items) if chronological else items

    for item in iterable:
        pairs.append((item.raw_event, item.txn))

    last_event_occurred_at = items[-1].raw_event.occurred_at if items else None
    return pairs, last_event_occurred_at


@router.get("/business/{business_id}")
def brief_by_business(
    business_id: str,
    window_days: int = Query(30, ge=30, le=30),
    db: Session = Depends(get_db),
):
    biz = _require_business(db, business_id)

    pairs, _last = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=2000,
        chronological=True,
    )
    txns = [t for _e, t in pairs]

    ledger = build_cash_ledger(txns, opening_balance=0.0)
    facts_obj = compute_facts(txns, ledger)
    signals = compute_signals(facts_obj)

    return build_brief(business_id=str(biz.id), facts=facts_obj, signals=signals)
