from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    ActionItem,
    Business,
    Case,
    CaseEvent,
    CaseLedgerAnchor,
    CaseSignal,
    HealthSignalState,
    Plan,
)
from backend.app.services.firm_overview_service import _risk_band, _risk_score

OPEN_CASE_STATUSES = {"open", "monitoring", "escalated"}
CLOSED_CASE_STATUSES = {"resolved", "dismissed"}
CASE_STATUSES = OPEN_CASE_STATUSES | CLOSED_CASE_STATUSES | {"reopened"}
SEVERITY_LEVELS = ["low", "medium", "high", "critical"]
TRANSITIONS = {
    "open": {"monitoring", "escalated", "resolved", "dismissed"},
    "monitoring": {"open", "escalated", "resolved", "dismissed"},
    "escalated": {"monitoring", "resolved", "dismissed"},
    "resolved": {"reopened"},
    "dismissed": {"reopened"},
    "reopened": {"monitoring", "escalated", "resolved", "dismissed"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _severity_rank(level: str) -> int:
    try:
        return SEVERITY_LEVELS.index((level or "low").lower())
    except ValueError:
        return 0


def _bump_severity(level: str) -> str:
    return SEVERITY_LEVELS[min(_severity_rank(level) + 1, len(SEVERITY_LEVELS) - 1)]


def _compute_risk_snapshot(db: Session, business_id: str) -> dict:
    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    signal_rows = (
        db.execute(
            select(func.lower(func.coalesce(HealthSignalState.severity, "info")), func.count())
            .where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.status == "open",
            )
            .group_by(func.lower(func.coalesce(HealthSignalState.severity, "info")))
        )
        .all()
    )
    for severity, count in signal_rows:
        key = severity if severity in severity_counts else "info"
        severity_counts[key] = int(count or 0)

    open_actions = int(
        db.execute(
            select(func.count())
            .where(ActionItem.business_id == business_id, ActionItem.status == "open")
        ).scalar_one()
        or 0
    )
    stale_actions = int(
        db.execute(
            select(func.count())
            .where(
                ActionItem.business_id == business_id,
                ActionItem.status == "open",
                ActionItem.created_at <= _now() - timedelta(days=7),
            )
        ).scalar_one()
        or 0
    )

    score = _risk_score(
        critical_signals=severity_counts["critical"],
        warning_signals=severity_counts["warning"],
        open_actions=open_actions,
        stale_actions=stale_actions,
        uncategorized_txns=0,
    )
    return {"score": score, "band": _risk_band(score)}


def _emit_case_event(db: Session, case_id: str, event_type: str, payload: Optional[dict] = None, *, now: Optional[datetime] = None) -> CaseEvent:
    event = CaseEvent(
        case_id=case_id,
        event_type=event_type,
        payload_json=payload or {},
        created_at=now or _now(),
    )
    db.add(event)
    return event


def _require_business(db: Session, business_id: str) -> Business:
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="business not found")
    return business




class CaseSignalInvariantError(ValueError):
    """Raised when a signal-case uniqueness invariant would be violated."""


def _attach_signal_to_case(
    db: Session,
    *,
    case: Case,
    business_id: str,
    signal_id: str,
    signal_type: str,
    domain: str,
    severity: Optional[str],
    occurred_at: datetime,
) -> bool:
    existing_link = (
        db.execute(
            select(CaseSignal).where(
                CaseSignal.business_id == business_id,
                CaseSignal.signal_id == signal_id,
            )
        )
        .scalars()
        .first()
    )
    if existing_link:
        if existing_link.case_id == case.id:
            return False
        raise CaseSignalInvariantError(
            f"Invariant violation: signal '{signal_id}' for business '{business_id}' is already attached to case '{existing_link.case_id}' and cannot be attached to '{case.id}'."
        )

    link = CaseSignal(
        case_id=case.id,
        business_id=business_id,
        signal_id=signal_id,
        created_at=occurred_at,
    )
    db.add(link)
    db.flush()
    _emit_case_event(
        db,
        case.id,
        "SIGNAL_ATTACHED",
        {"signal_id": signal_id, "signal_type": signal_type, "domain": domain, "severity": severity},
        now=occurred_at,
    )
    return True

