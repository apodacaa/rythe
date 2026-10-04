"""Human-readable rendering of entries, for `journal read` and `journal show`.

This is for reading, not for scripts: scripts use `--json`, whose shape is a stable contract and
is deliberately separate from anything in this module.
"""
from __future__ import annotations

from .entry import Entry

_SOURCE_LABELS = {"memo": "voice memo", "text": "imported"}
_RULE_WIDTH = 60


def day_header(entry: Entry) -> str:
    label = f"{entry.created:%A, %B} {entry.created.day}, {entry.created.year}"
    return f"── {label} ".ljust(_RULE_WIDTH, "─")


def entry_header(entry: Entry, *, show_id: bool = False) -> str:
    hour = entry.created.hour % 12 or 12
    parts = [f"{hour}:{entry.created:%M %p}"]
    label = _SOURCE_LABELS.get(entry.source)
    if label:
        parts.append(label)
    if entry.title:
        parts.append(f"“{entry.title}”")
    if show_id:
        parts.append(entry.id)
    return " · ".join(parts)


def render_entry(entry: Entry, *, show_id: bool = False) -> str:
    return f"{entry_header(entry, show_id=show_id)}\n{entry.body.rstrip()}\n"


def render_entries(entries: list[Entry], *, show_id: bool = False) -> str:
    """Entries grouped under a header per day, in the order given (callers pass oldest first)."""
    blocks: list[str] = []
    last_day = None
    for entry in entries:
        day = entry.created.date()
        if day != last_day:
            blocks.append(day_header(entry) + "\n")
            last_day = day
        blocks.append(render_entry(entry, show_id=show_id))
    return "\n".join(blocks)
