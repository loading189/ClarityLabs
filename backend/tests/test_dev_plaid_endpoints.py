from __future__ import annotations

import backend.app.sim.models  # noqa: F401
import backend.app.sim_v2.models  # noqa: F401

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.app.api.routes.dev_plaid import PumpTransactionsIn, pump_transactions_endpoint
from backend.app.models import Business, BusinessMembership, IntegrationConnection, Organization, User
from backend.app.services.dev_tools import require_dev_tools
from backend.app.services import plaid_dev_service


def _seed_membership(session):
    org = Organization(name="Org")
    existing = session.execute(select(func.count()).select_from(User)).scalar_one()
    user = User(email=f"dev{existing}@example.com", name="Dev")
    session.add_all([org, user])
    session.flush()
    biz = Business(org_id=org.id, name="Biz")
    session.add(biz)
    session.flush()
    session.add(BusinessMembership(business_id=biz.id, user_id=user.id, role="staff"))
    session.commit()
    return biz, user


def test_dev_gating_blocks_when_disabled(monkeypatch):
    monkeypatch.setenv("CLARITY_DEV_TOOLS", "0")
    with pytest.raises(HTTPException) as exc:
        require_dev_tools()
    assert exc.value.status_code == 404


def test_missing_plaid_config_returns_helpful_error(monkeypatch):
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.delenv("PLAID_ENV", raising=False)
    with pytest.raises(HTTPException) as exc:
        plaid_dev_service.require_plaid_sandbox_config()
    assert exc.value.status_code == 400
    assert "Missing Plaid sandbox config" in exc.value.detail


def test_ensure_dynamic_item_idempotent_and_force_recreate(sqlite_session, monkeypatch):
    biz, _ = _seed_membership(sqlite_session)
    monkeypatch.setenv("PLAID_CLIENT_ID", "client")
    monkeypatch.setenv("PLAID_SECRET", "secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")

    calls = {"public": 0, "exchange": 0}

    class FakeClient:
        def post(self, path, payload):
            assert path == "/sandbox/public_token/create"
            calls["public"] += 1
            return {"public_token": "public-token"}

    class FakeAdapter:
        def __init__(self):
            self.client = FakeClient()

        def exchange_public_token(self, *, public_token: str):
            calls["exchange"] += 1
            return {"access_token": f"access-{calls['exchange']}", "item_id": f"item-{calls['exchange']}"}

    monkeypatch.setattr(plaid_dev_service, "PlaidAdapter", FakeAdapter)

    first = plaid_dev_service.ensure_dynamic_item(sqlite_session, biz.id)
    sqlite_session.commit()
    second = plaid_dev_service.ensure_dynamic_item(sqlite_session, biz.id)
    sqlite_session.commit()

    assert first.id == second.id
    assert calls == {"public": 1, "exchange": 1}
    assert sqlite_session.execute(select(func.count()).select_from(IntegrationConnection)).scalar_one() == 1

    third = plaid_dev_service.ensure_dynamic_item(sqlite_session, biz.id, force_recreate=True)
    sqlite_session.commit()
    assert third.id == first.id
    assert calls == {"public": 2, "exchange": 2}


def test_pump_service_is_deterministic_and_batches(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, path, payload):
            self.calls.append((path, payload))
            return {"ok": True}

    fake_client = FakeClient()
    connection = IntegrationConnection(business_id="b1", provider="plaid", plaid_access_token="token")
    monkeypatch.setattr(plaid_dev_service.time, "sleep", lambda _: None)

    one = plaid_dev_service.pump_sandbox_transactions(
        connection=connection,
        business_id="b1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 20),
        daily_txn_count=25,
        profile="mixed",
        client=fake_client,
    )
    two = plaid_dev_service.pump_sandbox_transactions(
        connection=connection,
        business_id="b1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 20),
        daily_txn_count=25,
        profile="mixed",
        client=FakeClient(),
    )

    assert len(fake_client.calls) == 3
    assert all(call[0] == "/sandbox/transactions/create" for call in fake_client.calls)
    assert one.seed_key == two.seed_key
    assert one.created == two.created


def test_pump_endpoint_calls_hooks_in_order(sqlite_session, monkeypatch):
    biz, _ = _seed_membership(sqlite_session)
    sqlite_session.add(
        IntegrationConnection(
            business_id=biz.id,
            provider="plaid",
            is_enabled=True,
            status="connected",
            plaid_access_token="tok",
            plaid_item_id="item",
            plaid_environment="sandbox",
        )
    )
    sqlite_session.commit()

    monkeypatch.setenv("CLARITY_DEV_TOOLS", "1")
    monkeypatch.setenv("PLAID_CLIENT_ID", "client")
    monkeypatch.setenv("PLAID_SECRET", "secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")

    order = []

    class _Pump:
        seed_key = "seed"
        requested = 10
        created = 9

    monkeypatch.setattr("backend.app.api.routes.dev_plaid.pump_sandbox_transactions", lambda **kwargs: order.append("pump") or _Pump())
    monkeypatch.setattr(
        "backend.app.api.routes.dev_plaid.run_plaid_sync",
        lambda db, business_id: order.append("sync") or {"inserted": 5, "cursor": "c1"},
    )
    monkeypatch.setattr(
        "backend.app.api.routes.dev_plaid.monitoring_service.pulse",
        lambda db, business_id, force_run=True: order.append("pipeline") or {"counts": {"open": 2}},
    )

    class _ActionResult:
        created_count = 1
        updated_count = 2
        suppressed_count = 3
        suppression_reasons = {"duplicate": 3}

    monkeypatch.setattr(
        "backend.app.api.routes.dev_plaid.generate_actions_for_business",
        lambda db, business_id: order.append("actions") or _ActionResult(),
    )

    payload = pump_transactions_endpoint(
        biz.id,
        PumpTransactionsIn(start_date=date(2026, 1, 1), end_date=date(2026, 1, 10), daily_txn_count=25, profile="mixed"),
        db=sqlite_session,
    )

    assert order == ["pump", "sync", "pipeline", "actions"]
    assert payload["sync"]["cursor"] == "c1"
    assert payload["pipeline"]["ledger_rows"] >= 0
    assert "actions" in payload and "created_count" in payload["actions"]
