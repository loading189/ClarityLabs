from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import os
import random
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.plaid import PlaidAdapter, PlaidClient, plaid_environment
from backend.app.models import IntegrationConnection


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_plaid_sandbox_config() -> None:
    missing = [name for name in ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV") if not os.getenv(name)]
    if missing:
        raise HTTPException(400, f"Missing Plaid sandbox config: {', '.join(missing)}.")
    if plaid_environment() != "sandbox":
        raise HTTPException(400, "PLAID_ENV must be set to 'sandbox' for dev Plaid endpoints.")


def _derive_seed_key(business_id: str, start_date: date, end_date: date, profile: str) -> str:
    return f"{business_id}:{start_date.isoformat()}:{end_date.isoformat()}:{profile}"


def _stable_rng(seed_key: str) -> random.Random:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def ensure_dynamic_item(db: Session, business_id: str, *, force_recreate: bool = False) -> IntegrationConnection:
    require_plaid_sandbox_config()
    existing = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "plaid",
        )
    ).scalar_one_or_none()
    if existing and existing.is_enabled and existing.plaid_access_token and not force_recreate:
        return existing

    adapter = PlaidAdapter()
    public = adapter.client.post(
        "/sandbox/public_token/create",
        {
            "institution_id": "ins_109508",
            "initial_products": ["transactions"],
            "options": {
                "override_username": "user_transactions_dynamic",
                "override_password": "pass_good",
            },
        },
    )
    public_token = public.get("public_token")
    if not public_token:
        raise HTTPException(400, "Unable to create Plaid sandbox public token.")
    exchange = adapter.exchange_public_token(public_token=public_token)
    access_token = exchange.get("access_token")
    item_id = exchange.get("item_id")
    if not access_token or not item_id:
        raise HTTPException(400, "Plaid exchange failed to return access_token/item_id.")

    row = existing or IntegrationConnection(
        business_id=business_id,
        provider="plaid",
        created_at=utcnow(),
    )
    row.status = "connected"
    row.is_enabled = True
    row.disconnected_at = None
    row.connected_at = row.connected_at or utcnow()
    row.plaid_access_token = access_token
    row.plaid_item_id = item_id
    row.plaid_environment = plaid_environment()
    row.last_cursor = None
    row.last_cursor_at = None
    row.last_error = None
    row.last_error_at = None
    row.updated_at = utcnow()
    db.add(row)
    db.flush()
    return row


@dataclass(frozen=True)
class PumpSummary:
    seed_key: str
    requested: int
    created: int


def pump_sandbox_transactions(
    *,
    connection: IntegrationConnection,
    business_id: str,
    start_date: date,
    end_date: date,
    daily_txn_count: int,
    profile: str,
    client: PlaidClient | None = None,
) -> PumpSummary:
    plaid_client = client or PlaidClient()
    if not connection.plaid_access_token:
        raise HTTPException(400, "Plaid connection is missing access token.")

    seed_key = _derive_seed_key(business_id, start_date, end_date, profile)
    rng = _stable_rng(seed_key)
    current = start_date
    requested = 0
    created = 0
    while current <= end_date:
        batch_end = min(current + timedelta(days=6), end_date)
        days = (batch_end - current).days + 1
        requested += days * daily_txn_count
        distribution = [daily_txn_count + rng.randint(-2, 2) for _ in range(days)]
        distribution = [max(1, value) for value in distribution]
        payload = {
            "access_token": connection.plaid_access_token,
            "start_date": current.isoformat(),
            "end_date": batch_end.isoformat(),
            "options": {
                "transactions_per_day": distribution,
            },
        }
        plaid_client.post("/sandbox/transactions/create", payload)
        created += sum(distribution)
        current = batch_end + timedelta(days=1)
        time.sleep(0.05)
    return PumpSummary(seed_key=seed_key, requested=requested, created=created)

