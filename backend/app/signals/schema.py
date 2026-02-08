from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

Severity = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class Signal:
    id: str
    type: str
    severity: Severity
    window: str
    baseline_value: Optional[float]
    current_value: Optional[float]
    delta: Optional[float]
    explanation_seed: Dict[str, Any]
    confidence: float
    baseline_window: Optional[Dict[str, Any]] = None
    current_window: Optional[Dict[str, Any]] = None
    computed_deltas: Optional[Dict[str, Any]] = None
    contributing_dimensions: Optional[List[Dict[str, Any]]] = None
    ledger_anchors: Optional[List[Dict[str, Any]]] = None
    explanation: Optional[Dict[str, Any]] = None
