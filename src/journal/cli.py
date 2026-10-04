"""journal — a date/time-based personal journal.

Examples:
  journal new --text "Had a good day #gratitude"
  journal add had coffee with Sam -t friends   # one-line capture; -t because shells eat '#'
  journal write --prompt hard                 # opt-in prompt below the page: today (default), hard, distance
  journal new --editor                        # compose in $EDITOR instead
  echo "typed from a script" | journal new --source cli
  journal list --since 2026-09-01 --tag work
  journal list --since yesterday              # natural language works too; ISO is preferred
  journal read                                # the last 7 days, as prose, oldest first
  journal read --since 2026-09-01 --tag work  # any range or filter; pages through $PAGER
  journal show last                           # also: today, or any unique prefix like 2026-09-30
  journal edit                                # pick an entry with fzf (or edit the last one)
  journal show 2026-09-30T164608
  journal search "coffee" --tag morning
  journal search --tag work                  # tag filter alone, no text query
  journal list --on 2026-09-30
  journal list --untagged
  journal review                              # read your week, then write a #review entry about it
  journal status                              # last entry, entries this week; also --json
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

Settings and docs (both explain themselves; `journal docs --all` prints everything):
  journal config list                         # every setting: value, default, source
  journal config set history.enabled false    # change one (validated); `config explain` says what each does
  journal prompts list                        # the writing prompt sets and what each is for
  journal docs                                # the built-in guide; `docs --list` for topics
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from . import configcmd, docs, ingest, prompts, render, setup, store, transcribe
from .config import load_config
from .dates import (
    parse_date as _parse_date,
    parse_datetime as _parse_when,
    parse_range_end as _parse_until,
    parse_range_start as _parse_since,
)
from .entry import Entry
from .tags import extract_tags, normalize_tag


_PROMPT_HELP = (
    "show a writing prompt below the page (removed on save); sets: today (default), hard, "
    "distance, review, or your own under [prompts] in config"
)


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


def _compose_in_editor(prompt: str | None = None) -> tuple[str, Path] | None:
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
        path.write_text(prompts.draft_text(prompt) if prompt else "")
    subprocess.call(_editor_command() + [str(path)])
    body = prompts.strip_scissors(path.read_text())
    if not body.strip():
        path.unlink(missing_ok=True)
        return None
    return body, path


def _interactive() -> bool:
    return sys.stdout.isatty()


def _print_resurfaced(entry: Entry) -> None:
    """After saving, show one older entry — rereading is where a journal pays off."""
    if not load_config().resurface.enabled:
        return
    found = store.resurface(entry.created.date())
    if found:
        label, old = found
        print(f"{label}: {_preview(old, 70)}   (journal show {old.id})")


def cmd_new(args: argparse.Namespace) -> int:
    # Parse --at first: a bad date must fail before the user has typed a word.
    created = _parse_when(args.at) if args.at else _now()
    prompt = None
    if args.prompt:
        if not args.editor:
            print("journal: --prompt only applies when composing in the editor", file=sys.stderr)
            return 1
        prompt = prompts.pick(args.prompt, _now().date(), load_config().prompts)
    draft = None
    if args.editor:
        composed = _compose_in_editor(prompt)
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
    if getattr(args, "ensure_tags", None):
        body = _with_tags(body, args.ensure_tags)
    entry = store.create(created=created, body=body, source=args.source, title=args.title or "")
    if draft is not None:
        draft.unlink(missing_ok=True)
    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    else:
        print(f"created {entry.id}")
        if _interactive():
            _print_resurfaced(entry)
    return 0


def _with_tags(body: str, tags: list[str]) -> str:
    """Append a final #tag line for any of `tags` the body doesn't already carry."""
    present = set(extract_tags(body))
    missing: list[str] = []
    for tag in (normalize_tag(t) for t in tags):
        if tag not in present and tag not in missing:
            missing.append(tag)
    if not missing:
        return body
    return body.rstrip("\n") + "\n" + " ".join(f"#{t}" for t in missing) + "\n"


def cmd_add(args: argparse.Namespace) -> int:
    if args.words:
        body = " ".join(args.words)
    else:
        if sys.stdin.isatty():
            print("(type your entry, then Ctrl-D to save, or Ctrl-C to abort)", file=sys.stderr)
        body = sys.stdin.read()
    if not body.strip():
        print("journal: nothing to add (give some words, or pipe text in)", file=sys.stderr)
        return 1
    body = _with_tags(body, args.tag or [])
    return cmd_new(
        argparse.Namespace(
            at=args.at, title="", source="cli", text=body, editor=False, prompt=None, json=args.json
        )
    )


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


