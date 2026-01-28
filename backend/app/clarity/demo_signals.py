from __future__ import annotations
from pathlib import Path
from typing import Dict, Any

from backend.app.norma.ingest import load_csv
from backend.app.norma.normalize import normalize_txn
from backend.app.norma.ledger import build_cash_ledger
from backend.app.norma.facts import compute_facts
from .signals import compute_signals


def load_demo_facts() -> Dict[str, Any]:
    csv_path = Path(__file__).parents[1] / "norma" / "data" / "demo_transactions.csv"
    raw = load_csv(csv_path)
    norm = [normalize_txn(t) for t in raw]
    ledger = build_cash_ledger(norm, opening_balance=0.0)
    facts = compute_facts(norm, ledger)
    return {
        "current_cash": facts.current_cash,
        "monthly_inflow_outflow": facts.monthly_inflow_outflow,
        "totals_by_category": facts.totals_by_category,
        "last_10_ledger_rows": facts.last_10_ledger_rows,
    }


def run():
    facts = load_demo_facts()
    signals = compute_signals(facts)
    for s in signals:
        print(s.severity.upper(), "-", s.title, ":", s.message)


if __name__ == "__main__":
    run()
