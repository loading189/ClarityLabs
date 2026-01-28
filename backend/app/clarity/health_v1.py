from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Sequence, Tuple
import calendar

from backend.app.analytics.monthly_trends import build_monthly_trends_payload
from backend.app.norma.merchant import merchant_key
from backend.app.norma.normalize import NormalizedTransaction


Severity = Literal["green", "yellow", "red"]
Status = Literal["open", "monitoring", "resolved"]
DrilldownTarget = Literal["transactions", "categorize", "ledger", "trends"]


@dataclass(frozen=True)
class SignalEvidence:
    date_range: Dict[str, Any]
    metrics: Dict[str, Any]
    examples: List[Dict[str, Any]]


@dataclass(frozen=True)
class SignalDrilldown:
    target: DrilldownTarget
    payload: Optional[Dict[str, Any]] = None
    label: Optional[str] = None


@dataclass(frozen=True)
class HealthSignal:
    id: str
    title: str
    severity: Severity
    status: Status
    updated_at: Optional[str]
    short_summary: str
    why_it_matters: str
    evidence: List[SignalEvidence]
    drilldowns: List[SignalDrilldown]


def _status_for(severity: Severity) -> Status:
    if severity == "red":
        return "open"
    if severity == "yellow":
        return "monitoring"
    return "resolved"


def _month_range(month: str) -> Tuple[date, date]:
    y, m = month.split("-")
    year = int(y)
    month_num = int(m)
    last_day = calendar.monthrange(year, month_num)[1]
    return date(year, month_num, 1), date(year, month_num, last_day)


def _month_range_payload(month: str) -> Dict[str, str]:
    start, end = _month_range(month)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": month,
    }


def _date_range_payload(start: date, end: date, label: str) -> Dict[str, str]:
    return {"start": start.isoformat(), "end": end.isoformat(), "label": label}


def _latest_months(series: Sequence[Dict[str, Any]], count: int) -> List[str]:
    months = [str(row.get("month")) for row in series if row.get("month")]
    return months[-count:] if count > 0 else months


