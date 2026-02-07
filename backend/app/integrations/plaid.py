from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import os
from typing import Optional, TYPE_CHECKING, Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.base import IngestResult, WebhookVerificationResult
from backend.app.integrations.utils import upsert_raw_event, utcnow
from backend.app.models import IntegrationConnection
from backend.app.services import audit_service


PLAID_ENV_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


def plaid_is_configured() -> bool:
    return bool(os.getenv("PLAID_CLIENT_ID") and os.getenv("PLAID_SECRET"))


def plaid_environment() -> str:
    return (os.getenv("PLAID_ENV") or "sandbox").strip().lower()


def plaid_base_url() -> str:
    override = os.getenv("PLAID_BASE_URL")
    if override:
        return override
    return PLAID_ENV_URLS.get(plaid_environment(), PLAID_ENV_URLS["sandbox"])


def _build_httpx_client(base_url: str):
    import httpx  # local import to avoid hard dependency at import time

    return httpx.Client(base_url=base_url, timeout=20.0)


def _parse_plaid_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if "T" in value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        parsed_date = date.fromisoformat(value)
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
    except Exception:
        return None


def _plaid_direction(amount: float) -> Optional[str]:
    if amount > 0:
        return "outflow"
    if amount < 0:
        return "inflow"
    return None


@dataclass(frozen=True)
class PlaidSyncResult:
    added: list[dict]
    modified: list[dict]
    removed: list[dict]
    next_cursor: Optional[str]


class PlaidClient:
    def __init__(self, *, base_url: Optional[str] = None, client: Optional[Any] = None):
        self.base_url = base_url or plaid_base_url()
        self._client = client or _build_httpx_client(self.base_url)

    def _auth_payload(self) -> dict:
        client_id = os.getenv("PLAID_CLIENT_ID")
        secret = os.getenv("PLAID_SECRET")
        if not client_id or not secret:
            raise RuntimeError("PLAID_CLIENT_ID and PLAID_SECRET must be configured.")
        return {"client_id": client_id, "secret": secret}

    def post(self, path: str, payload: dict, *, retry_once: bool = True) -> dict:
        request_payload = {**self._auth_payload(), **payload}
        for attempt in range(2 if retry_once else 1):
            try:
                response = self._client.post(path, json=request_payload)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                import httpx

                if not isinstance(exc, httpx.HTTPError):
                    raise
                if attempt == 0 and retry_once:
                    continue
                raise


if TYPE_CHECKING:
    import httpx  # pragma: no cover


