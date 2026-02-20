from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from backend.app.models import ActionItem, HealthSignalState, RawEvent
from backend.app.services import case_engine_service


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return dt.isoformat()


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_detector(state: HealthSignalState, payload: Dict[str, Any]) -> Dict[str, str]:
    detector = payload.get("detector") if isinstance(payload.get("detector"), dict) else {}
    domain = detector.get("domain") or payload.get("domain") or (state.signal_type or "unknown").split("_")[0]
    rule_id = (
        detector.get("rule_id")
        or payload.get("rule_id")
        or payload.get("id")
        or state.signal_type
        or "unknown"
    )
    version = str(detector.get("version") or payload.get("version") or payload.get("rule_version") or "unknown")
    return {"domain": str(domain or "unknown"), "rule_id": str(rule_id), "version": version}


def _extract_window(payload: Dict[str, Any], newest_event_at: Optional[datetime]) -> Dict[str, Optional[str]]:
    current_window = payload.get("current_window") if isinstance(payload.get("current_window"), dict) else {}
    start = current_window.get("start") or payload.get("window_start")
    end = current_window.get("end") or payload.get("window_end")
    if isinstance(start, str) and isinstance(end, str):
        return {"start": start, "end": end}

    if not newest_event_at:
        newest_event_at = datetime.now(timezone.utc)
    start_dt = newest_event_at - timedelta(days=30)
    return {"start": start_dt.date().isoformat(), "end": newest_event_at.date().isoformat()}


def _linked_action_id(db: Session, business_id: str, signal_id: str) -> Optional[str]:
    action = (
        db.execute(
            select(ActionItem)
            .where(ActionItem.business_id == business_id, ActionItem.source_signal_id == signal_id)
            .order_by(ActionItem.updated_at.desc(), ActionItem.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return action.id if action else None


def _ledger_anchors(payload: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    raw = payload.get("ledger_anchors") if isinstance(payload.get("ledger_anchors"), list) else []
    anchors: List[Dict[str, Optional[str]]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        query = item.get("query") if isinstance(item.get("query"), dict) else item
        source_event_ids = query.get("source_event_ids") if isinstance(query.get("source_event_ids"), list) else []
        source_event_id = str(source_event_ids[0]) if source_event_ids else None
        anchors.append(
            {
                "anchor_id": str(item.get("anchor_id") or item.get("id") or f"anchor-{idx + 1}"),
                "occurred_at": query.get("end_date") or query.get("start_date"),
                "source_event_id": source_event_id,
            }
        )
    return anchors


def _top_transactions(
    db: Session,
    business_id: str,
    payload: Dict[str, Any],
    window: Dict[str, Optional[str]],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    source_ids: List[str] = []
    for anchor in payload.get("ledger_anchors") or []:
        if not isinstance(anchor, dict):
            continue
        query = anchor.get("query") if isinstance(anchor.get("query"), dict) else anchor
        ids = query.get("source_event_ids") if isinstance(query.get("source_event_ids"), list) else []
        source_ids.extend([str(item) for item in ids if item])

    q = select(RawEvent).where(RawEvent.business_id == business_id)
    if source_ids:
        q = q.where(RawEvent.source_event_id.in_(sorted(set(source_ids))))
    else:
        start = window.get("start")
        end = window.get("end")
        if start:
            q = q.where(RawEvent.occurred_at >= datetime.fromisoformat(f"{start}T00:00:00+00:00"))
        if end:
            q = q.where(RawEvent.occurred_at <= datetime.fromisoformat(f"{end}T23:59:59+00:00"))

    rows = db.execute(q.order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.asc()).limit(limit)).scalars().all()
    txns: List[Dict[str, Any]] = []
    for row in rows:
        event_payload = row.payload if isinstance(row.payload, dict) else {}
        txns.append(
            {
                "occurred_at": _iso(row.occurred_at),
                "source_event_id": row.source_event_id,
                "amount": _to_float(event_payload.get("amount")),
                "vendor": event_payload.get("counterparty_hint") or event_payload.get("vendor"),
                "name": event_payload.get("name") or event_payload.get("description"),
                "memo": event_payload.get("memo") or event_payload.get("description"),
            }
        )
    return txns


def _stats(payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    baseline = _to_float(payload.get("baseline_total") or payload.get("prior_total") or payload.get("baseline_value"))
    current = _to_float(payload.get("current_total") or payload.get("current_value"))
    pct = _to_float(payload.get("pct_change") or payload.get("percent_change"))
    if pct is None and baseline not in (None, 0.0) and current is not None:
        pct = ((current - baseline) / baseline) * 100.0
    return {"baseline_total": baseline, "current_total": current, "pct_change": pct}


def _expense_spike_narrative(title: str, payload: Dict[str, Any], stats: Dict[str, Optional[float]], txns: List[Dict[str, Any]]) -> Dict[str, Any]:
    label = str(payload.get("vendor") or payload.get("category") or payload.get("segment") or "Target")
    pct = stats.get("pct_change")
    pct_text = f"{pct:.1f}%" if isinstance(pct, (float, int)) else "materially"
    headline = f"{label} spend rose {pct_text} vs prior window."
    why = [
        "Spending acceleration can reduce cash runway if sustained.",
        "A concentrated increase often indicates a billing or usage shift.",
    ]
    what = []
    if stats.get("current_total") is not None and stats.get("baseline_total") is not None:
        what.append(
            f"Current window total is {stats['current_total']:.2f} vs baseline {stats['baseline_total']:.2f}."
        )
    if txns:
        top = txns[0]
        what.append(f"Largest recent transaction: {top.get('name') or top.get('vendor') or 'Unknown'} ({top.get('amount')}).")
    what.append("Review linked ledger entries to confirm expected business activity.")
    return {"headline": headline, "why_it_matters": why, "what_changed": what[:4]}


def _default_narrative(title: str) -> Dict[str, Any]:
    return {
        "headline": f"Signal detected: {title}",
        "why_it_matters": ["Review evidence and determine if action is needed."],
        "what_changed": ["See top transactions below."],
    }


def explain_signal(business_id: str, signal_id: str, db: Session) -> Dict[str, Any]:
    state = db.get(HealthSignalState, (business_id, signal_id))
    if not state:
        raise HTTPException(status_code=404, detail="signal not found")

    payload = state.payload_json if isinstance(state.payload_json, dict) else {}
    newest_event_at = (
        db.execute(
            select(RawEvent.occurred_at)
            .where(RawEvent.business_id == business_id)
            .order_by(RawEvent.occurred_at.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )

    detector = _extract_detector(state, payload)
    window = _extract_window(payload, newest_event_at)
    stats = _stats(payload)
    top_txns = _top_transactions(db, business_id, payload, window)
    anchors = _ledger_anchors(payload)
    narrative = (
        _expense_spike_narrative(state.title or "Signal", payload, stats, top_txns)
        if detector["rule_id"].startswith("expense_spike_")
        else _default_narrative(state.title or signal_id)
    )

    return {
        "signal_id": signal_id,
        "business_id": business_id,
        "title": state.title or signal_id,
        "status": state.status,
        "severity": state.severity,
        "detector": detector,
        "linked_action_id": _linked_action_id(db, business_id, signal_id),
        "case_id": case_engine_service.get_case_id_for_signal(db, business_id, signal_id),
        "narrative": narrative,
        "evidence": {
            "window": window,
            "stats": stats,
            "top_transactions": top_txns,
            "ledger_anchors": anchors,
        },
    }