def _pick_entry() -> str | None:
    """Choose an entry with fzf, if it's installed and we're on a terminal; else None."""
    if not (sys.stdin.isatty() and sys.stdout.isatty() and shutil.which("fzf")):
        return None
    lines = [f"{e.id}  [{e.source}]  {_preview(e, 70)}" for e in store.list_entries()]
    if not lines:
        return None
    picked = subprocess.run(
        ["fzf", "--preview", "journal show --no-pager {1}", "--preview-window", "right,60%,wrap"],
        input="\n".join(lines),
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.split()
    return picked[0] if picked else ""


def _resolve_args(args: argparse.Namespace, *, may_pick: bool = False) -> int | None:
    """Replace args.id (an id, `last`, `today`, a unique prefix, or None) with the real id.

    Returns None on success, or the exit code to return after printing the problem.
    """
    ref = args.id
    if ref is None:
        picked = _pick_entry() if may_pick else None
        if picked == "":
            return 1  # fzf cancelled
        ref = picked or "last"
        if picked is None:
            print("journal: no id given, using the last entry", file=sys.stderr)
    try:
        args.id = store.resolve(ref)
    except store.AmbiguousEntryError as exc:
        print(f"journal: {ref!r} matches {len(exc.candidates)} entries:", file=sys.stderr)
        for candidate in exc.candidates[:10]:
            print(f"  {candidate}", file=sys.stderr)
        return 1
    except store.EntryNotFoundError:
        print(f"journal: no entry {ref!r}", file=sys.stderr)
        return 2
    return None


def cmd_show(args: argparse.Namespace) -> int:
    if (code := _resolve_args(args, may_pick=True)) is not None:
        return code
    try:
        entry = store.get(args.id)
    except store.EntryNotFoundError:
        print(f"journal: no entry {args.id!r}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(_entry_to_dict(entry), indent=2))
    elif args.raw:
        print(entry.to_markdown())
    else:
        _output(render.render_entry(entry, show_id=True), no_pager=args.no_pager)
    return 0


def _output(text: str, *, no_pager: bool = False) -> None:
    """Print `text`, through $PAGER (else `less -R`) when stdout is a terminal. Falls back to a
    plain print when there's no pager available, so this works on any OS.
    """
    if no_pager or not sys.stdout.isatty():
        print(text, end="" if text.endswith("\n") else "\n")
        return
    pager = shlex.split(os.environ["PAGER"]) if os.environ.get("PAGER") else None
    if pager is None and shutil.which("less"):
        pager = ["less", "-R"]
    if pager is None:
        print(text, end="" if text.endswith("\n") else "\n")
        return
    try:
        subprocess.run(pager, input=text, text=True)
    except OSError:
        print(text, end="" if text.endswith("\n") else "\n")


def cmd_read(args: argparse.Namespace) -> int:
    has_range = args.since or args.until or args.on
    since = _parse_since(args.since) if args.since else None
    if since is None and not has_range:
        since = _parse_since((_now() - timedelta(days=6)).date().isoformat())
    entries = store.list_entries(
        since=since,
        until=_parse_until(args.until) if args.until else None,
        on=_parse_date(args.on) if args.on else None,
        tags=[normalize_tag(t) for t in args.tag] if args.tag else None,
        exclude_tags=[normalize_tag(t) for t in args.exclude_tag] if args.exclude_tag else None,
        source=args.source,
    )
    if not entries:
        print("nothing written in that period")
        return 0
    entries.reverse()  # list_entries is newest-first; reading order is oldest-first
    _output(render.render_entries(entries, show_id=args.ids), no_pager=args.no_pager)
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


def _status(now: datetime) -> dict:
    today = now.date()
    entries = store.list_entries()  # newest first
    last = entries[0] if entries else None
    week_start = today - timedelta(days=6)
    return {
        "last_entry_id": last.id if last else None,
        "last_entry_at": last.created.isoformat() if last else None,
        "days_since": (today - last.created.date()).days if last else None,
        "week_count": sum(1 for e in entries if e.created.date() >= week_start),
        "on_this_day_count": sum(
            1
            for e in entries
            if (e.created.month, e.created.day) == (today.month, today.day) and e.created.year < today.year
        ),
    }


def cmd_status(args: argparse.Namespace) -> int:
    status = _status(_now())
    if args.json:
        print(json.dumps(status, indent=2))
        return 0
    if status["last_entry_id"] is None:
        print("no entries yet")
        return 0
    days = status["days_since"]
    when = "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
    last = datetime.fromisoformat(status["last_entry_at"])
    n = status["week_count"]
    print(f"last entry: {when} ({last:%a %b} {last.day})")
    print(f"this week: {n} {'entry' if n == 1 else 'entries'}")
    if status["on_this_day_count"]:
        print(f"on this day: {status['on_this_day_count']} from past years")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    today = _now().date()
    custom = bool(args.since or args.until)
    since = _parse_since(args.since) if args.since else _parse_since((today - timedelta(days=6)).isoformat())
    until = _parse_until(args.until) if args.until else None
    if not args.no_read:
        # Past reviews are left out so a review reads the days themselves, not earlier summaries.
        entries = store.list_entries(since=since, until=until, exclude_tags=["review"])
        if entries:
            entries.reverse()
            _output(render.render_entries(entries, show_id=False), no_pager=args.no_pager)
        else:
            print("nothing written in that period", file=sys.stderr)
    first = since.date()
    last = until.date() if until else today
    span = f"{first:%b} {first.day} – {last:%b} {last.day}"
    return cmd_new(
        argparse.Namespace(
            at=None,
            title=f"{'Review of' if custom else 'Week of'} {span}",
            source="cli",
            text=None,
            editor=True,
            prompt="review",
            ensure_tags=["review"],
            json=False,
        )
    )


def cmd_setup(args: argparse.Namespace) -> int:
    if args.check:
        report = setup.environment_report()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(setup.render_report(report))
        return 0
    if args.json:
        print("journal: --json goes with --check", file=sys.stderr)
        return 1
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "journal: setup is interactive and needs a terminal. For scripts and agents: "
            "`journal setup --check --json` reports the environment and `journal config set` "
            "changes settings.",
            file=sys.stderr,
        )
        return 1
    return setup.run_wizard(start_entry=lambda: cmd_write(argparse.Namespace()))


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
    if (code := _resolve_args(args)) is not None:
        return code
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
    if (code := _resolve_args(args)) is not None:
        return code
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
    if (code := _resolve_args(args, may_pick=True)) is not None:
        return code
    try:
        entry = store.get(args.id)
    except store.EntryNotFoundError:
        print(f"journal: no entry {args.id!r}", file=sys.stderr)
        return 2

    # The editor only ever sees the body, never the frontmatter, so an edit can't corrupt it.
    fd, tmp_name = tempfile.mkstemp(suffix=".txt", prefix="journal-edit-")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(entry.body)
        subprocess.call(_editor_command() + [str(tmp_path)])
        after = tmp_path.read_text()
    finally:
        tmp_path.unlink(missing_ok=True)

    if after == entry.body:
        print(f"edited {args.id} (no changes)")
        return 0
    if not after.strip():
        print(f"journal: entry left empty, so it was not changed (use `journal delete {args.id}`)", file=sys.stderr)
        return 1

    store.update_body(args.id, after, _now())
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
    prompt = getattr(args, "prompt", None)
    return main(["new", "--editor"] + (["--prompt", prompt] if prompt else []))


# Help for flags that appear on many commands, applied to any flag defined without its own help
# text, so `--help` and the generated `journal docs commands` never show a bare flag.
_DEFAULT_FLAG_HELP = {
    "json": "print machine-readable JSON (stable shape; see `journal docs json`)",
    "since": "only entries on or after this ISO date or timestamp (a bare date means the start of that day)",
    "until": "only entries on or before this ISO date or timestamp (a bare date includes that whole day)",
    "title": "optional title, shown in listings and when reading",
    "source": "only/for this source: cli (typed), memo (voice memo), text (imported)",
    "limit": "show at most this many entries",
    "tag": "repeatable; entry must have all given tags",
    "regex": "treat the query as a regular expression",
    "no_pager": "print directly instead of through $PAGER",
}


def _fill_flag_help(parser: argparse.ArgumentParser) -> None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                _fill_flag_help(child)
        elif action.help is None and action.dest in _DEFAULT_FLAG_HELP:
            action.help = _DEFAULT_FLAG_HELP[action.dest]


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
    p_new.add_argument(
        "--prompt",
        nargs="?",
        const="today",
        metavar="SET",
        help=_PROMPT_HELP,
    )
    p_new.add_argument("--json", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_add = sub.add_parser(
        "add",
        help="one-line capture: journal add had coffee with Sam -t friends",
        description=(
            "Create an entry from the words on the command line. Tag with -t, or quote the text: "
            "in most shells an unquoted #tag starts a comment and is silently dropped."
        ),
    )
    p_add.add_argument("words", nargs="*", help="the entry text; reads stdin if omitted")
    p_add.add_argument("-t", "--tag", action="append", help="repeatable; appended as a #tag line")
    p_add.add_argument("--at", metavar="ISO", help="timestamp; default now")
    p_add.add_argument("--json", action="store_true")
    p_add.set_defaults(func=cmd_add)

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

    p_read = sub.add_parser(
        "read", help="read entries as prose, oldest first (default: the last 7 days)"
    )
    p_read.add_argument("--since", metavar="ISO")
    p_read.add_argument("--until", metavar="ISO")
    p_read.add_argument("--on", metavar="YYYY-MM-DD", help="entries created on this exact date")
    p_read.add_argument("--tag", action="append", help="repeatable; entry must have all given tags")
    p_read.add_argument("--exclude-tag", action="append", help="repeatable; entry must have none of these tags")
    p_read.add_argument("--source", choices=["cli", "memo", "text"])
    p_read.add_argument("--ids", action="store_true", help="show each entry's id (for edit/tag/delete)")
    p_read.add_argument("--no-pager", action="store_true")
    p_read.set_defaults(func=cmd_read)

    p_show = sub.add_parser(
        "show",
        help="print one entry (id, `last`, `today`, or a unique prefix)",
        description=(
            "Print one entry as prose. The id can be a full id, `last`, `today`, or a unique "
            "prefix like 2026-09-30; leave it off to pick with fzf (or fall back to the last "
            "entry). --raw prints the file as stored, frontmatter included; --json is the "
            "stable, scriptable form."
        ),
    )
    p_show.add_argument("id", nargs="?", help="id, `last`, `today`, or a unique prefix; omit to pick with fzf")
    p_show.add_argument("--json", action="store_true")
    p_show.add_argument("--raw", action="store_true", help="print the file as stored, frontmatter included")
    p_show.add_argument("--no-pager", action="store_true")
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

    p_status = sub.add_parser(
        "status",
        help="when you last wrote, and how this week is going (for prompts, status bars, schedulers)",
        description=(
            "Print when you last wrote and how many entries this week. --json gives "
            "{last_entry_id, last_entry_at, days_since, week_count, on_this_day_count} "
            "(nulls/zeros for an empty journal) — cheap enough to call from a shell prompt, "
            "status bar or scheduled reminder."
        ),
    )
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_review = sub.add_parser(
        "review",
        help="look back over a stretch of entries, then write a reflection (default: the last 7 days)",
        description=(
            "Show the period (your entries, oldest first, past #review entries left out), then "
            "open $EDITOR with reflection questions below the page. Saved as an entry titled "
            "\"Week of …\" (or \"Review of …\" for a custom range) and tagged #review."
        ),
    )
    p_review.add_argument("--since", metavar="ISO")
    p_review.add_argument("--until", metavar="ISO")
    p_review.add_argument("--no-read", action="store_true", help="skip showing the period first")
    p_review.add_argument("--no-pager", action="store_true")
    p_review.set_defaults(func=cmd_review)

    p_config = sub.add_parser(
        "config",
        help="see, explain and change settings (list, get, set, unset, explain, path)",
        description="Inspect and change the config file safely. `journal docs config` documents every setting.",
    )
    config_sub = p_config.add_subparsers(dest="config_command", required=True)

    p_cfg_list = config_sub.add_parser("list", help="every setting with its value, default and source")
    p_cfg_list.add_argument("--json", action="store_true")
    p_cfg_list.set_defaults(func=configcmd.cmd_config_list)

    p_cfg_get = config_sub.add_parser("get", help="print one setting's value")
    p_cfg_get.add_argument("key", help="e.g. history.enabled")
    p_cfg_get.add_argument("--json", action="store_true")
    p_cfg_get.set_defaults(func=configcmd.cmd_config_get)

    p_cfg_set = config_sub.add_parser(
        "set",
        help="change a setting (validated)",
        description=(
            "Set a setting. Booleans take true/false; transcribe.model must be a known model; "
            "prompts.<name> takes one or more prompts, e.g. "
            "`journal config set prompts.gratitude \"What am I grateful for?\" \"Who helped me?\"`. "
            "The file is rewritten; hand-written comments are saved to config.toml.bak first."
        ),
    )
    p_cfg_set.add_argument("key", help="e.g. history.enabled")
    p_cfg_set.add_argument("values", nargs="+", help="the new value (several for prompts.<name>)")
    p_cfg_set.add_argument("--json", action="store_true")
    p_cfg_set.set_defaults(func=configcmd.cmd_config_set)

    p_cfg_unset = config_sub.add_parser("unset", help="remove a setting, going back to its default")
    p_cfg_unset.add_argument("key")
    p_cfg_unset.set_defaults(func=configcmd.cmd_config_unset)

    p_cfg_explain = config_sub.add_parser("explain", help="say what a setting does (all of them if no key)")
    p_cfg_explain.add_argument("key", nargs="?")
    p_cfg_explain.add_argument("--json", action="store_true")
    p_cfg_explain.set_defaults(func=configcmd.cmd_config_explain)

    p_cfg_path = config_sub.add_parser("path", help="print the config file's location")
    p_cfg_path.set_defaults(func=configcmd.cmd_config_path)

    p_prompts = sub.add_parser("prompts", help="list and show writing prompt sets (today, hard, distance, …)")
    prompts_sub = p_prompts.add_subparsers(dest="prompts_command", required=True)
    p_pr_list = prompts_sub.add_parser("list", help="every prompt set, where it comes from, and what it is for")
    p_pr_list.add_argument("--json", action="store_true")
    p_pr_list.set_defaults(func=configcmd.cmd_prompts_list)
    p_pr_show = prompts_sub.add_parser("show", help="print one set's prompts")
    p_pr_show.add_argument("name")
    p_pr_show.add_argument("--json", action="store_true")
    p_pr_show.set_defaults(func=configcmd.cmd_prompts_show)

    p_docs = sub.add_parser(
        "docs",
        help="the built-in guide: concepts, commands, config, prompts, JSON, agent notes",
        description="Print the built-in documentation as markdown. No topic prints the overview.",
    )
    p_docs.add_argument("topic", nargs="?", help="see --list")
    p_docs.add_argument("--list", action="store_true", help="list the topics")
    p_docs.add_argument("--all", action="store_true", help="print every topic")
    p_docs.add_argument("--json", action="store_true")
    p_docs.set_defaults(func=docs.cmd_docs)

    p_setup = sub.add_parser(
        "setup",
        help="a short guided setup, or --check to see what this machine has",
        description=(
            "Walk through the few choices that matter (journal folder, history, resurfacing, "
            "voice memos). Safe to re-run: nothing is saved until you confirm. --check reports "
            "which tools are available and what each enables, without asking anything."
        ),
    )
    p_setup.add_argument("--check", action="store_true", help="report the environment only; ask nothing")
    p_setup.add_argument("--json", action="store_true", help="with --check: machine-readable report")
    p_setup.set_defaults(func=cmd_setup)

    p_tags = sub.add_parser("tags", help="tag counts across entries")
    p_tags.add_argument("--since", metavar="ISO")
    p_tags.add_argument("--until", metavar="ISO")
    p_tags.add_argument("--json", action="store_true")
    p_tags.set_defaults(func=cmd_tags)

    p_tag = sub.add_parser("tag", help="append missing #tags to an entry's body")
    p_tag.add_argument("id", help="id, `last`, `today`, or a unique prefix")
    p_tag.add_argument("tags", nargs="+")
    p_tag.add_argument("--json", action="store_true")
    p_tag.set_defaults(func=cmd_tag)

    p_delete = sub.add_parser("delete", help="move an entry to .trash under the data dir (not permanent)")
    p_delete.add_argument("id", help="id, `today`, `last`, or a unique prefix")
    p_delete.add_argument("--json", action="store_true")
    p_delete.set_defaults(func=cmd_delete)

    p_edit = sub.add_parser(
        "edit",
        help="edit an entry's text in $EDITOR (falls back to nvim, vim, then vi)",
        description=(
            "Open an entry's body in $EDITOR. The editor never sees the frontmatter, so an edit "
            "can't corrupt it, and `updated` is stamped only if the text actually changed. "
            "Emptying the body is refused (use `journal delete`). The id can be a full id, "
            "`last`, `today`, or a unique prefix; leave it off to pick with fzf (or fall back "
            "to the last entry)."
        ),
    )
    p_edit.add_argument("id", nargs="?", help="id, `last`, `today`, or a unique prefix; omit to pick with fzf")
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
    p_write.add_argument(
        "--prompt",
        nargs="?",
        const="today",
        metavar="SET",
        help=_PROMPT_HELP,
    )
    p_write.set_defaults(func=cmd_write)

    _fill_flag_help(parser)
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
