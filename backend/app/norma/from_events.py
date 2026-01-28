from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from backend.app.norma.normalize import NormalizedTransaction


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _maybe_json(x: Any) -> Any:
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return x
    return x


def _coerce_str(x: Any, default: str) -> str:
    if x is None:
        return default
    try:
        s = str(x).strip()
        return s if s else default
    except Exception:
        return default


def _get_hint_category(inner: Dict[str, Any]) -> Optional[str]:
    hint = inner.get("hint")
    if isinstance(hint, dict):
        cat = hint.get("category")
        if isinstance(cat, str) and cat.strip():
            return cat.strip()
    return None


def _extract_amount_generic(payload: Dict[str, Any]) -> Optional[float]:
    """
    Legacy / plaid-ish extractor.
    """
    if payload.get("amount_cents") is not None:
        return float(payload["amount_cents"]) / 100.0
    if payload.get("amount") is not None:
        return float(payload["amount"])

    txn = payload.get("transaction")
    if isinstance(txn, dict):
        if txn.get("amount_cents") is not None:
            return float(txn["amount_cents"]) / 100.0
        if txn.get("amount") is not None:
            return float(txn["amount"])

    inner = payload.get("payload")
    if isinstance(inner, dict):
        return _extract_amount_generic(inner)

    return None


def _direction_from_amount(amount: float, raw_dir: Optional[str] = None) -> Tuple[float, str]:
    """
    Normalize sign + direction.
    Convention in our pipeline:
      - amount >= 0 => inflow
      - amount < 0  => outflow
    If raw_dir is provided, honor it by flipping sign if needed.
    """
    raw_dir = (raw_dir or "").strip().lower() if isinstance(raw_dir, str) else None
    if raw_dir == "outflow" and amount > 0:
        return -abs(amount), "outflow"
    if raw_dir == "inflow" and amount < 0:
        return abs(amount), "inflow"
    return (amount, "inflow" if amount >= 0 else "outflow")


def _normalize_category(raw: Optional[str], *, direction: Optional[str] = None) -> str:
    """
    Converts whatever upstream gave us into our canonical system_key universe.

    IMPORTANT:
    - Your suggest_category() pipeline only runs when txn.category == "uncategorized"
    - So we only set a real category when the event type is truly authoritative.
      Otherwise we intentionally return "uncategorized" to trigger suggestions.
    """
    s = (raw or "").strip().lower()
    if not s or s in {"unknown", "none", "null", "n/a"}:
        return "uncategorized"

    # Common synonyms -> canonical system keys
    synonyms = {
        # Revenue-ish
        "revenue": "sales",
        "income": "sales",
        "sales revenue": "sales",
        "sales": "sales",

        # Refund-ish / contra revenue
        "refund": "contra",
        "refunds": "contra",
        "contra_revenue": "contra",
        "contra revenue": "contra",
        "returns": "contra",

        # Fees
        "fees": "software",          # treat payment fees as software/processing for now
        "processing_fees": "software",
        "stripe fees": "software",

        # Expense buckets
        "payroll expense": "payroll",
        "payroll": "payroll",
        "rent expense": "rent",
        "rent": "rent",
        "utilities": "utilities",
        "software subscriptions": "software",
        "software": "software",
        "marketing": "marketing",
        "advertising": "marketing",
        "hosting": "hosting",
        "infrastructure": "hosting",
        "insurance": "insurance",
        "office_supplies": "office_supplies",
        "office supplies": "office_supplies",
        "meals": "meals",
        "meals & entertainment": "meals",
        "travel": "travel",
        "taxes": "taxes",
        "licenses": "taxes",
        "cogs": "cogs",
        "cost of goods sold": "cogs",
        "inventory": "cogs",  # (rough MVP mapping)
        "supplies": "office_supplies",
    }

    mapped = synonyms.get(s)
    if mapped:
        return mapped

    # If the category is already a known system_key-ish token, keep it
    # (If you add more keys later, you can extend this list.)
    known = {
        "cogs",
        "payroll",
        "rent",
        "utilities",
        "software",
        "marketing",
        "hosting",
        "insurance",
        "office_supplies",
        "meals",
        "travel",
        "taxes",
        "sales",
        "contra",
        "uncategorized",
    }
    if s in known:
        return s

    # Anything else: keep it uncategorized so suggestion engine runs
    return "uncategorized"


