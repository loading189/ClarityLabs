from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, Sequence


ProviderName = str


@dataclass(frozen=True)
class IngestResult:
    provider: ProviderName
    inserted_count: int
    skipped_count: int
    source_event_ids: Sequence[str]


@dataclass(frozen=True)
class WebhookVerificationResult:
    ok: bool
    reason: str


class IntegrationAdapter(Protocol):
    provider: ProviderName

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookVerificationResult:
        ...

    def ingest_pull(
        self,
        *,
        business_id: str,
        since: Optional[datetime],
        db,
    ) -> IngestResult:
        ...