def _require_case(db: Session, case_id: str) -> Case:
    row = db.get(Case, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="case not found")
    return row


def aggregate_signal_into_case(
    db: Session,
    *,
    business_id: str,
    signal_id: str,
    signal_type: str,
    domain: str,
    severity: Optional[str],
    occurred_at: Optional[datetime],
) -> str:
    _require_business(db, business_id)
    now = occurred_at or _now()
    case = (
        db.execute(
            select(Case)
            .where(
                Case.business_id == business_id,
                Case.domain == domain,
                Case.status.in_(OPEN_CASE_STATUSES),
            )
            .order_by(Case.opened_at.asc(), Case.id.asc())
        )
        .scalars()
        .first()
    )
    if not case:
        case = Case(
            business_id=business_id,
            domain=domain,
            primary_signal_type=signal_type,
            severity=severity or "low",
            status="open",
            risk_score_snapshot=_compute_risk_snapshot(db, business_id),
            opened_at=now,
            last_activity_at=now,
        )
        db.add(case)
        db.flush()
        _emit_case_event(
            db,
            case.id,
            "CASE_CREATED",
            {
                "business_id": business_id,
                "domain": domain,
                "signal_id": signal_id,
                "signal_type": signal_type,
                "severity": severity,
            },
            now=now,
        )

    attached = _attach_signal_to_case(
        db,
        case=case,
        business_id=business_id,
        signal_id=signal_id,
        signal_type=signal_type,
        domain=domain,
        severity=severity,
        occurred_at=now,
    )
    if not attached:
        return case.id

    case.last_activity_at = now
    if severity and _severity_rank(severity) > _severity_rank(case.severity):
        case.severity = severity
    evaluate_escalation(db, case.id, now=now)
    return case.id


def evaluate_escalation(db: Session, case_id: str, *, now: Optional[datetime] = None) -> Optional[CaseEvent]:
    case = _require_case(db, case_id)
    current = now or _now()

    signal_count_30d = int(
        db.execute(
            select(func.count())
            .select_from(CaseSignal)
            .where(CaseSignal.case_id == case.id, CaseSignal.created_at >= current - timedelta(days=30))
        ).scalar_one()
        or 0
    )
    active_plan = (
        db.execute(
            select(Plan)
            .where(Plan.case_id == case.id, Plan.status.in_(["draft", "active"]))
            .order_by(Plan.created_at.asc(), Plan.id.asc())
        )
        .scalars()
        .first()
    )
    plan_overdue = bool(active_plan and active_plan.created_at <= current - timedelta(days=14))

    snapshot_score = int((case.risk_score_snapshot or {}).get("score", 0))
    current_risk = _compute_risk_snapshot(db, case.business_id)
    risk_delta = int(current_risk.get("score", 0)) - snapshot_score

    rule = None
    payload: Dict[str, Any] = {}
    if signal_count_30d >= 3:
        rule = "signal_volume_30d"
        payload = {"signal_count_30d": signal_count_30d, "threshold": 3}
    elif plan_overdue:
        rule = "plan_overdue"
        payload = {"plan_id": active_plan.id if active_plan else None, "overdue_days": 14}
    elif risk_delta >= 15:
        rule = "risk_delta"
        payload = {"snapshot_score": snapshot_score, "current_score": current_risk.get("score"), "delta": risk_delta}

    if not rule:
        return None

    last = (
        db.execute(
            select(CaseEvent)
            .where(CaseEvent.case_id == case.id, CaseEvent.event_type == "CASE_ESCALATED")
            .order_by(CaseEvent.created_at.desc(), CaseEvent.id.desc())
        )
        .scalars()
        .first()
    )
    signature = {"rule": rule, **payload}
    if last and isinstance(last.payload_json, dict) and last.payload_json == signature:
        return None

    case.status = "escalated"
    case.severity = _bump_severity(case.severity)
    case.last_activity_at = current
    return _emit_case_event(db, case.id, "CASE_ESCALATED", signature, now=current)


