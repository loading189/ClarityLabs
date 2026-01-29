from __future__ import annotations
import random
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
import backend.app.sim.models  # noqa: F401


ARTIFACT_DIR = Path("backend/.artifacts/golden")
DEFAULT_BIZ_NAME = "Golden Demo Business"
DEFAULT_ORG_NAME = "Golden Demo Org"

def _det_id(prefix: str, *, seed: int, occurred_at: datetime, idx: int) -> str:
    key = f"{seed}|{occurred_at.isoformat()}|{idx}|{prefix}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{h}"

def _event_fingerprint(e: Dict[str, Any]) -> str:
    # stable representation of the full raw event dict
    return _hash_json({
        "source": e.get("source"),
        "source_event_id": e.get("source_event_id"),
        "occurred_at": e.get("occurred_at").isoformat() if hasattr(e.get("occurred_at"), "isoformat") else e.get("occurred_at"),
        "payload": e.get("payload"),
    })


def debug_first_raw_event_mismatch():
    a = run_golden_run(seed=1337, days=90, scenario_key="restaurant", persist_events=False)
    b = run_golden_run(seed=1337, days=90, scenario_key="restaurant", persist_events=False)

    # we need the underlying raw_events (not the summarized contracts)
    # so temporarily re-run the scenario generation here
    random.seed(1337)
    start_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_at = start_at + timedelta(days=90)
    db = SessionLocal()
    try:
        biz = _get_or_create_demo_business(db, org_name=DEFAULT_ORG_NAME, biz_name=DEFAULT_BIZ_NAME)
        ctx = ScenarioContext(business_id=biz.id, tz="UTC", seed=1337)
        scenario = build_scenario("restaurant", ctx, start_at, end_at)

        random.seed(1337)
        raw_a, _ = generate_raw_events_for_scenario(scenario, start_at, end_at)
        _canonicalize_event_ids(raw_a, seed=1337)

        random.seed(1337)
        raw_b, _ = generate_raw_events_for_scenario(scenario, start_at, end_at)
        _canonicalize_event_ids(raw_b, seed=1337)

        if len(raw_a) != len(raw_b):
            print("DIFF: count", len(raw_a), len(raw_b))
            return

        for i, (ea, eb) in enumerate(zip(raw_a, raw_b)):
            ha, hb = _event_fingerprint(ea), _event_fingerprint(eb)
            if ha != hb:
                print("FIRST MISMATCH INDEX:", i)
                print("A:", _stable_json({
                    "source": ea.get("source"),
                    "source_event_id": ea.get("source_event_id"),
                    "occurred_at": ea.get("occurred_at"),
                    "payload": ea.get("payload"),
                })[:1200])

                print("B:", _stable_json({
                    "source": eb.get("source"),
                    "source_event_id": eb.get("source_event_id"),
                    "occurred_at": eb.get("occurred_at"),
                    "payload": eb.get("payload"),
                })[:1200])

                return

        print("No mismatch found (raw events identical).")
    finally:
        db.close()


def _canonicalize_event_ids(raw_events: List[Dict[str, Any]], *, seed: int) -> None:
    # ensure deterministic ordering before assigning deterministic ids
    raw_events.sort(
        key=lambda e: (
            e["occurred_at"].isoformat() if hasattr(e["occurred_at"], "isoformat") else str(e["occurred_at"]),
            e.get("source", ""),
            _stable_json(e.get("payload", {})),
        )
    )

    for i, e in enumerate(raw_events):
        payload = e.get("payload") or {}
        typ = payload.get("type", "")

        # choose a prefix by event type/source
        if typ == "transaction.posted":
            prefix = "sim"
        elif typ == "stripe.balance.fee":
            prefix = "fee"
        else:
            # fallback: stable but scoped
            prefix = (e.get("source") or "evt").lower()

        new_id = _det_id(prefix, seed=seed, occurred_at=e["occurred_at"], idx=i)

        e["source_event_id"] = new_id

        # keep transaction_id aligned for plaid txns (this is inside your payload)
        txn = payload.get("transaction")
        if isinstance(txn, dict) and "transaction_id" in txn:
            txn["transaction_id"] = new_id


def _model_dump(item: Any) -> Dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return item.dict()  # type: ignore[no-any-return]


def _json_default(o: Any):
    # handle datetimes + dates (and anything else with isoformat)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)

def _stable_json(data: Any) -> str:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


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
    random.seed(seed)  # critical: resets global RNG per run
    start_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_at = start_at + timedelta(days=days)

    db = SessionLocal()
    try:
        biz = _get_or_create_demo_business(db, org_name=org_name, biz_name=business_name)
        ctx = ScenarioContext(business_id=biz.id, tz="UTC", seed=seed)
        scenario = build_scenario(scenario_key, ctx, start_at, end_at)
        raw_events, _truth = generate_raw_events_for_scenario(scenario, start_at, end_at)
        _canonicalize_event_ids(raw_events, seed=seed)


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
                "date": r.date.isoformat(),
                "amount": float(r.amount),
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
