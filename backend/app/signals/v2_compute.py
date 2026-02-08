from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import re
from statistics import mean
from typing import Callable, Dict, Iterable, List, Optional

from backend.app.norma.normalize import NormalizedTransaction


@dataclass(frozen=True)
class DetectedSignal:
    signal_id: str
    signal_type: str
    fingerprint: str
    severity: str
    title: str
    summary: str
    payload: Dict[str, object]


@dataclass(frozen=True)
class DetectorRunResult:
    detector_id: str
    signal_id: str
    domain: str
    ran: bool
    skipped_reason: Optional[str]
    fired: bool
    severity: Optional[str]
    evidence_keys: List[str]


@dataclass(frozen=True)
class DetectorRunSummary:
    signals: List[DetectedSignal]
    detectors: List[DetectorRunResult]


@dataclass(frozen=True)
class DetectorDefinition:
    detector_id: str
    signal_type: str
    domain: str
    runner: Callable[..., List[DetectedSignal]]
    needs_audit_entries: bool = False


_SEVERITY_RANK = {"info": 0, "warning": 1, "medium": 1, "high": 2, "critical": 3}


def _fingerprint(parts: Iterable[object]) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signal_id(signal_type: str, fingerprint: str) -> str:
    return f"{signal_type}:{fingerprint}"


def _normalize_vendor(name: Optional[str]) -> str:
    if not name:
        return "unknown"
    lowered = name.strip().lower()
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered or "unknown"


def _latest_date(txns: Iterable[NormalizedTransaction]) -> Optional[date]:
    dates = [txn.date for txn in txns]
    return max(dates) if dates else None


def _window_dates(last_date: date, window_days: int) -> tuple[date, date]:
    start = last_date - timedelta(days=window_days - 1)
    return start, last_date


def _txns_in_window(
    txns: Iterable[NormalizedTransaction],
    start: date,
    end: date,
) -> List[NormalizedTransaction]:
    return [txn for txn in txns if start <= txn.date <= end]


def _sum_by_date(
    txns: Iterable[NormalizedTransaction],
    direction: Optional[str] = None,
) -> Dict[date, float]:
    totals: Dict[date, float] = {}
    for txn in txns:
        if direction and txn.direction != direction:
            continue
        totals[txn.date] = totals.get(txn.date, 0.0) + float(txn.amount or 0.0)
    return totals


def _sum_total(
    txns: Iterable[NormalizedTransaction],
    direction: Optional[str] = None,
) -> float:
    return sum(
        float(txn.amount or 0.0)
        for txn in txns
        if direction is None or txn.direction == direction
    )


def _txn_ids(txns: Iterable[NormalizedTransaction]) -> List[str]:
    return [txn.source_event_id for txn in txns if txn.source_event_id]


def _evidence_source_event_ids(txns: Iterable[NormalizedTransaction]) -> List[str]:
    ids = {str(txn.source_event_id) for txn in txns if txn.source_event_id}
    return sorted(ids)


def _window_meta(
    start: date,
    end: date,
    *,
    label: str,
    value: Optional[float] = None,
    unit: Optional[str] = None,
) -> Dict[str, object]:
    meta: Dict[str, object] = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": label,
    }
    if value is not None:
        meta["value"] = round(float(value), 2)
    if unit is not None:
        meta["unit"] = unit
    return meta


def _delta_meta(
    value: float,
    *,
    pct: Optional[float] = None,
    unit: Optional[str] = None,
) -> Dict[str, object]:
    delta: Dict[str, object] = {"value": round(float(value), 2)}
    if pct is not None:
        delta["pct"] = round(float(pct), 4)
    if unit is not None:
        delta["unit"] = unit
    return delta


def _avg_balance(values: Iterable[float]) -> tuple[float, int]:
    series = list(values)
    return (mean(series), len(series)) if series else (0.0, 0)
