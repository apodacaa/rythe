"""The registry of every config setting and environment variable the journal understands.

This is the single source of truth for `journal config`, for `journal docs config`, and for the
tests that fail when a setting exists in `config.py` but isn't described here. To add a setting:
add the field to `config.py`, add a `Setting` below, and the CLI and docs pick it up.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .transcribe import KNOWN_MODELS

PROMPT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


@dataclass(frozen=True)
class Setting:
    key: str  # dotted, e.g. "history.enabled"
    kind: str  # "bool" | "choice" | "text" | "path" | "list"
    default: object
    description: str
    example: str
    choices: tuple[str, ...] = ()
    default_text: str = ""  # how to show a default that isn't a plain value (e.g. a path)


SETTINGS: list[Setting] = [
    Setting(
        "storage.dir",
        "path",
        None,
        "The folder where entries (and audio, whisper models, drafts, trash and the git history) "
        "are stored. Absolute, or starting with ~. The $JOURNAL_DIR environment variable, if set, "
        "takes precedence. Changing it does not move existing entries: copy the old folder to the "
        "new location first (see `journal docs concepts`). `journal path` prints the folder in use.",
        "journal config set storage.dir ~/Documents/journal",
        default_text="~/.local/share/journal",
    ),
    Setting(
        "appearance.color",
        "choice",
        "auto",
        "Whether human-facing output uses color and bold. `auto` styles output only when it goes to "
        "a terminal (never when piped, with --json, or when the NO_COLOR environment variable is "
        "set); `always` forces styling (like FORCE_COLOR); `never` turns it off. Colors are your "
        "terminal's own 16-color palette, so they follow your terminal theme.",
        "journal config set appearance.color never",
        ("auto", "always", "never"),
    ),
    Setting(
        "history.enabled",
        "bool",
        True,
        "Commit every write (new, edit, tag, delete, ingest) to a local git repo inside the data "
        "directory, as a safety net against bad edits and deletes. Never pushed anywhere. Needs "
        "`git` on PATH; if it's missing, writes still succeed without history.",
        "journal config set history.enabled false",
    ),
    Setting(
        "resurface.enabled",
        "bool",
        True,
        "After you save a new entry in a terminal, show one older entry: the same day in an "
        "earlier year, else a month ago, else a week ago. Never shown with --json or when "
        "output is piped.",
        "journal config set resurface.enabled false",
    ),
    Setting(
        "transcribe.model",
        "choice",
        "small",
        "The whisper.cpp model used by `journal ingest audio`. Bigger models are more accurate "
        "and slower; `small` is a good CPU-only balance. Download one with "
        "`journal model download <name>`.",
        "journal config set transcribe.model medium",
        tuple(KNOWN_MODELS),
    ),
    Setting(
        "transcribe.language",
        "text",
        "en",
        "Language spoken in voice memos, as a two-letter code (en, de, es, …), or `auto` to let "
        "whisper detect it per memo.",
        "journal config set transcribe.language auto",
    ),
    Setting(
        "memo.subject_prefix",
        "text",
        "record-memo:",
        "Subject-line prefix that marks an email as a voice memo. Read by external tools that "
        "sweep a mailbox (such as the journal-sweep agent skill); the CLI itself never reads "
        "mail.",
        'journal config set memo.subject_prefix "voice:"',
    ),
]

# `prompts.<name>` is open-ended (any set name), so it's a pattern rather than a fixed entry.
PROMPTS_PATTERN = Setting(
    "prompts.<name>",
    "list",
    None,
    "A set of writing prompts for `journal write --prompt <name>`. Each value is one prompt; "
    "one is picked per day. A set named like a built-in (today, hard, distance, review) replaces "
    "it. See `journal prompts list`.",
    'journal config set prompts.gratitude "What am I grateful for today?" "Who helped me this week?"',
)

ENV_VARS: list[tuple[str, str]] = [
    (
        "JOURNAL_DIR",
        "Where entries live. Overrides the `storage.dir` setting (default ~/.local/share/journal). "
        "Only applies to programs started from a shell that exports it; to make the choice stick "
        "everywhere, use `journal config set storage.dir` instead. Tests always set this.",
    ),
    ("JOURNAL_CONFIG", "Path of the config file (default ~/.config/journal/config.toml)."),
    ("NO_COLOR", "If set to anything non-empty, turns styling off (see the `appearance.color` setting)."),
    ("FORCE_COLOR", "If set, forces styling on even when output isn't a terminal."),
    ("EDITOR", "Editor opened by write/new --editor/edit (falls back to nvim, vim, then vi)."),
    (
        "PAGER",
        "Pager for read/show/review/docs output on a terminal (falls back to `less`, else plain "
        "print). If you haven't set LESS, `less` is run with LESS=FRX: it quits at once when the "
        "text fits one screen and leaves it on screen afterwards. `--no-pager` skips it.",
    ),
]


def lookup(key: str) -> Setting | None:
    for setting in SETTINGS:
        if setting.key == key:
            return setting
    section, _, name = key.partition(".")
    if section == "prompts" and PROMPT_NAME_RE.fullmatch(name):
        return Setting(key, "list", None, PROMPTS_PATTERN.description, PROMPTS_PATTERN.example)
    return None


def suggestions(key: str) -> list[str]:
    import difflib

    return difflib.get_close_matches(key, [s.key for s in SETTINGS], n=3, cutoff=0.5)


def _dig(raw: dict, key: str):
    section, _, name = key.partition(".")
    table = raw.get(section, {})
    return (True, table[name]) if name in table else (False, None)


def current(raw: dict, setting: Setting) -> tuple[object, str]:
    """(effective value, source) where source is "config file" or "default"."""
    found, value = _dig(raw, setting.key)
    return (value, "config file") if found else (setting.default, "default")


def coerce(setting: Setting, values: list[str]):
    """Turn command-line words into a validated value of the setting's kind."""
    if setting.kind == "list":
        items = [v for v in values if v.strip()]
        if not items:
            raise ValueError(f"{setting.key} needs at least one non-empty prompt")
        return items
    if len(values) != 1:
        raise ValueError(f"{setting.key} takes exactly one value (quote it if it has spaces)")
    (value,) = values
    if setting.kind == "bool":
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
        raise ValueError(f"{setting.key} is true/false, not {value!r}")
    if setting.kind == "path" and not (value.startswith("~") or os.path.isabs(value)):
        raise ValueError(f"{setting.key} must be an absolute path, or start with ~ (got {value!r})")
    if setting.kind == "choice" and value not in setting.choices:
        raise ValueError(f"{setting.key} must be one of: {', '.join(setting.choices)}")
    if not value.strip():
        raise ValueError(f"{setting.key} can't be empty")
    return value


def set_in(raw: dict, key: str, value) -> None:
    section, _, name = key.partition(".")
    raw.setdefault(section, {})[name] = value


def unset_in(raw: dict, key: str) -> bool:
    section, _, name = key.partition(".")
    table = raw.get(section, {})
    if name not in table:
        return False
    del table[name]
    if not table:
        del raw[section]
    return True


def unknown_keys(raw: dict) -> list[str]:
    """Dotted keys present in the file that the journal doesn't know (typos, removed options)."""
    unknown = []
    for section, table in raw.items():
        if not isinstance(table, dict):
            unknown.append(section)
            continue
        for name in table:
            if lookup(f"{section}.{name}") is None:
                unknown.append(f"{section}.{name}")
    return unknown
