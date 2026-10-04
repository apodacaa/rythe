"""Auto-commit history: the data dir is a local git repo, one commit per write.

This is a safety net against bad edits and deletes, not a sync mechanism — nothing is ever
pushed. It's best-effort: if git is missing or a command fails, the write that triggered it
has already succeeded, so we warn on stderr and carry on.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config

_GITIGNORE = "models/\ndrafts/\n.trash/\n"
# Identity and signing are passed per command so history doesn't depend on the user's global git
# config (which may be unset, or may require a signing key that isn't available here).
_GIT = ["git", "-c", "user.name=journal", "-c", "user.email=journal@localhost", "-c", "commit.gpgsign=false"]


def record(root: Path, message: str) -> None:
    if not load_config().history.enabled:
        return
    if shutil.which("git") is None:
        return
    try:
        root.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            _run(root, "init", "-q")
            (root / ".gitignore").write_text(_GITIGNORE)
        _run(root, "add", "-A")
        if _run(root, "status", "--porcelain").stdout.strip():
            _run(root, "commit", "-q", "-m", message)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or exc
        print(f"journal: history: {str(detail).strip()}", file=sys.stderr)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        _GIT + ["-C", str(root), *args], check=True, capture_output=True, text=True
    )
