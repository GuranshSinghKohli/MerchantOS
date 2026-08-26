"""Store-timezone date windows for analytics. Bounds are half-open [start, end)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from merchantos_domain.errors import InvalidDateRangeError

MAX_RANGE_DAYS = 366


class DatePreset(StrEnum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7 = "last_7"
    LAST_30 = "last_30"
    LAST_90 = "last_90"
    THIS_MONTH = "this_month"
    PREVIOUS_MONTH = "previous_month"
    CUSTOM = "custom"


class CompareMode(StrEnum):
    PREVIOUS_PERIOD = "previous_period"
    PREVIOUS_MONTH = "previous_month"


@dataclass(frozen=True)
class DateWindow:
    """Half-open UTC instants covering a store-local calendar span."""

    preset: DatePreset
    timezone: str
    start_utc: datetime
    end_utc: datetime
    start_local: date
    end_local_exclusive: date


@dataclass(frozen=True)
class ComparedWindows:
    current: DateWindow
    previous: DateWindow
    compare: CompareMode


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise InvalidDateRangeError(f"unknown IANA timezone: {name}") from exc


def _local_midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone)


def _window_from_local_days(
    *,
    preset: DatePreset,
    timezone: str,
    start_local: date,
    end_local_exclusive: date,
) -> DateWindow:
    if end_local_exclusive <= start_local:
        raise InvalidDateRangeError("date range end must be after start")
    span = (end_local_exclusive - start_local).days
    if span > MAX_RANGE_DAYS:
        raise InvalidDateRangeError(f"date range cannot exceed {MAX_RANGE_DAYS} days")
    zone = _zone(timezone)
    start_utc = _local_midnight(start_local, zone).astimezone(ZoneInfo("UTC"))
    end_utc = _local_midnight(end_local_exclusive, zone).astimezone(ZoneInfo("UTC"))
    return DateWindow(
        preset=preset,
        timezone=timezone,
        start_utc=start_utc,
        end_utc=end_utc,
        start_local=start_local,
        end_local_exclusive=end_local_exclusive,
    )


def resolve_current_window(
    *,
    preset: DatePreset,
    timezone: str,
    now: datetime,
    custom_from: date | None = None,
    custom_to: date | None = None,
) -> DateWindow:
    zone = _zone(timezone)
    today = now.astimezone(zone).date()
    if preset is DatePreset.CUSTOM:
        if custom_from is None or custom_to is None:
            raise InvalidDateRangeError("custom range requires from and to")
        return _window_from_local_days(
            preset=preset,
            timezone=timezone,
            start_local=custom_from,
            end_local_exclusive=custom_to + timedelta(days=1),
        )
    if custom_from is not None or custom_to is not None:
        raise InvalidDateRangeError("from/to are only valid with preset=custom")
    if preset is DatePreset.TODAY:
        start, end = today, today + timedelta(days=1)
    elif preset is DatePreset.YESTERDAY:
        start, end = today - timedelta(days=1), today
    elif preset is DatePreset.LAST_7:
        start, end = today - timedelta(days=6), today + timedelta(days=1)
    elif preset is DatePreset.LAST_30:
        start, end = today - timedelta(days=29), today + timedelta(days=1)
    elif preset is DatePreset.LAST_90:
        start, end = today - timedelta(days=89), today + timedelta(days=1)
    elif preset is DatePreset.THIS_MONTH:
        start = today.replace(day=1)
        end = today + timedelta(days=1)
    elif preset is DatePreset.PREVIOUS_MONTH:
        first = today.replace(day=1)
        start = (first - timedelta(days=1)).replace(day=1)
        end = first
    else:
        raise InvalidDateRangeError(f"unsupported preset: {preset}")
    return _window_from_local_days(
        preset=preset, timezone=timezone, start_local=start, end_local_exclusive=end
    )


def _shift_calendar_month(start_local: date, end_exclusive: date) -> tuple[date, date]:
    """Previous calendar month covering the same number of local days when possible."""
    first = start_local.replace(day=1)
    prev_month_end = first
    prev_month_start = (first - timedelta(days=1)).replace(day=1)
    span = (end_exclusive - start_local).days
    candidate_end = prev_month_start + timedelta(days=span)
    if candidate_end > prev_month_end:
        candidate_end = prev_month_end
    if candidate_end <= prev_month_start:
        raise InvalidDateRangeError("previous month comparison is empty")
    return prev_month_start, candidate_end


def resolve_compared_windows(
    *,
    preset: DatePreset,
    compare: CompareMode,
    timezone: str,
    now: datetime,
    custom_from: date | None = None,
    custom_to: date | None = None,
) -> ComparedWindows:
    current = resolve_current_window(
        preset=preset,
        timezone=timezone,
        now=now,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    span = current.end_local_exclusive - current.start_local
    if compare is CompareMode.PREVIOUS_PERIOD:
        prev = _window_from_local_days(
            preset=DatePreset.CUSTOM,
            timezone=timezone,
            start_local=current.start_local - span,
            end_local_exclusive=current.start_local,
        )
    elif compare is CompareMode.PREVIOUS_MONTH:
        start, end = _shift_calendar_month(current.start_local, current.end_local_exclusive)
        prev = _window_from_local_days(
            preset=DatePreset.CUSTOM,
            timezone=timezone,
            start_local=start,
            end_local_exclusive=end,
        )
    else:
        raise InvalidDateRangeError(f"unsupported comparison: {compare}")
    return ComparedWindows(current=current, previous=prev, compare=compare)