class PlaidAdapter:
    provider = "plaid"

    def __init__(self, *, client: Optional[PlaidClient] = None):
        self.client = client or PlaidClient()

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookVerificationResult:
        _ = headers
        _ = body
        if os.getenv("PLAID_WEBHOOK_VERIFY_DISABLED", "true").lower() == "true":
            return WebhookVerificationResult(ok=True, reason="plaid_webhook_verification_disabled")
        return WebhookVerificationResult(ok=False, reason="plaid_webhook_verification_not_implemented")

    def create_link_token(self, *, business_id: str) -> dict:
        payload = {
            "client_name": "Clarity Labs",
            "language": "en",
            "country_codes": ["US"],
            "user": {"client_user_id": business_id},
            "products": ["transactions"],
        }
        webhook_url = os.getenv("PLAID_WEBHOOK_URL")
        if webhook_url:
            payload["webhook"] = webhook_url
        return self.client.post("/link/token/create", payload)

    def exchange_public_token(self, *, public_token: str) -> dict:
        payload = {"public_token": public_token}
        return self.client.post("/item/public_token/exchange", payload)

    def sync_transactions(self, *, access_token: str, cursor: Optional[str]) -> PlaidSyncResult:
        has_more = True
        added: list[dict] = []
        modified: list[dict] = []
        removed: list[dict] = []
        next_cursor = cursor

        while has_more:
            payload = {"access_token": access_token}
            if next_cursor:
                payload["cursor"] = next_cursor
            response = self.client.post("/transactions/sync", payload)
            added.extend(response.get("added", []))
            modified.extend(response.get("modified", []))
            removed.extend(response.get("removed", []))
            next_cursor = response.get("next_cursor")
            has_more = bool(response.get("has_more"))

        return PlaidSyncResult(added=added, modified=modified, removed=removed, next_cursor=next_cursor)

    def ingest_transactions(
        self,
        *,
        business_id: str,
        db: Session,
        transactions: list[dict],
    ) -> IngestResult:
        inserted_ids: list[str] = []
        skipped = 0
        for txn in transactions:
            txn_id = txn.get("transaction_id") or txn.get("id")
            if not txn_id:
                skipped += 1
                continue
            occurred_at = (
                _parse_plaid_datetime(txn.get("datetime"))
                or _parse_plaid_datetime(txn.get("authorized_datetime"))
                or _parse_plaid_datetime(txn.get("date"))
                or utcnow()
            )
            amount = float(txn.get("amount", 0.0))
            direction = _plaid_direction(amount)
            category = None
            if isinstance(txn.get("personal_finance_category"), dict):
                category = txn["personal_finance_category"].get("primary")
            if not category and isinstance(txn.get("category"), list) and txn["category"]:
                category = txn["category"][0]

            payload = {
                "type": "plaid.transaction",
                "transaction": {
                    "transaction_id": txn_id,
                    "amount": amount,
                    "name": txn.get("name"),
                    "merchant_name": txn.get("merchant_name"),
                    "account_id": txn.get("account_id"),
                    "pending": txn.get("pending"),
                    "iso_currency_code": txn.get("iso_currency_code"),
                    "date": txn.get("date"),
                    "datetime": txn.get("datetime"),
                    "authorized_date": txn.get("authorized_date"),
                    "authorized_datetime": txn.get("authorized_datetime"),
                    "payment_channel": txn.get("payment_channel"),
                },
                "direction": direction,
                "category": category,
                "provider": "plaid",
                "ingested_at": utcnow().isoformat(),
            }
            source_event_id = f"plaid:{txn_id}"
            inserted = upsert_raw_event(
                db,
                business_id=business_id,
                source=self.provider,
                source_event_id=source_event_id,
                occurred_at=occurred_at,
                payload=payload,
            )
            if inserted:
                inserted_ids.append(source_event_id)
            else:
                skipped += 1
        return IngestResult(
            provider=self.provider,
            inserted_count=len(inserted_ids),
            skipped_count=skipped,
            source_event_ids=inserted_ids,
        )

    def ingest_pull(
        self,
        *,
        business_id: str,
        since: Optional[datetime],
        db: Session,
    ) -> IngestResult:
        _ = since
        connection = db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.business_id == business_id,
                IntegrationConnection.provider == self.provider,
            )
        ).scalar_one_or_none()
        if not connection or not connection.plaid_access_token:
            raise RuntimeError("Plaid connection missing access_token.")

        previous_cursor = connection.last_cursor
        sync_result = self.sync_transactions(
            access_token=connection.plaid_access_token,
            cursor=connection.last_cursor,
        )
        ingest_result = self.ingest_transactions(
            business_id=business_id,
            db=db,
            transactions=[*sync_result.added, *sync_result.modified],
        )
        connection.last_cursor = sync_result.next_cursor
        connection.last_cursor_at = utcnow()
        connection.updated_at = utcnow()
        db.add(connection)

        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="plaid_cursor_advanced",
            actor="system",
            reason="plaid_sync",
            before={"cursor": previous_cursor},
            after={"cursor": sync_result.next_cursor},
        )

        return ingest_result


__all__ = ["PlaidAdapter", "PlaidClient", "PlaidSyncResult", "plaid_is_configured", "plaid_environment"]
