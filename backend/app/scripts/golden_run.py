from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.analytics.monthly_trends import build_monthly_trends_payload
from backend.app.clarity.adapters import signal_to_contract
from backend.app.clarity.signals import compute_signals
from backend.app.db import SessionLocal
from backend.app.domain.contracts import (
    CategorizedTransactionContract,
    LedgerRowContract,
    NormalizedTransactionContract,
    RawEventContract,
    SignalResult,
)
from backend.app.models import Business, Organization, RawEvent
from backend.app.norma.adapters import (
    categorized_to_contract,
    ledger_row_to_contract,
    normalized_to_contract,
    raw_event_to_contract,
)
from backend.app.norma.categorize import categorize_txn
from backend.app.norma.facts import compute_facts, facts_to_dict
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.ledger import build_cash_ledger
from backend.app.sim.engine import build_scenario, generate_raw_events_for_scenario
from backend.app.sim.scenarios import ScenarioContext


ARTIFACT_DIR = Path("backend/.artifacts/golden")
DEFAULT_BIZ_NAME = "Golden Demo Business"
DEFAULT_ORG_NAME = "Golden Demo Org"


def _model_dump(item: Any) -> Dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return item.dict()  # type: ignore[no-any-return]


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_json(data: Any) -> str:
    payload = _stable_json(data).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _summarize_list(items: Iterable[Any]) -> Dict[str, Any]:
    items_list = list(items)
    payload = [_model_dump(i) for i in items_list]
    return {
        "count": len(payload),
        "hash": _hash_json(payload),
        "sample_first": payload[:5],
        "sample_last": payload[-5:] if len(payload) > 5 else payload,
    }


def _summarize_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    series = payload.get("series") or []
    series_list = list(series) if isinstance(series, list) else []
    return {
        "count": len(series_list),
        "hash": _hash_json(payload),
        "sample_first": series_list[:5],
        "sample_last": series_list[-5:] if len(series_list) > 5 else series_list,
    }


def _get_or_create_demo_business(db: Session, *, org_name: str, biz_name: str) -> Business:
    existing = db.execute(select(Business).where(Business.name == biz_name)).scalars().first()
    if existing:
        return existing

    org = db.execute(select(Organization).where(Organization.name == org_name)).scalars().first()
    if not org:
        org = Organization(id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"claritylabs:{org_name}")), name=org_name)
        db.add(org)
        db.flush()

    biz = Business(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"claritylabs:{org_name}:{biz_name}")),
        org_id=org.id,
        name=biz_name,
        industry="demo",
    )
    db.add(biz)
    db.flush()
    db.commit()
    return biz


def _persist_raw_events(
    db: Session,
    business_id: str,
    raw_events: List[Dict[str, Any]],
    *,
    start_at: datetime,
    end_at: datetime,
) -> None:
    db.execute(
        delete(RawEvent).where(
            RawEvent.business_id == business_id,
            RawEvent.occurred_at >= start_at,
            RawEvent.occurred_at < end_at,
        )
    )

    inserts = [
        RawEvent(
            business_id=business_id,
            source=e["source"],
            source_event_id=e["source_event_id"],
            occurred_at=e["occurred_at"],
            payload=e["payload"],
        )
        for e in raw_events
    ]
    db.add_all(inserts)
    db.commit()


def run_golden_run(
    *,
    seed: int = 1337,
    days: int = 90,
    scenario_key: str = "restaurant",
    output_path: Optional[Path] = None,
    business_name: str = DEFAULT_BIZ_NAME,
    org_name: str = DEFAULT_ORG_NAME,
    persist_events: bool = True,
) -> Dict[str, Any]:
    start_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_at = start_at + timedelta(days=days)

    db = SessionLocal()
    try:
        biz = _get_or_create_demo_business(db, org_name=org_name, biz_name=business_name)
        ctx = ScenarioContext(business_id=biz.id, tz="UTC", seed=seed)
        scenario = build_scenario(scenario_key, ctx, start_at, end_at)
        raw_events, _truth = generate_raw_events_for_scenario(scenario, start_at, end_at)

        if persist_events:
            _persist_raw_events(db, biz.id, raw_events, start_at=start_at, end_at=end_at)

        normalized = [
            raw_event_to_txn(e["payload"], e["occurred_at"], source_event_id=e["source_event_id"])
            for e in raw_events
        ]
        categorized = [categorize_txn(t) for t in normalized]
        ledger = build_cash_ledger(categorized, opening_balance=0.0)
        facts_obj = compute_facts(categorized, ledger)
        facts_json = facts_to_dict(facts_obj)
        ledger_rows = [
            {
                "occurred_at": r.occurred_at.isoformat(),
                "balance": float(r.balance),
                "source_event_id": r.source_event_id,
            }
            for r in ledger
        ]
        trends_payload = build_monthly_trends_payload(
            facts_json=facts_json,
            lookback_months=12,
            k=2.0,
            ledger_rows=ledger_rows,
        )
        signals = compute_signals(facts_obj)

        raw_contracts: List[RawEventContract] = [raw_event_to_contract(e) for e in raw_events]
        normalized_contracts: List[NormalizedTransactionContract] = [normalized_to_contract(t) for t in normalized]
        categorized_contracts: List[CategorizedTransactionContract] = [categorized_to_contract(t) for t in categorized]
        ledger_contracts: List[LedgerRowContract] = [ledger_row_to_contract(r) for r in ledger]
        signal_contracts: List[SignalResult] = [signal_to_contract(s) for s in signals]

        artifact = {
            "metadata": {
                "seed": seed,
                "scenario": scenario_key,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "days": days,
                "business_id": biz.id,
                "business_name": biz.name,
            },
            "stages": {
                "raw_events": _summarize_list(raw_contracts),
                "normalized": _summarize_list(normalized_contracts),
                "categorized": _summarize_list(categorized_contracts),
                "ledger": _summarize_list(ledger_contracts),
                "signals": _summarize_list(signal_contracts),
                "trends": _summarize_dict(trends_payload),
            },
        }

        out_path = output_path or ARTIFACT_DIR / "golden_run.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_stable_json(artifact), encoding="utf-8")

        return artifact
    finally:
        db.close()


if __name__ == "__main__":
    run_golden_run()
