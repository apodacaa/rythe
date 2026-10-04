"""`journal setup`: check what this machine has and (interactively) walk through the options.

The environment report is plain data so agents get the same picture a person does
(`journal setup --check --json`).
"""
from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path
from typing import Callable

from . import prompts, settings, store, transcribe
from .config import config_path, load_config, load_raw, write_raw
from .configcmd import _fmt

# The settings the wizard asks about; a test checks each one is in the settings registry.
WIZARD_KEYS = (
    "storage.dir",
    "history.enabled",
    "resurface.enabled",
    "transcribe.model",
    "transcribe.language",
)


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


class _Wizard:
    """One run of the wizard: gathers answers as pending changes, then saves once at the end."""

    def __init__(self, ask: Callable[[str], str], say: Callable[[str], None]):
        self.ask = ask
        self.say = say
        self.raw = load_raw()
        self.changes: dict[str, tuple[object, object]] = {}  # key -> (old, new)
        self.moved_from: Path | None = None
        self.download: str | None = None  # a whisper model to fetch after saving

    # -- small helpers --------------------------------------------------------------------
    def yes_no(self, question: str, default: bool) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self.ask(f"{question} {suffix} ").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.say("  Please answer y or n.")

    def current(self, key: str):
        return settings.current(self.raw, settings.lookup(key))[0]

    def propose(self, key: str, new) -> None:
        old = self.current(key)
        if new != old:
            self.changes[key] = (old, new)

    # -- steps ----------------------------------------------------------------------------
    def welcome(self, report: dict) -> None:
        self.say("Welcome to journal. A few quick questions; press Enter to accept the default.")
        self.say("Nothing is saved until the end, and you can run this again any time.\n")
        for c in report["checks"]:
            if not c["found"] and c["name"] in ("editor", "fzf", "pager"):
                label = "needed" if c["name"] == "editor" else "note"
                self.say(f"  {label}: {c['name']} not found. {c['hint']}")

    def folder(self) -> None:
        current = store.data_dir()
        count = store.count_entries()
        self.say("\nWhere should your journal live?")
        if os.environ.get("JOURNAL_DIR"):
            self.say(
                f"  It's {current}. The $JOURNAL_DIR environment variable is set and overrides the "
                "storage.dir setting, so there's nothing to choose here. Unset it to use the setting."
            )
            return
        self.say(
            "  Entries are plain text files in one folder, together with audio, drafts and a git "
            "history. A folder you already back up (a synced one, say) is a good home."
        )
        self.say(f"  Right now: {current}" + (f" ({count} entries)" if count else ""))
        if self.yes_no("Keep it here?", True):
            return
        setting = settings.lookup("storage.dir")
        while True:
            value = self.ask("Folder (absolute, or starting with ~; Enter to keep it): ").strip()
            if not value:
                return
            try:
                new = settings.coerce(setting, [value])
            except ValueError as exc:
                self.say(f"  {exc}")
                continue
            break
        if Path(new).expanduser() != current:
            self.propose("storage.dir", new)
            if count:
                self.moved_from = current

    def history(self) -> None:
        self.say("\nKeep a history of your writing?")
        if shutil.which("git") is None:
            self.say("  Every write can be saved to a local git history (never uploaded), but git isn't "
                     "installed, so that's off for now. Install git and re-run this to turn it on.")
            return
        self.say("  Every write (new, edit, delete…) is saved to a local git history inside the "
                 "journal folder, so a bad edit or delete can always be undone. It's never uploaded.")
        self.propose("history.enabled", self.yes_no("Keep a local history?", bool(self.current("history.enabled"))))

    def resurface(self) -> None:
        self.say("\nBring up the past?")
        self.say("  After you save an entry, journal can show one older one (the same day last year, "
                 "else a month or a week ago). Rereading is where a journal pays off.")
        self.propose(
            "resurface.enabled",
            self.yes_no("Show an older entry after I save one?", bool(self.current("resurface.enabled"))),
        )

    def voice_memos(self) -> None:
        self.say("\nVoice memos?")
        self.say("  journal can turn a recording into an entry, transcribing it on this computer with "
                 "whisper.cpp (no audio ever leaves it).")
        if not self.yes_no("Will you use voice memos?", False):
            return
        for name in ("ffmpeg", "whisper-cli"):
            if shutil.which(name) is None:
                hint = next(c["hint"] for c in environment_report()["checks"] if c["name"] == name)
                self.say(f"  note: {name} not found. {hint}.")
        self.say("  Pick a speech model. Bigger ones are more accurate but slower and larger to "
                 "download. All of them understand many languages and run entirely on this computer.")
        for name in transcribe.KNOWN_MODELS:
            tags = []
            if name == transcribe.RECOMMENDED_MODEL:
                tags.append("recommended")
            if self._model_file(name).exists():
                tags.append("downloaded")
            tag = f" [{', '.join(tags)}]" if tags else ""
            self.say(f"    {name:<7} {transcribe.format_size(name):<8} {transcribe.MODEL_NOTES[name]}{tag}")
        model_setting = settings.lookup("transcribe.model")
        default = self.current("transcribe.model")
        while True:
            answer = self.ask(f"Which model? [{default}] ").strip() or default
            try:
                model = settings.coerce(model_setting, [answer])
                break
            except ValueError as exc:
                self.say(f"  {exc}")
        self.propose("transcribe.model", model)

        default = self.current("transcribe.language")
        while True:
            answer = (self.ask(f"Language spoken in your memos (a code like en, de, es, or auto) [{default}] ")
                      .strip().lower() or default)
            if answer == "auto" or (answer.isalpha() and 2 <= len(answer) <= 3):
                break
            self.say("  Use a short language code such as en, de or es, or `auto` to detect it each time.")
        self.propose("transcribe.language", answer)

        if self._model_file(model).exists():
            self.say(f"  The {model} model is already downloaded.")
        elif self.yes_no(f"Download the {model} model now ({transcribe.format_size(model)})?", False):
            self.download = model
        else:
            self.say(f"  OK. Voice memos won't work until it's downloaded: `journal model download {model}`.")

    def _model_file(self, model: str) -> Path:
        """Where `model` will live: under the folder chosen in this run, if it changed."""
        folder = self.changes.get("storage.dir")
        base = Path(folder[1]).expanduser() if folder else store.data_dir()
        return base / "models" / transcribe.KNOWN_MODELS[model]

    def prompts_info(self) -> None:
        extra = load_config().prompts
        self.say("\nWriting prompts (always optional; a bare `journal` is a blank page):")
        for name in sorted(prompts.available(extra)):
            self.say(f"  {name:<9} {prompts.SUMMARIES.get(name, 'your own set')}")
        self.say("  Try one with `journal write --prompt hard`; `journal prompts list` says more.")

    def summary_and_save(self) -> bool:
        """Show the pending changes and save them if confirmed. Returns True if anything was saved."""
        if not self.changes:
            self.say("\nNothing to change; your settings stay as they are.")
            return False
        self.say("\nHere's what will change:")
        for key, (old, new) in self.changes.items():
            setting = settings.lookup(key)
            self.say(f"  {key}: {_fmt(old, setting)} -> {_fmt(new, setting)}")
        if not self.yes_no("Save these?", True):
            self.say("Nothing was saved.")
            return False
        for key, (_, new) in self.changes.items():
            settings.set_in(self.raw, key, new)
        backup = write_raw(self.raw)
        self.say(f"Saved to {config_path()}.")
        if backup:
            self.say(f"  (Your file had comments, which rewriting drops; the old one is at {backup}.)")
        if self.moved_from is not None:
            new_dir = store.data_dir()
            self.say(
                f"\nYour existing entries are still in {self.moved_from}. To bring them along, move "
                f"the whole folder (history included):\n    mv {self.moved_from} {new_dir}"
            )
        return True


