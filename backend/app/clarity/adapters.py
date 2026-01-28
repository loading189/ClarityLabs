from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from backend.app.clarity.signals.core import Signal
from backend.app.domain.contracts import SignalResult


def signal_to_contract(signal: Signal | Mapping[str, Any]) -> SignalResult:
    if isinstance(signal, Signal):
        data = asdict(signal)
    else:
        data = dict(signal)
    return SignalResult(**data)
