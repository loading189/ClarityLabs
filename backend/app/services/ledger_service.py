# backend/app/services/ledger_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import List, Optional, Literal, Dict, Iterable, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models import Business
from backend.app.services.posted_txn_service import (
    fetch_posted_transaction_details,
    fetch_posted_transactions,
)

Direction = Literal["inflow", "outflow"]

logger = logging.getLogger(__name__)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _date_range_filter(occurred_at: datetime, start: Optional[date], end: Optional[date]) -> bool:
    d = occurred_at.date()
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def is_inflow(direction: str) -> bool:
    return direction == "inflow"


def signed_amount(amount: float, direction: str) -> float:
    amt = float(amount or 0.0)
    if amt < 0:
        # This should not happen for normalized txns; keep as a guard.
        logger.warning("Invariant guard: normalized transaction amount is negative: %s", amt)
    return amt if is_inflow(direction) else -amt


def _build_cash_series(
    txns: Iterable,
    starting_cash: float,
) -> List[Dict[str, Any]]:
    bal = float(starting_cash or 0.0)
    out: List[Dict[str, Any]] = []
    for txn in txns:
        bal += signed_amount(txn.amount or 0.0, txn.direction)
        out.append({"occurred_at": txn.occurred_at, "balance": round(bal, 2)})
    return out


def default_ledger_window() -> tuple[date, date]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=90)
    return start, end


def _vendor_label(txn) -> str:
    return (txn.counterparty_hint or txn.description or "Unknown").strip() or "Unknown"


def _matches_any(value: str, candidates: Optional[List[str]]) -> bool:
    """
    Case-insensitive exact match against a candidate list.
    If candidates is None/empty, returns True (no filtering).
    """
    if not candidates:
        return True
    normalized = (value or "").strip().lower()
    return any(normalized == (item or "").strip().lower() for item in candidates if item and item.strip())