def _series_by_month(series: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("month")): row for row in series if row.get("month")}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _pick_examples(
    txns: Iterable[NormalizedTransaction],
    start: date,
    end: date,
    direction: Optional[str] = None,
    limit: int = 3,
    merchant_keys: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    filtered = []
    for t in txns:
        if t.date < start or t.date > end:
            continue
        if direction and t.direction != direction:
            continue
        mk = merchant_key(t.description)
        if merchant_keys and mk not in merchant_keys:
            continue
        filtered.append((t, mk))

    filtered.sort(
        key=lambda pair: (
            -abs(_safe_float(pair[0].amount)),
            pair[0].occurred_at,
            pair[0].description or "",
            pair[0].source_event_id or "",
        )
    )

    examples = []
    for t, mk in filtered[:limit]:
        examples.append(
            {
                "source_event_id": t.source_event_id,
                "occurred_at": t.occurred_at.isoformat(),
                "date": t.date.isoformat(),
                "description": t.description,
                "amount": float(t.amount),
                "direction": t.direction,
                "category": t.category,
                "merchant_key": mk,
            }
        )
    return examples


def _last_txn_date(txns: Sequence[NormalizedTransaction]) -> Optional[date]:
    if not txns:
        return None
    return max(t.date for t in txns)


def _sum_outflow(txns: Iterable[NormalizedTransaction]) -> float:
    return sum(_safe_float(t.amount) for t in txns if t.direction == "outflow")


def _sum_inflow(txns: Iterable[NormalizedTransaction]) -> float:
    return sum(_safe_float(t.amount) for t in txns if t.direction == "inflow")


def _vendor_totals(txns: Iterable[NormalizedTransaction]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    for t in txns:
        if t.direction != "outflow":
            continue
        mk = merchant_key(t.description)
        if not mk:
            continue
        totals[mk] = totals.get(mk, 0.0) + _safe_float(t.amount)
    return totals


def _build_monthly_series(facts_json: Dict[str, Any], ledger_rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    payload = build_monthly_trends_payload(facts_json=facts_json, ledger_rows=ledger_rows)
    metrics = payload.get("metrics", {})
    series = metrics.get("net", {}).get("series")
    if isinstance(series, list) and series:
        return series
    return payload.get("series", []) or []


def _severity_from_ratio(ratio: float, yellow: float, red: float) -> Severity:
    if ratio >= red:
        return "red"
    if ratio >= yellow:
        return "yellow"
    return "green"


def build_health_v1_signals(
    *,
    facts_json: Dict[str, Any],
    ledger_rows: Optional[List[Dict[str, Any]]],
    txns: Sequence[NormalizedTransaction],
    updated_at: Optional[str],
    categorization_metrics: Optional[Dict[str, Any]] = None,
    rule_count: int = 0,
    is_known_vendor: Optional[Callable[[str], bool]] = None,
) -> List[Dict[str, Any]]:
    series = _build_monthly_series(facts_json, ledger_rows)
    series_by_month = _series_by_month(series)
    latest_months = _latest_months(series, 2)
    last_month = latest_months[-1] if latest_months else None
    prev_month = latest_months[-2] if len(latest_months) > 1 else None

    signals: List[HealthSignal] = []

    # 1) High Uncategorized Rate
    total_events = int((categorization_metrics or {}).get("total_events") or 0)
    uncategorized = int((categorization_metrics or {}).get("uncategorized") or 0)
    rate = (uncategorized / total_events) if total_events > 0 else 0.0
    severity = _severity_from_ratio(rate, yellow=0.15, red=0.3)
    summary = (
        f"{round(rate * 100)}% of events are uncategorized ({uncategorized} of {total_events})."
        if total_events > 0
        else "No categorized events yet."
    )
    evidence_metrics = {
        "uncategorized_rate": round(rate, 3),
        "uncategorized_count": uncategorized,
        "total_events": total_events,
    }
    if last_month and last_month in series_by_month:
        evidence_metrics.update(
            {
                "last_month_outflow": _safe_float(series_by_month[last_month].get("outflow")),
                "last_month_inflow": _safe_float(series_by_month[last_month].get("inflow")),
            }
        )
    evidence_uncat = SignalEvidence(
        date_range=_month_range_payload(last_month) if last_month else {"start": "", "end": "", "label": ""},
        metrics=evidence_metrics,
        examples=[],
    )
    signals.append(
        HealthSignal(
            id="high_uncategorized_rate",
            title="High Uncategorized Rate",
            severity=severity,
            status=_status_for(severity),
            updated_at=updated_at,
            short_summary=summary,
            why_it_matters="Uncategorized transactions weaken the accuracy of ledger-derived trends and signals.",
            evidence=[evidence_uncat],
            drilldowns=[
                SignalDrilldown(
                    target="categorize",
                    label="Review uncategorized",
                    payload={"date_preset": "30d"},
                )
            ],
        )
    )

    # 2) Cash Runway Risk
    current_cash = _safe_float(facts_json.get("current_cash"))
    last_three_months = _latest_months(series, 3)
    outflows = [_safe_float(series_by_month[m].get("outflow")) for m in last_three_months if m in series_by_month]
    avg_outflow = sum(outflows) / len(outflows) if outflows else 0.0
    runway_months = (current_cash / avg_outflow) if avg_outflow > 0 else None

    if runway_months is None:
        severity = "green"
        summary = "Outflows are minimal; runway risk is low."
    elif runway_months <= 1.0:
        severity = "red"
        summary = f"Estimated runway is {runway_months:.1f} months at current burn."
    elif runway_months <= 2.0:
        severity = "yellow"
        summary = f"Estimated runway is {runway_months:.1f} months at current burn."
    else:
        severity = "green"
        summary = f"Estimated runway is {runway_months:.1f} months at current burn."

    evidence_runway = SignalEvidence(
        date_range=_month_range_payload(last_month) if last_month else {"start": "", "end": "", "label": ""},
        metrics={
            "current_cash": round(current_cash, 2),
            "avg_outflow_3m": round(avg_outflow, 2),
            "runway_months": None if runway_months is None else round(runway_months, 2),
        },
        examples=[],
    )
    signals.append(
        HealthSignal(
            id="cash_runway_risk",
            title="Cash Runway Risk",
            severity=severity,
            status=_status_for(severity),
            updated_at=updated_at,
            short_summary=summary,
            why_it_matters="Runway estimates how long cash can cover recent burn without new inflows.",
            evidence=[evidence_runway],
            drilldowns=[
                SignalDrilldown(
                    target="trends",
                    label="View cash trend",
                    payload={"metric": "cash_end", "lookback_months": 12},
                ),
                SignalDrilldown(target="ledger", label="Open ledger", payload={"date_preset": "90d"}),
            ],
        )
    )

    # 3) Expense Spike
    expense_severity = "green"
    expense_summary = "Outflow is stable month-over-month."
    expense_metrics: Dict[str, Any] = {}
    expense_examples: List[Dict[str, Any]] = []
    if last_month and prev_month and last_month in series_by_month and prev_month in series_by_month:
        last_outflow = _safe_float(series_by_month[last_month].get("outflow"))
        prev_outflow = _safe_float(series_by_month[prev_month].get("outflow"))
        change = ((last_outflow - prev_outflow) / prev_outflow) if prev_outflow > 0 else 0.0
        if change >= 0.5:
            expense_severity = "red"
        elif change >= 0.25:
            expense_severity = "yellow"
        expense_summary = (
            f"Outflow increased {change * 100:.0f}% MoM (${last_outflow:,.0f} vs ${prev_outflow:,.0f})."
            if prev_outflow > 0
            else "Outflow jumped from a near-zero baseline."
        )
        start, end = _month_range(last_month)
        expense_examples = _pick_examples(txns, start, end, direction="outflow")
        expense_metrics = {
            "last_month_outflow": round(last_outflow, 2),
            "prev_month_outflow": round(prev_outflow, 2),
            "change_pct": round(change, 3),
        }

    signals.append(
        HealthSignal(
            id="expense_spike",
            title="Expense Spike",
            severity=expense_severity,
            status=_status_for(expense_severity),
            updated_at=updated_at,
            short_summary=expense_summary,
            why_it_matters="A sudden outflow jump can compress cash runway or signal one-off spend.",
            evidence=[
                SignalEvidence(
                    date_range=_month_range_payload(last_month) if last_month else {"start": "", "end": "", "label": ""},
                    metrics=expense_metrics,
                    examples=expense_examples,
                )
            ],
            drilldowns=[
                SignalDrilldown(
                    target="transactions",
                    label="Review outflows",
                    payload={"direction": "outflow", "date_preset": "30d"},
                ),
                SignalDrilldown(
                    target="trends",
                    label="View outflow trend",
                    payload={"metric": "outflow", "lookback_months": 12},
                ),
            ],
        )
    )

    # 4) Revenue Drop
    revenue_severity = "green"
    revenue_summary = "Inflow is stable month-over-month."
    revenue_metrics: Dict[str, Any] = {}
    revenue_examples: List[Dict[str, Any]] = []
    if last_month and prev_month and last_month in series_by_month and prev_month in series_by_month:
        last_inflow = _safe_float(series_by_month[last_month].get("inflow"))
        prev_inflow = _safe_float(series_by_month[prev_month].get("inflow"))
        change = ((prev_inflow - last_inflow) / prev_inflow) if prev_inflow > 0 else 0.0
        if change >= 0.4:
            revenue_severity = "red"
        elif change >= 0.2:
            revenue_severity = "yellow"
        revenue_summary = (
            f"Inflow dropped {change * 100:.0f}% MoM (${last_inflow:,.0f} vs ${prev_inflow:,.0f})."
            if prev_inflow > 0
            else "Inflow dipped after a low prior baseline."
        )
        start, end = _month_range(last_month)
        revenue_examples = _pick_examples(txns, start, end, direction="inflow")
        revenue_metrics = {
            "last_month_inflow": round(last_inflow, 2),
            "prev_month_inflow": round(prev_inflow, 2),
            "change_pct": round(change, 3),
        }

    signals.append(
        HealthSignal(
            id="revenue_drop",
            title="Revenue Drop",
            severity=revenue_severity,
            status=_status_for(revenue_severity),
            updated_at=updated_at,
            short_summary=revenue_summary,
            why_it_matters="A revenue drop can signal demand softness or delayed collections.",
            evidence=[
                SignalEvidence(
                    date_range=_month_range_payload(last_month) if last_month else {"start": "", "end": "", "label": ""},
                    metrics=revenue_metrics,
                    examples=revenue_examples,
                )
            ],
            drilldowns=[
                SignalDrilldown(
                    target="transactions",
                    label="Review inflows",
                    payload={"direction": "inflow", "date_preset": "30d"},
                ),
                SignalDrilldown(
                    target="trends",
                    label="View inflow trend",
                    payload={"metric": "inflow", "lookback_months": 12},
                ),
            ],
        )
    )

    # 5) Vendor Concentration
    anchor = _last_txn_date(txns)
    vendor_severity: Severity = "green"
    vendor_summary = "Outflow is diversified across vendors."
    vendor_metrics: Dict[str, Any] = {}
    vendor_examples: List[Dict[str, Any]] = []
    vendor_key: Optional[str] = None
    if anchor:
        start = anchor - timedelta(days=89)
        window_txns = [t for t in txns if start <= t.date <= anchor]
        vendor_totals = _vendor_totals(window_txns)
        total_outflow = sum(vendor_totals.values())
        if vendor_totals and total_outflow > 0:
            vendor_key, top_total = max(vendor_totals.items(), key=lambda kv: (kv[1], kv[0]))
            share = top_total / total_outflow
            vendor_severity = _severity_from_ratio(share, yellow=0.25, red=0.4)
            vendor_summary = (
                f"Top vendor accounts for {share * 100:.0f}% of outflow in the last 90 days."
            )
            vendor_metrics = {
                "top_vendor": vendor_key,
                "top_vendor_outflow": round(top_total, 2),
                "total_outflow_90d": round(total_outflow, 2),
                "top_vendor_share": round(share, 3),
            }
            vendor_examples = _pick_examples(
                window_txns,
                start,
                anchor,
                direction="outflow",
                merchant_keys={vendor_key},
            )
        else:
            vendor_metrics = {
                "total_outflow_90d": round(total_outflow, 2),
            }

    signals.append(
        HealthSignal(
            id="vendor_concentration",
            title="Vendor Concentration",
            severity=vendor_severity,
            status=_status_for(vendor_severity),
            updated_at=updated_at,
            short_summary=vendor_summary,
            why_it_matters="High concentration increases exposure if a vendor changes terms or volume shifts.",
            evidence=[
                SignalEvidence(
                    date_range=_date_range_payload(anchor - timedelta(days=89), anchor, "last 90d")
                    if anchor
                    else {"start": "", "end": "", "label": ""},
                    metrics=vendor_metrics,
                    examples=vendor_examples,
                )
            ],
            drilldowns=[
                SignalDrilldown(
                    target="transactions",
                    label="View top vendor",
                    payload={
                        "merchant_key": vendor_key,
                        "direction": "outflow",
                        "date_preset": "90d",
                    }
                    if vendor_key
                    else {"direction": "outflow", "date_preset": "90d"},
                )
            ],
        )
    )

    # 6) New / Unknown Vendors
    unknown_severity: Severity = "green"
    unknown_summary = "Vendor memory coverage is healthy."
    unknown_metrics: Dict[str, Any] = {}
    unknown_examples: List[Dict[str, Any]] = []
    if anchor and is_known_vendor:
        start = anchor - timedelta(days=29)
        window_txns = [t for t in txns if start <= t.date <= anchor]
        vendor_keys = [merchant_key(t.description) for t in window_txns if t.direction == "outflow"]
        unique_vendors = {k for k in vendor_keys if k}
        unknown_vendors = {k for k in unique_vendors if not is_known_vendor(k)}
        unknown_count = len(unknown_vendors)
        total_vendors = len(unique_vendors)
        if total_vendors > 0:
            ratio = unknown_count / total_vendors
            unknown_severity = _severity_from_ratio(ratio, yellow=0.25, red=0.45)
            unknown_summary = (
                f"{unknown_count} of {total_vendors} vendors are new or unlabeled in the last 30 days."
            )
            unknown_metrics = {
                "unknown_vendor_count": unknown_count,
                "total_vendors_30d": total_vendors,
                "unknown_vendor_ratio": round(ratio, 3),
            }
            unknown_examples = _pick_examples(
                window_txns,
                start,
                anchor,
                direction="outflow",
                merchant_keys=unknown_vendors,
            )
        else:
            unknown_metrics = {"total_vendors_30d": 0}

    signals.append(
        HealthSignal(
            id="new_unknown_vendors",
            title="New / Unknown Vendors",
            severity=unknown_severity,
            status=_status_for(unknown_severity),
            updated_at=updated_at,
            short_summary=unknown_summary,
            why_it_matters="Labeling new vendors improves categorization accuracy and reduces manual review.",
            evidence=[
                SignalEvidence(
                    date_range=_date_range_payload(anchor - timedelta(days=29), anchor, "last 30d")
                    if anchor
                    else {"start": "", "end": "", "label": ""},
                    metrics=unknown_metrics,
                    examples=unknown_examples,
                )
            ],
            drilldowns=[
                SignalDrilldown(
                    target="categorize",
                    label="Label vendors",
                    payload={"direction": "outflow", "date_preset": "30d"},
                ),
                SignalDrilldown(
                    target="transactions",
                    label="View recent outflows",
                    payload={"direction": "outflow", "date_preset": "30d"},
                ),
            ],
        )
    )

    # 7) Rule Coverage Low
    rule_severity: Severity = "green"
    rule_summary = "Rule coverage looks healthy."
    rule_metrics: Dict[str, Any] = {"active_rules": rule_count}
    rule_examples: List[Dict[str, Any]] = []
    top_repeat_vendor: Optional[str] = None
    if anchor:
        start = anchor - timedelta(days=89)
        window_txns = [t for t in txns if start <= t.date <= anchor and t.direction == "outflow"]
        vendor_counts: Dict[str, int] = {}
        for t in window_txns:
            mk = merchant_key(t.description)
            if not mk:
                continue
            vendor_counts[mk] = vendor_counts.get(mk, 0) + 1
        repeated = {k: v for k, v in vendor_counts.items() if v >= 3}
        repeated_count = len(repeated)
        if repeated:
            top_repeat_vendor = max(repeated.items(), key=lambda kv: (kv[1], kv[0]))[0]
        if repeated_count >= 5 and rule_count < 2:
            rule_severity = "red"
            rule_summary = "Few rules exist despite many repeated vendors."
        elif repeated_count >= 3 and rule_count < 5:
            rule_severity = "yellow"
            rule_summary = "Rule coverage is low for the number of repeat vendors."
        rule_metrics.update({"repeat_vendor_count": repeated_count, "top_repeat_vendor": top_repeat_vendor})
        if top_repeat_vendor:
            rule_examples = _pick_examples(
                window_txns,
                start,
                anchor,
                direction="outflow",
                merchant_keys={top_repeat_vendor},
            )

    signals.append(
        HealthSignal(
            id="rule_coverage_low",
            title="Rule Coverage Low",
            severity=rule_severity,
            status=_status_for(rule_severity),
            updated_at=updated_at,
            short_summary=rule_summary,
            why_it_matters="Rules reduce manual categorization when the same vendors recur.",
            evidence=[
                SignalEvidence(
                    date_range=_date_range_payload(anchor - timedelta(days=89), anchor, "last 90d")
                    if anchor
                    else {"start": "", "end": "", "label": ""},
                    metrics=rule_metrics,
                    examples=rule_examples,
                )
            ],
            drilldowns=[
                SignalDrilldown(
                    target="categorize",
                    label="Create rules",
                    payload={"direction": "outflow", "date_preset": "90d"},
                ),
                SignalDrilldown(
                    target="transactions",
                    label="Review repeats",
                    payload={"merchant_key": top_repeat_vendor, "direction": "outflow", "date_preset": "90d"}
                    if top_repeat_vendor
                    else {"direction": "outflow", "date_preset": "90d"},
                ),
            ],
        )
    )

    # 8) Overdraft-like pattern
    overdraft_severity: Severity = "green"
    overdraft_summary = "Cash balances have stayed above the safety buffer."
    overdraft_metrics: Dict[str, Any] = {}
    overdraft_examples: List[Dict[str, Any]] = []
    if series:
        cash_values = [(row.get("month"), _safe_float(row.get("cash_end"))) for row in series]
        min_month, min_cash = min(cash_values, key=lambda item: (item[1], item[0]))
        overdraft_metrics = {"min_cash_end": round(min_cash, 2), "min_cash_month": min_month}
        if min_cash <= 0:
            overdraft_severity = "red"
            overdraft_summary = f"Cash dipped below $0 in {min_month}."
        elif min_cash <= 200:
            overdraft_severity = "yellow"
            overdraft_summary = f"Cash dipped near zero in {min_month}."
        else:
            overdraft_summary = f"Lowest month-end cash was ${min_cash:,.0f}."
        if min_month:
            start, end = _month_range(min_month)
            overdraft_examples = _pick_examples(txns, start, end, direction="outflow")

    signals.append(
        HealthSignal(
            id="overdraft_pattern",
            title="Overdraft-like Pattern",
            severity=overdraft_severity,
            status=_status_for(overdraft_severity),
            updated_at=updated_at,
            short_summary=overdraft_summary,
            why_it_matters="Low cash cushions increase the risk of missed obligations or overdraft fees.",
            evidence=[
                SignalEvidence(
                    date_range=_month_range_payload(overdraft_metrics.get("min_cash_month"))
                    if overdraft_metrics.get("min_cash_month")
                    else {"start": "", "end": "", "label": ""},
                    metrics=overdraft_metrics,
                    examples=overdraft_examples,
                )
            ],
            drilldowns=[
                SignalDrilldown(target="ledger", label="Open ledger", payload={"date_preset": "90d"})
            ],
        )
    )

    def _sev_rank(sev: Severity) -> int:
        return {"red": 3, "yellow": 2, "green": 1}.get(sev, 0)

    signals_sorted = sorted(
        signals,
        key=lambda s: (_sev_rank(s.severity), s.id),
        reverse=True,
    )

    return [asdict(signal) for signal in signals_sorted]
