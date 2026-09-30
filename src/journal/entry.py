"""Entry: the on-disk representation of a single journal entry.

A flat frontmatter block (no YAML dependency needed) followed by the body. Only `title` is ever
quoted, since it's the one field that's free text; every other field is a controlled format
(ISO timestamp, an enum, a message id, a relative path) that never contains a ':'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
_FIELD_ORDER = ("created", "source", "title", "message_id", "audio", "transcriber")


def id_for(created: datetime) -> str:
    """The entry id: YYYY-MM-DDTHHMMSS in the entry's own local time (no colons, filename-safe)."""
    return created.strftime("%Y-%m-%dT%H%M%S")


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return value


@dataclass
class Entry:
    id: str
    created: datetime
    source: str = "cli"
    title: str = ""
    message_id: str | None = None
    audio: str | None = None
    transcriber: str | None = None
    body: str = ""

    def to_markdown(self) -> str:
        lines = ["---", f"created: {self.created.isoformat()}", f"source: {self.source}"]
        if self.title:
            lines.append(f"title: {_quote(self.title)}")
        if self.message_id:
            lines.append(f"message_id: {self.message_id}")
        if self.audio:
            lines.append(f"audio: {self.audio}")
        if self.transcriber:
            lines.append(f"transcriber: {self.transcriber}")
        lines.append("---")
        header = "\n".join(lines)
        body = self.body
        if body and not body.endswith("\n"):
            body += "\n"
        return f"{header}\n{body}"

    @classmethod
    def from_markdown(cls, entry_id: str, text: str) -> "Entry":
        match = _FRONTMATTER_RE.match(text)
        if not match:
            raise ValueError(f"entry {entry_id!r} has no frontmatter")
        header, body = match.group(1), match.group(2)

        fields: dict[str, str] = {}
        for line in header.splitlines():
            if not line.strip():
                continue
            key, _, value = line.partition(":")
            fields[key.strip()] = _unquote(value.strip())

        created_raw = fields.get("created")
        if not created_raw:
            raise ValueError(f"entry {entry_id!r} is missing 'created'")

        return cls(
            id=entry_id,
            created=datetime.fromisoformat(created_raw),
            source=fields.get("source", "cli"),
            title=fields.get("title", ""),
            message_id=fields.get("message_id") or None,
            audio=fields.get("audio") or None,
            transcriber=fields.get("transcriber") or None,
            body=body,
        )
