from datetime import UTC, date, datetime

import pytest
from merchantos_domain import (
    CompareMode,
    DatePreset,
    InvalidDateRangeError,
    resolve_compared_windows,
    resolve_current_window,
)


def test_last_7_is_inclusive_store_local_days() -> None:
    now = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)
    window = resolve_current_window(preset=DatePreset.LAST_7, timezone="UTC", now=now)
    assert window.start_local == date(2026, 8, 20)
    assert window.end_local_exclusive == date(2026, 8, 27)
    assert window.start_utc.isoformat() == "2026-08-20T00:00:00+00:00"
    assert window.end_utc.isoformat() == "2026-08-27T00:00:00+00:00"


def test_this_month_uses_store_timezone() -> None:
    now = datetime(2026, 8, 26, 2, 0, tzinfo=UTC)
    window = resolve_current_window(
        preset=DatePreset.THIS_MONTH, timezone="America/New_York", now=now
    )
    assert window.start_local == date(2026, 8, 1)
    assert window.end_local_exclusive == date(2026, 8, 26)


def test_custom_and_previous_equivalent_period() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    compared = resolve_compared_windows(
        preset=DatePreset.CUSTOM,
        compare=CompareMode.PREVIOUS_PERIOD,
        timezone="UTC",
        now=now,
        custom_from=date(2026, 8, 10),
        custom_to=date(2026, 8, 19),
    )
    assert compared.current.start_local == date(2026, 8, 10)
    assert compared.current.end_local_exclusive == date(2026, 8, 20)
    assert compared.previous.start_local == date(2026, 7, 31)
    assert compared.previous.end_local_exclusive == date(2026, 8, 10)


def test_previous_month_compare_for_this_month() -> None:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    compared = resolve_compared_windows(
        preset=DatePreset.THIS_MONTH,
        compare=CompareMode.PREVIOUS_MONTH,
        timezone="UTC",
        now=now,
    )
    assert compared.previous.start_local == date(2026, 7, 1)
    assert compared.previous.end_local_exclusive <= date(2026, 8, 1)


def test_rejects_inverted_and_huge_custom_ranges() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    with pytest.raises(InvalidDateRangeError):
        resolve_current_window(
            preset=DatePreset.CUSTOM,
            timezone="UTC",
            now=now,
            custom_from=date(2026, 8, 20),
            custom_to=date(2026, 8, 10),
        )
    with pytest.raises(InvalidDateRangeError):
        resolve_current_window(
            preset=DatePreset.CUSTOM,
            timezone="UTC",
            now=now,
            custom_from=date(2024, 1, 1),
            custom_to=date(2026, 8, 1),
        )


def test_unknown_timezone_rejected() -> None:
    with pytest.raises(InvalidDateRangeError, match="timezone"):
        resolve_current_window(
            preset=DatePreset.TODAY,
            timezone="Not/AZone",
            now=datetime(2026, 8, 26, tzinfo=UTC),
        )
