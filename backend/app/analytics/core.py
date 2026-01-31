from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

COMPUTATION_VERSION = "analytics_core_v1"
Bucket = Literal["day", "month"]


@dataclass(frozen=True)
class AnalyticsLine:
    occurred_at: datetime
    source_event_id: str
    signed_amount: float
    category: Optional[str] = None
    vendor: Optional[str] = None


@dataclass(frozen=True)
class TraceBundle:
    supporting_event_ids: List[str]
    supporting_line_count: int
    computation_version: str
    features_snapshot: Dict[str, Any]


def line_from_txn(txn: Any) -> AnalyticsLine:
    signed_amount = float(txn.amount or 0.0)
    if getattr(txn, "direction", "inflow") != "inflow":
        signed_amount = -signed_amount
    return AnalyticsLine(
        occurred_at=txn.occurred_at,
        source_event_id=txn.source_event_id,
        signed_amount=signed_amount,
        category=getattr(txn, "category", None),
        vendor=getattr(txn, "counterparty_hint", None),
    )


def compute_cash_summary(
    lines: Iterable[AnalyticsLine],
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    ordered = _sorted_lines(lines)
    in_range = [line for line in ordered if start_date <= line.occurred_at.date() <= end_date]

    inflow_ids = [line.source_event_id for line in in_range if line.signed_amount >= 0]
    outflow_ids = [line.source_event_id for line in in_range if line.signed_amount < 0]
    all_ids = [line.source_event_id for line in in_range]

    inflow_total = sum(line.signed_amount for line in in_range if line.signed_amount >= 0)
    outflow_total = sum(abs(line.signed_amount) for line in in_range if line.signed_amount < 0)
    net_total = inflow_total - outflow_total

    cash_end_lines = [line for line in ordered if line.occurred_at.date() <= end_date]
    cash_end = sum(line.signed_amount for line in cash_end_lines)
    cash_end_ids = [line.source_event_id for line in cash_end_lines]

    return {
        "range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "inflow": _metric(inflow_total, inflow_ids, start_date, end_date, "inflow"),
        "outflow": _metric(outflow_total, outflow_ids, start_date, end_date, "outflow"),
        "net": _metric(net_total, all_ids, start_date, end_date, "net"),
        "cash_end": _metric(cash_end, cash_end_ids, start_date, end_date, "cash_end"),
    }


def compute_timeseries(
    lines: Iterable[AnalyticsLine],
    bucket: Bucket = "day",
) -> List[Dict[str, Any]]:
    ordered = _sorted_lines(lines)
    buckets: Dict[str, Dict[str, Any]] = {}
    balance = 0.0

    for line in ordered:
        key = _bucket_key(line.occurred_at, bucket)
        bucket_entry = buckets.get(key)
        if not bucket_entry:
            bucket_entry = {
                "key": key,
                "inflow": 0.0,
                "outflow": 0.0,
                "net": 0.0,
                "cash_end": 0.0,
                "ids_inflow": [],
                "ids_outflow": [],
                "ids_net": [],
                "ids_cash_end": [],
            }
            buckets[key] = bucket_entry

        signed = line.signed_amount
        if signed >= 0:
            bucket_entry["inflow"] += signed
            bucket_entry["ids_inflow"].append(line.source_event_id)
        else:
            bucket_entry["outflow"] += abs(signed)
            bucket_entry["ids_outflow"].append(line.source_event_id)

        bucket_entry["net"] += signed
        bucket_entry["ids_net"].append(line.source_event_id)

        balance += signed
        bucket_entry["cash_end"] = balance
        bucket_entry["ids_cash_end"].append(line.source_event_id)

    rows: List[Dict[str, Any]] = []
    for key in sorted(buckets.keys()):
        entry = buckets[key]
        label = "month" if bucket == "month" else "date"
        rows.append(
            {
                label: entry["key"],
                "inflow": _metric(entry["inflow"], entry["ids_inflow"], None, None, "inflow"),
                "outflow": _metric(entry["outflow"], entry["ids_outflow"], None, None, "outflow"),
                "net": _metric(entry["net"], entry["ids_net"], None, None, "net"),
                "cash_end": _metric(entry["cash_end"], entry["ids_cash_end"], None, None, "cash_end"),
            }
        )

    return rows


def compute_category_breakdown(lines: Iterable[AnalyticsLine]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for line in _sorted_lines(lines):
        category = (line.category or "uncategorized").strip() or "uncategorized"
        entry = grouped.setdefault(
            category,
            {"category": category, "total": 0.0, "ids": [], "inflow": 0.0, "outflow": 0.0},
        )
        entry["total"] += line.signed_amount
        entry["ids"].append(line.source_event_id)
        if line.signed_amount >= 0:
            entry["inflow"] += line.signed_amount
        else:
            entry["outflow"] += abs(line.signed_amount)

    output = []
    for category, entry in grouped.items():
        output.append(
            {
                "category": category,
                "total": _metric(entry["total"], entry["ids"], None, None, "category_total"),
                "inflow": _metric(entry["inflow"], entry["ids"], None, None, "category_inflow"),
                "outflow": _metric(entry["outflow"], entry["ids"], None, None, "category_outflow"),
            }
        )

    output.sort(
        key=lambda row: (-abs(row["total"]["value"]), str(row["category"]).lower())
    )
    return output


def compute_vendor_concentration(lines: Iterable[AnalyticsLine]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for line in _sorted_lines(lines):
        if line.signed_amount >= 0:
            continue
        vendor = (line.vendor or "unknown").strip() or "unknown"
        entry = grouped.setdefault(
            vendor,
            {"vendor": vendor, "outflow": 0.0, "ids": []},
        )
        entry["outflow"] += abs(line.signed_amount)
        entry["ids"].append(line.source_event_id)

    total_outflow = sum(entry["outflow"] for entry in grouped.values())
    output = []
    for vendor, entry in grouped.items():
        share = (entry["outflow"] / total_outflow) if total_outflow else 0.0
        output.append(
            {
                "vendor": vendor,
                "outflow": _metric(entry["outflow"], entry["ids"], None, None, "vendor_outflow"),
                "share": share,
            }
        )
    output.sort(key=lambda row: (-row["outflow"]["value"], row["vendor"]))
    return output


def detect_anomalies(lines: Iterable[AnalyticsLine], threshold: float = 3.5) -> List[Dict[str, Any]]:
    series = compute_timeseries(lines, bucket="day")
    if not series:
        return []

    values = [row["net"]["value"] for row in series]
    median = _median(values)
    mad = _mad(values, median)
    scale = mad or 1.0

    anomalies = []
    for row in series:
        z = (row["net"]["value"] - median) / scale if scale else 0.0
        if abs(z) < threshold:
            continue
        trace = row["net"]["trace"]
        anomalies.append(
            {
                "date": row["date"],
                "net": row["net"],
                "z_score": z,
                "trace": trace,
            }
        )
    return anomalies


def explain_change(
    prev_period: Iterable[AnalyticsLine],
    curr_period: Iterable[AnalyticsLine],
    top_n: int = 5,
) -> Dict[str, Any]:
    prev_by_category = _sum_by_key(prev_period, key="category")
    curr_by_category = _sum_by_key(curr_period, key="category")
    prev_by_vendor = _sum_by_key(prev_period, key="vendor", only_outflow=True)
    curr_by_vendor = _sum_by_key(curr_period, key="vendor", only_outflow=True)

    category_drivers = _build_drivers(prev_by_category, curr_by_category, top_n)
    vendor_drivers = _build_drivers(prev_by_vendor, curr_by_vendor, top_n)

    return {
        "category_drivers": category_drivers,
        "vendor_drivers": vendor_drivers,
    }


def _build_drivers(
    prev: Dict[str, Dict[str, Any]],
    curr: Dict[str, Dict[str, Any]],
    top_n: int,
) -> List[Dict[str, Any]]:
    deltas: List[Tuple[str, float]] = []
    for key in set(prev.keys()) | set(curr.keys()):
        deltas.append((key, curr.get(key, {}).get("total", 0.0) - prev.get(key, {}).get("total", 0.0)))

    deltas.sort(key=lambda item: -abs(item[1]))
    drivers = []
    for key, delta in deltas[:top_n]:
        curr_entry = curr.get(key, {"total": 0.0, "ids": []})
        prev_entry = prev.get(key, {"total": 0.0, "ids": []})
        trace = _trace_bundle(
            curr_entry.get("ids", []),
            {
                "prev_total": prev_entry.get("total", 0.0),
                "curr_total": curr_entry.get("total", 0.0),
            },
        )
        drivers.append(
            {
                "name": key,
                "delta": _metric(delta, curr_entry.get("ids", []), None, None, "delta"),
                "prev_total": _metric(prev_entry.get("total", 0.0), prev_entry.get("ids", []), None, None, "prev_total"),
                "curr_total": _metric(curr_entry.get("total", 0.0), curr_entry.get("ids", []), None, None, "curr_total"),
                "trace": trace,
            }
        )
    return drivers


def _sum_by_key(
    lines: Iterable[AnalyticsLine],
    *,
    key: Literal["category", "vendor"],
    only_outflow: bool = False,
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for line in _sorted_lines(lines):
        if only_outflow and line.signed_amount >= 0:
            continue
        label = getattr(line, key) or ("unknown" if key == "vendor" else "uncategorized")
        label = str(label).strip() or ("unknown" if key == "vendor" else "uncategorized")
        entry = grouped.setdefault(label, {"total": 0.0, "ids": []})
        entry["total"] += abs(line.signed_amount) if only_outflow else line.signed_amount
        entry["ids"].append(line.source_event_id)
    return grouped


def _sorted_lines(lines: Iterable[AnalyticsLine]) -> List[AnalyticsLine]:
    return sorted(lines, key=lambda line: (line.occurred_at, line.source_event_id))


def _bucket_key(occurred_at: datetime, bucket: Bucket) -> str:
    if bucket == "month":
        return f"{occurred_at.year:04d}-{occurred_at.month:02d}"
    return occurred_at.date().isoformat()


def _trace_bundle(supporting_event_ids: List[str], features_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "supporting_event_ids": supporting_event_ids,
        "supporting_line_count": len(supporting_event_ids),
        "computation_version": COMPUTATION_VERSION,
        "features_snapshot": features_snapshot,
    }


def _metric(
    value: float,
    supporting_event_ids: List[str],
    start_date: Optional[date],
    end_date: Optional[date],
    metric_name: str,
) -> Dict[str, Any]:
    snapshot = {"metric": metric_name}
    if start_date and end_date:
        snapshot["range"] = {"start": start_date.isoformat(), "end": end_date.isoformat()}
    return {
        "value": float(value),
        "trace": _trace_bundle(supporting_event_ids, snapshot),
    }


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _mad(values: List[float], median: float) -> float:
    if not values:
        return 0.0
    deviations = [abs(v - median) for v in values]
    return _median(deviations) if deviations else 0.0
