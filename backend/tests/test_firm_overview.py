from datetime import datetime, timedelta, timezone

from backend.app.models import (
    ActionItem,
    Business,
    BusinessMembership,
    HealthSignalState,
    Organization,
    RawEvent,
    User,
)
from backend.app.services.firm_overview_service import get_firm_overview_for_user

import backend.app.sim.models  # noqa: F401


def _seed_user(session, email: str = "firm@example.com") -> User:
    user = User(email=email, name="Firm User")
    session.add(user)
    session.flush()
    return user


def _seed_business(session, org_name: str, business_name: str) -> Business:
    org = Organization(name=org_name)
    session.add(org)
    session.flush()
    business = Business(org_id=org.id, name=business_name)
    session.add(business)
    session.flush()
    return business


def _add_membership(session, user_id: str, business_id: str) -> None:
    session.add(BusinessMembership(user_id=user_id, business_id=business_id, role="advisor"))
    session.flush()


def test_firm_overview_risk_score_band_and_sorting(sqlite_session):
    now = datetime.now(timezone.utc)
    user = _seed_user(sqlite_session)
    high_risk = _seed_business(sqlite_session, "Org A", "Zulu Foods")
    low_risk = _seed_business(sqlite_session, "Org B", "Alpha Coffee")
    _add_membership(sqlite_session, user.id, high_risk.id)
    _add_membership(sqlite_session, user.id, low_risk.id)

    sqlite_session.add_all(
        [
            HealthSignalState(
                business_id=high_risk.id,
                signal_id="sig-critical",
                status="open",
                severity="critical",
                detected_at=now - timedelta(days=2),
                last_seen_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            ),
            HealthSignalState(
                business_id=high_risk.id,
                signal_id="sig-critical-2",
                status="open",
                severity="critical",
                detected_at=now - timedelta(days=1),
                last_seen_at=now - timedelta(hours=6),
                updated_at=now - timedelta(hours=6),
            ),
            HealthSignalState(
                business_id=high_risk.id,
                signal_id="sig-warning",
                status="open",
                severity="warning",
                detected_at=now - timedelta(days=1),
                last_seen_at=now,
                updated_at=now,
            ),
            HealthSignalState(
                business_id=high_risk.id,
                signal_id="sig-info",
                status="open",
                severity="info",
                detected_at=now - timedelta(hours=1),
                last_seen_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
            ),
        ]
    )

    sqlite_session.add_all(
        [
            ActionItem(
                business_id=high_risk.id,
                action_type="follow_up",
                title="Follow up 1",
                summary="Open action",
                priority=3,
                status="open",
                idempotency_key=f"{high_risk.id}:1",
                created_at=now - timedelta(days=10),
                updated_at=now - timedelta(days=1),
            ),
            ActionItem(
                business_id=high_risk.id,
                action_type="follow_up",
                title="Follow up 2",
                summary="Open action",
                priority=3,
                status="open",
                idempotency_key=f"{high_risk.id}:2",
                created_at=now - timedelta(days=2),
                updated_at=now,
            ),
        ]
    )

    sqlite_session.add_all(
        [
            RawEvent(
                business_id=high_risk.id,
                source="plaid",
                source_event_id="uncat-1",
                occurred_at=now,
                payload={"type": "transaction.posted", "transaction": {"transaction_id": "uncat-1"}},
            ),
            RawEvent(
                business_id=high_risk.id,
                source="plaid",
                source_event_id="uncat-2",
                occurred_at=now,
                payload={"type": "transaction.posted", "transaction": {"transaction_id": "uncat-2"}},
            ),
        ]
    )
    sqlite_session.commit()

    payload = get_firm_overview_for_user(user.id, sqlite_session)
    businesses = payload["businesses"]

    assert [entry["business_name"] for entry in businesses] == ["Zulu Foods", "Alpha Coffee"]

    zulu = businesses[0]
    assert zulu["signals_by_severity"] == {"critical": 2, "warning": 1, "info": 1}
    assert zulu["open_signals"] == 4
    assert zulu["open_actions"] == 2
    assert zulu["stale_actions"] == 1
    assert zulu["uncategorized_txn_count"] == 2
    assert zulu["risk_score"] == 85
    assert zulu["risk_band"] == "at_risk"

    alpha = businesses[1]
    assert alpha["risk_score"] == 0
    assert alpha["risk_band"] == "stable"


def test_firm_overview_zero_data_case(sqlite_session):
    user = _seed_user(sqlite_session, "empty@example.com")
    sqlite_session.commit()

    payload = get_firm_overview_for_user(user.id, sqlite_session)
    assert payload["businesses"] == []
    assert payload["generated_at"] is not None
