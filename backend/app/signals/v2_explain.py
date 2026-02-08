from __future__ import annotations

from typing import Dict, List, Optional


def _explanation_payload(
    observation: str,
    implication: str,
    *,
    counts: Dict[str, object],
    deltas: Dict[str, object],
    rows: Optional[List[str]] = None,
) -> Dict[str, object]:
    return {
        "observation": observation,
        "implication": implication,
        "evidence": {
            "counts": counts,
            "deltas": deltas,
            "rows": sorted({str(row) for row in (rows or []) if row}),
        },
    }
