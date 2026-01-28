"""
Demo API router (DB-backed).

Responsibility
- Provide stable demo endpoints for the frontend:
  - /dashboard cards
  - /health/{business_id} full detail (facts + signals + score + ledger preview)
  - /transactions/{business_id} (with drilldown filters)
  - /analytics/monthly-trends/{business_id}

Design notes
- Keep the pipeline deterministic:
    events -> txns -> ledger -> facts -> signals -> score
- Avoid identity bugs:
  - ALWAYS use RawEvent.source_event_id as source_event_id
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.analytics.monthly_trends import build_monthly_trends_payload
from backend.app.clarity.scoring import compute_business_score
from backend.app.clarity.signals import compute_signals
from backend.app.db import get_db
from backend.app.models import Business, RawEvent
from backend.app.norma.facts import compute_facts, facts_to_dict
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.ledger import build_cash_ledger

router = APIRouter(prefix="/demo", tags=["demo"])


# ----------------------------
# Small utilities
# ----------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _parse_id_set(source_event_ids: Optional[str]) -> Optional[set[str]]:
    """
    source_event_ids are RawEvent.source_event_id values (vendor/dedupe key),
    comma-separated.
    """
    if not source_event_ids:
        return None
    s = {x.strip() for x in source_event_ids.split(",") if x.strip()}
    return s or None


# ---------------------------------------
# DB helpers: events → txns → health
# ---------------------------------------

def _load_event_txn_pairs_from_db(
    db: Session,
    biz_db_id: str,  # Business.id (UUID string)
    limit_events: int = 2000,
    chronological: bool = True,
) -> Tuple[List[Tuple[RawEvent, Any]], Optional[datetime]]:
    """
    Returns [(RawEvent, NormalizedTransaction), ...] and newest occurred_at (if any).

    IMPORTANT:
    - The NormalizedTransaction.source_event_id MUST be RawEvent.source_event_id
      so it lines up with TxnCategorization joins.
    """
    events = (
        db.execute(
            select(RawEvent)
            .where(RawEvent.business_id == biz_db_id)
            .order_by(RawEvent.occurred_at.desc())
            .limit(limit_events)
        )
        .scalars()
        .all()
    )

    pairs: List[Tuple[RawEvent, Any]] = []
    iterable = reversed(events) if chronological else events

    for e in iterable:
        try:
            txn = raw_event_to_txn(
                e.payload,
                e.occurred_at,
                source_event_id=e.source_event_id,  # ✅ stable vendor/dedupe key
            )
            pairs.append((e, txn))
        except Exception:
            # keep current behavior: skip normalization failures
            continue

    last_event_occurred_at = events[0].occurred_at if events else None
    return pairs, last_event_occurred_at


def _compute_health_from_txns(txns: List[Any]):
    """
    Deterministic pipeline: txns -> ledger -> facts -> signals -> score.
    """
    ledger = build_cash_ledger(txns, opening_balance=0.0)

    facts_obj = compute_facts(txns, ledger)
    facts_json = facts_to_dict(facts_obj)

    scoring_input = {
        "current_cash": facts_json["current_cash"],
        "monthly_inflow_outflow": facts_json["monthly_inflow_outflow"],
        "totals_by_category": facts_json["totals_by_category"],
    }

    signals = compute_signals(facts_obj)               # List[Signal dataclass]
    signals_dicts = [asdict(s) for s in signals]       # score expects dict-ish inputs
    breakdown = compute_business_score(scoring_input, signals_dicts)

    return facts_obj, facts_json, scoring_input, signals, signals_dicts, breakdown


def _attach_signal_refs(signals_dicts: List[dict], pairs: List[Tuple[RawEvent, Any]]) -> List[dict]:
    """
    Attach evidence_refs for drilldowns (MVP).

    Current:
    - top_spend_drivers: attach top outflow events by absolute amount

    evidence_refs use source_event_id = RawEvent.source_event_id (stable join key).
    """
    spend_pairs = [(e, t) for (e, t) in pairs if float(getattr(t, "amount", 0.0)) < 0]
    spend_pairs.sort(key=lambda et: abs(float(et[1].amount)), reverse=True)
    top_spend_source_ids = [e.source_event_id for (e, _t) in spend_pairs[:12]]

    out: List[dict] = []
    for d in signals_dicts:
        if d.get("key") == "top_spend_drivers" and top_spend_source_ids:
            d = {**d}
            d["evidence_refs"] = [{"kind": "txn", "source_event_id": sid} for sid in top_spend_source_ids]
        out.append(d)
    return out


# ----------------------------
# Endpoints
# ----------------------------

@router.get("/health")
def health():
    return {"status": "ok", "time": _now_iso()}

@router.get("/analytics/monthly-trends/{business_id}")
def demo_monthly_trends_by_business(
    business_id: str,
    lookback_months: int = Query(12, ge=3, le=36),
    k: float = Query(2.0, ge=0.5, le=5.0),
    db: Session = Depends(get_db),
):
    biz = _require_business(db, business_id)

    pairs, _last = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=4000,
        chronological=True,
    )
    txns = [t for _e, t in pairs]

    # compute facts_json
    _facts_obj, facts_json, _scoring_input, _signals, _signals_dicts, _breakdown = _compute_health_from_txns(txns)

    # build full ledger rows for cash_end
    ledger = build_cash_ledger(txns, opening_balance=0.0)
    ledger_rows = [
        {
            "occurred_at": r.occurred_at.isoformat(),
            "balance": float(r.balance),
            "source_event_id": r.source_event_id,
        }
        for r in ledger
    ]

    payload = build_monthly_trends_payload(
        facts_json=facts_json,
        lookback_months=lookback_months,
        k=k,
        ledger_rows=ledger_rows,
    )

    return {
        "business_id": str(biz.id),
        "name": biz.name,
        **payload,
    }



@router.get("/dashboard")
def demo_dashboard(db: Session = Depends(get_db)):
    """
    DB-backed list of businesses (each card computed from raw_events).
    """
    biz_rows = db.execute(select(Business).order_by(Business.created_at.desc())).scalars().all()

    cards = []
    for biz in biz_rows:
        pairs, _last = _load_event_txn_pairs_from_db(
            db=db,
            biz_db_id=biz.id,
            limit_events=1000,
            chronological=True,
        )
        txns = [t for _e, t in pairs]
        _facts_obj, _facts_json, _scoring_input, signals, _signals_dicts, breakdown = _compute_health_from_txns(txns)

        cards.append(
            {
                "business_id": str(biz.id),
                "name": biz.name,
                "risk": breakdown.risk,
                "health_score": breakdown.overall,
                "highlights": [s.title for s in signals[:3]],
            }
        )

    return {"cards": cards}


@router.get("/health/{business_id}")
def demo_health_by_business(business_id: str, db: Session = Depends(get_db)):
    biz = _require_business(db, business_id)

    pairs, last_event_occurred_at = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=2000,
        chronological=True,
    )
    txns = [t for _e, t in pairs]

    _facts_obj, facts_json, scoring_input, signals, signals_dicts, breakdown = _compute_health_from_txns(txns)
    sig_out = _attach_signal_refs(signals_dicts, pairs)

    return {
        "business_id": str(biz.id),
        "name": biz.name,
        "as_of": _now_iso(),
        "last_event_occurred_at": None if not last_event_occurred_at else last_event_occurred_at.isoformat(),
        "risk": breakdown.risk,
        "health_score": breakdown.overall,
        "score_breakdown": {
            "liquidity": breakdown.liquidity,
            "stability": breakdown.stability,
            "discipline": breakdown.discipline,
        },
        "highlights": [s.title for s in signals[:3]],
        "signals": sig_out,
        "facts": scoring_input,
        "facts_full": facts_json,  # ✅ fixed
        "ledger_preview": facts_json.get("last_10_ledger_rows", []),
    }

@router.get("/transactions/{business_id}")
def demo_transactions_by_business(
    business_id: str,
    limit: int = Query(50, ge=1, le=200),
    source_event_ids: Optional[str] = Query(None, description="Comma-separated RawEvent.source_event_id values"),
    category: Optional[str] = Query(None),
    direction: Optional[str] = Query(None, pattern="^(inflow|outflow)$"),
    db: Session = Depends(get_db),
):
    """
    Recent normalized transactions derived from raw_events.
    Returns newest-first with provenance.

    Filters:
      - source_event_ids=<vendor_dedupe_key_1>,<vendor_dedupe_key_2>
      - category=<normalized_category>
      - direction=inflow|outflow
    """
    biz = _require_business(db, business_id)

    scan = max(2000, limit * 50)
    pairs, last_event_occurred_at = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=scan,
        chronological=True,
    )

    newest_first = list(reversed(pairs))
    id_set = _parse_id_set(source_event_ids)

    items: List[dict] = []
    for e, t in newest_first:
        if id_set and e.source_event_id not in id_set:
            continue
        if category and t.category != category:
            continue
        if direction and t.direction != direction:
            continue

        items.append(
            {
                "id": f"txn_{e.id}",                   # DB row id (internal)
                "source_event_id": e.source_event_id,  # ✅ stable public id
                "occurred_at": e.occurred_at.isoformat(),
                "date": t.date.isoformat(),
                "description": t.description,
                "amount": t.amount,
                "direction": t.direction,
                "account": t.account,
                "category": t.category,
                "counterparty_hint": t.counterparty_hint,
            }
        )

        if len(items) >= limit:
            break

    return {
        "business_id": str(biz.id),
        "name": biz.name,
        "as_of": _now_iso(),
        "last_event_occurred_at": None if not last_event_occurred_at else last_event_occurred_at.isoformat(),
        "count": len(items),
        "transactions": items,
    }