def ledger_query(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    accounts: Optional[List[str]] = None,
    vendors: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
    search: Optional[str] = None,
    direction: Optional[Direction] = None,
    source_event_ids: Optional[List[str]] = None,
    highlight_source_event_ids: Optional[List[str]] = None,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Deterministic ledger query over posted transactions.

    Notes:
    - Filtering is applied in Python for MVP simplicity.
    - `accounts` currently matches either account label OR account_id string.
      (The call sites can pass either.)
    - `start_balance` is the running balance prior to start_date.
    """
    require_business(db, business_id)
    if not start_date or not end_date:
        start_date, end_date = default_ledger_window()

    details = fetch_posted_transaction_details(db, business_id)

    q = (search or "").strip().lower()
    filtered: List[Dict[str, Any]] = []

    start_balance = 0.0
    source_id_set = {str(item) for item in (source_event_ids or []) if item}
    highlight_set = {str(item) for item in (highlight_source_event_ids or []) if item}
    highlight_enabled = highlight_source_event_ids is not None

    for detail in details:
        txn = detail.txn

        amount = signed_amount(txn.amount or 0.0, txn.direction)
        vendor = _vendor_label(txn)
        account = (detail.account_name or txn.account or "").strip() or "Unknown"
        account_id = (str(detail.account_id).strip() if getattr(detail, "account_id", None) else "")
        category = (detail.category_name or txn.category or "").strip() or "Uncategorized"

        # Window boundaries
        txn_date = txn.occurred_at.date()
        if txn_date < start_date:
            start_balance += amount
            continue
        if txn_date > end_date:
            continue

        # Optional exact filters
        if source_id_set and str(txn.source_event_id) not in source_id_set:
            continue

        if accounts:
            # Allow either account label or account_id to match.
            if not (_matches_any(account, accounts) or (account_id and _matches_any(account_id, accounts))):
                continue

        if not _matches_any(vendor, vendors):
            continue
        if not _matches_any(category, categories):
            continue

        if direction and txn.direction != direction:
            continue

        # Optional substring search
        if q:
            haystack = f"{txn.description or ''} {vendor} {account} {category}".lower()
            if q not in haystack:
                continue

        row: Dict[str, Any] = {
            "occurred_at": txn.occurred_at,
            "date": txn_date,
            "description": txn.description,
            "vendor": vendor,
            "amount": round(amount, 2),
            "category": category,
            "account": account,
            "balance": 0.0,
            "source_event_id": txn.source_event_id,
        }
        if highlight_enabled:
            row["is_highlighted"] = str(txn.source_event_id) in highlight_set

        filtered.append(row)

    # Deterministic order
    filtered.sort(key=lambda row: (row["occurred_at"], str(row["source_event_id"])))

    # Running balance + totals
    balance = start_balance
    total_in = 0.0
    total_out = 0.0
    for row in filtered:
        amt = float(row["amount"])
        balance += amt
        row["balance"] = round(balance, 2)
        if amt >= 0:
            total_in += amt
        else:
            total_out += abs(amt)

    total_count = len(filtered)
    # Page slice (after computing balances so balances are correct on the page)
    page = filtered[offset : offset + limit]
    next_offset = offset + len(page)
    has_more = next_offset < total_count

    return {
        "rows": page,
        "summary": {
            "start_balance": round(start_balance, 2),
            "end_balance": round(balance, 2),
            "total_in": round(total_in, 2),
            "total_out": round(total_out, 2),
            "row_count": total_count,
        },
        "total_count": total_count,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
        "window": {"start_date": start_date, "end_date": end_date},
    }


def ledger_dimensions(
    db: Session,
    business_id: str,
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    dimension: Literal["accounts", "vendors"],
) -> List[Dict[str, Any]]:
    """
    Dimension aggregation for UI facets.
    Note: Uses a high limit to approximate "all rows" in MVP.
    """
    payload = ledger_query(
        db,
        business_id,
        start_date=start_date,
        end_date=end_date,
        limit=1_000_000,
        offset=0,
    )

    groups: Dict[str, Dict[str, Any]] = {}
    for row in payload["rows"]:
        if dimension == "accounts":
            key = str(row["account"])
            item = groups.setdefault(
                key,
                {"account": key, "label": key, "count": 0, "total": 0.0},
            )
        else:
            key = str(row["vendor"])
            item = groups.setdefault(
                key,
                {"vendor": key, "label": key, "count": 0, "total": 0.0},
            )

        item["count"] += 1
        item["total"] += float(row["amount"])

    values = list(groups.values())
    for item in values:
        item["total"] = round(float(item["total"]), 2)

    values.sort(key=lambda item: (-int(item["count"]), str(item["label"]).lower()))
    return values


def ledger_lines(
    db: Session,
    business_id: str,
    start_date: Optional[date],
    end_date: Optional[date],
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Posted ledger lines only (i.e., events with TxnCategorization).
    """
    require_business(db, business_id)

    details = fetch_posted_transaction_details(
        db,
        business_id,
        order_desc=True,
        limit=limit,
    )

    out: List[Dict[str, Any]] = []
    for detail in details:
        txn = detail.txn
        if not _date_range_filter(txn.occurred_at, start_date, end_date):
            continue

        direction: Direction = txn.direction

        out.append(
            {
                "occurred_at": txn.occurred_at,
                "source_event_id": txn.source_event_id,
                "description": txn.description,
                "direction": direction,
                "signed_amount": signed_amount(txn.amount or 0.0, direction),
                "display_amount": float(txn.amount or 0.0),
                "category_id": detail.category_id,
                "category_name": detail.category_name,
                "account_id": detail.account_id,
                "account_name": detail.account_name,
                "account_type": detail.account_type,
                "account_subtype": detail.account_subtype,
            }
        )

    return sorted(out, key=lambda row: (row["occurred_at"], str(row["source_event_id"])))


def ledger_context_for_source_event(
    db: Session,
    business_id: str,
    source_event_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return ledger snapshot context for a single source_event_id, if it exists.
    Includes balance and running totals up to that row.
    """
    require_business(db, business_id)

    # Ensure deterministic ordering for running balances.
    txns = sorted(
        fetch_posted_transactions(db, business_id),
        key=lambda t: (t.occurred_at, str(t.source_event_id)),
    )

    balance = 0.0
    total_in = 0.0
    total_out = 0.0

    for txn in txns:
        amt = signed_amount(txn.amount or 0.0, txn.direction)
        balance += amt
        if amt >= 0:
            total_in += amt
        else:
            total_out += abs(amt)

        if str(txn.source_event_id) == str(source_event_id):
            row = {
                "source_event_id": txn.source_event_id,
                "occurred_at": txn.occurred_at,
                "date": txn.occurred_at.date(),
                "description": txn.description,
                "vendor": _vendor_label(txn),
                "amount": round(amt, 2),
                "category": (txn.category or "").strip() or "Uncategorized",
                "account": (txn.account or "").strip() or "Unknown",
                "balance": round(balance, 2),
            }
            return {
                "row": row,
                "balance": round(balance, 2),
                "running_total_in": round(total_in, 2),
                "running_total_out": round(total_out, 2),
            }

    return None


def ledger_trace_transactions(
    db: Session,
    business_id: str,
    *,
    txn_ids: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    require_business(db, business_id)
    if not txn_ids and not (start_date and end_date):
        raise HTTPException(status_code=400, detail="txn_ids or date range required")

    details = fetch_posted_transaction_details(
        db,
        business_id,
        source_event_ids=txn_ids,
        limit=limit,
    )

    out: List[Dict[str, Any]] = []
    for detail in details:
        txn = detail.txn
        if not txn_ids and not _date_range_filter(txn.occurred_at, start_date, end_date):
            continue

        direction: Direction = txn.direction
        out.append(
            {
                "occurred_at": txn.occurred_at,
                "source_event_id": txn.source_event_id,
                "description": txn.description,
                "direction": direction,
                "signed_amount": signed_amount(txn.amount or 0.0, direction),
                "display_amount": float(txn.amount or 0.0),
                "category_name": detail.category_name,
                "account_name": detail.account_name,
                "counterparty_hint": txn.counterparty_hint,
            }
        )

    return sorted(out, key=lambda row: (row["occurred_at"], str(row["source_event_id"])))


def income_statement(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    MVP income statement from posted ledger lines:
    - revenue = sum amounts where account.type == 'revenue'
    - expenses = sum absolute value of amounts where account.type == 'expense' OR acct.subtype == 'cogs'
    """
    require_business(db, business_id)
    details = fetch_posted_transaction_details(db, business_id)

    rev_by_name: Dict[str, float] = {}
    exp_by_name: Dict[str, float] = {}

    rev_total = 0.0
    exp_total = 0.0

    for detail in details:
        txn = detail.txn
        if not _date_range_filter(txn.occurred_at, start_date, end_date):
            continue

        amt = signed_amount(txn.amount or 0.0, txn.direction)
        t = (detail.account_type or "").strip().lower()
        st = (detail.account_subtype or "").strip().lower()

        if t == "revenue":
            rev_total += amt
            key = detail.category_name or "Uncategorized"
            rev_by_name[key] = rev_by_name.get(key, 0.0) + amt
        elif t == "expense" or st == "cogs":
            exp = -amt  # report expenses as positive
            exp_total += exp
            key = detail.category_name or "Uncategorized"
            exp_by_name[key] = exp_by_name.get(key, 0.0) + exp

    revenue_lines = [{"name": k, "amount": round(v, 2)} for k, v in sorted(rev_by_name.items())]
    expense_lines = [{"name": k, "amount": round(v, 2)} for k, v in sorted(exp_by_name.items())]

    net_income = rev_total - exp_total

    return {
        "start_date": start_date,
        "end_date": end_date,
        "revenue_total": round(rev_total, 2),
        "expense_total": round(exp_total, 2),
        "net_income": round(net_income, 2),
        "revenue": revenue_lines,
        "expenses": expense_lines,
    }


def cash_flow(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Direct-method cashflow MVP:
    cash_in = sum of inflow amounts across posted lines in range
    cash_out = sum of outflow amounts across posted lines in range
    """
    require_business(db, business_id)
    txns = fetch_posted_transactions(db, business_id)

    cash_in = 0.0
    cash_out = 0.0

    for txn in txns:
        if not _date_range_filter(txn.occurred_at, start_date, end_date):
            continue
        signed = signed_amount(txn.amount or 0.0, txn.direction)
        if is_inflow(txn.direction):
            cash_in += abs(signed)
        else:
            cash_out += abs(signed)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "cash_in": round(cash_in, 2),
        "cash_out": round(cash_out, 2),
        "net_cash_flow": round(cash_in - cash_out, 2),
    }


def cash_series(
    db: Session,
    business_id: str,
    start_date: Optional[date],
    end_date: Optional[date],
    starting_cash: float,
) -> List[Dict[str, Any]]:
    """
    Running cash balance series (for signals / bollinger bands).
    MVP = cumulative sum of posted signed amounts.

    NOTE: This assumes your posted lines represent cash-impacting events.
    """
    require_business(db, business_id)
    txns = []
    for txn in fetch_posted_transactions(db, business_id):
        if not _date_range_filter(txn.occurred_at, start_date, end_date):
            continue
        txns.append(txn)

    # Deterministic order for chart series
    txns.sort(key=lambda t: (t.occurred_at, str(t.source_event_id)))
    return _build_cash_series(txns, starting_cash)


def balance_sheet_v1(
    db: Session,
    business_id: str,
    as_of: date,
    starting_cash: float,
) -> Dict[str, Any]:
    """
    Balance Sheet MVP (cash-only):
      cash = starting_cash + cumulative signed amounts up to as_of (posted lines)
      assets_total = cash
      liabilities_total = 0
      equity_total = assets - liabilities
    """
    require_business(db, business_id)

    bal = float(starting_cash or 0.0)
    txns = fetch_posted_transactions(db, business_id)
    txns = sorted(txns, key=lambda t: (t.occurred_at, str(t.source_event_id)))

    for txn in txns:
        if txn.occurred_at.date() <= as_of:
            bal += signed_amount(txn.amount or 0.0, txn.direction)

    assets = bal
    liabilities = 0.0
    equity = assets - liabilities

    return {
        "as_of": as_of,
        "cash": round(bal, 2),
        "assets_total": round(assets, 2),
        "liabilities_total": round(liabilities, 2),
        "equity_total": round(equity, 2),
    }
