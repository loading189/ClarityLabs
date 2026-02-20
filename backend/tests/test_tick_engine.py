import backend.app.sim.models  # noqa: F401
from datetime import datetime, timedelta, timezone

from backend.app.models import (
    Business,
    BusinessMembership,
    Case,
    CaseEvent,
    HealthSignalState,
    Organization,
    TickRun,
    User,
    WorkItem,
)
from backend.app.services import case_engine_service, tick_service, work_engine_service


def _seed_business(db):
    suffix = datetime.now(timezone.utc).timestamp()
    org = Organization(name="Org")
    db.add(org)
    db.flush()
    biz = Business(org_id=org.id, name="Biz")
    db.add(biz)
    user = User(email=f"tick{suffix}@test.com", name="tick")
    db.add(user)
    db.flush()
    db.add(BusinessMembership(business_id=biz.id, user_id=user.id, role="owner"))
    db.commit()
    return biz


def _seed_signal(db, business_id: str, signal_id: str, *, severity: str = "warning"):
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


def _seed_case(db, business_id: str, *, case_severity: str = "high") -> str:
    occurred_at = datetime.now(timezone.utc) - timedelta(days=10)
    signal_id = f"sig-{occurred_at.timestamp()}-{case_severity}"
    _seed_signal(db, business_id, signal_id)
    case_id = case_engine_service.aggregate_signal_into_case(
        db,
        business_id=business_id,
        signal_id=signal_id,
        signal_type="liquidity.runway_low",
        domain="liquidity",
        severity=case_severity,
        occurred_at=occurred_at,
    )
    db.commit()
    return case_id


def test_tick_creates_work_items_deterministically(sqlite_session):
    biz = _seed_business(sqlite_session)
    case_id = _seed_case(sqlite_session, biz.id)

    first = tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-01")
    sqlite_session.commit()
    second = tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-01")

    assert first == second
    items = sqlite_session.query(WorkItem).filter(WorkItem.case_id == case_id).all()
    assert len(items) > 0


def test_tick_idempotent_in_same_bucket(sqlite_session):
    biz = _seed_business(sqlite_session)
    case_id = _seed_case(sqlite_session, biz.id)

    first = tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-02")
    sqlite_session.commit()
    first_events = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id).count()

    second = tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-02")
    sqlite_session.commit()
    second_events = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id).count()

    assert first == second
    assert sqlite_session.query(TickRun).filter(TickRun.business_id == biz.id, TickRun.bucket == "2026-02-02").count() == 1
    assert first_events == second_events


def test_tick_respects_snoozed_items(sqlite_session):
    biz = _seed_business(sqlite_session)
    case_id = _seed_case(sqlite_session, biz.id)
    tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-03")
    sqlite_session.commit()

    item = sqlite_session.query(WorkItem).filter(WorkItem.case_id == case_id, WorkItem.type == "UNASSIGNED_CASE").first()
    work_engine_service.snooze_work_item(sqlite_session, item.id, snoozed_until=datetime.now(timezone.utc) + timedelta(days=2))
    sqlite_session.commit()

    tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-04")
    sqlite_session.commit()

    items = sqlite_session.query(WorkItem).filter(WorkItem.case_id == case_id, WorkItem.type == "UNASSIGNED_CASE").all()
    assert len(items) == 1
    assert items[0].status == "snoozed"


def test_tick_without_apply_does_not_change_case(sqlite_session, monkeypatch):
    biz = _seed_business(sqlite_session)
    case_id = _seed_case(sqlite_session, biz.id)
    case_before = sqlite_session.get(Case, case_id)
    before_status = case_before.status
    before_severity = case_before.severity

    monkeypatch.setattr(
        case_engine_service,
        "_diff_case_state",
        lambda *_args, **_kwargs: case_engine_service.CaseStateDiff(
            is_match=False,
            status_changed=True,
            status_from="open",
            status_to="escalated",
            severity_changed=False,
            severity_from="high",
            severity_to="high",
            risk_delta_changed=False,
            risk_delta_from=None,
            risk_delta_to=None,
            sla_changed=False,
            sla_from=datetime.now(timezone.utc),
            sla_to=datetime.now(timezone.utc),
            last_activity_at_changed=False,
            last_activity_at_from=datetime.now(timezone.utc),
            last_activity_at_to=datetime.now(timezone.utc),
            reasons=["forced-diff"],
        ),
    )

    result = tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-05", apply_recompute=False)
    sqlite_session.commit()
    case_after = sqlite_session.get(Case, case_id)

    assert result.cases_recompute_changed >= 1
    assert result.cases_recompute_applied == 0
    assert case_after.status == before_status
    assert case_after.severity == before_severity


def test_tick_apply_emits_single_recompute_event(sqlite_session, monkeypatch):
    biz = _seed_business(sqlite_session)
    case_id = _seed_case(sqlite_session, biz.id)

    monkeypatch.setattr(
        case_engine_service,
        "_diff_case_state",
        lambda *_args, **_kwargs: case_engine_service.CaseStateDiff(
            is_match=False,
            status_changed=True,
            status_from="open",
            status_to="escalated",
            severity_changed=False,
            severity_from="high",
            severity_to="high",
            risk_delta_changed=False,
            risk_delta_from=None,
            risk_delta_to=None,
            sla_changed=False,
            sla_from=datetime.now(timezone.utc),
            sla_to=datetime.now(timezone.utc),
            last_activity_at_changed=False,
            last_activity_at_from=datetime.now(timezone.utc),
            last_activity_at_to=datetime.now(timezone.utc),
            reasons=["forced-diff"],
        ),
    )

    result = tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-06", apply_recompute=True)
    sqlite_session.commit()

    events = sqlite_session.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.event_type == "CASE_RECOMPUTE_APPLIED").count()
    assert result.cases_recompute_applied == 1
    assert events == 1


def test_review_due_idempotency_bucket_same_day(sqlite_session):
    biz = _seed_business(sqlite_session)
    case_id = _seed_case(sqlite_session, biz.id)

    case = sqlite_session.get(Case, case_id)
    case.next_review_at = datetime(2026, 2, 7, 10, 0, tzinfo=timezone.utc)
    sqlite_session.commit()

    tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-07")
    sqlite_session.commit()
    tick_service.run_tick(sqlite_session, business_id=biz.id, bucket="2026-02-07")
    sqlite_session.commit()

    keys = [
        row.idempotency_key
        for row in sqlite_session.query(WorkItem)
        .filter(WorkItem.case_id == case_id, WorkItem.type == "REVIEW_DUE")
        .all()
    ]
    assert keys == [f"{case_id}:REVIEW_DUE:2026-02-07"]
