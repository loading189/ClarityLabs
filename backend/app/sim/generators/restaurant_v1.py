from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import random
from typing import Any, Dict, List

from backend.app.sim.merchant_sets import pick_merchant
from backend.app.sim.schedule import daily_dates, weekly_dates, biweekly_dates, monthly_dates


def _stable_seed(seed: int, stream: str, when: date, extra: str = "") -> int:
    key = f"{seed}:{stream}:{when.isoformat()}:{extra}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _rng(seed: int, stream: str, when: date, extra: str = "") -> random.Random:
    return random.Random(_stable_seed(seed, stream, when, extra))


def _stable_event_id(seed: int, stream: str, when: date, extra: str = "") -> str:
    digest = hashlib.sha256(f"{seed}:{stream}:{when.isoformat()}:{extra}".encode("utf-8")).hexdigest()
    return f"sim_{stream}_{digest[:12]}"


def _occurred_at(when: date, seed: int, stream: str, window: tuple[int, int], extra: str = "") -> datetime:
    start_h, end_h = window
    r = _rng(seed, stream, when, extra)
    hour = r.randint(start_h, max(start_h, end_h - 1))
    minute = r.randint(0, 59)
    return datetime(when.year, when.month, when.day, hour, minute, tzinfo=timezone.utc)


def _scaled_amount(base: float, mult: float, min_amt: float, max_amt: float) -> float:
    scaled = base * mult
    low = min_amt * 0.3
    high = max_amt * 2.0
    return round(min(max(scaled, low), high), 2)


def _plaid_transaction(
    *,
    business_id: str,
    occurred_at: datetime,
    amount: float,
    merchant: str,
    merchant_group: str,
    stream: str,
    seed: int,
    when: date,
    extra: str = "",
    is_income: bool = False,
) -> Dict[str, Any]:
    signed_amount = -abs(amount) if is_income else abs(amount)
    event_id = _stable_event_id(seed, stream, when, extra)

    payload = {
        "type": "transaction.posted",
        "transaction": {
            "transaction_id": event_id,
            "amount": signed_amount,
            "iso_currency_code": "USD",
            "date": occurred_at.date().isoformat(),
            "name": merchant,
            "merchant_name": merchant,
            "payment_channel": "in_store",
            "pending": False,
        },
        "sim_meta": {
            "generator": "restaurant_v1",
            "stream": stream,
            "merchant_group": merchant_group,
        },
    }

    return {
        "source": "plaid",
        "source_event_id": event_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }


def _payroll_event(
    *,
    business_id: str,
    occurred_at: datetime,
    gross: float,
    taxes: float,
    net: float,
    seed: int,
    when: date,
    merchant: str,
    extra: str = "",
) -> Dict[str, Any]:
    run_id = _stable_event_id(seed, "payroll", when, extra).replace("sim_", "payroll_")
    payload = {
        "type": "payroll.run.posted",
        "payroll": {
            "run_id": run_id,
            "processed_at": occurred_at.isoformat(),
            "gross_pay": round(gross, 2),
            "taxes": round(taxes, 2),
            "net_pay": round(net, 2),
            "currency": "USD",
            "payee": merchant,
        },
        "meta": {"integration": "gusto_like"},
        "sim_meta": {
            "generator": "restaurant_v1",
            "stream": "payroll",
            "merchant": merchant,
        },
    }

    return {
        "source": "payroll",
        "source_event_id": run_id,
        "occurred_at": occurred_at,
        "payload": payload,
    }


def _first_weekday_on_or_after(start_date: date, weekday: int) -> date:
    delta = (weekday - start_date.weekday()) % 7
    return start_date + timedelta(days=delta)


