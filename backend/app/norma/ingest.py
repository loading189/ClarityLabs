"""
Norma - CSV ingest layer.

Responsibility:
- Read a CSV file from disk
- Parse rows into RawTransaction records (no business logic, no normalization)

Design notes:
- This is intentionally the "IO edge" of the pipeline.
- Everything after this should be pure functions where possible.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Mapping


@dataclass(frozen=True)
class RawTransaction:
    """
    Raw transaction as represented in the CSV.

    Invariants:
    - date is a real datetime.date
    - amount is a float (signed; positive=inflow, negative=outflow)
    - raw_category may be blank (""), which downstream can map to "uncategorized"
    """
    date: date
    description: str
    amount: float
    source_account: str
    raw_category: str


REQUIRED_COLUMNS = ("date", "description", "amount", "source_account")


def _parse_amount(value: str) -> float:
    """
    Parse a numeric amount from CSV.

    Supports:
    - "1234.56"
    - "1,234.56"
    - " -59.99 " (with whitespace)

    Raises ValueError if parsing fails.
    """
    cleaned = (value or "").strip().replace(",", "")
    return float(cleaned)


def _parse_row(row: Mapping[str, str], line_no: int) -> RawTransaction:
    """
    Parse a single CSV row into a RawTransaction.

    Raises ValueError with a useful message including line number.
    """
    try:
        d = date.fromisoformat((row.get("date") or "").strip())
        desc = (row.get("description") or "").strip()
        amt = _parse_amount(row.get("amount") or "")
        acct = (row.get("source_account") or "").strip()
        cat = (row.get("raw_category") or "").strip()
    except Exception as e:
        raise ValueError(f"CSV parse error on line {line_no}: {dict(row)} ({e})") from e

    if not desc:
        raise ValueError(f"CSV parse error on line {line_no}: description is required")

    if not acct:
        raise ValueError(f"CSV parse error on line {line_no}: source_account is required")

    return RawTransaction(date=d, description=desc, amount=amt, source_account=acct, raw_category=cat)


def load_csv(path: Path) -> List[RawTransaction]:
    """
    Load transactions from a CSV file.

    Required columns:
    - date (ISO format: YYYY-MM-DD)
    - description
    - amount
    - source_account

    Optional columns:
    - raw_category

    Returns:
        List[RawTransaction]

    Raises:
        FileNotFoundError: if the CSV path doesn't exist
        ValueError: for missing columns or row parse errors (with line numbers)
    """
    items: List[RawTransaction] = []

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate headers early so errors are obvious.
        headers = tuple(h.strip() for h in (reader.fieldnames or []))
        missing = [c for c in REQUIRED_COLUMNS if c not in headers]
        if missing:
            raise ValueError(
                f"CSV missing required columns {missing}. "
                f"Found columns: {list(headers)}"
            )

        # DictReader yields each row as a dict; start=2 because line 1 is headers.
        for line_no, row in enumerate(reader, start=2):
            # Optional: skip fully empty rows (common when CSVs end with blank line)
            if row is None or all((v or "").strip() == "" for v in row.values()):
                continue

            items.append(_parse_row(row, line_no))

    return items
