from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from backend.app.domain.contracts import (
    CategorizationContract,
    CategorizedTransactionContract,
    LedgerRowContract,
    NormalizedTransactionContract,
    RawEventContract,
)
from backend.app.models import RawEvent
from backend.app.norma.ledger import LedgerRow
from backend.app.norma.normalize import Categorization, EnrichedTransaction, NormalizedTransaction


def raw_event_to_contract(raw_event: RawEvent | Mapping[str, Any]) -> RawEventContract:
    if isinstance(raw_event, RawEvent):
        payload = raw_event.payload
        return RawEventContract(
            id=raw_event.id,
            business_id=raw_event.business_id,
            source=raw_event.source,
            source_event_id=raw_event.source_event_id,
            occurred_at=raw_event.occurred_at,
            payload=payload,
        )

    payload = dict(raw_event.get("payload") or {})
    return RawEventContract(
        id=raw_event.get("id"),
        business_id=raw_event.get("business_id"),
        source=str(raw_event.get("source") or ""),
        source_event_id=str(raw_event.get("source_event_id") or ""),
        occurred_at=raw_event.get("occurred_at"),
        payload=payload,
    )


def normalized_to_contract(txn: NormalizedTransaction) -> NormalizedTransactionContract:
    return NormalizedTransactionContract(
        id=txn.id,
        source_event_id=txn.source_event_id,
        occurred_at=txn.occurred_at,
        date=txn.date,
        description=txn.description,
        amount=float(txn.amount or 0.0),
        direction=txn.direction,
        account=txn.account,
        category=txn.category,
        counterparty_hint=txn.counterparty_hint,
    )


def _categorization_to_contract(categorization: Categorization) -> CategorizationContract:
    return CategorizationContract(**asdict(categorization))


def categorized_to_contract(txn: NormalizedTransaction) -> CategorizedTransactionContract:
    categorization = None
    if isinstance(txn, EnrichedTransaction) and txn.categorization:
        categorization = _categorization_to_contract(txn.categorization)
    return CategorizedTransactionContract(
        id=txn.id,
        source_event_id=txn.source_event_id,
        occurred_at=txn.occurred_at,
        date=txn.date,
        description=txn.description,
        amount=float(txn.amount or 0.0),
        direction=txn.direction,
        account=txn.account,
        category=txn.category,
        counterparty_hint=txn.counterparty_hint,
        categorization=categorization,
    )


def ledger_row_to_contract(row: LedgerRow) -> LedgerRowContract:
    return LedgerRowContract(
        occurred_at=row.occurred_at,
        source_event_id=row.source_event_id,
        date=row.date,
        description=row.description,
        amount=float(row.amount or 0.0),
        category=row.category,
        balance=float(row.balance or 0.0),
    )