def generate_restaurant_v1_events(
    *,
    business_id: str,
    start_date: date,
    end_date: date,
    seed: int,
    mods_by_day: Dict[date, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    open_days = list(range(7))

    # Daily deposits (one per day)
    for day in daily_dates(
        seed=seed,
        start_date=start_date,
        end_date=end_date,
        stream_key="daily_deposits",
        open_days=open_days,
    ):
        mods = mods_by_day.get(day, {})
        revenue_mult = float(mods.get("revenue_mult", 1.0))
        volume_mult = float(mods.get("volume_mult", 1.0))
        delay_days = int(mods.get("deposit_delay_days", 0))

        deposit_day = day + timedelta(days=delay_days)
        if deposit_day >= end_date:
            continue

        merchant, group = pick_merchant("deposits", seed, day)
        r = _rng(seed, "daily_deposits", day)
        base = r.uniform(1200.0, 9000.0)
        amount = _scaled_amount(base, revenue_mult * volume_mult, 1200.0, 9000.0)
        occurred_at = _occurred_at(deposit_day, seed, "daily_deposits", (6, 10), extra=day.isoformat())

        events.append(
            _plaid_transaction(
                business_id=business_id,
                occurred_at=occurred_at,
                amount=amount,
                merchant=merchant,
                merchant_group=group,
                stream="daily_deposits",
                seed=seed,
                when=day,
                extra=day.isoformat(),
                is_income=True,
            )
        )

    # Weekly suppliers
    supplier_days = weekly_dates(
        seed=seed,
        start_date=start_date,
        end_date=end_date,
        stream_key="suppliers",
        weekday=1,
    )
    for day in supplier_days:
        mods = mods_by_day.get(day, {})
        expense_mult = float(mods.get("expense_mult", 1.0))
        merchant, group = pick_merchant("suppliers", seed, day)
        r = _rng(seed, "suppliers", day)
        base = r.uniform(450.0, 2400.0)
        amount = _scaled_amount(base, expense_mult, 450.0, 2400.0)
        occurred_at = _occurred_at(day, seed, "suppliers", (8, 12))

        events.append(
            _plaid_transaction(
                business_id=business_id,
                occurred_at=occurred_at,
                amount=amount,
                merchant=merchant,
                merchant_group=group,
                stream="suppliers",
                seed=seed,
                when=day,
            )
        )

    # Payroll (biweekly, anchored to Friday)
    anchor = _first_weekday_on_or_after(start_date, 4)
    for day in biweekly_dates(
        seed=seed,
        start_date=start_date,
        end_date=end_date,
        stream_key="payroll",
        anchor=anchor,
    ):
        mods = mods_by_day.get(day, {})
        expense_mult = float(mods.get("expense_mult", 1.0))
        merchant, _ = pick_merchant("payroll", seed, day)
        r = _rng(seed, "payroll", day)
        base = r.uniform(3200.0, 14000.0)
        gross = _scaled_amount(base, expense_mult, 3200.0, 14000.0)
        taxes = gross * r.uniform(0.18, 0.26)
        net = gross - taxes
        occurred_at = _occurred_at(day, seed, "payroll", (8, 10))

        events.append(
            _payroll_event(
                business_id=business_id,
                occurred_at=occurred_at,
                gross=gross,
                taxes=taxes,
                net=net,
                seed=seed,
                when=day,
                merchant=merchant,
            )
        )

    # Monthly fixed costs (rent, utilities, software)
    monthly_defs = [
        ("rent", 1, 2800.0, 8200.0, (9, 11)),
        ("utilities", 12, 260.0, 1200.0, (9, 13)),
        ("software", 18, 90.0, 450.0, (9, 11)),
    ]
    for stream, day_of_month, min_amt, max_amt, window in monthly_defs:
        for day in monthly_dates(
            seed=seed,
            start_date=start_date,
            end_date=end_date,
            stream_key=stream,
            day=day_of_month,
        ):
            mods = mods_by_day.get(day, {})
            expense_mult = float(mods.get("expense_mult", 1.0))
            merchant, group = pick_merchant(stream, seed, day)
            r = _rng(seed, stream, day)
            base = r.uniform(min_amt, max_amt)
            amount = _scaled_amount(base, expense_mult, min_amt, max_amt)
            occurred_at = _occurred_at(day, seed, stream, window)

            events.append(
                _plaid_transaction(
                    business_id=business_id,
                    occurred_at=occurred_at,
                    amount=amount,
                    merchant=merchant,
                    merchant_group=group,
                    stream=stream,
                    seed=seed,
                    when=day,
                )
            )

    # Misc spend: 0-2 per month
    month_cursor = date(start_date.year, start_date.month, 1)
    while month_cursor < end_date:
        r = _rng(seed, "misc", month_cursor, "count")
        count = r.randint(0, 2)
        month_start = month_cursor
        if month_cursor.month == 12:
            month_end = date(month_cursor.year + 1, 1, 1)
        else:
            month_end = date(month_cursor.year, month_cursor.month + 1, 1)

        month_days = [
            d
            for d in daily_dates(
                seed=seed,
                start_date=month_start,
                end_date=month_end,
                stream_key="misc",
                open_days=open_days,
            )
        ]
        if month_days and count > 0:
            if count >= len(month_days):
                picks = list(month_days)
            else:
                picks = r.sample(month_days, k=count)
            for idx, day in enumerate(picks):
                if not (start_date <= day < end_date):
                    continue
                mods = mods_by_day.get(day, {})
                expense_mult = float(mods.get("expense_mult", 1.0))
                merchant, group = pick_merchant("misc", seed + idx, day)
                r_item = _rng(seed, "misc", day, str(idx))
                base = r_item.uniform(45.0, 360.0)
                amount = _scaled_amount(base, expense_mult, 45.0, 360.0)
                occurred_at = _occurred_at(day, seed, "misc", (10, 18), extra=str(idx))

                events.append(
                    _plaid_transaction(
                        business_id=business_id,
                        occurred_at=occurred_at,
                        amount=amount,
                        merchant=merchant,
                        merchant_group=group,
                        stream="misc",
                        seed=seed + idx,
                        when=day,
                        extra=str(idx),
                    )
                )

        month_cursor = month_end

    events.sort(key=lambda e: (e["occurred_at"], e["source_event_id"]))
    return events
