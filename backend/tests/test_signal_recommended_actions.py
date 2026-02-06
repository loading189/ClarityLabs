from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_signal_recommended_actions.db")

from backend.app.services import signals_service


def test_v2_signals_have_recommended_actions():
    for signal_type in [
        "expense_creep_by_vendor",
        "low_cash_runway",
        "unusual_outflow_spike",
    ]:
        catalog = signals_service.SIGNAL_CATALOG[signal_type]
        actions = signals_service._normalize_recommended_actions(
            signal_type, catalog.get("recommended_actions")
        )
        assert actions, f"{signal_type} should define recommended actions"
        for action in actions:
            assert action.get("action_id")
            assert action.get("label")
            assert action.get("rationale")
