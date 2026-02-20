from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    ActionItem,
    AssistantMessage,
    Business,
    HealthSignalState,
    Plan,
    PlanCondition,
    PlanObservation,
    PlanStateEvent,
)
from backend.app.services.actions_service import _signal_domain
from backend.app.services import case_engine_service
from backend.app.services.audit_service import log_audit_event


PLAN_STATUSES = {"draft", "active", "succeeded", "failed", "canceled"}
PLAN_CONDITION_TYPES = {"signal_resolved", "metric_delta"}
PLAN_CONDITION_DIRECTIONS = {"improve", "worsen", "resolve"}
PLAN_OBSERVATION_VERDICTS = {"no_change", "improving", "worsening", "success", "failure"}
PLAN_EVENT_TYPES = {"created", "activated", "assigned", "note_added", "succeeded", "failed", "canceled"}


@dataclass(frozen=True)
class PlanRefreshResult:
    observation: PlanObservation
    success_candidate: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _require_plan(db: Session, business_id: str, plan_id: str) -> Plan:
    plan = db.get(Plan, plan_id)
    if not plan or plan.business_id != business_id:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


def _normalize_date(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _daily_brief_values(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
    metric_key: str,
) -> Tuple[List[float], List[str], List[str]]:
    rows = (
        db.execute(
            select(AssistantMessage)
            .where(
                AssistantMessage.business_id == business_id,
                AssistantMessage.kind == "daily_brief",
            )
            .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        )
        .scalars()
        .all()
    )
    values: List[float] = []
    dates: List[str] = []
    message_ids: List[str] = []
    for row in rows:
        payload = row.content_json if isinstance(row.content_json, dict) else {}
        payload_date = _normalize_date(payload.get("date"))
        if not payload_date or payload_date < start_date or payload_date > end_date:
            continue
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            continue
        value = metrics.get(metric_key)
        if isinstance(value, (int, float)):
            values.append(float(value))
            dates.append(payload_date.isoformat())
            message_ids.append(row.id)
    return values, dates, message_ids


def _average(values: Iterable[float]) -> Optional[float]:
    values_list = list(values)
    if not values_list:
        return None
    return sum(values_list) / len(values_list)


def _evaluation_window(plan: Plan, condition: PlanCondition, now: datetime) -> Tuple[date, date]:
    if not plan.activated_at:
        raise HTTPException(status_code=400, detail="plan is not active")
    start = plan.activated_at.astimezone(timezone.utc).date()
    end = start + timedelta(days=max(condition.evaluation_window_days, 1) - 1)
    today = now.astimezone(timezone.utc).date()
    if today < end:
        end = today
    return start, end


def _baseline_window(condition: PlanCondition, evaluation_start: date) -> Tuple[date, date]:
    days = max(condition.baseline_window_days, 1)
    end = evaluation_start - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start, end


def _signal_success(state: Optional[HealthSignalState], condition: PlanCondition, evaluation_end: date) -> bool:
    if not state:
        return False
    status = (state.status or "").lower()
    if status not in {"resolved", "closed"}:
        return False
    resolved_at = state.resolved_at or state.updated_at
    if not resolved_at:
        return False
    resolved_date = resolved_at.astimezone(timezone.utc).date()
    if resolved_date > evaluation_end:
        return False
    stable_days = (evaluation_end - resolved_date).days + 1
    required_days = max(condition.evaluation_window_days, 1)
    return stable_days >= required_days or resolved_date == evaluation_end


def _metric_verdict(delta: Optional[float], condition: PlanCondition) -> tuple[str, bool]:
    if delta is None:
        return "no_change", False
    threshold = condition.threshold if condition.threshold is not None else 0.0
    if condition.direction == "improve":
        if delta >= threshold:
            return "success", True
        if delta > 0:
            return "improving", False
        if delta < 0:
            return "worsening", False
        return "no_change", False
    if condition.direction == "worsen":
        if delta <= -threshold:
            return "success", True
        if delta < 0:
            return "improving", False
        if delta > 0:
            return "worsening", False
        return "no_change", False
    return "no_change", False


def list_plans(
    db: Session,
    business_id: str,
    *,
    status: Optional[str] = None,
    assigned_to_user_id: Optional[str] = None,
    source_action_id: Optional[str] = None,
) -> List[Plan]:
    _require_business(db, business_id)
    stmt = select(Plan).where(Plan.business_id == business_id)
    if status:
        stmt = stmt.where(Plan.status == status)
    if assigned_to_user_id:
        stmt = stmt.where(Plan.assigned_to_user_id == assigned_to_user_id)
    if source_action_id:
        stmt = stmt.where(Plan.source_action_id == source_action_id)
    stmt = stmt.order_by(Plan.created_at.desc(), Plan.id.desc())
    return db.execute(stmt).scalars().all()


def get_plan_detail(
    db: Session,
    business_id: str,
    plan_id: str,
) -> tuple[Plan, List[PlanCondition], Optional[PlanObservation], List[PlanObservation], List[PlanStateEvent]]:
    plan = _require_plan(db, business_id, plan_id)
    conditions = (
        db.execute(select(PlanCondition).where(PlanCondition.plan_id == plan.id).order_by(PlanCondition.created_at.asc()))
        .scalars()
        .all()
    )
    observations = (
        db.execute(
            select(PlanObservation)
            .where(PlanObservation.plan_id == plan.id)
            .order_by(PlanObservation.observed_at.desc(), PlanObservation.id.desc())
        )
        .scalars()
        .all()
    )
    latest_observation = observations[0] if observations else None
    events = (
        db.execute(
            select(PlanStateEvent)
            .where(PlanStateEvent.plan_id == plan.id)
            .order_by(PlanStateEvent.created_at.desc(), PlanStateEvent.id.desc())
        )
        .scalars()
        .all()
    )
    return plan, conditions, latest_observation, observations, events


def list_plan_summaries(
    db: Session,
    plan_ids: List[str],
) -> List[tuple[Plan, Optional[PlanObservation]]]:
    if not plan_ids:
        return []
    plans = db.execute(select(Plan).where(Plan.id.in_(plan_ids))).scalars().all()
    if not plans:
        return []
    observations = (
        db.execute(
            select(PlanObservation)
            .where(PlanObservation.plan_id.in_(plan_ids))
            .order_by(PlanObservation.plan_id.asc(), PlanObservation.observed_at.desc(), PlanObservation.id.desc())
        )
        .scalars()
        .all()
    )
    latest_by_plan: Dict[str, PlanObservation] = {}
    for observation in observations:
        if observation.plan_id not in latest_by_plan:
            latest_by_plan[observation.plan_id] = observation
    plan_by_id = {plan.id: plan for plan in plans}
    ordered: List[tuple[Plan, Optional[PlanObservation]]] = []
    for plan_id in plan_ids:
        plan = plan_by_id.get(plan_id)
        if not plan:
            continue
        ordered.append((plan, latest_by_plan.get(plan_id)))
    return ordered


def create_plan(
    db: Session,
    *,
    business_id: str,
    created_by_user_id: str,
    title: str,
    intent: str,
    case_id: Optional[str],
    source_action_id: Optional[str],
    primary_signal_id: Optional[str],
    assigned_to_user_id: Optional[str],
    idempotency_key: Optional[str],
    conditions: List[Dict[str, Any]],
) -> Plan:
    _require_business(db, business_id)
    if not case_id and primary_signal_id:
        case_id = case_engine_service.get_case_id_for_signal(db, business_id, primary_signal_id)
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    now = utcnow()
    plan = Plan(
        business_id=business_id,
        created_by_user_id=created_by_user_id,
        assigned_to_user_id=assigned_to_user_id,
        title=title,
        intent=intent,
        case_id=case_id,
        status="draft",
        created_at=now,
        updated_at=now,
        source_action_id=source_action_id,
        primary_signal_id=primary_signal_id,
        idempotency_key=idempotency_key,
    )
    db.add(plan)
    db.flush()

    for condition in conditions:
        db.add(
            PlanCondition(
                plan_id=plan.id,
                type=condition["type"],
                signal_id=condition.get("signal_id"),
                metric_key=condition.get("metric_key"),
                baseline_window_days=condition["baseline_window_days"],
                evaluation_window_days=condition["evaluation_window_days"],
                threshold=condition.get("threshold"),
                direction=condition["direction"],
                created_at=now,
            )
        )

    db.add(
        PlanStateEvent(
            plan_id=plan.id,
            actor_user_id=created_by_user_id,
            event_type="created",
            from_status=None,
            to_status="draft",
            note=None,
        )
    )
    return plan


def create_plan_from_action(
    db: Session,
    *,
    business_id: str,
    action_id: str,
    actor_user_id: str,
) -> tuple[str, bool]:
    _require_business(db, business_id)
    action = db.get(ActionItem, action_id)
    if not action or action.business_id != business_id:
        raise HTTPException(status_code=404, detail="action not found")

    existing = (
        db.execute(
            select(Plan)
            .where(
                Plan.business_id == business_id,
                Plan.source_action_id == action.id,
            )
            .order_by(Plan.created_at.asc(), Plan.id.asc())
        )
        .scalars()
        .first()
    )
    if existing:
        return existing.id, False

    signal_type: Optional[str] = None
    if isinstance(action.evidence_json, dict):
        signal_type = action.evidence_json.get("signal_type")
    if not signal_type and action.source_signal_id:
        signal_state = (
            db.execute(
                select(HealthSignalState).where(
                    HealthSignalState.business_id == business_id,
                    HealthSignalState.signal_id == action.source_signal_id,
                )
            )
            .scalars()
            .first()
        )
        signal_type = signal_state.signal_type if signal_state else None

    domain = _signal_domain(signal_type)
    intent_by_domain = {
        "expense": "reduce expense creep",
        "expenses": "reduce expense creep",
        "liquidity": "prevent cash shortfall",
        "revenue": "stabilize revenue timing",
    }
    intent = intent_by_domain.get(domain, "resolve flagged risk")
    title = f"Remediation: {action.title}"[:200]
    conditions: list[dict[str, Any]] = [
        {
            "type": "signal_resolved",
            "signal_id": action.source_signal_id,
            "baseline_window_days": 0,
            "evaluation_window_days": 14,
            "direction": "resolve",
        },
        {
            "type": "metric_delta",
            "metric_key": "health_score",
            "baseline_window_days": 7,
            "evaluation_window_days": 7,
            "threshold": 1.0,
            "direction": "improve",
        },
    ]
    case_id = None
    if action.source_signal_id:
        case_id = case_engine_service.get_case_id_for_signal(db, business_id, action.source_signal_id)
    if not case_id:
        raise HTTPException(status_code=400, detail="action signal is not attached to a case")

    plan = create_plan(
        db,
        business_id=business_id,
        created_by_user_id=actor_user_id,
        title=title,
        intent=intent,
        case_id=case_id,
        source_action_id=action.id,
        primary_signal_id=action.source_signal_id,
        assigned_to_user_id=action.assigned_to_user_id,
        idempotency_key=f"from_action:{action.id}",
        conditions=conditions,
    )
    case_engine_service.emit_plan_event(db, plan.case_id, "PLAN_CREATED", {"plan_id": plan.id, "source_action_id": action.id})
    log_audit_event(
        db,
        business_id=business_id,
        event_type="plan_created_from_action",
        actor=actor_user_id,
        reason="plan seeded from action",
        before={"action_id": action.id, "plan_id": None},
        after={"action_id": action.id, "plan_id": plan.id},
    )
    return plan.id, True


def activate_plan(db: Session, business_id: str, plan_id: str, actor_user_id: str) -> Plan:
    plan = _require_plan(db, business_id, plan_id)
    if plan.status != "draft":
        raise HTTPException(status_code=400, detail="plan is not in draft status")
    now = utcnow()
    plan.status = "active"
    plan.activated_at = now
    plan.updated_at = now
    db.add(plan)
    db.add(
        PlanStateEvent(
            plan_id=plan.id,
            actor_user_id=actor_user_id,
            event_type="activated",
            from_status="draft",
            to_status="active",
            note=None,
        )
    )
    case_engine_service.emit_plan_event(db, plan.case_id, "PLAN_UPDATED", {"plan_id": plan.id, "status": "active"})
    return plan


def assign_plan(db: Session, business_id: str, plan_id: str, actor_user_id: str, assigned_to_user_id: Optional[str]) -> Plan:
    plan = _require_plan(db, business_id, plan_id)
    plan.assigned_to_user_id = assigned_to_user_id
    plan.updated_at = utcnow()
    db.add(plan)
    db.add(
        PlanStateEvent(
            plan_id=plan.id,
            actor_user_id=actor_user_id,
            event_type="assigned",
            from_status=plan.status,
            to_status=plan.status,
            note=f"assigned_to={assigned_to_user_id or 'unassigned'}",
        )
    )
    case_engine_service.emit_plan_event(db, plan.case_id, "PLAN_UPDATED", {"plan_id": plan.id, "assigned_to_user_id": assigned_to_user_id})
    return plan


def add_plan_note(db: Session, business_id: str, plan_id: str, actor_user_id: str, note: str) -> Plan:
    plan = _require_plan(db, business_id, plan_id)
    plan.updated_at = utcnow()
    db.add(plan)
    db.add(
        PlanStateEvent(
            plan_id=plan.id,
            actor_user_id=actor_user_id,
            event_type="note_added",
            from_status=plan.status,
            to_status=plan.status,
            note=note,
        )
    )
    case_engine_service.emit_plan_event(db, plan.case_id, "PLAN_UPDATED", {"plan_id": plan.id, "note": note})
    return plan


def close_plan(
    db: Session,
    business_id: str,
    plan_id: str,
    actor_user_id: str,
    *,
    outcome: str,
    note: Optional[str],
) -> Plan:
    if outcome not in {"succeeded", "failed", "canceled"}:
        raise HTTPException(status_code=400, detail="invalid outcome")
    plan = _require_plan(db, business_id, plan_id)
    now = utcnow()
    from_status = plan.status
    plan.status = outcome
    plan.closed_at = now
    plan.updated_at = now
    db.add(plan)
    db.add(
        PlanStateEvent(
            plan_id=plan.id,
            actor_user_id=actor_user_id,
            event_type=outcome,
            from_status=from_status,
            to_status=outcome,
            note=note,
        )
    )
    case_engine_service.emit_plan_event(db, plan.case_id, "PLAN_COMPLETED", {"plan_id": plan.id, "outcome": outcome})
    return plan


def refresh_plan(db: Session, business_id: str, plan_id: str) -> PlanRefreshResult:
    plan = _require_plan(db, business_id, plan_id)
    if plan.status != "active":
        raise HTTPException(status_code=400, detail="plan is not active")

    now = utcnow()
    conditions = (
        db.execute(select(PlanCondition).where(PlanCondition.plan_id == plan.id).order_by(PlanCondition.created_at.asc()))
        .scalars()
        .all()
    )
    evaluation_start, evaluation_end = _evaluation_window(plan, conditions[0], now) if conditions else (now.date(), now.date())

    condition_results: List[Dict[str, Any]] = []
    has_success = False
    has_improving = False
    has_worsening = False
    success_candidate = False
    signal_state_value: Optional[str] = None
    metric_value: Optional[float] = None
    metric_baseline: Optional[float] = None
    metric_delta: Optional[float] = None

    for condition in conditions:
        evaluation_start, evaluation_end = _evaluation_window(plan, condition, now)
        result: Dict[str, Any] = {
            "condition_id": condition.id,
            "type": condition.type,
            "signal_id": condition.signal_id,
            "metric_key": condition.metric_key,
            "baseline_window_days": condition.baseline_window_days,
            "evaluation_window_days": condition.evaluation_window_days,
            "threshold": condition.threshold,
            "direction": condition.direction,
            "evaluation_start": evaluation_start.isoformat(),
            "evaluation_end": evaluation_end.isoformat(),
        }

        if condition.type == "signal_resolved":
            state = None
            if condition.signal_id:
                state = db.get(HealthSignalState, (business_id, condition.signal_id))
            status = state.status if state else None
            result["signal_state"] = status
            is_success = _signal_success(state, condition, evaluation_end)
            verdict = "success" if is_success else "no_change"
            result["verdict"] = verdict
            if status and signal_state_value is None:
                signal_state_value = status
            if is_success:
                success_candidate = True
                has_success = True
        elif condition.type == "metric_delta":
            baseline_start, baseline_end = _baseline_window(condition, evaluation_start)
            values, dates, message_ids = _daily_brief_values(
                db,
                business_id,
                baseline_start,
                baseline_end,
                condition.metric_key or "",
            )
            baseline_avg = _average(values)
            evaluation_values, evaluation_dates, evaluation_message_ids = _daily_brief_values(
                db,
                business_id,
                evaluation_start,
                evaluation_end,
                condition.metric_key or "",
            )
            evaluation_avg = _average(evaluation_values)
            delta = None
            if baseline_avg is not None and evaluation_avg is not None:
                delta = evaluation_avg - baseline_avg
            verdict, condition_success = _metric_verdict(delta, condition)
            result.update(
                {
                    "metric_baseline": baseline_avg,
                    "metric_value": evaluation_avg,
                    "metric_delta": delta,
                    "verdict": verdict,
                    "baseline_window": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
                    "evaluation_window": {"start": evaluation_start.isoformat(), "end": evaluation_end.isoformat()},
                    "baseline_dates": dates,
                    "evaluation_dates": evaluation_dates,
                    "baseline_message_ids": message_ids,
                    "evaluation_message_ids": evaluation_message_ids,
                }
            )
            if metric_value is None:
                metric_value = evaluation_avg
                metric_baseline = baseline_avg
                metric_delta = delta
            if condition_success:
                success_candidate = True
                has_success = True
        else:
            verdict = "no_change"
            result["verdict"] = verdict

        condition_results.append(result)
        if result["verdict"] == "improving":
            has_improving = True
        if result["verdict"] == "worsening":
            has_worsening = True

    if has_success:
        best_verdict = "success"
    elif has_worsening:
        best_verdict = "worsening"
    elif has_improving:
        best_verdict = "improving"
    else:
        best_verdict = "no_change"

    evidence = {
        "conditions": condition_results,
    }

    observation = PlanObservation(
        plan_id=plan.id,
        observed_at=now,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        signal_state=signal_state_value,
        metric_value=metric_value,
        metric_baseline=metric_baseline,
        metric_delta=metric_delta,
        verdict=best_verdict,
        evidence_json=evidence,
        created_at=now,
    )
    db.add(observation)
    return PlanRefreshResult(observation=observation, success_candidate=success_candidate)
