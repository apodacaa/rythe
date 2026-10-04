"""`journal docs`: the built-in guide, readable by people and agents with no repo access.

Four topics are static markdown shipped in the package (`journal/docs/*.md`). The other three are
generated from the real source of truth — the argparse parser (commands), the settings registry
(config) and the prompt sets (prompts) — so they can't go out of date.
"""
from __future__ import annotations

import argparse
import json
from importlib import resources

from . import prompts, settings
from .config import config_path


def _static(name: str):
    return lambda: resources.files("journal").joinpath("docs", f"{name}.md").read_text()


def _subparsers_action(parser: argparse.ArgumentParser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _option_lines(parser: argparse.ArgumentParser) -> list[str]:
    lines = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        if action.option_strings:
            names = ", ".join(action.option_strings)
            if action.metavar or (action.nargs != 0 and action.const is None and action.type is not bool
                                  and not isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction))):
                names += f" {action.metavar or action.dest.upper()}"
        else:
            names = action.metavar or action.dest
        text = action.help or ""
        if action.choices:
            text = f"{text} (one of: {', '.join(map(str, action.choices))})".strip()
        lines.append(f"- `{names}`" + (f": {text}" if text else ""))
    return lines


def _render_parser(parser: argparse.ArgumentParser, path: str, depth: int, blocks: list[str]) -> None:
    sub = _subparsers_action(parser)
    helps = {a.dest: a.help for a in sub._choices_actions} if sub else {}
    for name, child in (sub.choices.items() if sub else []):
        full = f"{path} {name}"
        block = [f"{'#' * depth} `{full}`", helps.get(name) or ""]
        if child.description:
            block.append(child.description)
        usage = child.format_usage().strip().removeprefix("usage:").strip()
        block.append("```\n" + " ".join(usage.split()) + "\n```")
        options = _option_lines(child)
        if options:
            block.append("\n".join(options))
        blocks.append("\n\n".join(b for b in block if b))
        _render_parser(child, full, depth + 1, blocks)


def render_commands() -> str:
    from .cli import build_parser

    parser = build_parser()
    blocks = [
        "# journal: commands\n\nGenerated from the CLI itself, so it is always current. Every "
        "command also has `--help`. `journal` with no command is the same as `journal write`."
    ]
    _render_parser(parser, "journal", 2, blocks)
    return "\n\n".join(blocks) + "\n"


def render_config() -> str:
    path = config_path()
    out = [
        "# journal: configuration",
        f"Settings live in a TOML file at `{path}` (override the location with `JOURNAL_CONFIG`). "
        "Every setting is optional; a missing file just means all defaults.",
        "## Inspect and change settings\n\n"
        "```\n"
        "journal config list [--json]        every setting: value, default, where it came from\n"
        "journal config get <key>            one value\n"
        "journal config set <key> <value>…   change a setting (validated)\n"
        "journal config unset <key>          back to the default\n"
        "journal config explain [key]        what a setting does, with an example\n"
        "journal config path                 where the file is\n"
        "```\n\n"
        "`set` and `unset` rewrite the file. If it had hand-written comments they are dropped, so "
        "the old file is first saved as `config.toml.bak` and you are told.",
        "## Settings",
    ]
    for s in settings.SETTINGS:
        kind = {"bool": "true or false", "choice": "one of " + ", ".join(s.choices), "text": "text"}[s.kind]
        out.append(
            f"### `{s.key}`\n\n{s.description}\n\n- type: {kind}\n- default: `{_default(s)}`\n- example: `{s.example}`"
        )
    p = settings.PROMPTS_PATTERN
    out.append(
        f"### `{p.key}`\n\n{p.description}\n\n- type: one or more prompts (text)\n- default: none\n- example: `{p.example}`"
    )
    env = "\n".join(f"- `{name}`: {text}" for name, text in settings.ENV_VARS)
    out.append("## Environment variables\n\n" + env)
    return "\n\n".join(out) + "\n"


def _default(s: settings.Setting) -> str:
    return "true" if s.default is True else "false" if s.default is False else str(s.default)


def render_prompts() -> str:
    out = [
        "# journal: writing prompts",
        "A prompt is a question shown below the page when you ask for it: "
        "`journal write --prompt [set]` (or `journal new --editor --prompt [set]`). It sits under a "
        "divider line, and everything from that line down is removed when you save, so only your "
        "writing is kept. Prompts are always opt-in; a bare `journal` is a blank page. One prompt "
        "is chosen per set per day, so reopening the editor the same day shows the same one.",
        "## Built-in sets",
    ]
    for name, items in prompts.BUILTIN.items():
        body = "\n\n".join(f"> " + text.replace("\n", "\n> ") for text in items)
        out.append(f"### `{name}`\n\n{prompts.DESCRIPTIONS[name]}\n\n{body}")
    out.append(
        "## Your own sets\n\n"
        "```\n"
        'journal config set prompts.gratitude "What am I grateful for today?" "Who helped me this week?"\n'
        "journal write --prompt gratitude\n"
        "```\n\n"
        "Each value is one prompt. A set named like a built-in replaces it. `journal prompts list` "
        "shows every set and where it comes from; `journal prompts show <set>` prints its prompts."
    )
    return "\n\n".join(out) + "\n"


TOPICS: dict[str, tuple[str, object]] = {
    "overview": ("what journal is and the ideas behind it", _static("overview")),
    "concepts": ("entries, ids, tags, dates, safety nets, rereading, the data layout", _static("concepts")),
    "commands": ("every command and flag (generated from the CLI)", render_commands),
    "config": ("every setting and environment variable, and how to change them", render_config),
    "prompts": ("the writing prompt sets and what each is for", render_prompts),
    "json": ("the stable --json shapes and exit codes", _static("json")),
    "agents": ("rules of thumb for agents driving the CLI", _static("agents")),
}


def render_topic(name: str) -> str:
    return TOPICS[name][1]()


def cmd_docs(args: argparse.Namespace) -> int:
    import sys

    if args.list:
        rows = [{"topic": name, "summary": summary} for name, (summary, _) in TOPICS.items()]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                print(f"{r['topic']:<10} {r['summary']}")
        return 0
    if args.all:
        names = list(TOPICS)
    elif args.topic:
        if args.topic not in TOPICS:
            print(f"journal: no docs topic {args.topic!r} (topics: {', '.join(TOPICS)})", file=sys.stderr)
            return 2
        names = [args.topic]
    else:
        names = ["overview"]
    text = "\n---\n\n".join(render_topic(n) for n in names)
    if args.json:
        print(json.dumps({"topics": names, "markdown": text}, indent=2, ensure_ascii=False))
        return 0
    print(text, end="" if text.endswith("\n") else "\n")
    if not args.topic and not args.all:
        print("\nTopics: " + ", ".join(TOPICS) + "  (journal docs <topic>, or --list, or --all)")
    return 0
