from datetime import datetime, timezone, timedelta
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_category_rules.db")

from backend.app.db import Base, SessionLocal, engine
from backend.app.sim import models as sim_models  # noqa: F401
from backend.app.models import (
    Organization,
    Business,
    Account,
    Category,
    BusinessCategoryMap,
    CategoryRule,
)
from backend.app.api.categorize import (
    list_category_rules,
    update_category_rule,
    delete_category_rule,
    CategoryRulePatch,
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


def _create_business(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    biz = Business(org_id=org.id, name="Test Biz")
    db_session.add(biz)
    db_session.flush()
    return biz


def _create_category(db_session, business_id: str, name: str, system_key: str):
    account = Account(
        business_id=business_id,
        name=f"{name} Account",
        type="expense",
        subtype=system_key,
    )
    db_session.add(account)
    db_session.flush()
    category = Category(
        business_id=business_id,
        name=name,
        account_id=account.id,
    )
    db_session.add(category)
    db_session.flush()
    mapping = BusinessCategoryMap(
        business_id=business_id,
        system_key=system_key,
        category_id=category.id,
    )
    db_session.add(mapping)
    db_session.flush()
    return category


def test_list_category_rules_orders_by_priority_then_created_at(db_session):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")

    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rule_a = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="alpha",
        priority=1,
        active=True,
        created_at=base_time,
    )
    rule_b = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="beta",
        priority=1,
        active=True,
        created_at=base_time + timedelta(minutes=5),
    )
    rule_c = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="gamma",
        priority=2,
        active=True,
        created_at=base_time - timedelta(minutes=10),
    )
    db_session.add_all([rule_a, rule_b, rule_c])
    db_session.commit()

    res = list_category_rules(
        biz.id,
        active_only=False,
        limit=10,
        offset=0,
        db=db_session,
    )

    assert [r.id for r in res] == [rule_a.id, rule_b.id, rule_c.id]


def test_update_category_rule_and_rejects_uncategorized(db_session):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")
    new_category = _create_category(db_session, biz.id, "Meals", "meals")
    uncategorized = _create_category(db_session, biz.id, "Uncategorized", "uncategorized")

    rule = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="acme",
        priority=50,
        active=True,
    )
    db_session.add(rule)
    db_session.commit()

    patch = CategoryRulePatch(
        category_id=new_category.id,
        priority=10,
        active=False,
        contains_text="Acme Corp",
        direction="outflow",
        account="main",
    )
    updated = update_category_rule(biz.id, rule.id, patch, db_session)

    assert updated.category_id == new_category.id
    assert updated.priority == 10
    assert updated.active is False
    assert updated.contains_text == "acme corp"
    assert updated.direction == "outflow"
    assert updated.account == "main"

    bad_patch = CategoryRulePatch(category_id=uncategorized.id)
    with pytest.raises(HTTPException) as excinfo:
        update_category_rule(biz.id, rule.id, bad_patch, db_session)
    assert excinfo.value.status_code == 400


def test_delete_category_rule(db_session):
    biz = _create_business(db_session)
    category = _create_category(db_session, biz.id, "Software", "software")

    rule = CategoryRule(
        business_id=biz.id,
        category_id=category.id,
        contains_text="omega",
        priority=5,
        active=True,
    )
    db_session.add(rule)
    db_session.commit()

    res = delete_category_rule(biz.id, rule.id, db_session)
    assert res["deleted"] is True

    remaining = db_session.query(CategoryRule).filter(CategoryRule.business_id == biz.id).all()
    assert remaining == []
