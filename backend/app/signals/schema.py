from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

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
