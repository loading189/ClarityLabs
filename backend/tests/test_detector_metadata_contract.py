from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.app.services.signals_service import SIGNAL_CATALOG
from backend.app.signals.v2 import DETECTOR_DEFINITIONS


def test_detector_metadata_has_clear_condition_and_playbooks_together_or_neither():
    detector_signal_types = {detector.signal_type for detector in DETECTOR_DEFINITIONS}
    for signal_type in sorted(detector_signal_types):
        catalog = SIGNAL_CATALOG.get(signal_type)
        assert catalog is not None, f"Missing SIGNAL_CATALOG entry for detector signal type: {signal_type}"
        has_clear = "clear_condition" in catalog and catalog.get("clear_condition") is not None
        has_playbooks = "playbooks" in catalog and catalog.get("playbooks") is not None
        assert has_clear == has_playbooks, (
            f"Detector metadata for {signal_type} must define both clear_condition and playbooks or neither"
        )
