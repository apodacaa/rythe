"""journal — a date/time-based personal journal.

The CLI is a plain data tool for Claude: create, list, show, search and tag entries. It never
calls Claude or any API itself.

Examples:
  journal new --text "Had a good day #gratitude"
  echo "typed from a script" | journal new --source cli
  journal list --since 2026-09-01 --tag work
  journal show 2026-09-30T164608
  journal search "coffee" --tag morning
  journal tags
  journal tag 2026-09-30T164608 gratitude focus
  journal path

With no subcommand, opens the TUI on a new entry (same as `journal write`).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from . import store
from .entry import Entry
from .tags import extract_tags, normalize_tag


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_when(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _entry_to_dict(entry: Entry) -> dict:
    return {
        "id": entry.id,
        "created": entry.created.isoformat(),
        "source": entry.source,
        "title": entry.title,
        "message_id": entry.message_id,
        "audio": entry.audio,
        "transcriber": entry.transcriber,
        "tags": extract_tags(entry.body),
        "body": entry.body,
    }


def cmd_new(args: argparse.Namespace) -> int:
    body = args.text if args.text is not None else sys.stdin.read()
    created = _parse_when(args.at) if args.at else _now()
    entry = store.create(created=created, body=body, source=args.source, title=args.title or "")
    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(f"created {entry.id}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = store.list_entries(
        since=_parse_when(args.since) if args.since else None,
        until=_parse_when(args.until) if args.until else None,
        tags=[normalize_tag(t) for t in args.tag] if args.tag else None,
        source=args.source,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps([_entry_to_dict(e) for e in entries], indent=2))
    else:
        for e in entries:
            title = f" {e.title}" if e.title else ""
            print(f"{e.id}  [{e.source}]{title}")
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


def cmd_search(args: argparse.Namespace) -> int:
    results = store.search(
        args.query,
        regex=args.regex,
        tags=[normalize_tag(t) for t in args.tag] if args.tag else None,
        since=_parse_when(args.since) if args.since else None,
        until=_parse_when(args.until) if args.until else None,
    )
    if args.json:
        payload = [
            {"id": e.id, "created": e.created.isoformat(), "matches": matches}
            for e, matches in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        for e, matches in results:
            print(f"{e.id}:")
            for line in matches:
                print(f"  {line}")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    counts = store.tag_counts(
        since=_parse_when(args.since) if args.since else None,
        until=_parse_when(args.until) if args.until else None,
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


def cmd_path(args: argparse.Namespace) -> int:
    print(store.data_dir())
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    try:
        from .tui.app import JournalApp
    except ModuleNotFoundError:
        print("journal: the TUI isn't built yet (milestone 2)", file=sys.stderr)
        return 1
    JournalApp().run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="journal",
        description="A date/time-based personal journal: a vim-modal TUI to write, a CLI for everything else.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="create an entry without the TUI")
    p_new.add_argument("--at", metavar="ISO", help="timestamp; default now")
    p_new.add_argument("--title", default="")
    p_new.add_argument("--source", default="cli", choices=["tui", "cli", "memo", "text"])
    p_new.add_argument("--text", help="entry body; reads stdin if omitted")
    p_new.add_argument("--json", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_list = sub.add_parser("list", help="list entries, newest first")
    p_list.add_argument("--since", metavar="ISO")
    p_list.add_argument("--until", metavar="ISO")
    p_list.add_argument("--tag", action="append", help="repeatable; entry must have all given tags")
    p_list.add_argument("--source", choices=["tui", "cli", "memo", "text"])
    p_list.add_argument("--limit", type=int)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print a full entry")
    p_show.add_argument("id")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_search = sub.add_parser("search", help="search entry bodies, line by line")
    p_search.add_argument("query")
    p_search.add_argument("--regex", action="store_true")
    p_search.add_argument("--tag", action="append")
    p_search.add_argument("--since", metavar="ISO")
    p_search.add_argument("--until", metavar="ISO")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

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

    p_path = sub.add_parser("path", help="print the data directory")
    p_path.set_defaults(func=cmd_path)

    p_write = sub.add_parser("write", help="open the TUI (default with no command)")
    p_write.set_defaults(func=cmd_write)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return cmd_write(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
