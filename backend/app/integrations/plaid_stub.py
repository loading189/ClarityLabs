from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.integrations.base import IngestResult, WebhookVerificationResult
from backend.app.integrations.utils import upsert_raw_event, utcnow


class PlaidStubAdapter:
    provider = "plaid"

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookVerificationResult:
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
        anchor = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        sample = [
            {
                "id": "plaid_txn_001",
                "occurred_at": anchor - timedelta(days=2),
                "amount": -42.15,
                "name": "Coffee Supply Co",
                "merchant_name": "Coffee Supply Co",
            },
            {
                "id": "plaid_txn_002",
                "occurred_at": anchor - timedelta(days=1),
                "amount": -120.00,
                "name": "Paper Goods",
                "merchant_name": "Paper Goods",
            },
            {
                "id": "plaid_txn_003",
                "occurred_at": anchor,
                "amount": 875.00,
                "name": "Daily Sales",
                "merchant_name": "Daily Sales",
            },
        ]
        inserted_ids: list[str] = []
        skipped = 0
        for row in sample:
            occurred_at = row["occurred_at"]
            if since and occurred_at <= since:
                continue
            payload = {
                "type": "transaction.posted",
                "transaction": {
                    "transaction_id": row["id"],
                    "amount": row["amount"],
                    "name": row["name"],
                    "merchant_name": row["merchant_name"],
                    "posted_at": occurred_at.isoformat(),
                },
                "provider": "plaid_stub",
                "ingested_at": utcnow().isoformat(),
            }
            source_event_id = f"plaid:{row['id']}"
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
