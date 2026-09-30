"""Date/time parsing: strict ISO 8601 first, natural language as a fallback.

Every CLI flag that takes a date or datetime accepts either form. ISO is tried first and is
what an agent should always use — it's unambiguous and never subject to a parser's judgment
call. Natural language ("yesterday", "3 days ago", "monday") is for a human typing a command by
hand, and only kicks in when the value isn't already valid ISO. Note: "monday" resolves to the
most recent Monday, but "last monday" does not parse (a dateparser limitation, not ours) — use
the bare weekday name instead.
"""
from __future__ import annotations

from datetime import date, datetime, time

import dateparser

_HELP_DATETIME = (
    "try an ISO timestamp like 2026-09-30T16:46:08+02:00, or a phrase like 'yesterday'"
)
_HELP_DATE = "try YYYY-MM-DD, or a phrase like 'yesterday'"


def parse_datetime(value: str, *, now: datetime | None = None) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        settings = {"PREFER_DATES_FROM": "past"}
        if now is not None:
            settings["RELATIVE_BASE"] = now.replace(tzinfo=None)
        parsed = dateparser.parse(value, settings=settings)
        if parsed is None:
            raise ValueError(f"could not parse {value!r} as a date/time ({_HELP_DATETIME})") from None
        dt = parsed

    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def parse_date(value: str, *, today: date | None = None) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass

    settings = {"PREFER_DATES_FROM": "past"}
    if today is not None:
        settings["RELATIVE_BASE"] = datetime(today.year, today.month, today.day)
    parsed = dateparser.parse(value, settings=settings)
    if parsed is None:
        raise ValueError(f"could not parse {value!r} as a date ({_HELP_DATE})") from None
    return parsed.date()


def _is_full_iso_datetime(value: str) -> bool:
    """True only for a strict ISO 8601 string that includes a time component.

    dateparser fills in the *current* time of day for a bare date phrase like "today" or
    "2026-09-30" (it doesn't default to midnight), which is wrong for a range boundary: a plain
    date should mean the whole day, not "from this exact second". So --since/--until only treat
    a value as an exact instant when it's unambiguously a full ISO timestamp; every other case
    (a bare ISO date, or any natural-language phrase) is handled as a whole day instead.
    """
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return True  # parsed as a datetime but not as a bare date -> it carried a time part
    return False


def parse_range_start(value: str, *, today: date | None = None) -> datetime:
    """For --since (and similar lower bounds): an exact ISO timestamp is used as-is; a bare
    date or natural-language phrase resolves to the start of that day.
    """
    if _is_full_iso_datetime(value):
        return parse_datetime(value)
    d = parse_date(value, today=today)
    return datetime.combine(d, time.min).astimezone()


def parse_range_end(value: str, *, today: date | None = None) -> datetime:
    """For --until (and similar upper bounds): an exact ISO timestamp is used as-is; a bare
    date or natural-language phrase resolves to the end of that day, so the whole day is
    included rather than being cut off at the moment the command happens to run.
    """
    if _is_full_iso_datetime(value):
        return parse_datetime(value)
    d = parse_date(value, today=today)
    return datetime.combine(d, time(23, 59, 59, 999999)).astimezone()
