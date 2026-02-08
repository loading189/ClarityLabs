from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.app.models import ActionItem, HealthSignalState, IntegrationConnection, RawEvent, TxnCategorization
from backend.app.services.posted_txn_service import count_uncategorized_raw_events, fetch_posted_transactions
from backend.app.services.signals_service import SIGNAL_CATALOG, _payload_ledger_anchors


ACTION_COOLDOWN_DAYS = 14
INTEGRATION_STALE_HOURS = 12
VENDOR_VARIANCE_RATIO = 0.5
VENDOR_MIN_DELTA = 200.0
VENDOR_MIN_RECENT = 300.0


@dataclass(frozen=True)
class ActionCandidate:
    action_type: str
    title: str
    summary: str
    priority: int
    idempotency_key: str
    due_at: Optional[datetime]
    source_signal_id: Optional[str]
    evidence_json: dict
    rationale_json: dict


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _date_bounds(now: datetime, days: int) -> tuple[date, date]:
    end_date = now.date()
    start_date = (now - timedelta(days=days)).date()
    return start_date, end_date


def _idempotency_key(
    business_id: str,
    action_type: str,
    source_signal_id: Optional[str],
    window_start: Optional[str],
    window_end: Optional[str],
    dimension_key: Optional[str],
) -> str:
    parts = [
        business_id,
        action_type,
        source_signal_id or "none",
        window_start or "none",
        window_end or "none",
        dimension_key or "none",
    ]
    return ":".join(parts)


def _signal_domain(signal_type: Optional[str]) -> Optional[str]:
    if not signal_type:
        return None
    return SIGNAL_CATALOG.get(signal_type, {}).get("domain")


def _signal_material_change(existing: ActionItem, candidate: ActionCandidate) -> bool:
    if existing.source_signal_id and existing.source_signal_id == candidate.source_signal_id:
        existing_evidence = existing.evidence_json if isinstance(existing.evidence_json, dict) else {}
        candidate_evidence = candidate.evidence_json if isinstance(candidate.evidence_json, dict) else {}
        if existing_evidence.get("signal_severity") != candidate_evidence.get("signal_severity"):
            return True
        if existing_evidence.get("ledger_anchors") != candidate_evidence.get("ledger_anchors"):
            return True
    return (
        existing.summary != candidate.summary
        or existing.priority != candidate.priority
        or existing.evidence_json != candidate.evidence_json
        or existing.rationale_json != candidate.rationale_json
    )


def _apply_candidate(existing: ActionItem, candidate: ActionCandidate, now: datetime, *, reopen: bool) -> None:
    existing.title = candidate.title
    existing.summary = candidate.summary
    existing.priority = candidate.priority
    existing.due_at = candidate.due_at
    existing.source_signal_id = candidate.source_signal_id
    existing.evidence_json = candidate.evidence_json
    existing.rationale_json = candidate.rationale_json
    existing.updated_at = now
    if reopen:
        existing.status = "open"
        existing.resolution_reason = None
        existing.resolved_at = None
        existing.snoozed_until = None


def _should_reopen(existing: ActionItem, candidate: ActionCandidate, now: datetime) -> bool:
    if existing.status == "snoozed":
        if existing.snoozed_until and existing.snoozed_until > now:
            return False
        return True

    if existing.status in {"done", "ignored"}:
        if existing.resolved_at:
            cooldown = now - existing.resolved_at
            if cooldown < timedelta(days=ACTION_COOLDOWN_DAYS) and not _signal_material_change(existing, candidate):
                return False
        return True

    return False


