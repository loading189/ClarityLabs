# tools/generate_demo_csv.py
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple


@dataclass(frozen=True)
class Category:
    name: str
    min_amt: float
    max_amt: float
    sign: int  # -1 spend, +1 inflow


CATEGORIES: List[Category] = [
    Category("Sales Income", 1200, 9000, +1),
    Category("Payroll", 1200, 4200, -1),
    Category("Rent", 900, 2400, -1),
    Category("Hosting", 80, 450, -1),
    Category("Supplies", 25, 600, -1),
    Category("Fuel", 35, 300, -1),
    Category("Insurance", 120, 900, -1),
    Category("Marketing", 50, 800, -1),
    Category("Meals", 15, 180, -1),
]

DESCRIPTIONS = {
    "Sales Income": ["Client payment", "Invoice paid", "Project deposit", "Retainer payment"],
    "Payroll": ["Payroll", "Payroll run", "Wages"],
    "Rent": ["Rent"],
    "Hosting": ["Hosting", "Cloud services", "Software subscription"],
    "Supplies": ["Supplies", "Materials", "Shop supplies"],
    "Fuel": ["Fuel", "Gas"],
    "Insurance": ["Insurance premium"],
    "Marketing": ["Marketing", "Ads spend"],
    "Meals": ["Meals", "Team lunch"],
}

SOURCE_ACCOUNTS = ["Checking", "Operating Checking", "Business Checking"]


def month_multiplier(m: int) -> float:
    """
    Simple seasonality curve.
    - Q4 stronger
    - summer a bit softer
    """
    if m in (11, 12):
        return 1.25
    if m in (1, 2):
        return 0.95
    if m in (6, 7):
        return 0.90
    return 1.00


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def choose_amount(rng: random.Random, cat: Category, mult: float) -> float:
    amt = rng.uniform(cat.min_amt, cat.max_amt) * mult
    amt = round(amt, 2)
    return amt * cat.sign


def write_csv(path: Path, rows: List[Tuple[str, str, float, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "description", "amount", "source_account", "raw_category"])
        for r in rows:
            w.writerow(r)


def generate(
    start: date,
    end: date,
    seed: int = 7,
    bad_months: List[str] | None = None,  # e.g. ["2025-11", "2026-02"]
) -> List[Tuple[str, str, float, str, str]]:
    rng = random.Random(seed)
    bad_months = bad_months or []

    rows: List[Tuple[str, str, float, str, str]] = []

    # cadence rules
    payroll_weekday = 4  # Friday
    rent_day = 1

    for d in daterange(start, end):
        mk = f"{d.year:04d}-{d.month:02d}"
        mult = month_multiplier(d.month)

        # In bad months: reduce inflows, increase spend slightly
        inflow_mult = mult * (0.70 if mk in bad_months else 1.0)
        spend_mult = mult * (1.10 if mk in bad_months else 1.0)

        # Weekly payroll (every Friday)
        if d.weekday() == payroll_weekday:
            cat = next(c for c in CATEGORIES if c.name == "Payroll")
            amt = choose_amount(rng, cat, spend_mult)
            rows.append((d.isoformat(), rng.choice(DESCRIPTIONS[cat.name]), amt, rng.choice(SOURCE_ACCOUNTS), cat.name))

        # Monthly rent (1st)
        if d.day == rent_day:
            cat = next(c for c in CATEGORIES if c.name == "Rent")
            amt = choose_amount(rng, cat, spend_mult)
            rows.append((d.isoformat(), "Rent", amt, rng.choice(SOURCE_ACCOUNTS), cat.name))

        # Random daily vendor spend (0–3 txns/day)
        spend_txns = rng.randint(0, 3)
        for _ in range(spend_txns):
            cat = rng.choice([c for c in CATEGORIES if c.sign < 0 and c.name not in ("Payroll", "Rent")])
            amt = choose_amount(rng, cat, spend_mult)
            desc = rng.choice(DESCRIPTIONS[cat.name])
            rows.append((d.isoformat(), desc, amt, rng.choice(SOURCE_ACCOUNTS), cat.name))

        # Random client payments (0–2 txns/day, more likely on weekdays)
        inflow_txns = rng.randint(0, 2 if d.weekday() < 5 else 1)
        for _ in range(inflow_txns):
            cat = next(c for c in CATEGORIES if c.name == "Sales Income")
            amt = choose_amount(rng, cat, inflow_mult)
            desc = rng.choice(DESCRIPTIONS[cat.name])
            rows.append((d.isoformat(), desc, amt, rng.choice(SOURCE_ACCOUNTS), cat.name))

    # Shuffle for realism then sort by date (stable)
    rng.shuffle(rows)
    rows.sort(key=lambda r: r[0])
    return rows


if __name__ == "__main__":
    out = Path("backend/app/norma/data/demo_big.csv")
    rows = generate(
        start=date(2025, 1, 1),
        end=date(2026, 12, 31),
        seed=42,
        bad_months=["2025-08", "2026-02", "2026-03"],
    )
    write_csv(out, rows)
    print(f"Wrote {len(rows)} rows to {out}")
