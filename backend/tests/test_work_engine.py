import backend.app.sim.models  # noqa: F401
from datetime import datetime, timedelta, timezone

from backend.app.models import (
    Business,
    BusinessMembership,
    Case,
    CaseEvent,
    CaseSignal,
    HealthSignalState,
    Organization,
    User,
    WorkItem,
)
from backend.app.services import case_engine_service, work_engine_service


def _seed_business(db):
    suffix = datetime.now(timezone.utc).timestamp()
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    user = User(email=f"work{suffix}@test.com", name="work")
    db.add(user)
    db.flush()
    db.add(BusinessMembership(business_id=biz.id, user_id=user.id, role="owner"))
    db.commit()
    return biz, user


def _seed_signal(db, business_id: str, signal_id: str, severity: str = "warning"):
    now = datetime.now(timezone.utc)
    db.add(
        HealthSignalState(
            business_id=business_id,
            signal_id=signal_id,
            signal_type="liquidity.runway_low",
            status="open",
            severity=severity,
            title="sig",
            summary="summary",
            payload_json={},
            detected_at=now,
            last_seen_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _seed_case_with_signal(db, business_id: str, *, severity: str = "high") -> str:
    now = datetime.now(timezone.utc) - timedelta(days=10)
    signal_id = f"sig-{now.timestamp()}"
    _seed_signal(db, business_id, signal_id, severity="warning")
    case_id = case_engine_service.aggregate_signal_into_case(
        db,
        business_id=business_id,
        signal_id=signal_id,
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity=severity,
        occurred_at=now,
    )
    db.commit()
    return case_id


def test_deterministic_generation(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    case_id = _seed_case_with_signal(sqlite_session, biz.id, severity="high")
    anchor_now = datetime(2026, 2, 1, tzinfo=timezone.utc)

    first = work_engine_service.generate_work_items_for_case(sqlite_session, case_id, now=anchor_now)
    second = work_engine_service.generate_work_items_for_case(sqlite_session, case_id, now=anchor_now)

    assert first == second


def test_idempotent_materialization(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    case_id = _seed_case_with_signal(sqlite_session, biz.id)

    work_engine_service.materialize_work_items_for_case(sqlite_session, case_id)
    work_engine_service.materialize_work_items_for_case(sqlite_session, case_id)
    sqlite_session.commit()

    keys = [row.idempotency_key for row in sqlite_session.query(WorkItem).filter(WorkItem.case_id == case_id).all()]
    assert len(keys) == len(set(keys))


def test_auto_resolution_emits_event(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    case_id = _seed_case_with_signal(sqlite_session, biz.id)

    work_engine_service.materialize_work_items_for_case(sqlite_session, case_id)
    sqlite_session.commit()

    case = sqlite_session.get(Case, case_id)
    case.assigned_to = "advisor-1"
    sqlite_session.commit()

    before = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "WORK_ITEM_AUTO_RESOLVED").count()
    work_engine_service.materialize_work_items_for_case(sqlite_session, case_id)
    sqlite_session.commit()
    after = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "WORK_ITEM_AUTO_RESOLVED").count()

    unresolved = sqlite_session.query(WorkItem).filter(WorkItem.case_id == case_id, WorkItem.idempotency_key.like(f"{case_id}:UNASSIGNED%"), WorkItem.status == "open").count()
    assert unresolved == 0
    assert after == before + 1


def test_completion_emits_exactly_one_event(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    case_id = _seed_case_with_signal(sqlite_session, biz.id)
    work_engine_service.materialize_work_items_for_case(sqlite_session, case_id)
    sqlite_session.commit()
    work_item = sqlite_session.query(WorkItem).filter(WorkItem.case_id == case_id).first()

    work_engine_service.complete_work_item(sqlite_session, work_item.id)
    work_engine_service.complete_work_item(sqlite_session, work_item.id)
    sqlite_session.commit()
    assert sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "WORK_ITEM_COMPLETED").count() == 1


def test_portfolio_ordering_is_deterministic(sqlite_session):
    biz, _ = _seed_business(sqlite_session)
    case_a = _seed_case_with_signal(sqlite_session, biz.id, severity="high")
    case_b = _seed_case_with_signal(sqlite_session, biz.id, severity="medium")
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)

    sqlite_session.add_all(
        [
            WorkItem(case_id=case_a, business_id=biz.id, type="SLA_BREACH", priority=90, status="open", due_at=now + timedelta(days=1), idempotency_key=f"{case_a}:custom-1"),
            WorkItem(case_id=case_b, business_id=biz.id, type="NO_PLAN", priority=90, status="open", due_at=now + timedelta(hours=1), idempotency_key=f"{case_b}:custom-2"),
            WorkItem(case_id=case_b, business_id=biz.id, type="REVIEW_DUE", priority=50, status="open", due_at=now, idempotency_key=f"{case_b}:custom-3"),
        ]
    )
    sqlite_session.commit()

    rows = work_engine_service.list_work_items(
        sqlite_session,
        business_id=biz.id,
        status="open",
        priority_gte=None,
        due_before=None,
        assigned_only=False,
        case_severity_gte=None,
        sort="priority",
    )

    assert [row["idempotency_key"] for row in rows] == [f"{case_b}:custom-2", f"{case_a}:custom-1", f"{case_b}:custom-3"]
