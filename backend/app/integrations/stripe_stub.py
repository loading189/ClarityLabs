from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.integrations.base import IngestResult, WebhookVerificationResult
from backend.app.integrations.utils import upsert_raw_event


class StripeStubAdapter:
    provider = "stripe"

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookVerificationResult:
        # Dev-only stub: accept all payloads but keep a hook for future checks.
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
        # Stripe stub does not support pull yet.
        _ = since
        return IngestResult(provider=self.provider, inserted_count=0, skipped_count=0, source_event_ids=[])

    def ingest_webhook_event(
        self,
        *,
        business_id: str,
        payload: dict,
        db: Session,
    ) -> IngestResult:
        event_id = str(payload.get("id") or payload.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("stripe webhook payload missing id")
        source_event_id = f"stripe:{event_id}"
        occurred_at_raw = payload.get("created")
        occurred_at = None
        if isinstance(occurred_at_raw, (int, float)):
            occurred_at = datetime.fromtimestamp(float(occurred_at_raw), tz=timezone.utc)
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