def raw_event_to_txn(payload: Any, occurred_at: datetime, source_event_id: str) -> NormalizedTransaction:
    payload = _maybe_json(payload)
    if not isinstance(payload, dict):
        raise ValueError("raw_event_to_txn: payload is not a dict")

    occurred_at_utc = _as_utc(occurred_at)
    d = occurred_at_utc.date()

    # Your RawEvent.payload sometimes nests the “real thing” under payload.payload
    inner = payload["payload"] if isinstance(payload.get("payload"), dict) else payload
    if not isinstance(inner, dict):
        raise ValueError("raw_event_to_txn: inner payload is not a dict")

    event_type = _coerce_str(inner.get("type"), "")
    if not isinstance(event_type, str):
        event_type = ""
    event_type = event_type.strip()

    # --- Stripe payout (inflow)
    if event_type == "stripe.payout.paid":
        obj = ((inner.get("data") or {}).get("object") or {})
        description = "Stripe Payout"
        account = "bank"

        amt = float(obj.get("amount", 0.0))
        amount, direction = _direction_from_amount(amt, raw_dir=None)

        # Stripe payout is real cash inflow, so we can safely mark sales
        category = _normalize_category("sales", direction=direction)

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint="stripe",
        )

    # --- Stripe fee (expense, outflow)
    if event_type == "stripe.balance.fee":
        data = inner.get("data") or {}
        description = _coerce_str(data.get("description"), "Stripe Fees")
        account = "processor"

        amt = float(data.get("amount", 0.0))
        amt = -abs(amt)
        amount, direction = _direction_from_amount(amt, raw_dir="outflow")

        # fees: map to software for MVP
        category = _normalize_category("software", direction=direction)

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint="stripe",
        )

    # --- Shopify order paid (inflow)
    if event_type == "shopify.order.paid":
        order = inner.get("order") or {}
        total = float(order.get("total_price", 0.0))
        description = f"Shopify Order {order.get('name', '')}".strip() or "Shopify Order"
        account = "processor"

        amount, direction = _direction_from_amount(total, raw_dir="inflow")
        category = _normalize_category("sales", direction=direction)

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint="shopify",
        )

    # --- Shopify refund (outflow)
    if event_type == "shopify.refund":
        refund = inner.get("refund") or {}
        amt = float(refund.get("amount", 0.0))
        description = "Shopify Refund"
        account = "processor"

        amount, direction = _direction_from_amount(-abs(amt), raw_dir="outflow")
        category = _normalize_category("contra", direction=direction)

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint="shopify",
        )

    # --- Payroll run (outflow)
    if event_type == "payroll.run.posted":
        pr = inner.get("payroll") or {}
        net = float(pr.get("net_pay", 0.0))
        description = "Payroll Run"
        account = "bank"

        amount, direction = _direction_from_amount(-abs(net), raw_dir="outflow")
        category = _normalize_category("payroll", direction=direction)

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint="payroll",
        )

    # --- Invoice paid (inflow)
    if event_type == "invoicing.invoice.paid":
        inv = inner.get("invoice") or {}
        amt = float(inv.get("amount", 0.0))
        description = f"Invoice Paid - {inv.get('customer_name', 'Customer')}"
        account = "bank"

        amount, direction = _direction_from_amount(amt, raw_dir="inflow")
        category = _normalize_category("sales", direction=direction)

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint=str(inv.get("customer_name") or "customer"),
        )

    # -------------------------
    # 1) Payroll (cash outflow) (legacy)
    # -------------------------
    if event_type == "payroll.run.posted":
        payroll = inner.get("payroll") if isinstance(inner.get("payroll"), dict) else {}
        amt = payroll.get("net_total")
        if amt is None:
            amt = payroll.get("gross_total")
        if amt is None:
            raise ValueError("raw_event_to_txn: payroll event missing net_total/gross_total")

        amount = -abs(float(amt))
        amount, direction = _direction_from_amount(amount)

        description = f"Payroll run ({int(payroll.get('employee_count') or 0)} employees)" if payroll else "Payroll run"
        raw_cat = _coerce_str(_get_hint_category(inner), "payroll")
        category = _normalize_category(raw_cat, direction=direction)

        account = _coerce_str(inner.get("account_hint") or inner.get("account"), "checking")

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint=None,
        )

    # -------------------------------------------
    # 2) Card processor (payout / fee / chargeback)
    # -------------------------------------------
    if event_type.startswith("card_processor."):
        proc = inner.get("processor") if isinstance(inner.get("processor"), dict) else {}
        amt = proc.get("amount")
        if amt is None:
            raise ValueError("raw_event_to_txn: card processor event missing processor.amount")

        amount = float(amt)
        amount, direction = _direction_from_amount(amount)

        provider = _coerce_str(proc.get("provider"), "card_processor")
        description = f"{provider.upper()} {event_type.split('.', 1)[1].replace('_', ' ')}"

        # IMPORTANT: don’t “pre-categorize” unknown processor txns.
        # Leave uncategorized unless hint gives a known system key.
        raw_cat = _coerce_str(_get_hint_category(inner), "")
        category = _normalize_category(raw_cat, direction=direction)

        account = _coerce_str(inner.get("account_hint") or inner.get("account"), "checking")

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint=provider,
        )

    # -------------------------
    # 3) E-commerce (order/refund)
    # -------------------------
    if event_type.startswith("ecommerce."):
        shop = inner.get("shop") if isinstance(inner.get("shop"), dict) else {}
        amt = shop.get("total")
        if amt is None:
            raise ValueError("raw_event_to_txn: ecommerce event missing shop.total")

        amount = float(amt)
        amount, direction = _direction_from_amount(amount)

        platform = _coerce_str(shop.get("platform"), "ecommerce")
        order_id = _coerce_str(shop.get("order_id"), "order")
        description = f"{platform.title()} {event_type.split('.', 1)[1].replace('_', ' ')} ({order_id})"

        raw_cat = _coerce_str(_get_hint_category(inner), "")
        category = _normalize_category(raw_cat, direction=direction)

        account = _coerce_str(inner.get("account_hint") or inner.get("account"), "checking")

        return NormalizedTransaction(
            id=None,
            source_event_id=source_event_id,
            occurred_at=occurred_at_utc,
            date=d,
            description=description,
            amount=float(amount),
            direction=direction,  # type: ignore[arg-type]
            account=account,
            category=category,
            counterparty_hint=platform,
        )

    # -------------------------
    # 4) Invoicing (paid is cash, issued is non-cash)
    # -------------------------
    if event_type.startswith("invoicing."):
        inv = inner.get("invoice") if isinstance(inner.get("invoice"), dict) else {}
        kind = event_type.split(".", 1)[1]

        if kind == "invoice_issued":
            raise ValueError("raw_event_to_txn: invoice_issued is non-cash (skip for cash ledger MVP)")

        if kind == "invoice_paid":
            cash_amt = inv.get("cash_amount")
            if cash_amt is None:
                cash_amt = inv.get("amount")
            if cash_amt is None:
                raise ValueError("raw_event_to_txn: invoice_paid missing invoice.cash_amount/amount")

            amount = float(cash_amt)
            amount, direction = _direction_from_amount(amount)

            invoice_id = _coerce_str(inv.get("invoice_id"), "invoice")
            customer = _coerce_str(inv.get("customer_name"), "customer")
            description = f"Invoice paid ({invoice_id}) - {customer}"

            raw_cat = _coerce_str(_get_hint_category(inner), "")
            category = _normalize_category(raw_cat, direction=direction)

            account = _coerce_str(inner.get("account_hint") or inner.get("account"), "checking")

            return NormalizedTransaction(
                id=None,
                source_event_id=source_event_id,
                occurred_at=occurred_at_utc,
                date=d,
                description=description,
                amount=float(amount),
                direction=direction,  # type: ignore[arg-type]
                account=account,
                category=category,
                counterparty_hint=customer,
            )

    # -------------------------
    # 5) Plaid-like / generic fallback
    # -------------------------
    txn = inner.get("transaction")
    if isinstance(txn, dict):
        description = _coerce_str(
            txn.get("merchant_name") or txn.get("name") or inner.get("description"),
            "Unknown",
        )
        account = _coerce_str(inner.get("account_hint") or inner.get("account"), "checking")

        raw_cat = (
            _coerce_str(inner.get("category"), "")
            or _coerce_str((inner.get("sim_meta") or {}).get("hint"), "")
            or _coerce_str(_get_hint_category(inner), "")
            or "uncategorized"
        )
    else:
        description = _coerce_str(inner.get("description") or inner.get("name"), "Unknown")
        account = _coerce_str(inner.get("account_hint") or inner.get("account"), "checking")
        raw_cat = (
            _coerce_str(inner.get("category"), "")
            or _coerce_str(_get_hint_category(inner), "")
            or "uncategorized"
        )

    amt = _extract_amount_generic(inner)
    if amt is None:
        raise ValueError("raw_event_to_txn: payload missing amount_cents/amount")

    amount, direction = _direction_from_amount(float(amt), raw_dir=inner.get("direction"))

    # KEY FIX: normalize category so unknown stuff becomes "uncategorized"
    category = _normalize_category(raw_cat, direction=direction)

    return NormalizedTransaction(
        id=None,
        source_event_id=source_event_id,
        occurred_at=occurred_at_utc,
        date=d,
        description=description,
        amount=float(amount),
        direction=direction,  # type: ignore[arg-type]
        account=account,
        category=category,
        counterparty_hint=inner.get("counterparty_hint"),
    )