def _uncategorized_candidates(db: Session, business_id: str, now: datetime) -> list[ActionCandidate]:
    count = count_uncategorized_raw_events(db, business_id)
    if count <= 0:
        return []

    rows = (
        db.execute(
            select(RawEvent.source_event_id)
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
            .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
            .limit(5)
        )
        .scalars()
        .all()
    )

    window_start = "all"
    window_end = now.date().isoformat()
    evidence = {
        "uncategorized_count": count,
        "sample_source_event_ids": rows,
        "window": {"start": window_start, "end": window_end},
    }
    rationale = {
        "why_now": "New transactions arrived without a category mapping.",
        "thresholds": {"min_uncategorized": 1},
    }

    return [
        ActionCandidate(
            action_type="fix_mapping",
            title="Categorize new transactions",
            summary=f"{count} transactions need category mappings before the ledger is complete.",
            priority=4,
            idempotency_key=_idempotency_key(
                business_id,
                "fix_mapping",
                None,
                window_start,
                window_end,
                "uncategorized",
            ),
            due_at=None,
            source_signal_id=None,
            evidence_json=evidence,
            rationale_json=rationale,
        )
    ]


def _signal_candidates(db: Session, business_id: str, now: datetime) -> list[ActionCandidate]:
    rows = (
        db.execute(
            select(HealthSignalState)
            .where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.status == "open",
            )
            .order_by(HealthSignalState.updated_at.desc())
        )
        .scalars()
        .all()
    )

    candidates: list[ActionCandidate] = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        anchors = _payload_ledger_anchors(payload)
        if not anchors:
            continue
        domain = _signal_domain(row.signal_type)
        severity = (row.severity or "").lower()
        title = "Investigate signal"
        if domain and severity:
            title = f"Investigate {severity} {domain} anomaly"
        elif domain:
            title = f"Investigate {domain} anomaly"
        elif severity:
            title = f"Investigate {severity} anomaly"

        window_start = payload.get("window_start") or payload.get("window", {}).get("start")
        window_end = payload.get("window_end") or payload.get("window", {}).get("end")
        window_start = str(window_start) if window_start else None
        window_end = str(window_end) if window_end else None
        evidence = {
            "signal_id": row.signal_id,
            "signal_type": row.signal_type,
            "signal_severity": row.severity,
            "signal_summary": row.summary,
            "ledger_anchors": anchors,
            "explain_ref": {
                "path": f"/api/signals/{business_id}/{row.signal_id}/explain",
            },
        }
        rationale = {
            "why_now": "Signal is open with ledger anchors requiring review.",
            "baseline_window": payload.get("baseline_window"),
            "delta": payload.get("delta"),
        }
        candidates.append(
            ActionCandidate(
                action_type="investigate_anomaly",
                title=title,
                summary=row.summary or row.title or "Review the underlying ledger evidence.",
                priority=5 if severity in {"high", "critical"} else 4,
                idempotency_key=_idempotency_key(
                    business_id,
                    "investigate_anomaly",
                    row.signal_id,
                    window_start,
                    window_end,
                    domain or row.signal_type or "signal",
                ),
                due_at=None,
                source_signal_id=row.signal_id,
                evidence_json=evidence,
                rationale_json=rationale,
            )
        )
    return candidates


def _integration_candidates(db: Session, business_id: str, now: datetime) -> list[ActionCandidate]:
    rows = (
        db.execute(select(IntegrationConnection).where(IntegrationConnection.business_id == business_id))
        .scalars()
        .all()
    )
    candidates: list[ActionCandidate] = []
    stale_threshold = now - timedelta(hours=INTEGRATION_STALE_HOURS)

    for row in rows:
        status = (row.status or "").lower()
        last_sync_at = row.last_sync_at
        is_stale = last_sync_at is None or last_sync_at < stale_threshold
        if status != "connected" or is_stale:
            reason = "Integration is disconnected." if status != "connected" else "Integration sync is stale."
            evidence = {
                "provider": row.provider,
                "status": row.status,
                "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
                "stale_hours": INTEGRATION_STALE_HOURS,
            }
            rationale = {
                "why_now": reason,
                "thresholds": {"stale_hours": INTEGRATION_STALE_HOURS},
            }
            candidates.append(
                ActionCandidate(
                    action_type="sync_integration",
                    title=f"Sync {row.provider} integration",
                    summary=reason,
                    priority=5 if status != "connected" else 3,
                    idempotency_key=_idempotency_key(
                        business_id,
                        "sync_integration",
                        None,
                        None,
                        None,
                        row.provider,
                    ),
                    due_at=None,
                    source_signal_id=None,
                    evidence_json=evidence,
                    rationale_json=rationale,
                )
            )

    return candidates


