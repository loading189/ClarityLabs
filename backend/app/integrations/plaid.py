from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from typing import Optional, TYPE_CHECKING, Any, Iterable
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.base import IngestResult, WebhookVerificationResult
from backend.app.integrations.utils import upsert_raw_event, utcnow
from backend.app.models import IntegrationConnection, RawEvent
from backend.app.services import integration_connection_service
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


def _plaid_fingerprint(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _plaid_base_event_id(txn_id: str) -> str:
    return f"plaid:{txn_id}"


def _parse_plaid_version(source_event_id: str, base_id: str) -> Optional[int]:
    if source_event_id == base_id:
        return 1
    prefix = f"{base_id}:v"
    if source_event_id.startswith(prefix):
        suffix = source_event_id[len(prefix):]
        if suffix.isdigit():
            return int(suffix)
    return None


def _collect_plaid_versions(
    rows: Iterable[tuple[str, dict]],
    base_id: str,
) -> list[dict]:
    versions: list[dict] = []
    for source_event_id, payload in rows:
        version = _parse_plaid_version(source_event_id, base_id)
        if version is None:
            continue
        meta = payload.get("meta") if isinstance(payload, dict) else None
        fingerprint = meta.get("event_fingerprint") if isinstance(meta, dict) else None
        event_kind = meta.get("event_kind") if isinstance(meta, dict) else None
        versions.append(
            {
                "source_event_id": source_event_id,
                "version": version,
                "fingerprint": fingerprint,
                "event_kind": event_kind,
            }
        )
    return versions


@dataclass(frozen=True)
class PlaidSyncResult:
    added: list[dict]
    modified: list[dict]
    removed: list[dict]
    next_cursor: Optional[str]


# backend/app/integrations/plaid.py

from fastapi import HTTPException

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

        # We NEVER include access_token in error details. Strip it if present.
        def _sanitize(obj: Any) -> Any:
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if k in ("access_token", "public_token", "secret", "client_id"):
                        out[k] = "***redacted***"
                    else:
                        out[k] = _sanitize(v)
                return out
            if isinstance(obj, list):
                return [_sanitize(x) for x in obj]
            return obj

        last_exc: Optional[Exception] = None
        for attempt in range(2 if retry_once else 1):
            try:
                response = self._client.post(path, json=request_payload)
                if response.status_code >= 400:
                    # Try to parse Plaid's error payload
                    try:
                        err = response.json()
                    except Exception:
                        err = {"raw": response.text}

                    raise HTTPException(
                        status_code=response.status_code,
                        detail={
                            "provider": "plaid",
                            "path": path,
                            "status": response.status_code,
                            "error": _sanitize(err),
                            "request": {"payload_keys": sorted(list(request_payload.keys()))},
                        },
                    )
                return response.json()
            except HTTPException as e:
                last_exc = e
                if attempt == 0 and retry_once:
                    continue
                raise
            except Exception as exc:
                # Non-HTTP errors (timeouts, etc.)
                last_exc = exc
                if attempt == 0 and retry_once:
                    continue
                raise

        # should never hit
        raise last_exc or RuntimeError("Plaid request failed unexpectedly.")



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
        event_kind: str,
    ) -> IngestResult:
        inserted_ids: list[str] = []
        skipped = 0
        for txn in transactions:
            txn_id = txn.get("transaction_id") or txn.get("id")
            if not txn_id:
                skipped += 1
                continue
            base_event_id = _plaid_base_event_id(txn_id)
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

            payload_core = {
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
            }
            fingerprint = _plaid_fingerprint(payload_core)
            existing_rows = db.execute(
                select(RawEvent.source_event_id, RawEvent.payload).where(
                    RawEvent.business_id == business_id,
                    RawEvent.source == self.provider,
                    RawEvent.source_event_id.like(f"{base_event_id}%"),
                )
            ).all()
            versions = _collect_plaid_versions(existing_rows, base_event_id)
            if any(version.get("fingerprint") == fingerprint for version in versions):
                skipped += 1
                continue
            latest_version = max((version["version"] for version in versions), default=0)
            next_version = latest_version + 1 if latest_version else 1
            if next_version == 1:
                source_event_id = base_event_id
            else:
                source_event_id = f"{base_event_id}:v{next_version}"
            supersedes = None
            if versions:
                supersedes = max(versions, key=lambda row: row["version"])["source_event_id"]
            payload = {
                **payload_core,
                "ingested_at": utcnow().isoformat(),
                "meta": {
                    "event_kind": event_kind,
                    "event_version": next_version,
                    "event_fingerprint": fingerprint,
                    "source_event_base_id": base_event_id,
                    "supersedes": supersedes,
                },
            }
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

    def ingest_removed_transactions(
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
            base_event_id = _plaid_base_event_id(txn_id)
            tombstone_core = {
                "type": "plaid.transaction.removed",
                "transaction": {"transaction_id": txn_id},
                "provider": "plaid",
            }
            fingerprint = _plaid_fingerprint(tombstone_core)
            existing_rows = db.execute(
                select(RawEvent.source_event_id, RawEvent.payload).where(
                    RawEvent.business_id == business_id,
                    RawEvent.source == self.provider,
                    RawEvent.source_event_id.like(f"{base_event_id}%"),
                )
            ).all()
            versions = _collect_plaid_versions(existing_rows, base_event_id)
            if any(version.get("fingerprint") == fingerprint for version in versions):
                skipped += 1
                continue
            latest_version = max((version["version"] for version in versions), default=0)
            next_version = latest_version + 1 if latest_version else 1
            if next_version == 1:
                source_event_id = base_event_id
            else:
                source_event_id = f"{base_event_id}:v{next_version}"
            supersedes = None
            if versions:
                supersedes = max(versions, key=lambda row: row["version"])["source_event_id"]
            payload = {
                **tombstone_core,
                "ingested_at": utcnow().isoformat(),
                "meta": {
                    "event_kind": "removed",
                    "event_version": next_version,
                    "event_fingerprint": fingerprint,
                    "source_event_base_id": base_event_id,
                    "supersedes": supersedes,
                    "is_removed": True,
                },
            }
            inserted = upsert_raw_event(
                db,
                business_id=business_id,
                source=self.provider,
                source_event_id=source_event_id,
                occurred_at=utcnow(),
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
        if since is not None:
            connection.last_cursor = None
        sync_result = self.sync_transactions(
            access_token=connection.plaid_access_token,
            cursor=connection.last_cursor,
        )
        ingest_added = self.ingest_transactions(
            business_id=business_id,
            db=db,
            transactions=sync_result.added,
            event_kind="added",
        )
        ingest_modified = self.ingest_transactions(
            business_id=business_id,
            db=db,
            transactions=sync_result.modified,
            event_kind="modified",
        )
        ingest_removed = self.ingest_removed_transactions(
            business_id=business_id,
            db=db,
            transactions=sync_result.removed,
        )
        ingest_result = IngestResult(
            provider=self.provider,
            inserted_count=ingest_added.inserted_count + ingest_modified.inserted_count + ingest_removed.inserted_count,
            skipped_count=ingest_added.skipped_count + ingest_modified.skipped_count + ingest_removed.skipped_count,
            source_event_ids=[
                *ingest_added.source_event_ids,
                *ingest_modified.source_event_ids,
                *ingest_removed.source_event_ids,
            ],
        )
        connection.last_cursor = sync_result.next_cursor
        connection.last_cursor_at = utcnow()
        connection.updated_at = utcnow()
        if ingest_result.source_event_ids:
            latest = db.execute(
                select(RawEvent.occurred_at, RawEvent.source_event_id)
                .where(RawEvent.business_id == business_id, RawEvent.source == self.provider)
                .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
                .limit(1)
            ).first()
            if latest:
                connection.last_ingested_at = latest[0]
                connection.last_ingested_source_event_id = latest[1]
        db.add(connection)
        integration_connection_service.mark_sync_success(connection)

        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="plaid_cursor_advanced",
            actor="system",
            reason="plaid_sync",
            before={"cursor": previous_cursor},
            after={"cursor": sync_result.next_cursor},
        )
        if sync_result.modified:
            audit_service.log_audit_event(
                db,
                business_id=business_id,
                event_type="plaid_transactions_modified",
                actor="system",
                reason="plaid_sync",
                before=None,
                after={"count": len(sync_result.modified)},
            )
        if sync_result.removed:
            audit_service.log_audit_event(
                db,
                business_id=business_id,
                event_type="plaid_transactions_removed",
                actor="system",
                reason="plaid_sync",
                before=None,
                after={"count": len(sync_result.removed)},
            )

        return ingest_result


__all__ = ["PlaidAdapter", "PlaidClient", "PlaidSyncResult", "plaid_is_configured", "plaid_environment"]
