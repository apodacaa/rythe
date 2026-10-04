"""journal — a date/time-based personal journal.

Examples:
  journal new --text "Had a good day #gratitude"
  journal new --editor                        # compose in $EDITOR instead
  echo "typed from a script" | journal new --source cli
  journal list --since 2026-09-01 --tag work
  journal list --since yesterday              # natural language works too; ISO is preferred
  journal show 2026-09-30T164608
  journal search "coffee" --tag morning
  journal search --tag work                  # tag filter alone, no text query
  journal list --on 2026-09-30
  journal list --untagged
  journal on-this-day                        # entries from today's date in any past year
  journal on-this-day --date monday           # bare weekday names work; "last monday" doesn't
  journal tags
  journal tag 2026-09-30T164608 gratitude focus
  journal edit 2026-09-30T164608
  journal delete 2026-09-30T164608
  journal model download small
  journal ingest audio memo.m4a --message-id "<abc@mail>"
  journal ingest text transcript.txt --at 2026-09-30T16:46:08+02:00
  journal ingest seen "<abc@mail>"            # exit 0 if already ingested, else exit 1
  journal path

With no subcommand (or `journal write`), opens $EDITOR on a new entry — same as `journal new
--editor`.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import ingest, store, transcribe
from .dates import (
    parse_date as _parse_date,
    parse_datetime as _parse_when,
    parse_range_end as _parse_until,
    parse_range_start as _parse_since,
)
from .entry import Entry
from .tags import extract_tags, normalize_tag


def _now() -> datetime:
    return datetime.now().astimezone()


def _entry_to_dict(entry: Entry) -> dict:
    return {
        "id": entry.id,
        "created": entry.created.isoformat(),
        "updated": entry.updated.isoformat() if entry.updated else None,
        "source": entry.source,
        "title": entry.title,
        "message_id": entry.message_id,
        "audio": entry.audio,
        "transcriber": entry.transcriber,
        "tags": extract_tags(entry.body),
        "body": entry.body,
    }


def _preview(entry: Entry, length: int = 50) -> str:
    """Title if set, else the first `length` characters of the body with whitespace collapsed
    to single spaces — so plain-text listings show more than just a bare id and date.
    """
    if entry.title:
        return entry.title
    collapsed = " ".join(entry.body.split())
    if len(collapsed) > length:
        return collapsed[:length].rstrip() + "…"
    return collapsed


def _compose_in_editor() -> tuple[str, Path] | None:
    """Open $EDITOR on a draft kept under the data dir; returns (body, draft path), or None if
    the draft came back empty.

    The draft lives on disk until the caller has saved the entry and unlinked it, so a
    crash, a killed editor or a failed save never loses what was typed — the next write
    resumes it.
    """
    leftovers = store.list_drafts()
    if leftovers:
        path = leftovers[0]
        stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%a %b %-d, %-I:%M %p")
        print(f"journal: resuming an unsaved draft from {stamp}", file=sys.stderr)
    else:
        path = store.new_draft_path()
        path.touch()
    subprocess.call(_editor_command() + [str(path)])
    body = path.read_text()
    if not body.strip():
        path.unlink(missing_ok=True)
        return None
    return body, path


def cmd_new(args: argparse.Namespace) -> int:
    # Parse --at first: a bad date must fail before the user has typed a word.
    created = _parse_when(args.at) if args.at else _now()
    draft = None
    if args.editor:
        composed = _compose_in_editor()
        if composed is None:
            print("journal: no entry created (empty)", file=sys.stderr)
            return 1
        body, draft = composed
    elif args.text is None:
        if sys.stdin.isatty():
            print("(type your entry, then Ctrl-D to save, or Ctrl-C to abort)", file=sys.stderr)
        body = sys.stdin.read()
    else:
        body = args.text
    entry = store.create(created=created, body=body, source=args.source, title=args.title or "")
    if draft is not None:
        draft.unlink(missing_ok=True)
    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(f"created {entry.id}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = store.list_entries(
        since=_parse_since(args.since) if args.since else None,
        until=_parse_until(args.until) if args.until else None,
        on=_parse_date(args.on) if args.on else None,
        tags=[normalize_tag(t) for t in args.tag] if args.tag else None,
        exclude_tags=[normalize_tag(t) for t in args.exclude_tag] if args.exclude_tag else None,
        untagged=args.untagged,
        source=args.source,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps([_entry_to_dict(e) for e in entries], indent=2))
    else:
        for e in entries:
            preview = _preview(e)
            suffix = f"  {preview}" if preview else ""
            print(f"{e.id}  [{e.source}]{suffix}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        entry = store.get(args.id)
    except store.EntryNotFoundError:
        print(f"journal: no entry {args.id!r}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(entry.to_markdown())
    return 0


def cmd_on_this_day(args: argparse.Namespace) -> int:
    target = _parse_date(args.date) if args.date else _now().date()
    entries = store.on_this_day(
        target,
        tags=[normalize_tag(t) for t in args.tag] if args.tag else None,
        source=args.source,
    )
    if args.json:
        print(json.dumps([_entry_to_dict(e) for e in entries], indent=2))
        return 0

    if not entries:
        print(f"nothing written on {target:%B %-d} in past years")
        return 0

    last_year = None
    for e in entries:
        if e.created.year != last_year:
            print(f"{e.created.year}:")
            last_year = e.created.year
        preview = _preview(e)
        suffix = f"  {preview}" if preview else ""
        print(f"  {e.id}  [{e.source}]{suffix}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    if args.regex and not args.query:
        print("journal: --regex needs a query to match against", file=sys.stderr)
        return 1
    has_filter = args.tag or args.exclude_tag or args.untagged or args.since or args.until or args.on
    if not args.query and not has_filter:
        print(
            "journal: search needs a query, or at least one of "
            "--tag/--exclude-tag/--untagged/--since/--until/--on",
            file=sys.stderr,
        )
        return 1
    results = store.search(
        args.query,
        regex=args.regex,
        tags=[normalize_tag(t) for t in args.tag] if args.tag else None,
        exclude_tags=[normalize_tag(t) for t in args.exclude_tag] if args.exclude_tag else None,
        untagged=args.untagged,
        since=_parse_since(args.since) if args.since else None,
        until=_parse_until(args.until) if args.until else None,
        on=_parse_date(args.on) if args.on else None,
    )
    if args.json:
        payload = [
            {"id": e.id, "created": e.created.isoformat(), "matches": matches}
            for e, matches in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        for e, matches in results:
            preview = _preview(e)
            suffix = f"  {preview}" if preview else ""
            print(f"{e.id}{suffix}:")
            for line in matches:
                print(f"  {line}")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    counts = store.tag_counts(
        since=_parse_since(args.since) if args.since else None,
        until=_parse_until(args.until) if args.until else None,
    )
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if args.json:
        print(json.dumps(dict(ordered), indent=2))
    else:
        for tag, count in ordered:
            print(f"{count:>4}  #{tag}")
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    try:
        entry = store.add_tags(args.id, args.tags)
    except store.EntryNotFoundError:
        print(f"journal: no entry {args.id!r}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(f"tagged {entry.id}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    try:
        trashed = store.delete(args.id)
    except store.EntryNotFoundError:
        print(f"journal: no entry {args.id!r}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"id": args.id, "trashed_at": str(trashed)}, indent=2))
    else:
        print(f"deleted {args.id} (moved to {trashed}, not purged)")
    return 0


def _editor_command() -> list[str]:
    editor = os.environ.get("EDITOR")
    if editor:
        return shlex.split(editor)
    for candidate in ("nvim", "vim", "vi"):
        found = shutil.which(candidate)
        if found:
            return [found]
    return ["vi"]


def cmd_edit(args: argparse.Namespace) -> int:
    try:
        path = store.path_for(args.id)
    except store.EntryNotFoundError:
        print(f"journal: no entry {args.id!r}", file=sys.stderr)
        return 2

    before = path.read_text()
    subprocess.call(_editor_command() + [str(path)])
    after = path.read_text()

    if after == before:
        print(f"edited {args.id} (no changes)")
        return 0

    try:
        Entry.from_markdown(args.id, after)
    except ValueError as exc:
        print(f"journal: entry {args.id} may be corrupted after editing: {exc}", file=sys.stderr)
        return 1

    store.touch(args.id, _now())
    print(f"edited {args.id}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    print(store.data_dir())
    return 0


def cmd_ingest_audio(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"journal: no such file {args.file!r}", file=sys.stderr)
        return 2

    created = _parse_when(args.at) if args.at else _now()
    try:
        entry = ingest.ingest_audio(
            path,
            created=created,
            message_id=args.message_id,
            title=args.title or "",
            model=args.model,
            language=args.language,
            force=args.force,
        )
    except store.DuplicateMessageError as exc:
        print(f"journal: {exc}", file=sys.stderr)
        return 3
    except transcribe.TranscribeError as exc:
        print(f"journal: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(f"ingested {entry.id}")
    return 0


def cmd_ingest_text(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"journal: no such file {args.file!r}", file=sys.stderr)
        return 2

    created = _parse_when(args.at) if args.at else _now()
    try:
        entry = ingest.ingest_text(
            path, created=created, message_id=args.message_id, title=args.title or "", force=args.force
        )
    except store.DuplicateMessageError as exc:
        print(f"journal: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(f"ingested {entry.id}")
    return 0


def cmd_ingest_seen(args: argparse.Namespace) -> int:
    existing = store.find_by_message_id(args.message_id)
    if existing is not None:
        print(json.dumps({"seen": True, "id": existing.id}))
        return 0
    print(json.dumps({"seen": False}))
    return 1


def cmd_model_download(args: argparse.Namespace) -> int:
    def progress(downloaded: int, total: int) -> None:
        if total:
            pct = downloaded * 100 // total
            mb = downloaded // (1024 * 1024)
            total_mb = total // (1024 * 1024)
            print(f"\rdownloading {args.name}: {pct}% ({mb} / {total_mb} MB)", end="", file=sys.stderr)

    try:
        path = transcribe.download_model(args.name, force=args.force, progress=progress)
    except transcribe.TranscribeError as exc:
        print(f"\njournal: {exc}", file=sys.stderr)
        return 1

    print(file=sys.stderr)
    print(f"downloaded {args.name} -> {path}")
    return 0


def cmd_model_list(args: argparse.Namespace) -> int:
    models = transcribe.list_models()
    if args.json:
        print(json.dumps(models, indent=2))
    else:
        for m in models:
            mark = "x" if m["downloaded"] else " "
            print(f"[{mark}] {m['name']:8} {m['file']}")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    return main(["new", "--editor"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="journal",
        description="A date/time-based personal journal: $EDITOR to write, a CLI for everything else.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="create an entry: --text, stdin, or --editor")
    p_new.add_argument("--at", metavar="ISO", help="timestamp; default now")
    p_new.add_argument("--title", default="")
    p_new.add_argument("--source", default="cli", choices=["cli", "memo", "text"])
    p_new.add_argument("--text", help="entry body; reads stdin if omitted")
    p_new.add_argument(
        "-e", "--editor", action="store_true", help="compose in $EDITOR instead of --text/stdin"
    )
    p_new.add_argument("--json", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_list = sub.add_parser("list", help="list entries, newest first")
    p_list.add_argument("--since", metavar="ISO")
    p_list.add_argument("--until", metavar="ISO")
    p_list.add_argument("--on", metavar="YYYY-MM-DD", help="entries created on this exact date")
    p_list.add_argument("--tag", action="append", help="repeatable; entry must have all given tags")
    p_list.add_argument("--exclude-tag", action="append", help="repeatable; entry must have none of these tags")
    p_list.add_argument("--untagged", action="store_true", help="only entries with no #tags at all")
    p_list.add_argument("--source", choices=["cli", "memo", "text"])
    p_list.add_argument("--limit", type=int)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print a full entry")
    p_show.add_argument("id")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_search = sub.add_parser("search", help="search entry bodies, line by line")
    p_search.add_argument(
        "query", nargs="?", help="text to match; omit to filter by --tag/--since/--until/--on alone"
    )
    p_search.add_argument("--regex", action="store_true")
    p_search.add_argument("--tag", action="append")
    p_search.add_argument("--exclude-tag", action="append", help="repeatable; entry must have none of these tags")
    p_search.add_argument("--untagged", action="store_true", help="only entries with no #tags at all")
    p_search.add_argument("--since", metavar="ISO")
    p_search.add_argument("--until", metavar="ISO")
    p_search.add_argument("--on", metavar="YYYY-MM-DD", help="entries created on this exact date")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_otd = sub.add_parser(
        "on-this-day", help="entries from this month/day across every year (default: today)"
    )
    p_otd.add_argument("--date", metavar="YYYY-MM-DD", help="default: today")
    p_otd.add_argument("--tag", action="append")
    p_otd.add_argument("--source", choices=["cli", "memo", "text"])
    p_otd.add_argument("--json", action="store_true")
    p_otd.set_defaults(func=cmd_on_this_day)

    p_tags = sub.add_parser("tags", help="tag counts across entries")
    p_tags.add_argument("--since", metavar="ISO")
    p_tags.add_argument("--until", metavar="ISO")
    p_tags.add_argument("--json", action="store_true")
    p_tags.set_defaults(func=cmd_tags)

    p_tag = sub.add_parser("tag", help="append missing #tags to an entry's body")
    p_tag.add_argument("id")
    p_tag.add_argument("tags", nargs="+")
    p_tag.add_argument("--json", action="store_true")
    p_tag.set_defaults(func=cmd_tag)

    p_delete = sub.add_parser("delete", help="move an entry to .trash under the data dir (not permanent)")
    p_delete.add_argument("id")
    p_delete.add_argument("--json", action="store_true")
    p_delete.set_defaults(func=cmd_delete)

    p_edit = sub.add_parser("edit", help="open an entry in $EDITOR (falls back to nvim, vim, then vi)")
    p_edit.add_argument("id")
    p_edit.set_defaults(func=cmd_edit)

    p_path = sub.add_parser("path", help="print the data directory")
    p_path.set_defaults(func=cmd_path)

    p_ingest = sub.add_parser("ingest", help="pull external content (audio, text) into the journal")
    ingest_sub = p_ingest.add_subparsers(dest="ingest_command", required=True)

    p_ingest_audio = ingest_sub.add_parser("audio", help="transcribe an audio file and create an entry")
    p_ingest_audio.add_argument("file")
    p_ingest_audio.add_argument("--at", metavar="ISO", help="timestamp; default now")
    p_ingest_audio.add_argument("--message-id", help="for dedupe; see `journal ingest seen`")
    p_ingest_audio.add_argument("--title", default="")
    p_ingest_audio.add_argument("--model", choices=list(transcribe.KNOWN_MODELS), help="default: config, else small")
    p_ingest_audio.add_argument("--language", help="default: config, else en ('auto' to detect)")
    p_ingest_audio.add_argument("--force", action="store_true", help="ingest even if --message-id was already seen")
    p_ingest_audio.add_argument("--json", action="store_true")
    p_ingest_audio.set_defaults(func=cmd_ingest_audio)

    p_ingest_text = ingest_sub.add_parser("text", help="create an entry from a text/transcript file")
    p_ingest_text.add_argument("file")
    p_ingest_text.add_argument("--at", metavar="ISO", help="timestamp; default now")
    p_ingest_text.add_argument("--message-id", help="for dedupe; see `journal ingest seen`")
    p_ingest_text.add_argument("--title", default="")
    p_ingest_text.add_argument("--force", action="store_true", help="ingest even if --message-id was already seen")
    p_ingest_text.add_argument("--json", action="store_true")
    p_ingest_text.set_defaults(func=cmd_ingest_text)

    p_ingest_seen = ingest_sub.add_parser(
        "seen", help="check whether a message-id was already ingested (exit 0 if so, else 1)"
    )
    p_ingest_seen.add_argument("message_id")
    p_ingest_seen.set_defaults(func=cmd_ingest_seen)

    p_model = sub.add_parser("model", help="manage local whisper.cpp models")
    model_sub = p_model.add_subparsers(dest="model_command", required=True)

    p_model_download = model_sub.add_parser("download", help="download a whisper.cpp model")
    p_model_download.add_argument("name", nargs="?", default="small", choices=list(transcribe.KNOWN_MODELS))
    p_model_download.add_argument("--force", action="store_true", help="re-download even if already present")
    p_model_download.set_defaults(func=cmd_model_download)

    p_model_list = model_sub.add_parser("list", help="list known models and whether they're downloaded")
    p_model_list.add_argument("--json", action="store_true")
    p_model_list.set_defaults(func=cmd_model_list)

    p_write = sub.add_parser(
        "write", help="open $EDITOR on a new entry (default with no command); same as `journal new --editor`"
    )
    p_write.set_defaults(func=cmd_write)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command is None:
            return cmd_write(args)
        return args.func(args)
    except ValueError as exc:
        # Covers unparseable dates from .dates (bad ISO and bad natural language both land
        # here), plus any other plain input-validation failure a command didn't already handle.
        print(f"journal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
