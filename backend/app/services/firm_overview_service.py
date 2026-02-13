from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.app.models import ActionItem, Business, BusinessMembership, HealthSignalState
from backend.app.services.posted_txn_service import count_uncategorized_raw_events


RISK_BANDS: list[tuple[int, int, str]] = [
    (0, 20, "stable"),
    (21, 40, "watch"),
    (41, 70, "elevated"),
    (71, 100, "at_risk"),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _risk_band(score: int) -> str:
    for min_score, max_score, label in RISK_BANDS:
        if min_score <= score <= max_score:
            return label
    return "stable"


def _risk_score(*, critical_signals: int, warning_signals: int, open_actions: int, stale_actions: int, uncategorized_txns: int) -> int:
    score = (
        (critical_signals * 20)
        + (warning_signals * 10)
        + (open_actions * 8)
        + (stale_actions * 15)
        + (uncategorized_txns * 2)
    )
    return max(0, min(100, score))


def get_firm_overview_for_user(user_id: str, db: Session) -> dict:
    now = _utcnow()
    stale_threshold = now - timedelta(days=7)

    businesses = (
        db.execute(
            select(Business)
            .join(BusinessMembership, BusinessMembership.business_id == Business.id)
            .where(BusinessMembership.user_id == user_id)
            .order_by(Business.name.asc(), Business.id.asc())
        )
        .scalars()
        .all()
    )
    business_ids = [business.id for business in businesses]

    if not business_ids:
        return {"businesses": [], "generated_at": now}

    signal_rows = db.execute(
        select(
            HealthSignalState.business_id,
            func.lower(func.coalesce(HealthSignalState.severity, "info")).label("severity"),
            func.count().label("count"),
            func.max(func.coalesce(HealthSignalState.last_seen_at, HealthSignalState.detected_at)).label("latest_signal_at"),
        )
        .where(
            HealthSignalState.business_id.in_(business_ids),
            HealthSignalState.status == "open",
        )
        .group_by(HealthSignalState.business_id, func.lower(func.coalesce(HealthSignalState.severity, "info")))
    ).all()

    signal_summary: dict[str, dict] = {
        business_id: {
            "open_signals": 0,
            "signals_by_severity": {"critical": 0, "warning": 0, "info": 0},
            "latest_signal_at": None,
        }
        for business_id in business_ids
    }

    for row in signal_rows:
        bucket = signal_summary[row.business_id]
        severity = row.severity if row.severity in {"critical", "warning", "info"} else "info"
        count = int(row.count or 0)
        bucket["signals_by_severity"][severity] += count
        bucket["open_signals"] += count
        latest_signal_at = row.latest_signal_at
        if latest_signal_at and (
            bucket["latest_signal_at"] is None or latest_signal_at > bucket["latest_signal_at"]
        ):
            bucket["latest_signal_at"] = latest_signal_at

    action_rows = db.execute(
        select(
            ActionItem.business_id,
            func.count().label("open_actions"),
            func.sum(case((ActionItem.created_at <= stale_threshold, 1), else_=0)).label("stale_actions"),
            func.max(ActionItem.updated_at).label("latest_action_at"),
        )
        .where(
            ActionItem.business_id.in_(business_ids),
            ActionItem.status == "open",
        )
        .group_by(ActionItem.business_id)
    ).all()

    action_summary: dict[str, dict] = {
        business_id: {"open_actions": 0, "stale_actions": 0, "latest_action_at": None}
        for business_id in business_ids
    }

    for row in action_rows:
        action_summary[row.business_id] = {
            "open_actions": int(row.open_actions or 0),
            "stale_actions": int(row.stale_actions or 0),
            "latest_action_at": row.latest_action_at,
        }

    overview_businesses = []
    for business in businesses:
        uncategorized_txn_count = count_uncategorized_raw_events(db, business.id)
        signal_data = signal_summary[business.id]
        action_data = action_summary[business.id]
        risk_score = _risk_score(
            critical_signals=signal_data["signals_by_severity"]["critical"],
            warning_signals=signal_data["signals_by_severity"]["warning"],
            open_actions=action_data["open_actions"],
            stale_actions=action_data["stale_actions"],
            uncategorized_txns=uncategorized_txn_count,
        )

        overview_businesses.append(
            {
                "business_id": business.id,
                "business_name": business.name,
                "open_signals": signal_data["open_signals"],
                "signals_by_severity": signal_data["signals_by_severity"],
                "open_actions": action_data["open_actions"],
                "stale_actions": action_data["stale_actions"],
                "uncategorized_txn_count": uncategorized_txn_count,
                "latest_signal_at": signal_data["latest_signal_at"],
                "latest_action_at": action_data["latest_action_at"],
                "risk_score": risk_score,
                "risk_band": _risk_band(risk_score),
            }
        )

    overview_businesses.sort(key=lambda item: (-item["risk_score"], item["business_name"], item["business_id"]))
    return {"businesses": overview_businesses, "generated_at": now}
