"""File-backed storage for journal entries under JOURNAL_DIR (default ~/.local/share/journal).

Tags are never indexed: every read scans the body with tags.extract_tags. At journal scale a
full directory scan on every command is fast enough, and there is no index to keep in sync.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from pathlib import Path

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


def _entry_path(entry_id: str) -> Path:
    year, month = entry_id[:4], entry_id[5:7]
    return entries_root() / year / month / f"{entry_id}.md"


def _find_path(entry_id: str) -> Path | None:
    path = _entry_path(entry_id)
    if path.exists():
        return path
    # Fallback scan, in case an id ever doesn't encode its own year/month (e.g. imported data).
    root = entries_root()
    if root.exists():
        for candidate in root.rglob(f"{entry_id}.md"):
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
    for path in sorted(root.rglob("*.md")):
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
    return entry


def get(entry_id: str) -> Entry:
    path = _find_path(entry_id)
    if path is None:
        raise EntryNotFoundError(entry_id)
    return Entry.from_markdown(entry_id, path.read_text())


def list_entries(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
    limit: int | None = None,
) -> list[Entry]:
    results = []
    for entry in iter_entries():
        if since and entry.created < since:
            continue
        if until and entry.created > until:
            continue
        if source and entry.source != source:
            continue
        if tags:
            entry_tags = set(extract_tags(entry.body))
            if not set(tags).issubset(entry_tags):
                continue
        results.append(entry)
    results.sort(key=lambda e: e.created, reverse=True)
    if limit:
        results = results[:limit]
    return results


def search(
    query: str,
    *,
    regex: bool = False,
    tags: list[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[tuple[Entry, list[str]]]:
    import re as _re

    if regex:
        matcher = _re.compile(query, _re.IGNORECASE).search
    else:
        needle = query.lower()
        matcher = lambda line: needle in line.lower()  # noqa: E731

    results = []
    for entry in list_entries(since=since, until=until, tags=tags):
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
        _entry_path(entry.id).write_text(entry.to_markdown())
    return entry
