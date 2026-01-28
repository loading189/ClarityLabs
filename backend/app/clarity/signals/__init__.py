# backend/app/clarity/signals/__init__.py
from __future__ import annotations

from typing import Callable, List, Sequence

from backend.app.norma.facts import Facts
from .core import Signal

SignalBuilder = Callable[[Facts], Sequence[Signal]]
_BUILDERS: List[SignalBuilder] = []


def register(fn: SignalBuilder) -> SignalBuilder:
    _BUILDERS.append(fn)
    return fn


def compute_signals(facts: Facts) -> List[Signal]:
    signals: List[Signal] = []

    for builder in _BUILDERS:
        try:
            signals.extend(list(builder(facts)))
        except Exception as e:
            # Never let one bad builder take down the app
            signals.append(
                Signal(
                    key=f"signals_builder_error:{getattr(builder, '__name__', 'unknown')}",
                    title="Signal builder error",
                    severity="yellow",
                    dimension="ops",
                    priority=1,
                    value=None,
                    message=str(e),
                )
            )

    def _sev_rank(sev: str) -> int:
        return {"red": 3, "yellow": 2, "green": 1}.get((sev or "green").lower(), 0)

    return sorted(signals, key=lambda s: (_sev_rank(s.severity), int(s.priority), s.key), reverse=True)


# Import modules so @register decorators run
from . import liquidity  # noqa: E402,F401
from . import stability  # noqa: E402,F401
from . import spend      # noqa: E402,F401
