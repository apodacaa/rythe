"""Human-readable rendering of entries, for `rythe read` and `rythe show`.

This is for reading, not for scripts: scripts use `--json`, whose shape is a stable contract and
is deliberately separate from anything in this module.
"""
from __future__ import annotations

import re

from . import ui
from .entry import Entry
from .tags import TAG_RE

_SOURCE_LABELS = {"memo": "voice memo", "text": "imported"}
_RULE_WIDTH = 60


def day_header(entry: Entry) -> str:
    label = f"{entry.created:%A, %B} {entry.created.day}, {entry.created.year}"
    head = f"── {label} "
    return ui.style(head, "bold", "cyan") + ui.style("─" * max(0, _RULE_WIDTH - len(head)), "gray")


def entry_header(entry: Entry, *, show_id: bool = False) -> str:
    hour = entry.created.hour % 12 or 12
    parts = [ui.style(f"{hour}:{entry.created:%M %p}", "bold")]
    label = _SOURCE_LABELS.get(entry.source)
    if label:
        parts.append(ui.style(label, "magenta"))
    if entry.title:
        parts.append(ui.style(f"“{entry.title}”", "italic"))
    if show_id:
        parts.append(ui.style(entry.id, "dim"))
    return ui.style(" · ", "gray").join(parts)


def _body(entry: Entry) -> str:
    """The entry text, with #tags picked out in cyan (plain text is unchanged without color)."""
    body = entry.body.rstrip()
    if not ui.color():
        return body
    return TAG_RE.sub(lambda m: ui.style(m.group(0), "cyan"), body)


def render_entry(entry: Entry, *, show_id: bool = False) -> str:
    return f"{entry_header(entry, show_id=show_id)}\n{_body(entry)}\n"


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


# -- shared styling for one-line entry listings (list, search, on-this-day) ---------------------

_SOURCE_COLORS = {"cli": ("dim",), "memo": ("magenta",), "text": ("yellow",)}


def source_badge(source: str) -> str:
    return ui.style(f"[{source}]", *_SOURCE_COLORS.get(source, ("dim",)))


def entry_id(entry_id: str) -> str:
    return ui.style(entry_id, "cyan")


def listing_line(entry: Entry, preview: str, *, indent: str = "") -> str:
    """`<id>  [source]  <preview>`: the id in cyan, the source as a colored badge."""
    suffix = f"  {preview}" if preview else ""
    return f"{indent}{entry_id(entry.id)}  {source_badge(entry.source)}{suffix}"


def done(verb: str, ref: str, rest: str = "") -> str:
    """`created <id>`-style confirmations: the verb in green, the id in cyan."""
    return f"{ui.style(verb, 'green')} {entry_id(ref)}{rest}"


def highlight(line: str, query: str | None, *, regex: bool = False) -> str:
    """Bold-yellow the parts of `line` that matched a search query (no-op without color)."""
    if not query or not ui.color():
        return line
    try:
        pattern = re.compile(query if regex else re.escape(query), re.IGNORECASE)
    except re.error:
        return line
    return pattern.sub(lambda m: ui.style(m.group(0), "bold", "yellow"), line)


def tag_counts_line(count: int, tag: str) -> str:
    return f"{ui.style(f'{count:>4}', 'bold')}  {ui.style('#' + tag, 'cyan')}"
