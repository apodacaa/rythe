"""File-backed storage for journal entries under JOURNAL_DIR (default ~/.local/share/journal).

Tags are never indexed: every read scans the body with tags.extract_tags. At journal scale a
full directory scan on every command is fast enough, and there is no index to keep in sync.
"""
from __future__ import annotations

import calendar
import os
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from . import history
from .entry import Entry, id_for
from .tags import extract_tags, normalize_tag


class EntryNotFoundError(Exception):
    pass


class DuplicateMessageError(Exception):
    def __init__(self, message_id: str, existing_id: str):
        super().__init__(f"message_id {message_id!r} already ingested as entry {existing_id!r}")
        self.message_id = message_id
        self.existing_id = existing_id


def data_dir() -> Path:
    override = os.environ.get("JOURNAL_DIR")
    return Path(override) if override else Path.home() / ".local/share/journal"


def entries_root() -> Path:
    return data_dir() / "entries"


def audio_root() -> Path:
    return data_dir() / "audio"


def drafts_root() -> Path:
    return data_dir() / "drafts"


def list_drafts() -> list[Path]:
    """Unsaved editor drafts left behind by an interrupted write, oldest first."""
    root = drafts_root()
    return sorted(root.glob("*.txt")) if root.exists() else []


def new_draft_path() -> Path:
    drafts_root().mkdir(parents=True, exist_ok=True)
    return drafts_root() / f"{datetime.now().strftime('%Y%m%dT%H%M%S%f')}.txt"


def _entry_path(entry_id: str) -> Path:
    year, month = entry_id[:4], entry_id[5:7]
    return entries_root() / year / month / f"{entry_id}.txt"


def _find_path(entry_id: str) -> Path | None:
    path = _entry_path(entry_id)
    if path.exists():
        return path
    # Fallback scan, in case an id ever doesn't encode its own year/month (e.g. imported data).
    root = entries_root()
    if root.exists():
        for candidate in root.rglob(f"{entry_id}.txt"):
            return candidate
    return None


