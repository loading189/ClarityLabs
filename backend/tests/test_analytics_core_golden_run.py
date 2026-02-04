import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.app.analytics.core import (
    compute_cash_summary,
    compute_category_breakdown,
    compute_timeseries,
    compute_vendor_concentration,
    line_from_txn,
)
from backend.app.services import analytics_service
from backend.app.norma.categorize import categorize_txn
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.sim.engine import build_scenario, generate_raw_events_for_scenario
from backend.app.sim.scenarios import ScenarioContext


def _det_id(prefix: str, *, seed: int, occurred_at: datetime, idx: int) -> str:
    key = f"{seed}|{occurred_at.isoformat()}|{idx}|{prefix}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{h}"


def _stable_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonicalize_event_ids(raw_events, *, seed: int) -> None:
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

        if typ == "transaction.posted":
            prefix = "sim"
        elif typ == "stripe.balance.fee":
            prefix = "fee"
        else:
            prefix = (e.get("source") or "evt").lower()

        new_id = _det_id(prefix, seed=seed, occurred_at=e["occurred_at"], idx=i)

        e["source_event_id"] = new_id

        txn = payload.get("transaction")
        if isinstance(txn, dict) and "transaction_id" in txn:
            txn["transaction_id"] = new_id


def _build_lines(seed: int, days: int):
    random.seed(seed)
    start_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_at = start_at + timedelta(days=days)
    ctx = ScenarioContext(business_id="test-biz", tz="UTC", seed=seed)
    scenario = build_scenario("restaurant", ctx, start_at, end_at)
    raw_events, _truth = generate_raw_events_for_scenario(scenario, start_at, end_at)
    _canonicalize_event_ids(raw_events, seed=seed)
    txns = [
        categorize_txn(raw_event_to_txn(e["payload"], e["occurred_at"], source_event_id=e["source_event_id"]))
        for e in raw_events
    ]
    lines = [line_from_txn(txn) for txn in txns]
    return lines, scenario, txns


def test_analytics_core_invariants_restaurant():
    lines, scenario, _txns = _build_lines(seed=1337, days=90)
    assert lines

    start_date = min(line.occurred_at.date() for line in lines)
    end_date = max(line.occurred_at.date() for line in lines)

    summary = compute_cash_summary(lines, start_date, end_date)
    series = compute_timeseries(lines, bucket="day")

    total_inflow = sum(row["inflow"]["value"] for row in series)
    total_outflow = sum(row["outflow"]["value"] for row in series)

    assert abs(total_inflow - summary["inflow"]["value"]) < 0.01
    assert abs(total_outflow - summary["outflow"]["value"]) < 0.01

    category_totals = compute_category_breakdown(lines)
    summed_categories = sum(row["total"]["value"] for row in category_totals)
    assert abs(summed_categories - summary["net"]["value"]) < 0.01

    total_signed = sum(line.signed_amount for line in lines)
    last_cash_end = series[-1]["cash_end"]["value"]
    assert abs(total_signed - last_cash_end) < 0.01

    truth_events = [event for event in scenario.truth_events if event.type == "revenue_drop"]
    assert truth_events
    drop_event = truth_events[0]

    inflow_by_day = {row["date"]: row["inflow"]["value"] for row in series}
    drop_start = drop_event.start_at.date()
    drop_end = drop_event.end_at.date()
    drop_days = [
        (drop_start + timedelta(days=offset)).isoformat()
        for offset in range((drop_end - drop_start).days + 1)
    ]
    prev_end = drop_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=9)
    prev_days = [
        (prev_start + timedelta(days=offset)).isoformat()
        for offset in range((prev_end - prev_start).days + 1)
    ]

    drop_avg = sum(inflow_by_day.get(day, 0.0) for day in drop_days) / max(len(drop_days), 1)
    prev_avg = sum(inflow_by_day.get(day, 0.0) for day in prev_days) / max(len(prev_days), 1)
    assert drop_avg < prev_avg

    vendor_totals = compute_vendor_concentration(lines)
    vendor_outflow = sum(row["outflow"]["value"] for row in vendor_totals)
    assert abs(vendor_outflow - summary["outflow"]["value"]) < 0.01


def test_analytics_core_contract_guards():
    lines_a, _scenario, txns = _build_lines(seed=1337, days=90)
    lines_b, _scenario_b, _txns_b = _build_lines(seed=1337, days=90)

    assert [line.source_event_id for line in lines_a] == [
        line.source_event_id for line in lines_b
    ]
    occurred_times = [line.occurred_at for line in lines_a]
    assert occurred_times == sorted(occurred_times)

    line_by_id = {line.source_event_id: line for line in lines_a}
    assert line_by_id
    for txn in txns:
        line = line_by_id.get(txn.source_event_id)
        assert line is not None
        if txn.direction == "inflow":
            assert line.signed_amount >= 0
        else:
            assert line.signed_amount <= 0
        assert abs(abs(line.signed_amount) - float(txn.amount or 0.0)) < 0.01

    dashboard_payload = analytics_service.build_dashboard_analytics(
        txns,
        start_at=min(line.occurred_at.date() for line in lines_a),
        end_at=max(line.occurred_at.date() for line in lines_a),
        lookback_months=12,
    )
    trends_payload = analytics_service.build_trends_analytics(
        txns,
        start_at=min(line.occurred_at.date() for line in lines_a),
        end_at=max(line.occurred_at.date() for line in lines_a),
        lookback_months=12,
    )

    for key in [
        "computation_version",
        "kpis",
        "series",
        "category_breakdown",
        "vendor_concentration",
        "anomalies",
        "change_explanations",
    ]:
        assert key in dashboard_payload

    for key in ["current_cash", "last_30d_inflow", "last_30d_outflow", "last_30d_net"]:
        assert key in dashboard_payload["kpis"]

    assert "series" in trends_payload
    assert "computation_version" in trends_payload
