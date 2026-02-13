# backend/app/services/plaid_dev_service.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import os
import random
import time
from typing import Any, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.plaid import PlaidAdapter, PlaidClient, plaid_environment
from backend.app.models import IntegrationConnection

# Plaid sandbox/transactions/create constraints:
# - transactions[] items must include: date_transacted, date_posted, amount, description
# - dates must be today or within last 14 days inclusive (no future)
# - max 10 transactions per request
MAX_TXNS_PER_REQUEST = 10

# Plaid sandbox rate limit (default): /sandbox/transactions/create = 2 per minute per Item
# Enforce a safe interval slightly above 30 seconds to avoid edge timing / rolling window effects.
PLAID_CREATE_MIN_INTERVAL_SECONDS = float(os.getenv("PLAID_CREATE_MIN_INTERVAL_SECONDS", "31.5"))

# Retry tuning for 429s (we still enforce min-interval; this is extra safety)
MAX_RETRIES_ON_429 = 6
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _debug_enabled() -> bool:
    return os.getenv("CLARITY_PLAID_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")


def require_plaid_sandbox_config() -> None:
    missing = [name for name in ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV") if not os.getenv(name)]
    if missing:
        raise HTTPException(400, f"Missing Plaid sandbox config: {', '.join(missing)}.")
    if plaid_environment() != "sandbox":
        raise HTTPException(400, "PLAID_ENV must be set to 'sandbox' for dev Plaid endpoints.")


def _derive_seed_key(business_id: str, start_date: date, end_date: date, profile: str) -> str:
    return f"{business_id}:{start_date.isoformat()}:{end_date.isoformat()}:{(profile or 'mixed').strip().lower()}"


def _stable_rng(seed_key: str) -> random.Random:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _clamp_to_last_14_days(start: date, end: date) -> Tuple[date, date, Optional[str]]:
    """
    Plaid sandbox requires date_posted/date_transacted be within last 14 days inclusive.
    We clamp into [today-13, today] (14 calendar days inclusive).
    """
    today = utcnow().date()
    min_allowed = today - timedelta(days=13)

    orig_start, orig_end = start, end

    if start < min_allowed:
        start = min_allowed
    if end < min_allowed:
        end = min_allowed
    if end > today:
        end = today
    if start > today:
        start = today
    if start > end:
        start = end

    note = None
    if (orig_start, orig_end) != (start, end):
        note = (
            f"Clamped requested date range {orig_start.isoformat()}→{orig_end.isoformat()} "
            f"into {start.isoformat()}→{end.isoformat()} to satisfy Plaid 14-day sandbox constraint."
        )
    return start, end, note


def ensure_dynamic_item(db: Session, business_id: str, *, force_recreate: bool = False) -> IntegrationConnection:
    """
    Creates (or reuses) a sandbox Item and stores access_token/item_id on IntegrationConnection.
    """
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
    clamped_start_date: str
    clamped_end_date: str
    date_clamp_note: Optional[str]
    plaid_requests: int
    slept_seconds: float
    min_interval_seconds: float
    rate_limit_note: str
    last_error: Optional[str] = None
    sample_plaid_transaction: Optional[dict] = None


def _profile_descriptions(profile: str) -> list[str]:
    pools = {
        "mixed": [
            "Office supplies",
            "Coffee",
            "Software subscription",
            "Client payment",
            "Fuel",
            "Shipping",
            "Meals",
            "Insurance",
            "Rent",
            "Payroll",
        ],
        "retail": [
            "Daily sales",
            "Card processing fee",
            "Inventory purchase",
            "Shipping labels",
            "Refund",
            "Marketing spend",
            "Utilities",
        ],
        "services": [
            "Client retainer",
            "Contractor payout",
            "Software subscription",
            "Travel",
            "Meals",
            "Office supplies",
        ],
    }
    key = (profile or "mixed").strip().lower()
    return pools.get(key, pools["mixed"])


def _chunk(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_plaid_transactions_for_day(*, d: date, count: int, rng: random.Random, descriptions: list[str]) -> list[dict]:
    """
    Build CustomSandboxTransaction objects:
      - date_transacted (YYYY-MM-DD)
      - date_posted (YYYY-MM-DD)
      - amount (number, can be negative)
      - description (string)
      - iso_currency_code (optional; we set USD)
    """
    txns: list[dict] = []
    for _ in range(count):
        desc = descriptions[rng.randrange(0, len(descriptions))]

        # Mix inflows/outflows. Your pipeline uses sign to infer direction.
        if rng.random() < 0.18:
            amount = -round(rng.uniform(75.0, 950.0), 2)  # inflow
        else:
            amount = round(rng.uniform(8.0, 240.0), 2)  # outflow

        txns.append(
            {
                "date_transacted": d.isoformat(),
                "date_posted": d.isoformat(),
                "amount": float(amount),
                "description": desc,
                "iso_currency_code": "USD",
            }
        )
    return txns


def _looks_like_plaid_429_limit(exc: HTTPException) -> bool:
    """
    Your PlaidClient.post raises HTTPException with detail containing:
      detail = { provider, path, status, error:{error_code, ...}, request:{...} }
    """
    if exc.status_code != 429:
        return False
    detail = exc.detail
    if not isinstance(detail, dict):
        return False
    err = detail.get("error")
    if not isinstance(err, dict):
        return False
    code = err.get("error_code")
    return code in ("SANDBOX_TRANSACTIONS_CREATE_LIMIT", "RATE_LIMIT", "TRANSACTIONS_LIMIT")


def _enforce_min_interval(last_call_ts: Optional[float]) -> Tuple[Optional[float], float]:
    """
    Ensures at most ~2 calls/min by sleeping until PLAID_CREATE_MIN_INTERVAL_SECONDS has elapsed
    since last_call_ts. Returns (new_last_call_ts, slept_seconds_added).
    """
    slept = 0.0
    now = time.time()
    if last_call_ts is not None:
        elapsed = now - last_call_ts
        remaining = PLAID_CREATE_MIN_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)
            slept += remaining
    return time.time(), slept


def _post_create_with_throttle_and_backoff(
    plaid_client: PlaidClient,
    payload: dict,
    *,
    last_call_ts: Optional[float],
) -> Tuple[float, float]:
    """
    Makes ONE /sandbox/transactions/create call, respecting the 2/minute limit and retrying 429.
    Returns (new_last_call_ts, slept_seconds_added).
    """
    slept_total = 0.0

    # Always enforce spacing BEFORE attempting a call, so we don't instantly violate 2/min.
    last_call_ts, slept = _enforce_min_interval(last_call_ts)
    slept_total += slept

    for attempt in range(MAX_RETRIES_ON_429 + 1):
        try:
            if _debug_enabled():
                sample_txn = None
                if isinstance(payload.get("transactions"), list) and payload["transactions"]:
                    sample_txn = payload["transactions"][0]
                print(
                    "[plaid_dev] POST /sandbox/transactions/create",
                    "batch_size=",
                    len(payload.get("transactions") or []),
                    "sample_txn=",
                    sample_txn,
                )

            plaid_client.post("/sandbox/transactions/create", payload, retry_once=False)
            # Success: record this as the call time for the next throttle step
            return time.time(), slept_total

        except HTTPException as exc:
            if _looks_like_plaid_429_limit(exc) and attempt < MAX_RETRIES_ON_429:
                # Backoff, then enforce min-interval again before retry
                backoff = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
                time.sleep(backoff)
                slept_total += backoff

                last_call_ts, slept = _enforce_min_interval(last_call_ts)
                slept_total += slept
                continue
            raise


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
    """
    Pumps deterministic sandbox transactions into Plaid, respecting:
      - last-14-days constraint
      - max 10 transactions per request
      - /sandbox/transactions/create = 2/min per Item (hard throttle)
      - correct 429 retry handling (HTTPException-based)
    """
    require_plaid_sandbox_config()

    if not connection.plaid_access_token:
        raise HTTPException(400, "Plaid connection is missing access token.")

    clamped_start, clamped_end, clamp_note = _clamp_to_last_14_days(start_date, end_date)

    seed_key = _derive_seed_key(business_id, clamped_start, clamped_end, profile)
    rng = _stable_rng(seed_key)
    descriptions = _profile_descriptions(profile)
    plaid_client = client or PlaidClient()

    requested = 0
    created = 0
    plaid_requests = 0
    slept_seconds = 0.0
    last_error: Optional[str] = None
    sample_plaid_txn: Optional[dict] = None

    # For throttling the Plaid create endpoint.
    last_create_call_ts: Optional[float] = None

    current = clamped_start
    while current <= clamped_end:
        # bounded jitter to keep “natural” but deterministic volume
        count = max(1, int(daily_txn_count) + rng.randint(-2, 2))
        requested += count

        day_txns = _build_plaid_transactions_for_day(d=current, count=count, rng=rng, descriptions=descriptions)
        if sample_plaid_txn is None and day_txns:
            sample_plaid_txn = day_txns[0]

        batches = _chunk(day_txns, MAX_TXNS_PER_REQUEST)
        for batch in batches:
            payload = {
                "access_token": connection.plaid_access_token,
                "transactions": batch,
            }
            try:
                last_create_call_ts, slept_add = _post_create_with_throttle_and_backoff(
                    plaid_client,
                    payload,
                    last_call_ts=last_create_call_ts,
                )
                slept_seconds += slept_add
            except Exception as exc:
                last_error = str(exc)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Plaid request failed while creating sandbox transactions. "
                        "Constraints: last-14-days dates, max 10 txns/request, and 2 create calls/min per Item. "
                        f"Attempted date={current.isoformat()} batch_size={len(batch)}. "
                        f"Underlying error: {exc}"
                    ),
                )

            plaid_requests += 1
            created += len(batch)

        current = current + timedelta(days=1)

    rate_limit_note = (
        f"Throttled /sandbox/transactions/create to ~2/min per Item "
        f"(min_interval_seconds={PLAID_CREATE_MIN_INTERVAL_SECONDS}). "
        f"Large daily_txn_count values will take longer because Plaid caps 10 txns/request."
    )

    return PumpSummary(
        seed_key=seed_key,
        requested=requested,
        created=created,
        clamped_start_date=clamped_start.isoformat(),
        clamped_end_date=clamped_end.isoformat(),
        date_clamp_note=clamp_note,
        plaid_requests=plaid_requests,
        slept_seconds=round(slept_seconds, 2),
        min_interval_seconds=PLAID_CREATE_MIN_INTERVAL_SECONDS,
        rate_limit_note=rate_limit_note,
        last_error=last_error,
        sample_plaid_transaction=sample_plaid_txn if _debug_enabled() else None,
    )


def pump_summary_to_dict(summary: PumpSummary) -> dict[str, Any]:
    return asdict(summary)
