"""`journal config` and `journal prompts`: inspect and change settings, and explain them.

Everything here is driven by the registry in `settings.py` (and `prompts.py` for prompt sets), so
what these commands report can't drift from what the app actually reads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import prompts, settings, store, ui
from .config import config_path, load_raw, write_raw


def _fmt(value, setting: settings.Setting | None = None) -> str:
    if value is None and setting is not None and setting.default_text:
        return setting.default_text
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return "(none)" if value is None else str(value)


def _row(setting: settings.Setting, raw: dict) -> dict:
    value, source = settings.current(raw, setting)
    return {
        "key": setting.key,
        "kind": setting.kind,
        "value": value,
        "default": setting.default,
        "source": source,
        "choices": list(setting.choices),
        "description": setting.description,
        "example": setting.example,
    }


def _rows(raw: dict) -> list[dict]:
    rows = [_row(s, raw) for s in settings.SETTINGS]
    for name in raw.get("prompts", {}):
        setting = settings.lookup(f"prompts.{name}")
        if setting:
            rows.append(_row(setting, raw))
    return rows


def _unknown_key(key: str) -> int:
    print(f"journal: unknown setting {key!r}", file=sys.stderr)
    near = settings.suggestions(key)
    if near:
        print(f"  did you mean: {', '.join(near)}?", file=sys.stderr)
    print("  `journal config list` shows every setting.", file=sys.stderr)
    return 1


def cmd_config_path(args: argparse.Namespace) -> int:
    print(config_path())
    return 0


def cmd_config_list(args: argparse.Namespace) -> int:
    raw = load_raw()
    rows = _rows(raw)
    unknown = settings.unknown_keys(raw)
    if args.json:
        payload = {
            "path": str(config_path()),
            "exists": config_path().exists(),
            "settings": rows,
            "unknown_keys": unknown,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    path = config_path()
    print(
        f"{ui.style('config file:', 'bold')} {ui.style(str(path), 'cyan')}"
        + ("" if path.exists() else ui.style(" (not created yet; all defaults)", "dim"))
    )
    width = max(len(r["key"]) for r in rows)
    for r in rows:
        if r["source"] == "default":
            note = "(default)"
        elif r["kind"] == "list":
            note = "(config file)"
        else:
            note = f"(config file; default {_fmt(r['default'], settings.lookup(r['key']))})"
        value = _fmt(r["value"], settings.lookup(r["key"]))
        if r["kind"] == "list":
            value = f"{len(r['value'])} prompt{'s' if len(r['value']) != 1 else ''}"
        changed = r["source"] != "default"
        shown = ui.style(f"{value:<14}", "bold", "green") if changed else f"{value:<14}"
        key = r["key"]
        print(f"  {ui.style(f'{key:<{width}}', 'bold')}  {shown} {ui.style(note, 'dim')}")
    if unknown:
        print(ui.warn(f"unknown keys in the file (ignored): {', '.join(unknown)}"))
    print(ui.style("`journal config explain [key]` says what a setting does; `journal docs config` has it all.", "dim"))
    return 0


def cmd_config_get(args: argparse.Namespace) -> int:
    setting = settings.lookup(args.key)
    if setting is None:
        return _unknown_key(args.key)
    value, source = settings.current(load_raw(), setting)
    if args.json:
        print(json.dumps({"key": args.key, "value": value, "default": setting.default, "source": source}, indent=2))
    elif isinstance(value, list):
        print("\n".join(value))
    else:
        print(_fmt(value))
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    setting = settings.lookup(args.key)
    if setting is None:
        return _unknown_key(args.key)
    value = settings.coerce(setting, args.values)  # ValueError -> "journal: ..." exit 1 in main
    raw = load_raw()
    old_dir = store.data_dir() if args.key == "storage.dir" else None
    settings.set_in(raw, args.key, value)
    backup = write_raw(raw)
    if old_dir is not None:
        _storage_notes(old_dir)
    if args.json:
        print(json.dumps({"key": args.key, "value": value}, indent=2, ensure_ascii=False))
    else:
        print(f"set {args.key} = {_fmt(value)}")
    if backup:
        print(
            f"journal: your config had comments, which rewriting drops; the old file is saved as {backup}",
            file=sys.stderr,
        )
    return 0


def _storage_notes(old_dir) -> None:
    new_dir = store.data_dir()
    if os.environ.get("JOURNAL_DIR"):
        print(
            "journal: $JOURNAL_DIR is set and takes precedence, so it is still the folder in use; "
            "unset it for this setting to apply",
            file=sys.stderr,
        )
        return
    if new_dir != old_dir and old_dir.exists() and any(old_dir.iterdir()):
        print(
            f"journal: entries already in {old_dir} were not moved; copy that whole folder to "
            f"{new_dir} or they won't show up",
            file=sys.stderr,
        )


def cmd_config_unset(args: argparse.Namespace) -> int:
    setting = settings.lookup(args.key)
    raw = load_raw()
    stale = setting is None and args.key in settings.unknown_keys(raw)  # e.g. a removed option
    if setting is None and not stale:
        return _unknown_key(args.key)
    if not settings.unset_in(raw, args.key):
        print(f"{args.key} is already at its default")
        return 0
    backup = write_raw(raw)
    print(f"unset {args.key} " + ("(it was an unused setting)" if stale else "(back to the default)"))
    if backup:
        print(
            f"journal: your config had comments, which rewriting drops; the old file is saved as {backup}",
            file=sys.stderr,
        )
    return 0


def _explain_text(setting: settings.Setting, raw: dict) -> str:
    def label(name: str) -> str:
        return ui.style(f"  {name}:", "dim")

    lines = [ui.style(setting.key, "bold", "cyan"), f"  {setting.description}", f"{label('type')} {_kind_label(setting)}"]
    if setting.kind != "list":
        lines.append(f"{label('default')} {_fmt(setting.default, setting)}")
        value, source = settings.current(raw, setting)
        lines.append(f"{label('now')} {ui.style(_fmt(value, setting), 'bold')} {ui.style('(' + source + ')', 'dim')}")
    lines.append(f"{label('example')} {ui.style(setting.example, 'bold')}")
    return "\n".join(lines)


def _kind_label(setting: settings.Setting) -> str:
    if setting.kind == "bool":
        return "true or false"
    if setting.kind == "choice":
        return "one of " + ", ".join(setting.choices)
    if setting.kind == "list":
        return "one or more prompts (text)"
    if setting.kind == "path":
        return "a folder path (absolute, or starting with ~)"
    return "text"


def cmd_config_explain(args: argparse.Namespace) -> int:
    raw = load_raw()
    if args.key:
        setting = settings.lookup(args.key)
        if setting is None:
            return _unknown_key(args.key)
        targets = [setting]
    else:
        targets = settings.SETTINGS + [settings.PROMPTS_PATTERN]
    if args.json:
        print(json.dumps([_row(s, raw) if s.key != "prompts.<name>" else _pattern_row(s) for s in targets], indent=2, ensure_ascii=False))
        return 0
    print("\n\n".join(_explain_text(s, raw) for s in targets))
    return 0


def _pattern_row(setting: settings.Setting) -> dict:
    return {
        "key": setting.key,
        "kind": setting.kind,
        "value": None,
        "default": None,
        "source": "default",
        "choices": [],
        "description": setting.description,
        "example": setting.example,
    }


def _config_prompts() -> dict[str, list[str]]:
    from .config import load_config

    return load_config().prompts


def cmd_prompts_list(args: argparse.Namespace) -> int:
    extra = _config_prompts()
    sets = prompts.available(extra)
    rows = [
        {
            "name": name,
            "source": prompts.source_of(name, extra),
            "count": len(items),
            "description": prompts.DESCRIPTIONS.get(name, "Your own prompt set (from your config)."),
        }
        for name, items in sorted(sets.items())
    ]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        meta = f"[{r['source']}, {r['count']} prompt{'s' if r['count'] != 1 else ''}]"
        print(f"{ui.style(r['name'], 'bold', 'cyan')}  {ui.style(meta, 'dim')}")
        print(f"  {r['description']}")
    print(ui.style("Use one with `journal write --prompt <name>`; add your own with `journal config set prompts.<name> \"…\"`.", "dim"))
    return 0


def cmd_prompts_show(args: argparse.Namespace) -> int:
    extra = _config_prompts()
    sets = prompts.available(extra)
    if args.name not in sets:
        print(f"journal: no prompt set {args.name!r} (available: {', '.join(sorted(sets))})", file=sys.stderr)
        return 2
    row = {
        "name": args.name,
        "source": prompts.source_of(args.name, extra),
        "description": prompts.DESCRIPTIONS.get(args.name, "Your own prompt set (from your config)."),
        "prompts": sets[args.name],
    }
    if args.json:
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0
    print(f"{ui.style(row['name'], 'bold', 'cyan')}  {ui.style('[' + row['source'] + ']', 'dim')}\n{row['description']}\n")
    for i, text in enumerate(row["prompts"], 1):
        print(f"{ui.style(f'{i}.', 'bold', 'magenta')} {text}\n")
    return 0
