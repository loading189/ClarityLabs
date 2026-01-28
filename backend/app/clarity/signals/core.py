# backend/app/signals/core.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

Severity = Literal["green", "yellow", "red"]
Dimension = Literal["liquidity", "stability", "discipline", "spend", "revenue", "ops"]


@dataclass(frozen=True)
class Signal:
    key: str
    title: str
    severity: Severity
    dimension: Dimension
    priority: int
    value: Any
    message: str

    inputs: Optional[List[str]] = None
    conditions: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    why: Optional[str] = None
    how_to_fix: Optional[str] = None
    evidence_refs: Optional[List[Dict[str, Any]]] = None

    version: int = 1


def mk_signal(**kwargs) -> Signal:
    return Signal(**kwargs)
