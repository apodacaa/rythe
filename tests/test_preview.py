from datetime import datetime, timezone

from journal.cli import _preview
from journal.entry import Entry


def entry(title="", body=""):
    return Entry(id="x", created=datetime(2026, 9, 30, tzinfo=timezone.utc), title=title, body=body)


def test_preview_prefers_title():
    assert _preview(entry(title="My Title", body="the body text here")) == "My Title"


def test_preview_falls_back_to_body_when_no_title():
    assert _preview(entry(body="a short thought")) == "a short thought"


def test_preview_collapses_whitespace_and_newlines():
    assert _preview(entry(body="line one\nline   two\n\nline three")) == "line one line two line three"


def test_preview_truncates_long_body_with_ellipsis():
    body = "x" * 80
    result = _preview(entry(body=body), length=50)
    assert result == "x" * 50 + "…"


def test_preview_short_body_not_truncated():
    body = "short"
    assert _preview(entry(body=body), length=50) == "short"


def test_preview_empty_entry_is_empty_string():
    assert _preview(entry()) == ""
