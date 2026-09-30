from datetime import date, datetime, time, timedelta, timezone

import pytest

from journal.dates import parse_date, parse_datetime, parse_range_end, parse_range_start

TZ = timezone(timedelta(hours=2))


def test_parse_datetime_accepts_iso():
    assert parse_datetime("2026-09-30T16:46:08+02:00") == datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)


def test_parse_datetime_iso_without_tz_gets_local_tz_attached():
    dt = parse_datetime("2026-09-30T16:46:08")
    assert dt.tzinfo is not None


def test_parse_datetime_falls_back_to_natural_language():
    now = datetime(2026, 9, 30, 12, 0, 0)
    dt = parse_datetime("yesterday", now=now)
    assert dt.date() == date(2026, 9, 29)


def test_parse_datetime_natural_language_relative_phrase():
    now = datetime(2026, 9, 30, 12, 0, 0)
    dt = parse_datetime("3 days ago", now=now)
    assert dt.date() == date(2026, 9, 27)


def test_parse_datetime_unparseable_raises_value_error():
    with pytest.raises(ValueError, match="could not parse"):
        parse_datetime("not a date at all, sorry")


def test_parse_date_accepts_iso():
    assert parse_date("2026-09-30") == date(2026, 9, 30)


def test_parse_date_falls_back_to_natural_language():
    today = date(2026, 9, 30)
    assert parse_date("yesterday", today=today) == date(2026, 9, 29)


def test_parse_date_unparseable_raises_value_error():
    with pytest.raises(ValueError, match="could not parse"):
        parse_date("not a date at all, sorry")


def test_parse_range_start_bare_date_is_midnight_not_now():
    # This is the bug that motivated parse_range_start/end: dateparser resolves a bare date
    # phrase to the *current* time of day, which would wrongly exclude anything created
    # earlier today than the moment the command runs.
    today = date(2026, 9, 30)
    result = parse_range_start("today", today=today)
    assert result.date() == today
    assert result.time() == time.min


def test_parse_range_end_bare_date_is_end_of_day():
    today = date(2026, 9, 30)
    result = parse_range_end("today", today=today)
    assert result.date() == today
    assert result.time() == time(23, 59, 59, 999999)


def test_parse_range_start_bare_iso_date_is_midnight():
    result = parse_range_start("2026-09-30")
    assert result.date() == date(2026, 9, 30)
    assert result.time() == time.min


def test_parse_range_start_full_iso_timestamp_used_exactly():
    result = parse_range_start("2026-09-30T14:30:00+02:00")
    assert result == datetime(2026, 9, 30, 14, 30, 0, tzinfo=timezone(timedelta(hours=2)))


def test_parse_range_end_full_iso_timestamp_used_exactly():
    result = parse_range_end("2026-09-30T14:30:00+02:00")
    assert result == datetime(2026, 9, 30, 14, 30, 0, tzinfo=timezone(timedelta(hours=2)))


def test_parse_range_start_natural_language_relative():
    today = date(2026, 9, 30)
    result = parse_range_start("yesterday", today=today)
    assert result.date() == date(2026, 9, 29)
    assert result.time() == time.min
