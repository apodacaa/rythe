"""`journal setup`: check what this machine has and (interactively) walk through the options.

The environment report is plain data so agents get the same picture a person does
(`journal setup --check --json`).
"""
from __future__ import annotations

import os
import shlex
import shutil

from . import store, transcribe
from .config import config_path, load_config


def _check(name: str, found: bool, detail: str, needed_for: str, hint: str) -> dict:
    return {"name": name, "found": found, "detail": detail, "needed_for": needed_for, "hint": hint}


def _tool(name: str, command: str, needed_for: str, hint: str) -> dict:
    path = shutil.which(command)
    return _check(name, path is not None, path or "", needed_for, hint)


def environment_report() -> dict:
    from .cli import _editor_command  # lazy: cli imports this module

    editor = _editor_command()
    editor_path = shutil.which(editor[0])

    pager_env = os.environ.get("PAGER")
    pager_cmd = shlex.split(pager_env)[0] if pager_env else "less"
    pager_path = shutil.which(pager_cmd)

    model = load_config().transcribe.model
    model_file = transcribe.model_path(model)

    checks = [
        _check(
            "editor",
            editor_path is not None,
            " ".join(editor) if editor_path else "",
            "writing entries (`journal`, `journal write`, `journal edit`)",
            "set $EDITOR (for example `export EDITOR=nano`) or install nvim or vim",
        ),
        _tool(
            "git",
            "git",
            "a local history of every write",
            "install git; without it everything still works, just without history",
        ),
        _tool(
            "fzf",
            "fzf",
            "the entry picker for `journal edit` and `journal show` with no id",
            "install fzf; without it those commands use the last entry",
        ),
        _check(
            "pager",
            pager_path is not None,
            pager_path or "",
            "paging long output from `read`, `show` and `review`",
            "install less or set $PAGER; without it output is printed directly",
        ),
        _tool(
            "ffmpeg",
            "ffmpeg",
            "voice memos (`journal ingest audio`)",
            "install ffmpeg with your package manager",
        ),
        _tool(
            "whisper-cli",
            "whisper-cli",
            "voice memos (`journal ingest audio`)",
            "install whisper.cpp (the package that provides `whisper-cli`)",
        ),
        _check(
            f"whisper model ({model})",
            model_file.exists(),
            str(model_file) if model_file.exists() else "",
            "voice memos (`journal ingest audio`)",
            f"run `journal model download {model}`",
        ),
    ]
    return {
        "checks": checks,
        "data_dir": str(store.data_dir()),
        "config_path": str(config_path()),
        "config_exists": config_path().exists(),
        "entries": store.count_entries(),
    }


def render_report(report: dict) -> str:
    lines = ["Your setup:"]
    width = max(len(c["name"]) for c in report["checks"])
    for c in report["checks"]:
        status = "ok     " if c["found"] else "missing"
        detail = c["detail"] if c["found"] else c["hint"]
        lines.append(f"  {status}  {c['name']:<{width}}  {detail}")
    lines.append("")
    lines.append(f"journal folder: {report['data_dir']} ({report['entries']} entries)")
    lines.append(
        f"settings file:  {report['config_path']}"
        + ("" if report["config_exists"] else " (not created yet; all defaults)")
    )
    return "\n".join(lines)
