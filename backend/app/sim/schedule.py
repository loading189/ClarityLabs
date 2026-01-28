from __future__ import annotations

from datetime import date, timedelta
import calendar
from typing import Iterable, List, Optional, Sequence


def _date_range(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current < end_date:
        yield current
        current += timedelta(days=1)


def daily_dates(
    *,
    seed: int,
    start_date: date,
    end_date: date,
    stream_key: str,
    open_days: Optional[Sequence[int]] = None,
) -> List[date]:
    """
    Return all dates in [start_date, end_date) that match open_days.
    Deterministic from (seed, start_date, end_date, stream_key).
    """
    _ = (seed, stream_key)
    open_set = set(open_days) if open_days is not None else set(range(7))
    return [d for d in _date_range(start_date, end_date) if d.weekday() in open_set]


def weekly_dates(
    *,
    seed: int,
    start_date: date,
    end_date: date,
    stream_key: str,
    weekday: int,
) -> List[date]:
    """
    Return dates in [start_date, end_date) that fall on weekday (0=Mon).
    Deterministic from (seed, start_date, end_date, stream_key).
    """
    _ = (seed, stream_key)
    if weekday < 0 or weekday > 6:
        raise ValueError("weekday must be 0..6")

    days_ahead = (weekday - start_date.weekday()) % 7
    first = start_date + timedelta(days=days_ahead)
    dates: List[date] = []
    current = first
    while current < end_date:
        dates.append(current)
        current += timedelta(days=7)
    return dates


def biweekly_dates(
    *,
    seed: int,
    start_date: date,
    end_date: date,
    stream_key: str,
    anchor: date,
) -> List[date]:
    """
    Return dates in [start_date, end_date) every 14 days aligned to anchor.
    Deterministic from (seed, start_date, end_date, stream_key).
    """
    _ = (seed, stream_key)
    if start_date <= anchor:
        first = anchor
    else:
        delta_days = (start_date - anchor).days
        offset = (14 - (delta_days % 14)) % 14
        first = start_date + timedelta(days=offset)

    dates: List[date] = []
    current = first
    while current < end_date:
        dates.append(current)
        current += timedelta(days=14)
    return dates


def monthly_dates(
    *,
    seed: int,
    start_date: date,
    end_date: date,
    stream_key: str,
    day: int,
) -> List[date]:
    """
    Return dates in [start_date, end_date) on a given day of month.
    If day exceeds the month length, use the last day.
    Deterministic from (seed, start_date, end_date, stream_key).
    """
    _ = (seed, stream_key)
    if day < 1:
        raise ValueError("day must be >= 1")

    dates: List[date] = []
    current = date(start_date.year, start_date.month, 1)
    while current < end_date:
        _, month_days = calendar.monthrange(current.year, current.month)
        actual_day = min(day, month_days)
        candidate = date(current.year, current.month, actual_day)
        if start_date <= candidate < end_date:
            dates.append(candidate)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return dates
