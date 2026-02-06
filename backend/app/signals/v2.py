from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import math
import re
from statistics import mean, pstdev
from typing import Callable, Dict, Iterable, List, Optional

from backend.app.norma.ledger import build_cash_ledger
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


def detect_expense_creep_by_vendor(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 14,
    threshold_pct: float = 0.40,
    min_delta: float = 200.0,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    current_start = last_date - timedelta(days=window_days - 1)
    prior_end = current_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=window_days - 1)

    current: Dict[str, float] = {}
    prior: Dict[str, float] = {}
    current_txns: Dict[str, List[NormalizedTransaction]] = {}
    prior_txns: Dict[str, List[NormalizedTransaction]] = {}
    vendor_label: Dict[str, str] = {}

    for txn in txns:
        if txn.direction != "outflow":
            continue
        vendor_raw = txn.counterparty_hint or txn.description
        vendor_key = _normalize_vendor(vendor_raw)
        vendor_label.setdefault(vendor_key, vendor_raw or "Unknown")
        if prior_start <= txn.date <= prior_end:
            prior[vendor_key] = prior.get(vendor_key, 0.0) + float(txn.amount or 0.0)
            prior_txns.setdefault(vendor_key, []).append(txn)
        if current_start <= txn.date <= last_date:
            current[vendor_key] = current.get(vendor_key, 0.0) + float(txn.amount or 0.0)
            current_txns.setdefault(vendor_key, []).append(txn)

    signals: List[DetectedSignal] = []
    for vendor_key, current_total in current.items():
        prior_total = prior.get(vendor_key, 0.0)
        if prior_total <= 0.0:
            continue
        delta = current_total - prior_total
        if delta <= 0:
            continue
        increase_pct = delta / prior_total
        if increase_pct < threshold_pct or delta < min_delta:
            continue

        severity = "high" if increase_pct >= 1.0 or delta >= (min_delta * 3) else "medium"
        vendor_name = vendor_label.get(vendor_key, vendor_key)
        evidence_txns = (current_txns.get(vendor_key) or []) + (prior_txns.get(vendor_key) or [])
        payload = {
            "vendor_key": vendor_key,
            "vendor_name": vendor_name,
            "current_total": round(current_total, 2),
            "prior_total": round(prior_total, 2),
            "delta": round(delta, 2),
            "increase_pct": round(increase_pct, 4),
            "window_days": window_days,
            "threshold_pct": threshold_pct,
            "min_delta": min_delta,
            "current_window": {"start": current_start.isoformat(), "end": last_date.isoformat()},
            "prior_window": {"start": prior_start.isoformat(), "end": prior_end.isoformat()},
            "evidence_source_event_ids": _evidence_source_event_ids(evidence_txns),
        }
        signal_type = "expense_creep_by_vendor"
        fingerprint = _fingerprint([business_id, signal_type, vendor_key])
        signals.append(
            DetectedSignal(
                signal_id=_signal_id(signal_type, fingerprint),
                signal_type=signal_type,
                fingerprint=fingerprint,
                severity=severity,
                title=f"Expense creep: {vendor_name}",
                summary=(
                    f"Outflow to {vendor_name} rose {increase_pct:.0%} "
                    f"(${delta:,.0f}) over the prior {window_days} days."
                ),
                payload=payload,
            )
        )

    return signals


