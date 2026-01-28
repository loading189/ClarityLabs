from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from backend.app.norma.ingest import load_csv
from backend.app.norma.normalize import normalize_txn
from backend.app.norma.ledger import build_cash_ledger
from backend.app.norma.facts import compute_facts


def load_demo_bundle() -> Dict[str, Any]:
    """
    Returns a consistent demo bundle for the API layer.
    """
    csv_path = Path(__file__).parent / "data" / "demo_transactions.csv"
    raw = load_csv(csv_path)
    norm = [normalize_txn(t) for t in raw]
    ledger = build_cash_ledger(norm, opening_balance=0.0)
    facts = compute_facts(norm, ledger)

    return {
        "facts": {
            "current_cash": facts.current_cash,
            "monthly_inflow_outflow": facts.monthly_inflow_outflow,
            "totals_by_category": facts.totals_by_category,
        },
        "ledger": facts.last_10_ledger_rows,  # already dicts
    }
