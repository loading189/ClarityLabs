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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.analytics.monthly_trends import build_monthly_trends_payload
from backend.app.clarity.scoring import compute_business_score
from backend.app.clarity.signals import compute_signals
from backend.app.db import get_db
from backend.app.models import Business, CategoryRule, RawEvent, TxnCategorization
from backend.app.norma.category_engine import suggest_category
from backend.app.norma.facts import compute_facts, facts_to_dict
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.services import analytics_service
from backend.app.norma.ledger import build_cash_ledger
from backend.app.norma.merchant import merchant_key
from backend.app.norma.categorize_brain import brain
from backend.app.services import categorize_service, demo_seed_service, health_signal_service, signals_service
from backend.app.clarity.health_v1 import build_health_v1_signals

router = APIRouter(prefix="/demo", tags=["demo"])


class HealthSignalStatusIn(BaseModel):
    status: str = Field(..., min_length=2, max_length=32)
    reason: Optional[str] = Field(default=None, max_length=500)
    actor: Optional[str] = Field(default=None, max_length=40)


class DashboardMetadataOut(BaseModel):
    business_id: str
    name: str
    as_of: str
    last_event_occurred_at: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None


class DashboardKpisOut(BaseModel):
    current_cash: Dict[str, Any]
    last_30d_inflow: Dict[str, Any]
    last_30d_outflow: Dict[str, Any]
    last_30d_net: Dict[str, Any]
    prev_30d_inflow: Dict[str, Any]
    prev_30d_outflow: Dict[str, Any]
    prev_30d_net: Dict[str, Any]


class DashboardSignalDrilldownOut(BaseModel):
    kind: Literal["category", "vendor"]
    value: str
    window_days: int = Field(default=30, ge=1, le=365)
    label: Optional[str] = None


class DashboardSignalOut(BaseModel):
    key: str
    title: str
    severity: str
    dimension: str
    priority: int
    value: Optional[Any] = None
    message: str
    drilldown: Optional[DashboardSignalDrilldownOut] = None


class DashboardTrendsOut(BaseModel):
    experiment: Dict[str, Any]
    metrics: Dict[str, Any]
    cash: Dict[str, Any]
    series: List[Dict[str, Any]]
    band: Optional[Dict[str, Any]] = None
    status: str
    current: Optional[Dict[str, Any]] = None


class AnalyticsPayloadOut(BaseModel):
    computation_version: str
    kpis: Dict[str, Any]
    series: List[Dict[str, Any]]
    category_breakdown: List[Dict[str, Any]]
    vendor_concentration: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    change_explanations: Dict[str, Any]


class DashboardPayloadOut(BaseModel):
    metadata: DashboardMetadataOut
    kpis: DashboardKpisOut
    signals: List[DashboardSignalOut]
    trends: DashboardTrendsOut
    analytics: AnalyticsPayloadOut


class DrilldownRowOut(BaseModel):
    source_event_id: str
    occurred_at: str
    date: str
    description: str
    amount: float
    direction: str
    account: str
    category: str
    counterparty_hint: Optional[str] = None
    merchant_key: str


class DrilldownResponseOut(BaseModel):
    business_id: str
    name: str
    window_days: int
    limit: int
    offset: int
    total: int
    rows: List[DrilldownRowOut]


class DemoSeedOut(BaseModel):
    organization_id: str
    business_id: str
    seeded: bool
    window: Dict[str, str]
    stats: Dict[str, int]
    monitoring: Optional[Dict[str, Any]] = None


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


@router.post("/seed", response_model=DemoSeedOut)
def seed_demo(db: Session = Depends(get_db)):
    """
    Dev-only deterministic seed for the full golden-path workflow:
    raw events -> categorization -> ledger -> monitoring -> evidence -> audit.
    """
    return demo_seed_service.seed_demo(db)


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

    return facts_obj, facts_json, scoring_input, signals, signals_dicts, breakdown, ledger


def _resolve_demo_date_range(txns: List[Any], ledger: List[Any]) -> Tuple[Optional[str], Optional[str]]:
    dates: List[Any] = []
    for row in ledger or []:
        row_date = getattr(row, "date", None)
        if row_date:
            dates.append(row_date)
    if not dates:
        for txn in txns:
            txn_date = getattr(txn, "date", None)
            if txn_date:
                dates.append(txn_date)
    if not dates:
        return None, None
    start_at = min(dates)
    end_at = max(dates)
    return start_at.isoformat(), end_at.isoformat()


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