def _unique_id(created: datetime) -> str:
    base = id_for(created)
    candidate = base
    n = 2
    while _entry_path(candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def iter_entries():
    root = entries_root()
    if not root.exists():
        return
    for path in sorted(root.rglob("*.txt")):
        yield Entry.from_markdown(path.stem, path.read_text())


def find_by_message_id(message_id: str) -> Entry | None:
    for entry in iter_entries():
        if entry.message_id == message_id:
            return entry
    return None


def create(
    *,
    created: datetime,
    body: str,
    source: str = "cli",
    title: str = "",
    message_id: str | None = None,
    audio: str | None = None,
    transcriber: str | None = None,
    force: bool = False,
) -> Entry:
    if message_id and not force:
        existing = find_by_message_id(message_id)
        if existing is not None:
            raise DuplicateMessageError(message_id, existing.id)

    entry = Entry(
        id=_unique_id(created),
        created=created,
        source=source,
        title=title,
        message_id=message_id,
        audio=audio,
        transcriber=transcriber,
        body=body,
    )
    path = _entry_path(entry.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry.to_markdown())
    history.record(data_dir(), f"new {entry.id}")
    return entry


def get(entry_id: str) -> Entry:
    path = _find_path(entry_id)
    if path is None:
        raise EntryNotFoundError(entry_id)
    return Entry.from_markdown(entry_id, path.read_text())


def path_for(entry_id: str) -> Path:
    path = _find_path(entry_id)
    if path is None:
        raise EntryNotFoundError(entry_id)
    return path


def _save(entry: Entry, action: str = "edit") -> None:
    path_for(entry.id).write_text(entry.to_markdown())
    history.record(data_dir(), f"{action} {entry.id}")


def update_body(entry_id: str, body: str, when: datetime) -> Entry:
    """Replace an entry's body and stamp `updated`. Callers should only call this when the body
    actually changed, so `updated` doesn't drift just from opening and re-saving an entry
    untouched. Frontmatter is never exposed to the editor, so it can't be damaged by an edit.
    """
    entry = get(entry_id)
    entry.body = body
    entry.updated = when
    _save(entry)
    return entry


def set_audio(entry_id: str, audio_relpath: str) -> Entry:
    """Record an entry's audio file. Used after ingest_audio(), once the entry's id (and so the
    audio file's name, which reuses it) is known.
    """
    entry = get(entry_id)
    entry.audio = audio_relpath
    _save(entry, "audio")
    return entry


def trash_root() -> Path:
    return data_dir() / ".trash"


def delete(entry_id: str) -> Path:
    """Soft-delete: moves the entry (and its audio, if any) into .trash instead of unlinking it.

    Returns the entry's new path in the trash.
    """
    path = _find_path(entry_id)
    if path is None:
        raise EntryNotFoundError(entry_id)
    entry = Entry.from_markdown(entry_id, path.read_text())

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    trash_entries = trash_root() / "entries"
    trash_entries.mkdir(parents=True, exist_ok=True)
    dest = trash_entries / f"{entry_id}.{stamp}.txt"
    path.rename(dest)

    if entry.audio:
        audio_path = data_dir() / entry.audio
        if audio_path.exists():
            trash_audio = trash_root() / "audio"
            trash_audio.mkdir(parents=True, exist_ok=True)
            audio_path.rename(trash_audio / f"{audio_path.stem}.{stamp}{audio_path.suffix}")

    history.record(data_dir(), f"delete {entry_id}")
    return dest


def list_entries(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    on: date | None = None,
    tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    untagged: bool = False,
    source: str | None = None,
    limit: int | None = None,
) -> list[Entry]:
    results = []
    for entry in iter_entries():
        if since and entry.created < since:
            continue
        if until and entry.created > until:
            continue
        if on and entry.created.date() != on:
            continue
        if source and entry.source != source:
            continue
        if tags or exclude_tags or untagged:
            entry_tags = set(extract_tags(entry.body))
            if untagged and entry_tags:
                continue
            if tags and not set(tags).issubset(entry_tags):
                continue
            if exclude_tags and entry_tags & set(exclude_tags):
                continue
        results.append(entry)
    results.sort(key=lambda e: e.created, reverse=True)
    if limit:
        results = results[:limit]
    return results


def on_this_day(target: date, *, tags: list[str] | None = None, source: str | None = None) -> list[Entry]:
    """Entries written on this calendar month/day in any year — a "this day in history" view."""
    results = []
    for entry in iter_entries():
        if (entry.created.month, entry.created.day) != (target.month, target.day):
            continue
        if source and entry.source != source:
            continue
        if tags:
            entry_tags = set(extract_tags(entry.body))
            if not set(tags).issubset(entry_tags):
                continue
        results.append(entry)
    results.sort(key=lambda e: e.created, reverse=True)
    return results


def _months_ago(day: date, months: int) -> date:
    year, month0 = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(year, month0 + 1, min(day.day, calendar.monthrange(year, month0 + 1)[1]))


def resurface(today: date) -> tuple[str, Entry] | None:
    """One past entry worth showing again, with a label like "2 years ago today".

    Prefers the longest look-back: the same calendar day in an earlier year (oldest first), then
    a month ago, then a week ago — so a young journal still has something to show.
    """
    yearly = [e for e in on_this_day(today) if e.created.year < today.year]
    if yearly:
        oldest = min(yearly, key=lambda e: e.created)
        years = today.year - oldest.created.year
        return (f"{years} year{'s' if years != 1 else ''} ago today", oldest)
    for label, day in (
        ("a month ago today", _months_ago(today, 1)),
        ("a week ago today", today - timedelta(days=7)),
    ):
        found = list_entries(on=day)
        if found:
            return (label, min(found, key=lambda e: e.created))
    return None


def search(
    query: str | None = None,
    *,
    regex: bool = False,
    tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    untagged: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    on: date | None = None,
) -> list[tuple[Entry, list[str]]]:
    import re as _re

    if regex:
        if not query:
            raise ValueError("regex search requires a query")
        matcher = _re.compile(query, _re.IGNORECASE).search
    elif query:
        needle = query.lower()
        matcher = lambda line: needle in line.lower()  # noqa: E731
    else:
        # No text query: caller is filtering by tag/since/until/on alone, so every line "matches".
        matcher = lambda line: True  # noqa: E731

    results = []
    for entry in list_entries(
        since=since, until=until, on=on, tags=tags, exclude_tags=exclude_tags, untagged=untagged
    ):
        matches = [line for line in entry.body.splitlines() if matcher(line)]
        if matches:
            results.append((entry, matches))
    return results


def tag_counts(since: datetime | None = None, until: datetime | None = None) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for entry in list_entries(since=since, until=until):
        counter.update(extract_tags(entry.body))
    return dict(counter)


def add_tags(entry_id: str, new_tags: list[str]) -> Entry:
    entry = get(entry_id)
    existing = set(extract_tags(entry.body))
    to_add = [normalize_tag(t) for t in new_tags]

    missing: list[str] = []
    for tag in to_add:
        if tag not in existing and tag not in missing:
            missing.append(tag)

    if missing:
        body = entry.body
        if body and not body.endswith("\n"):
            body += "\n"
        body += " ".join(f"#{t}" for t in missing) + "\n"
        entry.body = body
        entry.updated = datetime.now().astimezone()
        _save(entry, "tag")
    return entry