def _vendor_variance_candidates(db: Session, business_id: str, now: datetime) -> list[ActionCandidate]:
    start_90, end_90 = _date_bounds(now, 90)
    txns = fetch_posted_transactions(db, business_id, start_date=start_90, end_date=end_90)
    totals_90: dict[str, float] = {}
    for txn in txns:
        if (txn.direction or "").lower() != "outflow":
            continue
        vendor = (txn.description or "").strip() or "Unknown"
        totals_90[vendor] = totals_90.get(vendor, 0.0) + abs(float(txn.amount or 0.0))
    top_vendors = sorted(totals_90.items(), key=lambda item: item[1], reverse=True)[:5]

    recent_start = (now - timedelta(days=14)).date()
    recent_end = now.date()
    baseline_start = (now - timedelta(days=74)).date()
    baseline_end = (now - timedelta(days=14)).date()

    recent_txns = fetch_posted_transactions(db, business_id, start_date=recent_start, end_date=recent_end)
    baseline_txns = fetch_posted_transactions(db, business_id, start_date=baseline_start, end_date=baseline_end)

    def _aggregate(txns_list: list, vendor_name: str) -> float:
        total = 0.0
        for txn in txns_list:
            if (txn.direction or "").lower() != "outflow":
                continue
            vendor = (txn.description or "").strip() or "Unknown"
            if vendor != vendor_name:
                continue
            total += abs(float(txn.amount or 0.0))
        return total

    candidates: list[ActionCandidate] = []
    for vendor, total_90 in top_vendors:
        recent_total = _aggregate(recent_txns, vendor)
        baseline_total = _aggregate(baseline_txns, vendor)
        delta = recent_total - baseline_total
        ratio = None
        if baseline_total > 0:
            ratio = delta / baseline_total
            high_variance = abs(ratio) >= VENDOR_VARIANCE_RATIO and abs(delta) >= VENDOR_MIN_DELTA
        else:
            high_variance = recent_total >= VENDOR_MIN_RECENT
        if not high_variance:
            continue

        evidence = {
            "vendor": vendor,
            "recent_total": recent_total,
            "baseline_total": baseline_total,
            "window": {
                "recent_start": recent_start.isoformat(),
                "recent_end": recent_end.isoformat(),
                "baseline_start": baseline_start.isoformat(),
                "baseline_end": baseline_end.isoformat(),
            },
        }
        rationale = {
            "why_now": "Vendor spend deviated from baseline.",
            "baseline_window": {
                "start": baseline_start.isoformat(),
                "end": baseline_end.isoformat(),
            },
            "recent_window": {
                "start": recent_start.isoformat(),
                "end": recent_end.isoformat(),
            },
            "delta": delta,
            "change_ratio": ratio,
            "thresholds": {
                "variance_ratio": VENDOR_VARIANCE_RATIO,
                "min_delta": VENDOR_MIN_DELTA,
                "min_recent": VENDOR_MIN_RECENT,
            },
        }
        candidates.append(
            ActionCandidate(
                action_type="review_vendor",
                title=f"Review spend at {vendor}",
                summary=(
                    f"Spend in the last 14 days totaled {recent_total:.2f}, versus {baseline_total:.2f}"
                    " in the prior 60 days."
                ),
                priority=4 if ratio and abs(ratio) >= 1 else 3,
                idempotency_key=_idempotency_key(
                    business_id,
                    "review_vendor",
                    None,
                    baseline_start.isoformat(),
                    recent_end.isoformat(),
                    vendor,
                ),
                due_at=None,
                source_signal_id=None,
                evidence_json=evidence,
                rationale_json=rationale,
            )
        )

    return candidates