def detect_low_cash_runway(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    burn_window_days: int = 30,
    high_threshold_days: int = 30,
    medium_threshold_days: int = 60,
    epsilon: float = 1e-6,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    ledger = build_cash_ledger(txns, opening_balance=0.0)
    current_cash = float(ledger[-1].balance) if ledger else 0.0

    burn_start, burn_end = _window_dates(last_date, burn_window_days)
    burn_txns = _txns_in_window(txns, burn_start, burn_end)
    inflow_total = _sum_total(burn_txns, "inflow")
    outflow_total = _sum_total(burn_txns, "outflow")

    net_burn = outflow_total - inflow_total
    burn_per_day = net_burn / burn_window_days
    runway_days = current_cash / max(burn_per_day, epsilon) if current_cash > 0 else 0.0

    severity: Optional[str] = None
    if runway_days < high_threshold_days:
        severity = "high"
    elif runway_days < medium_threshold_days:
        severity = "medium"

    if not severity:
        return []

    evidence_ids = _evidence_source_event_ids(burn_txns)
    if ledger and ledger[-1].source_event_id:
        evidence_ids.append(ledger[-1].source_event_id)
        evidence_ids = sorted(set(evidence_ids))
    payload = {
        "current_cash": round(current_cash, 2),
        "burn_window_days": burn_window_days,
        "burn_start": burn_start.isoformat(),
        "burn_end": burn_end.isoformat(),
        "total_inflow": round(inflow_total, 2),
        "total_outflow": round(outflow_total, 2),
        "net_burn": round(net_burn, 2),
        "burn_per_day": round(burn_per_day, 4),
        "runway_days": round(runway_days, 2),
        "epsilon": epsilon,
        "thresholds": {"high": high_threshold_days, "medium": medium_threshold_days},
        "evidence_source_event_ids": evidence_ids,
    }
    signal_type = "low_cash_runway"
    fingerprint = _fingerprint([business_id, signal_type])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Low cash runway",
            summary=f"Runway is {runway_days:.1f} days based on the last {burn_window_days} days of burn.",
            payload=payload,
        )
    ]


def detect_unusual_outflow_spike(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 30,
    trailing_mean_days: int = 14,
    spike_sigma: float = 3.0,
    spike_mult: float = 2.5,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    start_date = last_date - timedelta(days=window_days - 1)
    daily_totals: Dict[date, float] = {start_date + timedelta(days=i): 0.0 for i in range(window_days)}

    for txn in txns:
        if txn.direction != "outflow":
            continue
        if txn.date < start_date or txn.date > last_date:
            continue
        daily_totals[txn.date] = daily_totals.get(txn.date, 0.0) + float(txn.amount or 0.0)

    ordered_dates = sorted(daily_totals.keys())
    totals = [daily_totals[d] for d in ordered_dates]
    if not totals:
        return []

    avg = mean(totals)
    std = pstdev(totals) if len(totals) > 1 else 0.0
    latest_total = daily_totals[last_date]

    trailing_start = last_date - timedelta(days=trailing_mean_days)
    trailing_dates = [
        d for d in ordered_dates if trailing_start <= d < last_date
    ]
    trailing_mean = mean([daily_totals[d] for d in trailing_dates]) if trailing_dates else 0.0

    threshold_sigma = avg + (spike_sigma * std)
    threshold_mult = spike_mult * trailing_mean if trailing_mean > 0 else math.inf

    trigger_sigma = latest_total > threshold_sigma
    trigger_mult = latest_total > threshold_mult
    if not (trigger_sigma or trigger_mult):
        return []

    severity = "high" if trigger_sigma else "medium"
    spike_txns = [
        txn
        for txn in txns
        if txn.direction == "outflow" and txn.date == last_date
    ]
    payload = {
        "latest_date": last_date.isoformat(),
        "latest_total": round(latest_total, 2),
        "mean_30d": round(avg, 2),
        "std_30d": round(std, 2),
        "sigma_threshold": round(threshold_sigma, 2),
        "trailing_mean_days": trailing_mean_days,
        "trailing_mean": round(trailing_mean, 2),
        "mult_threshold": round(threshold_mult, 2) if math.isfinite(threshold_mult) else None,
        "window_days": window_days,
        "spike_sigma": spike_sigma,
        "spike_mult": spike_mult,
        "evidence_source_event_ids": _evidence_source_event_ids(spike_txns),
    }
    signal_type = "unusual_outflow_spike"
    fingerprint = _fingerprint([business_id, signal_type, last_date.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Unusual outflow spike",
            summary=f"Outflows on {last_date.isoformat()} spiked to ${latest_total:,.0f}.",
            payload=payload,
        )
    ]


def detect_liquidity_runway_low(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    burn_window_days: int = 30,
    high_threshold_days: int = 30,
    medium_threshold_days: int = 60,
    epsilon: float = 1e-6,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    ledger = build_cash_ledger(txns, opening_balance=0.0)
    current_cash = float(ledger[-1].balance) if ledger else 0.0

    burn_start, burn_end = _window_dates(last_date, burn_window_days)
    burn_txns = _txns_in_window(txns, burn_start, burn_end)
    inflow_total = _sum_total(burn_txns, "inflow")
    outflow_total = _sum_total(burn_txns, "outflow")

    net_burn = outflow_total - inflow_total
    burn_per_day = net_burn / burn_window_days
    runway_days = current_cash / max(burn_per_day, epsilon) if current_cash > 0 else 0.0

    severity: Optional[str] = None
    if runway_days < high_threshold_days:
        severity = "critical"
    elif runway_days < medium_threshold_days:
        severity = "warning"

    if not severity:
        return []

    payload = {
        "current_cash": round(current_cash, 2),
        "burn_window_days": burn_window_days,
        "burn_start": burn_start.isoformat(),
        "burn_end": burn_end.isoformat(),
        "total_inflow": round(inflow_total, 2),
        "total_outflow": round(outflow_total, 2),
        "net_burn": round(net_burn, 2),
        "burn_per_day": round(burn_per_day, 4),
        "runway_days": round(runway_days, 2),
        "thresholds": {"high": high_threshold_days, "medium": medium_threshold_days},
        "txn_ids": _txn_ids(burn_txns),
    }
    signal_type = "liquidity.runway_low"
    fingerprint = _fingerprint([business_id, signal_type])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Low cash runway",
            summary=f"Runway is {runway_days:.1f} days based on the last {burn_window_days} days.",
            payload=payload,
        )
    ]


