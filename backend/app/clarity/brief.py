from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from backend.app.clarity.signals import Signal
from backend.app.domain.contracts import BriefFactsMeta, BriefResult, SignalResult
from backend.app.norma.facts import Facts


STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"
STATUS_CRITICAL = "CRITICAL"
STATUS_ATTENTION = "ATTENTION"
STATUS_ALL_CLEAR = "ALL_CLEAR"


def _severity_rank(severity: str) -> int:
    return {"red": 3, "yellow": 2, "green": 1}.get((severity or "green").lower(), 0)


def _sorted_signals(signals: List[Signal]) -> List[Signal]:
    return sorted(
        signals,
        key=lambda s: (-_severity_rank(s.severity), -int(s.priority), s.key),
    )


def _default_headline(status: str) -> str:
    if status == STATUS_INSUFFICIENT:
        return "Not enough recent transaction history to summarize yet."
    if status == STATUS_ALL_CLEAR:
        return "All clear — cash activity looks steady."
    if status == STATUS_CRITICAL:
        return "Urgent issues detected that need immediate attention."
    return "A few items need attention, but nothing urgent."


def _default_next_action(status: str) -> str:
    if status == STATUS_INSUFFICIENT:
        return "Connect more accounts or upload additional transactions to build a fuller brief."
    if status == STATUS_CRITICAL:
        return "Address the highest priority issue first and reassess in a few days."
    if status == STATUS_ATTENTION:
        return "Review the highlighted items and make targeted adjustments this week."
    return "Keep monitoring weekly and maintain current spending discipline."


def _confidence(status: str, txn_count: int, months_covered: int) -> tuple[float, str]:
    if status == STATUS_INSUFFICIENT:
        return 0.25, "Limited transaction history makes the brief less reliable."

    base = {
        STATUS_CRITICAL: 0.55,
        STATUS_ATTENTION: 0.65,
        STATUS_ALL_CLEAR: 0.75,
    }.get(status, 0.5)
    reason = f"Based on {txn_count} transactions across {months_covered} months."
    return base, reason


def _pick_primary_signal(signals: List[Signal]) -> Optional[Signal]:
    for signal in signals:
        if signal.how_to_fix:
            return signal
    return signals[0] if signals else None


def _deduped_bullets(signals: List[Signal], limit: int = 3) -> List[str]:
    bullets: List[str] = []
    used_dimensions: set[str] = set()
    for signal in signals:
        if signal.dimension in used_dimensions:
            continue
        if signal.message:
            bullets.append(signal.message)
            used_dimensions.add(signal.dimension)
        if len(bullets) >= limit:
            break
    return bullets


def build_brief(business_id: str, facts: Facts, signals: List[Signal]) -> BriefResult:
    signals_sorted = _sorted_signals(signals)

    windows_30 = (
        facts.windows is not None
        and facts.windows.windows is not None
        and 30 in facts.windows.windows
    )
    insufficient = (
        facts.meta.txn_count < 30
        or facts.meta.months_covered < 2
        or not windows_30
    )

    if insufficient:
        status = STATUS_INSUFFICIENT
    elif any(s.severity == "red" and s.priority >= 80 for s in signals_sorted):
        status = STATUS_CRITICAL
    elif any(s.severity == "red" for s in signals_sorted) or any(
        s.severity == "yellow" and s.priority >= 60 for s in signals_sorted
    ):
        status = STATUS_ATTENTION
    else:
        status = STATUS_ALL_CLEAR

    primary_signal = _pick_primary_signal(signals_sorted)
    if status == STATUS_ALL_CLEAR:
        headline = _default_headline(status)
    elif primary_signal:
        headline = primary_signal.message or _default_headline(status)
    else:
        headline = _default_headline(status)

    if status == STATUS_ALL_CLEAR:
        bullets = [
            "Inflow and outflow are balanced over the recent window.",
            "No material alerts surfaced across the core financial signals.",
        ]
    else:
        bullets = _deduped_bullets(signals_sorted, limit=3)
        if not bullets and status == STATUS_INSUFFICIENT:
            bullets = [
                "At least 2 months of transaction history is required for trend checks.",
                "Add more transactions to unlock detailed insights.",
            ]

    next_best_action = (
        primary_signal.how_to_fix
        if primary_signal and primary_signal.how_to_fix
        else _default_next_action(status)
    )

    confidence, confidence_reason = _confidence(
        status=status,
        txn_count=facts.meta.txn_count,
        months_covered=facts.meta.months_covered,
    )

    top_signals = [
        SignalResult(**asdict(signal)) for signal in signals_sorted[:3]
    ]

    return BriefResult(
        business_id=business_id,
        as_of=facts.meta.as_of,
        window_days=30,
        status=status,
        headline=headline,
        bullets=bullets[:3],
        next_best_action=next_best_action,
        confidence=confidence,
        confidence_reason=confidence_reason,
        top_signals=top_signals,
        facts_meta=BriefFactsMeta(
            as_of=facts.meta.as_of,
            txn_count=facts.meta.txn_count,
            months_covered=facts.meta.months_covered,
        ),
    )