def update_case_status(db: Session, case_id: str, *, status: str, reason: Optional[str], actor: Optional[str]) -> Case:
    case = _require_case(db, case_id)
    next_status = status.lower()
    if next_status not in CASE_STATUSES:
        raise HTTPException(status_code=400, detail="invalid case status")
    allowed = TRANSITIONS.get(case.status, set())
    if next_status not in allowed:
        raise HTTPException(status_code=400, detail=f"invalid status transition {case.status}->{next_status}")

    now = _now()
    from_status = case.status
    case.status = next_status
    case.last_activity_at = now
    case.closed_at = now if next_status in CLOSED_CASE_STATUSES else None
    _emit_case_event(
        db,
        case.id,
        "CASE_STATUS_CHANGED",
        {"from_status": from_status, "to_status": next_status, "reason": reason, "actor": actor},
        now=now,
    )
    return case


def attach_plan_to_case(db: Session, case_id: str, plan: Plan, *, actor_user_id: str) -> None:
    case = _require_case(db, case_id)
    if case.business_id != plan.business_id:
        raise HTTPException(status_code=400, detail="plan and case must belong to same business")
    plan.case_id = case.id
    case.last_activity_at = _now()
    _emit_case_event(db, case.id, "PLAN_CREATED", {"plan_id": plan.id, "actor_user_id": actor_user_id})


def emit_plan_event(db: Session, case_id: Optional[str], event_type: str, payload: dict) -> None:
    if not case_id:
        return
    _emit_case_event(db, case_id, event_type, payload)


