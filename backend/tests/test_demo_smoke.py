from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_demo_smoke.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import (
    Organization,
    Business,
    RawEvent,
    Account,
    Category,
    BusinessCategoryMap,
    CategoryRule,
)


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _create_business(db_session):
    org = Organization(name="Demo Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Demo Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _make_event(business_id: str, source_event_id: str, description: str, amount: float):
    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": source_event_id,
            "amount": amount,
            "name": description,
            "merchant_name": description,
        },
    }
    return RawEvent(
        business_id=business_id,
        source="bank",
        source_event_id=source_event_id,
        occurred_at=datetime(2024, 1, 12, 12, 0, tzinfo=timezone.utc),
        payload=payload,
    )


def _create_category_rule(db_session, business_id: str):
    account = Account(
        business_id=business_id,
        name="Utilities Account",
        type="expense",
        subtype="utilities",
    )
    db_session.add(account)
    db_session.flush()
    category = Category(
        business_id=business_id,
        name="Utilities",
        account_id=account.id,
    )
    db_session.add(category)
    db_session.flush()
    mapping = BusinessCategoryMap(
        business_id=business_id,
        system_key="utilities",
        category_id=category.id,
    )
    db_session.add(mapping)
    db_session.flush()
    rule = CategoryRule(
        business_id=business_id,
        category_id=category.id,
        contains_text="coffee",
        priority=1,
        active=True,
    )
    db_session.add(rule)
    db_session.flush()
    return rule


def _drop_rule_run_columns(db_session):
    db_session.execute(text("ALTER TABLE category_rules RENAME TO category_rules_old"))
    db_session.execute(
        text(
            """
            CREATE TABLE category_rules (
                id VARCHAR(36) PRIMARY KEY,
                business_id VARCHAR(36) NOT NULL,
                category_id VARCHAR(36) NOT NULL,
                contains_text VARCHAR(120) NOT NULL,
                direction VARCHAR(10),
                account VARCHAR(60),
                priority INTEGER NOT NULL,
                active BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    db_session.execute(
        text(
            """
            INSERT INTO category_rules (
                id,
                business_id,
                category_id,
                contains_text,
                direction,
                account,
                priority,
                active,
                created_at
            )
            SELECT
                id,
                business_id,
                category_id,
                contains_text,
                direction,
                account,
                priority,
                active,
                created_at
            FROM category_rules_old
            """
        )
    )
    db_session.execute(text("DROP TABLE category_rules_old"))
    db_session.commit()


def test_demo_health_and_transactions_smoke(client, db_session):
    biz = _create_business(db_session)
    db_session.add(_make_event(biz.id, "evt-1", "Coffee Shop", -12.34))
    db_session.add(_make_event(biz.id, "evt-2", "Client Payment", 250.0))
    db_session.commit()

    health = client.get(f"/demo/health/{biz.id}")
    assert health.status_code == 200
    health_json = health.json()
    for key in [
        "business_id",
        "name",
        "risk",
        "health_score",
        "signals",
        "health_signals",
        "facts",
        "facts_full",
        "ledger_preview",
    ]:
        assert key in health_json

    txns = client.get(f"/demo/transactions/{biz.id}")
    assert txns.status_code == 200
    txns_json = txns.json()
    for key in ["business_id", "name", "count", "transactions", "as_of"]:
        assert key in txns_json


def test_rule_preview_apply_handles_missing_last_run_columns(client, db_session):
    biz = _create_business(db_session)
    db_session.add(_make_event(biz.id, "evt-1", "Coffee Shop", -12.34))
    rule = _create_category_rule(db_session, biz.id)
    db_session.commit()

    _drop_rule_run_columns(db_session)

    preview = client.get(f"/categorize/{biz.id}/rules/{rule.id}/preview")
    assert preview.status_code == 200
    assert "matched" in preview.json()

    applied = client.post(f"/categorize/{biz.id}/rules/{rule.id}/apply")
    assert applied.status_code == 200


def test_demo_dashboard_payload_ordering(client, db_session):
    biz = _create_business(db_session)
    db_session.add(_make_event(biz.id, "evt-1", "Coffee Shop", -120.0))
    db_session.add(_make_event(biz.id, "evt-2", "Client Payment", 500.0))
    db_session.commit()

    resp = client.get(f"/demo/dashboard/{biz.id}")
    assert resp.status_code == 200
    payload = resp.json()

    for key in ["metadata", "kpis", "signals", "trends"]:
        assert key in payload

    kpis = payload["kpis"]
    for key in [
        "current_cash",
        "last_30d_inflow",
        "last_30d_outflow",
        "last_30d_net",
        "prev_30d_inflow",
        "prev_30d_outflow",
        "prev_30d_net",
    ]:
        assert key in kpis

    signals = payload["signals"]
    assert signals
    sorted_signals = sorted(signals, key=lambda s: (-int(s["priority"]), str(s["key"])))
    assert signals == sorted_signals