def _download(model: str) -> None:
    import sys

    transcribe.download_model(model, progress=transcribe.progress_printer(model))
    print(file=sys.stderr)


def run_wizard(
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
    start_entry: Callable[[], int] | None = None,
    download: Callable[[str], None] = _download,
) -> int:
    """The interactive setup. `ask`, `say`, `start_entry` and `download` are injected so tests can
    script it without a terminal or the network.
    """
    wiz = _Wizard(ask, say)
    try:
        wiz.welcome(environment_report())
        wiz.folder()
        wiz.history()
        wiz.resurface()
        wiz.voice_memos()
        wiz.prompts_info()
        saved = wiz.summary_and_save()
        if wiz.download:
            if "storage.dir" in wiz.changes and not saved:
                say(f"Skipped the {wiz.download} download, since the new folder wasn't saved.")
            else:
                say(f"Downloading the {wiz.download} model...")
                try:
                    download(wiz.download)
                    say("Done.")
                except transcribe.TranscribeError as exc:
                    say(f"Couldn't download it: {exc}\n  Try again later with `journal model download {wiz.download}`.")
        say("")
        code = 0
        if start_entry is not None and wiz.yes_no("Write your first entry now?", False):
            code = start_entry()
        say("\nYou're set. A few good next commands:")
        say("  journal add <words>     capture a thought in one line")
        say("  journal read            reread your recent entries")
        say("  journal docs            the built-in guide")
        return code
    except (EOFError, KeyboardInterrupt):
        say("\nNothing was changed.")
        return 130