def _build_fix_suggestions(txns: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for txn in txns:
        merchant_key_value = txn.get("merchant_key")
        category_id = txn.get("suggested_category_id")
        category_name = txn.get("suggested_category_name")
        if not merchant_key_value or not category_id or not category_name:
            continue

        key = (merchant_key_value, category_id)
        if key not in grouped:
            grouped[key] = {
                "merchant_key": merchant_key_value,
                "suggested_category_id": category_id,
                "suggested_category_name": category_name,
                "contains_text": (txn.get("description") or merchant_key_value).lower(),
                "direction": txn.get("direction"),
                "account": txn.get("account"),
                "sample_description": txn.get("description"),
                "sample_source_event_id": txn.get("source_event_id"),
                "sample_amount": float(txn.get("amount")) if txn.get("amount") is not None else None,
                "sample_occurred_at": txn.get("occurred_at").isoformat()
                if getattr(txn.get("occurred_at"), "isoformat", None)
                else txn.get("occurred_at"),
                "count": 0,
                "total_abs_amount": 0.0,
            }

        grouped[key]["count"] += 1
        amt = txn.get("amount")
        if amt is not None:
            grouped[key]["total_abs_amount"] += abs(float(amt))

    suggestions = sorted(
        grouped.values(),
        key=lambda item: (item.get("count", 0), item.get("total_abs_amount", 0.0)),
        reverse=True,
    )
    return suggestions[:limit]


def _build_uncategorized_examples(txns: List[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
    sorted_txns = sorted(
        txns,
        key=lambda item: abs(float(item.get("amount") or 0.0)),
        reverse=True,
    )
    examples: List[Dict[str, Any]] = []
    for txn in sorted_txns[:limit]:
        occurred_at = txn.get("occurred_at")
        examples.append(
            {
                "source_event_id": txn.get("source_event_id"),
                "occurred_at": occurred_at.isoformat() if getattr(occurred_at, "isoformat", None) else occurred_at,
                "date": occurred_at.date().isoformat()
                if getattr(occurred_at, "date", None)
                else None,
                "description": txn.get("description"),
                "amount": float(txn.get("amount")) if txn.get("amount") is not None else None,
                "direction": txn.get("direction"),
                "account": txn.get("account"),
                "merchant_key": txn.get("merchant_key"),
                "suggested_category_id": txn.get("suggested_category_id"),
                "suggested_category_name": txn.get("suggested_category_name"),
            }
        )
    return examples


def _dashboard_kpis(analytics_payload: Dict[str, Any]) -> DashboardKpisOut:
    kpis = analytics_payload.get("kpis") or {}
    return DashboardKpisOut(**kpis)


def _primary_spend_category(facts_json: Dict[str, Any]) -> Optional[str]:
    totals = facts_json.get("totals_by_category") or []
    for row in totals:
        try:
            total = float(row.get("total") or 0.0)
        except Exception:
            continue
        if total < 0:
            return str(row.get("category") or "uncategorized")
    return None


def _build_dashboard_signals(signals: List[Any], facts_json: Dict[str, Any]) -> List[DashboardSignalOut]:
    primary_spend_category = _primary_spend_category(facts_json)
    out: List[DashboardSignalOut] = []
    for s in sorted(signals, key=lambda item: (-int(item.priority), str(item.key))):
        drilldown: Optional[DashboardSignalDrilldownOut] = None
        if s.key == "top_spend_drivers" and primary_spend_category:
            drilldown = DashboardSignalDrilldownOut(
                kind="category",
                value=primary_spend_category,
                window_days=30,
                label=f"Category: {primary_spend_category}",
            )
        out.append(
            DashboardSignalOut(
                key=s.key,
                title=s.title,
                severity=s.severity,
                dimension=s.dimension,
                priority=int(s.priority),
                value=s.value,
                message=s.message,
                drilldown=drilldown,
            )
        )
    return out


def _filter_pairs_for_window(
    pairs: List[Tuple[RawEvent, Any]],
    window_days: int,
) -> List[Tuple[RawEvent, Any]]:
    if not pairs:
        return []
    anchor = max(e.occurred_at for e, _t in pairs)
    start = anchor - timedelta(days=window_days - 1)
    return [(e, t) for e, t in pairs if start <= e.occurred_at <= anchor]


def _sort_pairs_deterministic(pairs: List[Tuple[RawEvent, Any]]) -> List[Tuple[RawEvent, Any]]:
    return sorted(pairs, key=lambda pair: (pair[0].occurred_at, pair[0].source_event_id))


def _build_drilldown_rows(pairs: List[Tuple[RawEvent, Any]]) -> List[DrilldownRowOut]:
    rows: List[DrilldownRowOut] = []
    for e, t in pairs:
        rows.append(
            DrilldownRowOut(
                source_event_id=e.source_event_id,
                occurred_at=e.occurred_at.isoformat(),
                date=t.date.isoformat(),
                description=t.description,
                amount=float(t.amount),
                direction=t.direction,
                account=t.account,
                category=t.category,
                counterparty_hint=t.counterparty_hint,
                merchant_key=merchant_key(t.description),
            )
        )
    return rows


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

    _facts_obj, facts_json, _scoring_input, _signals, _signals_dicts, _breakdown, ledger = _compute_health_from_txns(txns)
    start_at, end_at = _resolve_demo_date_range(txns, ledger)
    analytics_payload = analytics_service.build_trends_analytics(
        txns,
        start_at=start_at,
        end_at=end_at,
        lookback_months=lookback_months,
    )

    payload = build_monthly_trends_payload(
        facts_json=facts_json,
        lookback_months=lookback_months,
        k=k,
        ledger_rows=[
            {
                "occurred_at": r.occurred_at.isoformat(),
                "date": r.date.isoformat(),
                "amount": float(r.amount),
                "balance": float(r.balance),
                "source_event_id": r.source_event_id,
            }
            for r in ledger
        ],
    )

    return {
        "business_id": str(biz.id),
        "name": biz.name,
        **payload,
        "analytics": analytics_payload,
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
        _facts_obj, _facts_json, _scoring_input, signals, _signals_dicts, breakdown, _ledger = _compute_health_from_txns(txns)

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


@router.get("/dashboard/{business_id}", response_model=DashboardPayloadOut)
def demo_dashboard_by_business(
    business_id: str,
    lookback_months: int = Query(12, ge=3, le=36),
    k: float = Query(2.0, ge=0.5, le=5.0),
    db: Session = Depends(get_db),
):
    biz = _require_business(db, business_id)
    pairs, last_event_occurred_at = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=4000,
        chronological=True,
    )
    txns = [t for _e, t in pairs]

    _facts_obj, facts_json, _scoring_input, signals, _signals_dicts, _breakdown, ledger = _compute_health_from_txns(txns)
    start_at, end_at = _resolve_demo_date_range(txns, ledger)
    ledger_rows = [
        {
            "occurred_at": r.occurred_at.isoformat(),
            "date": r.date.isoformat(),
            "amount": float(r.amount),
            "balance": float(r.balance),
            "source_event_id": r.source_event_id,
        }
        for r in ledger
    ]

    trends_payload = build_monthly_trends_payload(
        facts_json=facts_json,
        lookback_months=lookback_months,
        k=k,
        ledger_rows=ledger_rows,
    )
    analytics_payload = analytics_service.build_dashboard_analytics(
        txns,
        start_at=start_at,
        end_at=end_at,
        lookback_months=lookback_months,
    )

    return DashboardPayloadOut(
        metadata=DashboardMetadataOut(
            business_id=str(biz.id),
            name=biz.name,
            as_of=_now_iso(),
            last_event_occurred_at=None
            if not last_event_occurred_at
            else last_event_occurred_at.isoformat(),
            start_at=start_at,
            end_at=end_at,
        ),
        kpis=_dashboard_kpis(analytics_payload),
        signals=_build_dashboard_signals(signals, facts_json),
        trends=DashboardTrendsOut(**trends_payload),
        analytics=AnalyticsPayloadOut(**analytics_payload),
    )


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

    _facts_obj, facts_json, scoring_input, signals, signals_dicts, breakdown, ledger = _compute_health_from_txns(txns)
    start_at, end_at = _resolve_demo_date_range(txns, ledger)
    sig_out = _attach_signal_refs(signals_dicts, pairs)

    ledger_rows = [
        {
            "occurred_at": r.occurred_at.isoformat(),
            "date": r.date.isoformat(),
            "amount": float(r.amount),
            "balance": float(r.balance),
            "source_event_id": r.source_event_id,
        }
        for r in ledger
    ]

    categorization_metrics = categorize_service.categorization_metrics(db, biz.id)
    uncategorized_txns = categorize_service.list_txns_to_categorize(db, biz.id, limit=120, only_uncategorized=True)
    fix_suggestions = _build_fix_suggestions(uncategorized_txns, limit=4)
    fix_examples = _build_uncategorized_examples(uncategorized_txns, limit=4)
    rule_count = db.execute(
        select(func.count()).select_from(CategoryRule).where(CategoryRule.business_id == biz.id)
    ).scalar_one()

    def _is_known_vendor(key: str) -> bool:
        return brain.lookup_label(business_id=biz.id, alias_key=key) is not None

    health_signals: List[dict] = []
    if signals_service.v1_signals_enabled():
        health_signals = build_health_v1_signals(
            facts_json=facts_json,
            ledger_rows=ledger_rows,
            txns=txns,
            updated_at=None if not last_event_occurred_at else last_event_occurred_at.isoformat(),
            categorization_metrics=categorization_metrics,
            rule_count=int(rule_count or 0),
            is_known_vendor=_is_known_vendor,
        )
        for signal in health_signals:
            if signal.get("id") in {"high_uncategorized_rate", "rule_coverage_low", "new_unknown_vendors"}:
                signal["fix_suggestions"] = fix_suggestions
                if fix_examples:
                    signal.setdefault("evidence", []).append(
                        {
                            "date_range": {"start": "", "end": "", "label": "Top uncategorized merchants"},
                            "metrics": {},
                            "examples": fix_examples,
                        }
                    )

        health_signals = health_signal_service.hydrate_signal_states(db, biz.id, health_signals)

    return {
        "business_id": str(biz.id),
        "name": biz.name,
        "as_of": _now_iso(),
        "last_event_occurred_at": None if not last_event_occurred_at else last_event_occurred_at.isoformat(),
        "start_at": start_at,
        "end_at": end_at,
        "risk": breakdown.risk,
        "health_score": breakdown.overall,
        "score_breakdown": {
            "liquidity": breakdown.liquidity,
            "stability": breakdown.stability,
            "discipline": breakdown.discipline,
        },
        "highlights": [s.title for s in signals[:3]],
        "signals": sig_out,
        "health_signals": health_signals,
        "facts": scoring_input,
        "facts_full": facts_json,  # ✅ fixed
        "ledger_preview": facts_json.get("last_10_ledger_rows", []),
    }


@router.get("/drilldown/category", response_model=DrilldownResponseOut)
def demo_drilldown_category(
    business_id: str,
    category: str,
    window_days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    biz = _require_business(db, business_id)
    pairs, _last = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=4000,
        chronological=True,
    )
    window_pairs = _filter_pairs_for_window(pairs, window_days)
    filtered = [(e, t) for e, t in window_pairs if t.category == category]
    sorted_pairs = _sort_pairs_deterministic(filtered)
    total = len(sorted_pairs)
    paged = sorted_pairs[offset : offset + limit]
    return DrilldownResponseOut(
        business_id=str(biz.id),
        name=biz.name,
        window_days=window_days,
        limit=limit,
        offset=offset,
        total=total,
        rows=_build_drilldown_rows(paged),
    )


@router.get("/drilldown/vendor", response_model=DrilldownResponseOut)
def demo_drilldown_vendor(
    business_id: str,
    vendor: str,
    window_days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    biz = _require_business(db, business_id)
    vendor_key = merchant_key(vendor)
    pairs, _last = _load_event_txn_pairs_from_db(
        db=db,
        biz_db_id=biz.id,
        limit_events=4000,
        chronological=True,
    )
    window_pairs = _filter_pairs_for_window(pairs, window_days)
    filtered = [
        (e, t) for e, t in window_pairs if merchant_key(t.description) == vendor_key
    ]
    sorted_pairs = _sort_pairs_deterministic(filtered)
    total = len(sorted_pairs)
    paged = sorted_pairs[offset : offset + limit]
    return DrilldownResponseOut(
        business_id=str(biz.id),
        name=biz.name,
        window_days=window_days,
        limit=limit,
        offset=offset,
        total=total,
        rows=_build_drilldown_rows(paged),
    )


@router.post("/health/{business_id}/signals/{signal_id}/status")
def update_health_signal_status(
    business_id: str,
    signal_id: str,
    req: HealthSignalStatusIn,
    db: Session = Depends(get_db),
):
    return health_signal_service.update_signal_status(
        db,
        business_id,
        signal_id,
        status=req.status,
        reason=req.reason,
        actor=req.actor,
    )

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

    source_event_ids = [e.source_event_id for e, _t in pairs]
    categorization_rows = (
        db.execute(
            select(TxnCategorization).where(
                TxnCategorization.business_id == biz.id,
                TxnCategorization.source_event_id.in_(source_event_ids),
            )
        )
        .scalars()
        .all()
    )
    categorization_map = {row.source_event_id: row for row in categorization_rows}

    items: List[dict] = []
    for e, t in newest_first:
        if id_set and e.source_event_id not in id_set:
            continue
        if category and t.category != category:
            continue
        if direction and t.direction != direction:
            continue

        suggestion_source: Optional[str] = None
        confidence: Optional[float] = None
        reason: Optional[str] = None

        manual = categorization_map.get(e.source_event_id)
        if manual:
            suggestion_source = manual.source
            confidence = manual.confidence
            reason = manual.note
        elif (t.category or "").strip().lower() == "uncategorized":
            suggested = suggest_category(db, t, business_id=biz.id)
            cat_obj = getattr(suggested, "categorization", None)
            if cat_obj:
                candidate = (cat_obj.category or "").strip().lower()
                if candidate and candidate != "uncategorized":
                    suggestion_source = cat_obj.source
                    confidence = float(cat_obj.confidence or 0.0)
                    reason = cat_obj.reason

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
                "merchant_key": merchant_key(t.description),
                "suggestion_source": suggestion_source,
                "confidence": confidence,
                "reason": reason,
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
