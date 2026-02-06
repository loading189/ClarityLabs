from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.integrations.base import IngestResult, WebhookVerificationResult
from backend.app.integrations.utils import upsert_raw_event


class ShopifyStubAdapter:
    provider = "shopify"

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookVerificationResult:
        # Dev-only stub: accept all payloads but keep hook for signature verification.
        _ = headers
        _ = body
        return WebhookVerificationResult(ok=True, reason="stub_accept_all")

    def ingest_pull(
        self,
        *,
        business_id: str,
        since: Optional[datetime],
        db: Session,
    ) -> IngestResult:
        _ = since
        return IngestResult(provider=self.provider, inserted_count=0, skipped_count=0, source_event_ids=[])

    def ingest_webhook_event(
        self,
        *,
        business_id: str,
        payload: dict,
        db: Session,
    ) -> IngestResult:
        event_id = str(payload.get("id") or payload.get("event_id") or payload.get("webhook_id") or "").strip()
        if not event_id:
            raise ValueError("shopify webhook payload missing id")
        source_event_id = f"shopify:{event_id}"
        occurred_at = None
        occurred_at_raw = payload.get("created_at") or payload.get("processed_at")
        if isinstance(occurred_at_raw, str):
            try:
                occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
            except ValueError:
                occurred_at = None
        if occurred_at and occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        inserted = upsert_raw_event(
            db,
            business_id=business_id,
            source=self.provider,
            source_event_id=source_event_id,
            occurred_at=occurred_at,
            payload=payload,
        )
        return IngestResult(
            provider=self.provider,
            inserted_count=1 if inserted else 0,
            skipped_count=0 if inserted else 1,
            source_event_ids=[source_event_id] if inserted else [],
        )


def parse_body(body: bytes) -> dict:
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))
