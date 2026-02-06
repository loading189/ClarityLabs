from __future__ import annotations

from backend.app.integrations.base import IngestResult, ProviderName, WebhookVerificationResult
from backend.app.integrations.plaid_stub import PlaidStubAdapter
from backend.app.integrations.shopify_stub import ShopifyStubAdapter
from backend.app.integrations.stripe_stub import StripeStubAdapter


ADAPTERS = {
    "stripe": StripeStubAdapter(),
    "shopify": ShopifyStubAdapter(),
    "plaid": PlaidStubAdapter(),
}


def get_adapter(provider: ProviderName):
    key = (provider or "").strip().lower()
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