def _net_cash_trend(db: Session, business_id: str, now: datetime) -> dict:
    start_30, end_30 = _date_bounds(now, 30)
    txns = fetch_posted_transactions(db, business_id, start_date=start_30, end_date=end_30)
    inflow = 0.0
    outflow = 0.0
    for txn in txns:
        if (txn.direction or "").lower() == "inflow":
            inflow += abs(float(txn.amount or 0.0))
        else:
            outflow += abs(float(txn.amount or 0.0))
    return {
        "starting_cash": None,
        "net_cash_trend": inflow - outflow,
        "window": {"start": start_30.isoformat(), "end": end_30.isoformat()},
        "note": "Starting cash unavailable; using net cash trend.",
    }


def generate_actions_for_business(db: Session, business_id: str, *, now: Optional[datetime] = None) -> list[ActionItem]:
    now = now or utcnow()
    _ = _net_cash_trend(db, business_id, now)

    candidates: list[ActionCandidate] = []
    candidates.extend(_uncategorized_candidates(db, business_id, now))
    candidates.extend(_signal_candidates(db, business_id, now))
    candidates.extend(_integration_candidates(db, business_id, now))
    candidates.extend(_vendor_variance_candidates(db, business_id, now))

    existing_rows = (
        db.execute(select(ActionItem).where(ActionItem.business_id == business_id))
        .scalars()
        .all()
    )
    existing_map = {row.idempotency_key: row for row in existing_rows}

    open_actions: list[ActionItem] = []
    for candidate in candidates:
        existing = existing_map.get(candidate.idempotency_key)
        if existing:
            if existing.status == "open":
                _apply_candidate(existing, candidate, now, reopen=False)
                open_actions.append(existing)
            elif _should_reopen(existing, candidate, now):
                _apply_candidate(existing, candidate, now, reopen=True)
                open_actions.append(existing)
            continue

        action = ActionItem(
            business_id=business_id,
            action_type=candidate.action_type,
            title=candidate.title,
            summary=candidate.summary,
            priority=candidate.priority,
            status="open",
            created_at=now,
            updated_at=now,
            due_at=candidate.due_at,
            source_signal_id=candidate.source_signal_id,
            evidence_json=candidate.evidence_json,
            rationale_json=candidate.rationale_json,
            idempotency_key=candidate.idempotency_key,
        )
        db.add(action)
        open_actions.append(action)

    return open_actions


def list_actions(
    db: Session,
    business_id: str,
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ActionItem], dict]:
    stmt = select(ActionItem).where(ActionItem.business_id == business_id)
    if status:
        stmt = stmt.where(ActionItem.status == status)
    stmt = stmt.order_by(ActionItem.priority.desc(), ActionItem.created_at.desc(), ActionItem.id.desc())
    stmt = stmt.offset(offset).limit(limit)

    actions = db.execute(stmt).scalars().all()

    summary_rows = (
        db.execute(
            select(ActionItem.status, func.count()).where(ActionItem.business_id == business_id).group_by(ActionItem.status)
        )
        .all()
    )
    summary = {row[0]: int(row[1]) for row in summary_rows}
    for key in ["open", "done", "ignored", "snoozed"]:
        summary.setdefault(key, 0)
    return actions, summary


def resolve_action(
    db: Session,
    business_id: str,
    action_id: str,
    *,
    status: str,
    resolution_reason: Optional[str],
) -> ActionItem:
    row = db.get(ActionItem, action_id)
    if not row or row.business_id != business_id:
        raise ValueError("action not found")
    if status not in {"done", "ignored"}:
        raise ValueError("invalid status")
    row.status = status
    row.resolution_reason = resolution_reason
    row.resolved_at = utcnow()
    row.updated_at = utcnow()
    db.add(row)
    return row


def snooze_action(
    db: Session,
    business_id: str,
    action_id: str,
    *,
    until: datetime,
    reason: Optional[str],
) -> ActionItem:
    row = db.get(ActionItem, action_id)
    if not row or row.business_id != business_id:
        raise ValueError("action not found")
    row.status = "snoozed"
    row.snoozed_until = until
    row.resolution_reason = reason
    row.updated_at = utcnow()
    db.add(row)
    return row
