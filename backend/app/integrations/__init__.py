from __future__ import annotations

import os

from backend.app.integrations.base import IngestResult, ProviderName, WebhookVerificationResult
from backend.app.integrations.plaid import PlaidAdapter, plaid_is_configured
from backend.app.integrations.plaid_stub import PlaidStubAdapter
from backend.app.integrations.shopify_stub import ShopifyStubAdapter
from backend.app.integrations.stripe_stub import StripeStubAdapter


PLAID_ADAPTER: PlaidAdapter | None = None
PLAID_STUB_ADAPTER = PlaidStubAdapter()

ADAPTERS = {
    "stripe": StripeStubAdapter(),
    "shopify": ShopifyStubAdapter(),
}


def get_adapter(provider: ProviderName):
    key = (provider or "").strip().lower()
    if key == "plaid":
        if os.getenv("PLAID_USE_STUB", "").lower() == "true":
            return PLAID_STUB_ADAPTER
        if not plaid_is_configured():
            return PLAID_STUB_ADAPTER
        global PLAID_ADAPTER
        if PLAID_ADAPTER is None:
            PLAID_ADAPTER = PlaidAdapter()
        return PLAID_ADAPTER
    adapter = ADAPTERS.get(key)
    if not adapter:
        raise ValueError(f"unsupported provider: {provider}")
    return adapter


__all__ = [
    "ADAPTERS",
    "IngestResult",
    "ProviderName",
    "WebhookVerificationResult",
    "get_adapter",
]
