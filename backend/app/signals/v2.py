from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import math
import re
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional

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
    vendor_label: Dict[str, str] = {}

    for txn in txns:
        if txn.direction != "outflow":
            continue
        vendor_raw = txn.counterparty_hint or txn.description
        vendor_key = _normalize_vendor(vendor_raw)
        vendor_label.setdefault(vendor_key, vendor_raw or "Unknown")
        if prior_start <= txn.date <= prior_end:
            prior[vendor_key] = prior.get(vendor_key, 0.0) + float(txn.amount or 0.0)
        if current_start <= txn.date <= last_date:
            current[vendor_key] = current.get(vendor_key, 0.0) + float(txn.amount or 0.0)

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

    burn_start = last_date - timedelta(days=burn_window_days - 1)
    inflow_total = 0.0
    outflow_total = 0.0

    for txn in txns:
        if txn.date < burn_start or txn.date > last_date:
            continue
        if txn.direction == "inflow":
            inflow_total += float(txn.amount or 0.0)
        else:
            outflow_total += float(txn.amount or 0.0)

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

    payload = {
        "current_cash": round(current_cash, 2),
        "burn_window_days": burn_window_days,
        "burn_start": burn_start.isoformat(),
        "burn_end": last_date.isoformat(),
        "total_inflow": round(inflow_total, 2),
        "total_outflow": round(outflow_total, 2),
        "net_burn": round(net_burn, 2),
        "burn_per_day": round(burn_per_day, 4),
        "runway_days": round(runway_days, 2),
        "epsilon": epsilon,
        "thresholds": {"high": high_threshold_days, "medium": medium_threshold_days},
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


def run_v2_detectors(
    business_id: str,
    txns: List[NormalizedTransaction],
) -> List[DetectedSignal]:
    signals: List[DetectedSignal] = []
    signals.extend(detect_expense_creep_by_vendor(business_id, txns))
    signals.extend(detect_low_cash_runway(business_id, txns))
    signals.extend(detect_unusual_outflow_spike(business_id, txns))
    return signals