def list_cases(
    db: Session,
    *,
    business_id: str,
    status: Optional[str],
    severity: Optional[str],
    domain: Optional[str],
    q: Optional[str],
    sort: str,
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    _require_business(db, business_id)
    stmt = select(Case).where(Case.business_id == business_id)
    if status:
        stmt = stmt.where(Case.status == status)
    if severity:
        stmt = stmt.where(Case.severity == severity)
    if domain:
        stmt = stmt.where(Case.domain == domain)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((Case.primary_signal_type.ilike(like)) | (Case.domain.ilike(like)))

    if sort == "severity":
        stmt = stmt.order_by(Case.severity.desc(), Case.last_activity_at.desc(), Case.id.asc())
    elif sort == "aging":
        stmt = stmt.order_by(Case.opened_at.asc(), Case.severity.desc(), Case.id.asc())
    else:
        stmt = stmt.order_by(Case.last_activity_at.desc(), Case.severity.desc(), Case.id.asc())

    offset = max(page - 1, 0) * page_size
    rows = db.execute(stmt.offset(offset).limit(page_size)).scalars().all()
    total = int(db.execute(select(func.count()).select_from(Case).where(Case.business_id == business_id)).scalar_one() or 0)
    return {"items": [serialize_case_summary(db, row) for row in rows], "total": total, "page": page, "page_size": page_size}


def serialize_case_summary(db: Session, row: Case) -> dict:
    signal_count = int(db.execute(select(func.count()).select_from(CaseSignal).where(CaseSignal.case_id == row.id)).scalar_one() or 0)
    return {
        "id": row.id,
        "business_id": row.business_id,
        "domain": row.domain,
        "primary_signal_type": row.primary_signal_type,
        "severity": row.severity,
        "status": row.status,
        "risk_score_snapshot": row.risk_score_snapshot,
        "opened_at": row.opened_at,
        "last_activity_at": row.last_activity_at,
        "closed_at": row.closed_at,
        "signal_count": signal_count,
    }


def get_case_detail(db: Session, case_id: str) -> dict:
    row = _require_case(db, case_id)
    signal_links = (
        db.execute(select(CaseSignal).where(CaseSignal.case_id == case_id).order_by(CaseSignal.created_at.asc(), CaseSignal.signal_id.asc()))
        .scalars()
        .all()
    )
    signal_ids = [link.signal_id for link in signal_links]
    signals = (
        db.execute(
            select(HealthSignalState)
            .where(HealthSignalState.business_id == row.business_id, HealthSignalState.signal_id.in_(signal_ids))
            .order_by(HealthSignalState.detected_at.asc(), HealthSignalState.signal_id.asc())
        )
        .scalars()
        .all()
        if signal_ids
        else []
    )
    actions = (
        db.execute(
            select(ActionItem)
            .where(ActionItem.business_id == row.business_id, ActionItem.source_signal_id.in_(signal_ids))
            .order_by(ActionItem.created_at.desc(), ActionItem.id.asc())
        )
        .scalars()
        .all()
        if signal_ids
        else []
    )
    plans = (
        db.execute(select(Plan).where(Plan.case_id == row.id).order_by(Plan.created_at.desc(), Plan.id.asc())).scalars().all()
    )
    anchors = (
        db.execute(select(CaseLedgerAnchor).where(CaseLedgerAnchor.case_id == row.id).order_by(CaseLedgerAnchor.created_at.asc(), CaseLedgerAnchor.id.asc())).scalars().all()
    )
    return {
        "case": serialize_case_summary(db, row),
        "signals": [
            {
                "signal_id": signal.signal_id,
                "signal_type": signal.signal_type,
                "severity": signal.severity,
                "status": signal.status,
                "title": signal.title,
                "summary": signal.summary,
            }
            for signal in signals
        ],
        "actions": [{"id": action.id, "title": action.title, "status": action.status, "priority": action.priority} for action in actions],
        "plans": [{"id": plan.id, "title": plan.title, "status": plan.status, "created_at": plan.created_at} for plan in plans],
        "ledger_anchors": [{"id": anchor.id, "anchor_key": anchor.anchor_key, "anchor_payload_json": anchor.anchor_payload_json} for anchor in anchors],
    }


def case_timeline(db: Session, case_id: str) -> List[dict]:
    _require_case(db, case_id)
    rows = (
        db.execute(select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(CaseEvent.created_at.asc(), CaseEvent.id.asc()))
        .scalars()
        .all()
    )
    return [{"id": row.id, "event_type": row.event_type, "payload_json": row.payload_json, "created_at": row.created_at} for row in rows]


def add_case_note(db: Session, case_id: str, text: str, actor: Optional[str]) -> None:
    case = _require_case(db, case_id)
    case.last_activity_at = _now()
    _emit_case_event(db, case.id, "CASE_NOTE", {"text": text, "actor": actor})


def attach_ledger_anchor(db: Session, case_id: str, anchor_key: str, payload: Optional[dict]) -> None:
    case = _require_case(db, case_id)
    existing = db.execute(select(CaseLedgerAnchor).where(CaseLedgerAnchor.case_id == case.id, CaseLedgerAnchor.anchor_key == anchor_key)).scalars().first()
    if existing:
        return
    db.add(CaseLedgerAnchor(case_id=case.id, anchor_key=anchor_key, anchor_payload_json=payload))
    case.last_activity_at = _now()
    _emit_case_event(db, case.id, "LEDGER_ANCHOR_ATTACHED", {"anchor_key": anchor_key})


def detach_ledger_anchor(db: Session, case_id: str, anchor_key: str) -> None:
    case = _require_case(db, case_id)
    existing = db.execute(select(CaseLedgerAnchor).where(CaseLedgerAnchor.case_id == case.id, CaseLedgerAnchor.anchor_key == anchor_key)).scalars().first()
    if not existing:
        return
    db.delete(existing)
    case.last_activity_at = _now()
    _emit_case_event(db, case.id, "LEDGER_ANCHOR_DETACHED", {"anchor_key": anchor_key})


def get_case_id_for_signal(db: Session, business_id: str, signal_id: str) -> Optional[str]:
    row = db.execute(select(CaseSignal).where(CaseSignal.business_id == business_id, CaseSignal.signal_id == signal_id)).scalars().first()
    return row.case_id if row else None