def detect_liquidity_cash_trend_down(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 14,
    min_delta: float = 500.0,
    decline_pct: float = 0.15,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    ledger = build_cash_ledger(txns, opening_balance=0.0)
    if not ledger:
        return []

    balance_by_date: Dict[date, float] = {}
    for row in ledger:
        balance_by_date[row.date] = float(row.balance)

    current_start, current_end = _window_dates(last_date, window_days)
    prior_end = current_start - timedelta(days=1)
    prior_start, _ = _window_dates(prior_end, window_days)

    def _avg_balance(start: date, end: date) -> tuple[float, int]:
        values = [balance_by_date[d] for d in balance_by_date if start <= d <= end]
        return (mean(values), len(values)) if values else (0.0, 0)

    current_avg, current_days = _avg_balance(current_start, current_end)
    prior_avg, prior_days = _avg_balance(prior_start, prior_end)
    if current_days < 5 or prior_days < 5 or prior_avg == 0:
        return []

    delta = current_avg - prior_avg
    decline = -delta / abs(prior_avg) if delta < 0 else 0.0
    if delta >= -min_delta or decline < decline_pct:
        return []

    severity = "warning" if decline < 0.3 else "critical"
    payload = {
        "current_window": {"start": current_start.isoformat(), "end": current_end.isoformat()},
        "prior_window": {"start": prior_start.isoformat(), "end": prior_end.isoformat()},
        "current_avg_balance": round(current_avg, 2),
        "prior_avg_balance": round(prior_avg, 2),
        "delta": round(delta, 2),
        "decline_pct": round(decline, 4),
        "sample_days": {"current": current_days, "prior": prior_days},
        "txn_ids": _txn_ids(_txns_in_window(txns, current_start, current_end)),
    }
    signal_type = "liquidity.cash_trend_down"
    fingerprint = _fingerprint([business_id, signal_type, current_end.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Cash balance trending down",
            summary=f"Average cash balance declined {decline:.0%} vs the prior period.",
            payload=payload,
        )
    ]


def detect_revenue_decline_vs_baseline(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 30,
    decline_pct: float = 0.25,
    min_delta: float = 500.0,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    current_start, current_end = _window_dates(last_date, window_days)
    prior_end = current_start - timedelta(days=1)
    prior_start, _ = _window_dates(prior_end, window_days)

    current_txns = _txns_in_window(txns, current_start, current_end)
    prior_txns = _txns_in_window(txns, prior_start, prior_end)
    current_total = _sum_total(current_txns, "inflow")
    prior_total = _sum_total(prior_txns, "inflow")
    if prior_total <= 0:
        return []
    delta = current_total - prior_total
    decline = (-delta / prior_total) if delta < 0 else 0.0
    if decline < decline_pct or abs(delta) < min_delta:
        return []

    severity = "critical" if decline >= 0.4 else "warning"
    payload = {
        "current_window": {"start": current_start.isoformat(), "end": current_end.isoformat()},
        "prior_window": {"start": prior_start.isoformat(), "end": prior_end.isoformat()},
        "current_total": round(current_total, 2),
        "prior_total": round(prior_total, 2),
        "delta": round(delta, 2),
        "decline_pct": round(decline, 4),
        "txn_ids": _txn_ids([txn for txn in current_txns if txn.direction == "inflow"]),
    }
    signal_type = "revenue.decline_vs_baseline"
    fingerprint = _fingerprint([business_id, signal_type, current_end.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Revenue decline vs baseline",
            summary=f"Revenue declined {decline:.0%} vs the prior {window_days} days.",
            payload=payload,
        )
    ]


def detect_revenue_volatility_spike(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 30,
    ratio_threshold: float = 1.6,
    min_std: float = 200.0,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    current_start, current_end = _window_dates(last_date, window_days)
    prior_end = current_start - timedelta(days=1)
    prior_start, _ = _window_dates(prior_end, window_days)

    current_txns = _txns_in_window(txns, current_start, current_end)
    prior_txns = _txns_in_window(txns, prior_start, prior_end)
    current_totals = _sum_by_date(current_txns, "inflow")
    prior_totals = _sum_by_date(prior_txns, "inflow")
    current_series = list(current_totals.values())
    prior_series = list(prior_totals.values())
    if len(current_series) < 5 or len(prior_series) < 5:
        return []
    current_std = pstdev(current_series) if len(current_series) > 1 else 0.0
    prior_std = pstdev(prior_series) if len(prior_series) > 1 else 0.0
    if prior_std <= 0:
        return []
    ratio = current_std / prior_std
    if ratio < ratio_threshold or current_std < min_std:
        return []

    severity = "critical" if ratio >= 2.2 else "warning"
    payload = {
        "current_window": {"start": current_start.isoformat(), "end": current_end.isoformat()},
        "prior_window": {"start": prior_start.isoformat(), "end": prior_end.isoformat()},
        "current_std": round(current_std, 2),
        "prior_std": round(prior_std, 2),
        "ratio": round(ratio, 4),
        "window_days": window_days,
        "txn_ids": _txn_ids([txn for txn in current_txns if txn.direction == "inflow"]),
    }
    signal_type = "revenue.volatility_spike"
    fingerprint = _fingerprint([business_id, signal_type, current_end.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Revenue volatility spike",
            summary="Revenue volatility is elevated compared to the prior period.",
            payload=payload,
        )
    ]


def detect_expense_spike_vs_baseline(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    current_days: int = 7,
    baseline_days: int = 30,
    ratio_threshold: float = 1.8,
    min_delta: float = 500.0,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    current_start, current_end = _window_dates(last_date, current_days)
    baseline_end = current_start - timedelta(days=1)
    baseline_start, _ = _window_dates(baseline_end, baseline_days)

    current_txns = _txns_in_window(txns, current_start, current_end)
    baseline_txns = _txns_in_window(txns, baseline_start, baseline_end)
    current_total = _sum_total(current_txns, "outflow")
    baseline_total = _sum_total(baseline_txns, "outflow")
    baseline_avg = (baseline_total / baseline_days) * current_days if baseline_days else 0.0
    if baseline_avg <= 0:
        return []
    ratio = current_total / baseline_avg if baseline_avg > 0 else 0.0
    delta = current_total - baseline_avg
    if ratio < ratio_threshold or delta < min_delta:
        return []

    severity = "critical" if ratio >= 2.5 else "warning"
    payload = {
        "current_window": {"start": current_start.isoformat(), "end": current_end.isoformat()},
        "prior_window": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
        "current_total": round(current_total, 2),
        "baseline_avg": round(baseline_avg, 2),
        "ratio": round(ratio, 4),
        "delta": round(delta, 2),
        "txn_ids": _txn_ids([txn for txn in current_txns if txn.direction == "outflow"]),
    }
    signal_type = "expense.spike_vs_baseline"
    fingerprint = _fingerprint([business_id, signal_type, current_end.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity=severity,
            title="Expense spike vs baseline",
            summary="Recent outflows spiked above the baseline trend.",
            payload=payload,
        )
    ]


def detect_expense_new_recurring(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    current_days: int = 30,
    prior_days: int = 60,
    min_txns: int = 3,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    current_start, current_end = _window_dates(last_date, current_days)
    prior_end = current_start - timedelta(days=1)
    prior_start, _ = _window_dates(prior_end, prior_days)

    current_txns = [txn for txn in _txns_in_window(txns, current_start, current_end) if txn.direction == "outflow"]
    prior_txns = [txn for txn in _txns_in_window(txns, prior_start, prior_end) if txn.direction == "outflow"]

    current_by_vendor: Dict[str, List[NormalizedTransaction]] = {}
    prior_vendor_keys = set()
    for txn in prior_txns:
        vendor_key = _normalize_vendor(txn.counterparty_hint or txn.description)
        prior_vendor_keys.add(vendor_key)
    for txn in current_txns:
        vendor_key = _normalize_vendor(txn.counterparty_hint or txn.description)
        current_by_vendor.setdefault(vendor_key, []).append(txn)

    signals: List[DetectedSignal] = []
    for vendor_key in sorted(current_by_vendor.keys()):
        vendor_txns = current_by_vendor[vendor_key]
        if vendor_key in prior_vendor_keys:
            continue
        if len(vendor_txns) < min_txns:
            continue
        vendor_name = vendor_txns[0].counterparty_hint or vendor_txns[0].description or vendor_key
        total_amount = _sum_total(vendor_txns, "outflow")
        payload = {
            "vendor_key": vendor_key,
            "vendor_name": vendor_name,
            "txn_count": len(vendor_txns),
            "total_amount": round(total_amount, 2),
            "first_seen": min(txn.date for txn in vendor_txns).isoformat(),
            "last_seen": max(txn.date for txn in vendor_txns).isoformat(),
            "window_days": current_days,
            "txn_ids": _txn_ids(vendor_txns),
        }
        signal_type = "expense.new_recurring"
        fingerprint = _fingerprint([business_id, signal_type, vendor_key])
        signals.append(
            DetectedSignal(
                signal_id=_signal_id(signal_type, fingerprint),
                signal_type=signal_type,
                fingerprint=fingerprint,
                severity="warning",
                title=f"New recurring expense: {vendor_name}",
                summary=f"Detected {len(vendor_txns)} new recurring outflows to {vendor_name}.",
                payload=payload,
            )
        )

    return signals


def detect_timing_inflow_outflow_mismatch(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 30,
    min_total: float = 1000.0,
    gap_days: int = 5,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    window_start, window_end = _window_dates(last_date, window_days)
    window_txns = _txns_in_window(txns, window_start, window_end)
    inflows = [txn for txn in window_txns if txn.direction == "inflow"]
    outflows = [txn for txn in window_txns if txn.direction == "outflow"]
    inflow_total = _sum_total(inflows, "inflow")
    outflow_total = _sum_total(outflows, "outflow")
    if inflow_total < min_total or outflow_total < min_total:
        return []

    def _centroid(txns_subset: List[NormalizedTransaction]) -> float:
        total = sum(float(txn.amount or 0.0) for txn in txns_subset)
        if total <= 0:
            return 0.0
        weighted = sum(txn.date.toordinal() * float(txn.amount or 0.0) for txn in txns_subset)
        return weighted / total

    inflow_centroid = _centroid(inflows)
    outflow_centroid = _centroid(outflows)
    if inflow_centroid <= 0 or outflow_centroid <= 0:
        return []
    gap = inflow_centroid - outflow_centroid
    if gap < gap_days:
        return []

    payload = {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "inflow_centroid": round(inflow_centroid, 2),
        "outflow_centroid": round(outflow_centroid, 2),
        "centroid_gap_days": round(gap, 2),
        "inflow_total": round(inflow_total, 2),
        "outflow_total": round(outflow_total, 2),
        "txn_ids": _txn_ids(outflows),
    }
    signal_type = "timing.inflow_outflow_mismatch"
    fingerprint = _fingerprint([business_id, signal_type, window_end.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity="warning",
            title="Inflow/outflow timing mismatch",
            summary="Outflows cluster earlier than inflows in the recent window.",
            payload=payload,
        )
    ]


def detect_timing_payroll_rent_cliff(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 30,
    ratio_threshold: float = 0.4,
    min_total: float = 500.0,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    window_start, window_end = _window_dates(last_date, window_days)
    window_txns = [
        txn
        for txn in _txns_in_window(txns, window_start, window_end)
        if txn.direction == "outflow"
    ]
    if not window_txns:
        return []

    def _is_target(txn: NormalizedTransaction) -> bool:
        category = (txn.category or "").strip().lower()
        description = (txn.description or "").strip().lower()
        return category in {"payroll", "rent"} or "payroll" in description or "rent" in description

    target_txns = [txn for txn in window_txns if _is_target(txn)]
    if not target_txns:
        return []

    totals_by_date = _sum_by_date(target_txns)
    cliff_date = max(totals_by_date, key=totals_by_date.get)
    cliff_total = totals_by_date[cliff_date]
    total_outflow = _sum_total(window_txns, "outflow")
    if total_outflow <= 0:
        return []
    ratio = cliff_total / total_outflow
    if ratio < ratio_threshold or cliff_total < min_total:
        return []

    payload = {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "cliff_date": cliff_date.isoformat(),
        "cliff_total": round(cliff_total, 2),
        "outflow_total": round(total_outflow, 2),
        "cliff_ratio": round(ratio, 4),
        "txn_ids": _txn_ids([txn for txn in target_txns if txn.date == cliff_date]),
    }
    signal_type = "timing.payroll_rent_cliff"
    fingerprint = _fingerprint([business_id, signal_type, cliff_date.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity="warning",
            title="Payroll/rent cash cliff",
            summary="Payroll or rent outflows are concentrated into a single day.",
            payload=payload,
        )
    ]


def _detect_concentration(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    direction: str,
    signal_type: str,
    title_prefix: str,
    share_threshold: float,
    min_total: float,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    window_start, window_end = _window_dates(last_date, 30)
    window_txns = [txn for txn in _txns_in_window(txns, window_start, window_end) if txn.direction == direction]
    if not window_txns:
        return []

    totals: Dict[str, float] = {}
    txn_map: Dict[str, List[NormalizedTransaction]] = {}
    for txn in window_txns:
        name = _normalize_vendor(txn.counterparty_hint or txn.description)
        if name == "unknown":
            continue
        totals[name] = totals.get(name, 0.0) + float(txn.amount or 0.0)
        txn_map.setdefault(name, []).append(txn)

    if not totals:
        return []

    sorted_totals = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    top_name, top_total = sorted_totals[0]
    total = sum(totals.values())
    if total < min_total:
        return []
    share = top_total / total if total > 0 else 0.0
    if share < share_threshold:
        return []

    label = txn_map[top_name][0].counterparty_hint or txn_map[top_name][0].description or top_name
    payload = {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "counterparty_name": label,
        "counterparty_total": round(top_total, 2),
        "total_amount": round(total, 2),
        "share": round(share, 4),
        "txn_ids": _txn_ids(txn_map[top_name]),
    }
    fingerprint = _fingerprint([business_id, signal_type, top_name])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity="warning",
            title=f"{title_prefix}: {label}",
            summary=f"{title_prefix} accounts for {share:.0%} of recent volume.",
            payload=payload,
        )
    ]


def detect_concentration_revenue_top_customer(
    business_id: str,
    txns: List[NormalizedTransaction],
) -> List[DetectedSignal]:
    return _detect_concentration(
        business_id,
        txns,
        direction="inflow",
        signal_type="concentration.revenue_top_customer",
        title_prefix="Top customer concentration",
        share_threshold=0.6,
        min_total=1000.0,
    )


def detect_concentration_expense_top_vendor(
    business_id: str,
    txns: List[NormalizedTransaction],
) -> List[DetectedSignal]:
    return _detect_concentration(
        business_id,
        txns,
        direction="outflow",
        signal_type="concentration.expense_top_vendor",
        title_prefix="Top vendor concentration",
        share_threshold=0.5,
        min_total=1000.0,
    )


def detect_hygiene_uncategorized_high(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    window_days: int = 30,
    ratio_threshold: float = 0.3,
    min_count: int = 5,
) -> List[DetectedSignal]:
    last_date = _latest_date(txns)
    if not last_date:
        return []

    window_start, window_end = _window_dates(last_date, window_days)
    window_txns = _txns_in_window(txns, window_start, window_end)
    if not window_txns:
        return []
    uncategorized = [txn for txn in window_txns if (txn.category or "").strip().lower() == "uncategorized"]
    ratio = len(uncategorized) / len(window_txns) if window_txns else 0.0
    if ratio < ratio_threshold or len(uncategorized) < min_count:
        return []

    payload = {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "uncategorized_count": len(uncategorized),
        "total_count": len(window_txns),
        "uncategorized_ratio": round(ratio, 4),
        "txn_ids": _txn_ids(uncategorized),
    }
    signal_type = "hygiene.uncategorized_high"
    fingerprint = _fingerprint([business_id, signal_type, window_end.isoformat()])
    return [
        DetectedSignal(
            signal_id=_signal_id(signal_type, fingerprint),
            signal_type=signal_type,
            fingerprint=fingerprint,
            severity="info" if ratio < 0.45 else "warning",
            title="High uncategorized transactions",
            summary="A large share of recent transactions are uncategorized.",
            payload=payload,
        )
    ]


def detect_hygiene_signal_flapping(
    business_id: str,
    audit_entries: List[Dict[str, object]],
    *,
    window_days: int = 14,
    min_changes: int = 3,
) -> List[DetectedSignal]:
    if not audit_entries:
        return []

    signal_changes: Dict[str, List[date]] = {}
    for entry in audit_entries:
        after_state = entry.get("after_state") if isinstance(entry, dict) else None
        if not isinstance(after_state, dict):
            continue
        signal_id = after_state.get("signal_id")
        if not signal_id:
            continue
        created_at = entry.get("created_at")
        if not isinstance(created_at, date):
            continue
        signal_changes.setdefault(str(signal_id), []).append(created_at)

    signals: List[DetectedSignal] = []
    for signal_id in sorted(signal_changes.keys()):
        dates = signal_changes[signal_id]
        if len(dates) < min_changes:
            continue
        dates_sorted = sorted(dates)
        window_start = dates_sorted[0]
        window_end = dates_sorted[-1]
        payload = {
            "signal_id": signal_id,
            "change_count": len(dates_sorted),
            "window_days": window_days,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        }
        signal_type = "hygiene.signal_flapping"
        fingerprint = _fingerprint([business_id, signal_type, signal_id])
        signals.append(
            DetectedSignal(
                signal_id=_signal_id(signal_type, fingerprint),
                signal_type=signal_type,
                fingerprint=fingerprint,
                severity="warning",
                title="Signal flapping detected",
                summary=f"Signal {signal_id} changed status {len(dates_sorted)} times recently.",
                payload=payload,
            )
        )

    return signals


DETECTOR_DEFINITIONS: List[DetectorDefinition] = [
    DetectorDefinition("detect_expense_creep_by_vendor", "expense_creep_by_vendor", "expense", detect_expense_creep_by_vendor),
    DetectorDefinition("detect_low_cash_runway", "low_cash_runway", "liquidity", detect_low_cash_runway),
    DetectorDefinition("detect_unusual_outflow_spike", "unusual_outflow_spike", "expense", detect_unusual_outflow_spike),
    DetectorDefinition("detect_liquidity_runway_low", "liquidity.runway_low", "liquidity", detect_liquidity_runway_low),
    DetectorDefinition("detect_liquidity_cash_trend_down", "liquidity.cash_trend_down", "liquidity", detect_liquidity_cash_trend_down),
    DetectorDefinition("detect_revenue_decline_vs_baseline", "revenue.decline_vs_baseline", "revenue", detect_revenue_decline_vs_baseline),
    DetectorDefinition("detect_revenue_volatility_spike", "revenue.volatility_spike", "revenue", detect_revenue_volatility_spike),
    DetectorDefinition("detect_expense_spike_vs_baseline", "expense.spike_vs_baseline", "expense", detect_expense_spike_vs_baseline),
    DetectorDefinition("detect_expense_new_recurring", "expense.new_recurring", "expense", detect_expense_new_recurring),
    DetectorDefinition("detect_timing_inflow_outflow_mismatch", "timing.inflow_outflow_mismatch", "timing", detect_timing_inflow_outflow_mismatch),
    DetectorDefinition("detect_timing_payroll_rent_cliff", "timing.payroll_rent_cliff", "timing", detect_timing_payroll_rent_cliff),
    DetectorDefinition("detect_concentration_revenue_top_customer", "concentration.revenue_top_customer", "concentration", detect_concentration_revenue_top_customer),
    DetectorDefinition("detect_concentration_expense_top_vendor", "concentration.expense_top_vendor", "concentration", detect_concentration_expense_top_vendor),
    DetectorDefinition("detect_hygiene_uncategorized_high", "hygiene.uncategorized_high", "hygiene", detect_hygiene_uncategorized_high),
    DetectorDefinition("detect_hygiene_signal_flapping", "hygiene.signal_flapping", "hygiene", detect_hygiene_signal_flapping, needs_audit_entries=True),
]


def run_v2_detectors_with_summary(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    audit_entries: Optional[List[Dict[str, object]]] = None,
) -> DetectorRunSummary:
    all_signals: List[DetectedSignal] = []
    detector_results: List[DetectorRunResult] = []

    for detector in DETECTOR_DEFINITIONS:
        if detector.needs_audit_entries:
            if not audit_entries:
                detector_results.append(
                    DetectorRunResult(
                        detector_id=detector.detector_id,
                        signal_id=detector.signal_type,
                        domain=detector.domain,
                        ran=False,
                        skipped_reason="missing_audit_entries",
                        fired=False,
                        severity=None,
                        evidence_keys=[],
                    )
                )
                continue
            signals = detector.runner(business_id, audit_entries)
        else:
            signals = detector.runner(business_id, txns)

        fired = bool(signals)
        strongest = None
        if fired:
            strongest = max((sig.severity for sig in signals), key=lambda sev: _SEVERITY_RANK.get(sev, -1))
        evidence_keys = sorted({k for sig in signals for k in sig.payload.keys()})
        detector_results.append(
            DetectorRunResult(
                detector_id=detector.detector_id,
                signal_id=detector.signal_type,
                domain=detector.domain,
                ran=True,
                skipped_reason=None,
                fired=fired,
                severity=strongest,
                evidence_keys=evidence_keys,
            )
        )
        all_signals.extend(signals)

    ordered_signals = sorted(all_signals, key=lambda sig: (sig.signal_type, sig.signal_id))
    ordered_detectors = sorted(detector_results, key=lambda d: (d.domain, d.signal_id, d.detector_id))
    return DetectorRunSummary(signals=ordered_signals, detectors=ordered_detectors)


def run_v2_detectors(
    business_id: str,
    txns: List[NormalizedTransaction],
    *,
    audit_entries: Optional[List[Dict[str, object]]] = None,
) -> List[DetectedSignal]:
    return run_v2_detectors_with_summary(
        business_id,
        txns,
        audit_entries=audit_entries,
    ).signals
