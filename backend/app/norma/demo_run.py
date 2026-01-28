from pathlib import Path
from .ingest import load_csv
from .normalize import normalize_txn
from .ledger import build_cash_ledger
from .facts import compute_facts


def run():
    csv_path = Path(__file__).parent / "data" / "demo_transactions.csv"
    raw = load_csv(csv_path)
    norm = [normalize_txn(t) for t in raw]
    ledger = build_cash_ledger(norm, opening_balance=0.0)
    facts = compute_facts(norm, ledger)

    print("CURRENT CASH:", facts.current_cash)
    print("\nMONTHLY INFLOW/OUTFLOW:")
    for row in facts.monthly_inflow_outflow:
        print(row)

    print("\nTOP CATEGORIES:")
    for row in facts.totals_by_category[:8]:
        print(row)

    print("\nLAST 5 LEDGER ROWS:")
    for row in facts.last_10_ledger_rows[-5:]:
        print(row)


if __name__ == "__main__":
    run()
