from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Case, TickRun, WorkItem
from backend.app.services import case_engine_service, work_engine_service


ACTIVE_CASE_STATUSES = ("open", "monitoring", "escalated")
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass(frozen=True)
class TickError:
    case_id: Optional[str]
    message: str


@dataclass(frozen=True)
class TickResult:
    business_id: str
    bucket: str
    cases_processed: int
    cases_recompute_changed: int
    cases_recompute_applied: int
    work_items_created: int
    work_items_updated: int
    work_items_auto_resolved: int
    work_items_unchanged: int
    errors: list[dict]
    started_at: str
    finished_at: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def tick_bucket(now_utc: datetime, *, hourly: bool = False) -> str:
    normalized = now_utc.astimezone(timezone.utc)
    if hourly:
        return normalized.strftime("%Y-%m-%dT%H")
    return normalized.strftime("%Y-%m-%d")


def _count_materialize_changes(before: dict[str, WorkItem], after: list[WorkItem]) -> tuple[int, int, int, int]:
    created = 0
    updated = 0
    auto_resolved = 0
    unchanged = 0

    for row in after:
        existing = before.get(row.idempotency_key)
        if existing is None:
            created += 1
            continue

        if existing.status in {"open", "snoozed"} and row.status == "completed":
            auto_resolved += 1
            continue

        if row.priority != existing.priority or row.due_at != existing.due_at:
            updated += 1
            continue

        unchanged += 1

    return created, updated, auto_resolved, unchanged


def _result_from_row(row: TickRun) -> TickResult:
    if not row.result_json:
        raise ValueError("tick run is missing result_json")
    return TickResult(**row.result_json)


def run_tick(
    db: Session,
    *,
    business_id: str,
    bucket: str | None = None,
    apply_recompute: bool = False,
    materialize_work: bool = True,
    limit_cases: int | None = None,
) -> TickResult:
    started_at_dt = _now_utc()
    effective_bucket = bucket or tick_bucket(started_at_dt)

    existing = db.execute(
        select(TickRun)
        .where(TickRun.business_id == business_id, TickRun.bucket == effective_bucket)
        .order_by(TickRun.started_at.asc(), TickRun.id.asc())
    ).scalars().first()
    if existing and existing.finished_at is not None:
        return _result_from_row(existing)

    run = existing
    if run is None:
        run = TickRun(business_id=business_id, bucket=effective_bucket, started_at=started_at_dt)
        db.add(run)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            repeat = db.execute(
                select(TickRun).where(TickRun.business_id == business_id, TickRun.bucket == effective_bucket)
            ).scalars().first()
            if repeat and repeat.finished_at is not None:
                return _result_from_row(repeat)
            raise

    cases_stmt = (
        select(Case)
        .where(Case.business_id == business_id, Case.status.in_(ACTIVE_CASE_STATUSES))
        .order_by(
            Case.severity.desc(),
            Case.last_activity_at.desc(),
            Case.opened_at.asc(),
            Case.id.asc(),
        )
    )
    rows = db.execute(cases_stmt).scalars().all()
    rows = sorted(
        rows,
        key=lambda case: (
            -SEVERITY_RANK.get((case.severity or "low").lower(), 0),
            -(case.last_activity_at.timestamp() if case.last_activity_at else 0),
            case.opened_at.timestamp() if case.opened_at else 0,
            case.id,
        ),
    )
    if limit_cases is not None:
        rows = rows[:limit_cases]

    errors: list[TickError] = []
    recompute_changed = 0
    recompute_applied = 0
    work_created = 0
    work_updated = 0
    work_auto_resolved = 0
    work_unchanged = 0

    for case in rows:
        try:
            recompute_result = case_engine_service.recompute_case(db, case.id, apply=apply_recompute)
            if not recompute_result["diff"]["is_match"]:
                recompute_changed += 1
            if recompute_result["applied"]:
                recompute_applied += 1

            if materialize_work:
                before_items = {
                    item.idempotency_key: item
                    for item in db.execute(select(WorkItem).where(WorkItem.case_id == case.id)).scalars().all()
                }
                after_items = work_engine_service.materialize_work_items_for_case(db, case.id)
                created, updated, auto_resolved, unchanged = _count_materialize_changes(before_items, after_items)
                work_created += created
                work_updated += updated
                work_auto_resolved += auto_resolved
                work_unchanged += unchanged
        except Exception as exc:  # pragma: no cover - defensive surface
            errors.append(TickError(case_id=case.id, message=str(exc)))

    finished_at_dt = _now_utc()
    result = TickResult(
        business_id=business_id,
        bucket=effective_bucket,
        cases_processed=len(rows),
        cases_recompute_changed=recompute_changed,
        cases_recompute_applied=recompute_applied,
        work_items_created=work_created,
        work_items_updated=work_updated,
        work_items_auto_resolved=work_auto_resolved,
        work_items_unchanged=work_unchanged,
        errors=[asdict(err) for err in errors],
        started_at=started_at_dt.isoformat(),
        finished_at=finished_at_dt.isoformat(),
    )
    run.finished_at = finished_at_dt
    run.result_json = asdict(result)
    db.flush()
    return result


def get_last_tick(db: Session, *, business_id: str) -> Optional[TickRun]:
    return (
        db.execute(
            select(TickRun)
            .where(TickRun.business_id == business_id, TickRun.finished_at.is_not(None))
            .order_by(TickRun.finished_at.desc(), TickRun.id.desc())
        )
        .scalars()
        .first()
    )
