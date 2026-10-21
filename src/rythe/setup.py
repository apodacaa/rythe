"""`rythe setup`: check what this machine has and (interactively) walk through the options.

The environment report is plain data so agents get the same picture a person does
(`rythe setup --check --json`).
"""
from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path
from typing import Callable

from . import prompts, settings, store, transcribe, ui
from .config import config_path, load_config, load_raw, write_raw
from .configcmd import _fmt

# The settings the wizard asks about: the registry marks them (`in_setup`), so `rythe config list --json`
# can tell an agent which ones to start with.
WIZARD_KEYS = tuple(s.key for s in settings.SETTINGS if s.in_setup)


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
            "writing entries (`rythe`, `rythe write`, `rythe edit`)",
            "set $EDITOR (for example `export EDITOR=nano`) or install nvim or vim",
        ),
        _tool(
            "fzf",
            "fzf",
            "the entry picker for `rythe edit` and `rythe show` with no id",
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
            "voice memos (`rythe ingest audio`)",
            "install ffmpeg with your package manager",
        ),
        _tool(
            "whisper-cli",
            "whisper-cli",
            "voice memos (`rythe ingest audio`)",
            "install whisper.cpp (the package that provides `whisper-cli`)",
        ),
        _check(
            f"whisper model ({model})",
            model_file.exists(),
            str(model_file) if model_file.exists() else "",
            "voice memos (`rythe ingest audio`)",
            f"run `rythe model download {model}`",
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
    lines = [ui.rule("Your setup")]
    width = max(len(c["name"]) for c in report["checks"])
    for c in report["checks"]:
        name = c["name"]
        if c["found"]:
            badge = ui.style(f"{ui.glyph('ok')} ok     ", "green")
            detail = ui.style(c["detail"], "dim")
        else:
            badge = ui.style(f"{ui.glyph('bad')} missing", "yellow")
            detail = ui.style(c["hint"], "yellow")
        lines.append(f"  {badge}  {ui.style(f'{name:<{width}}', 'bold')}  {detail}")
    lines.append("")
    entries = report["entries"]
    lines.append(
        f"{ui.style('journal folder:', 'bold')} {ui.style(report['data_dir'], 'cyan')} "
        f"{ui.style(f'({entries} entries)', 'dim')}"
    )
    lines.append(
        f"{ui.style('settings file: ', 'bold')} {ui.style(report['config_path'], 'cyan')}"
        + ("" if report["config_exists"] else ui.style(" (not created yet; all defaults)", "dim"))
    )
    return "\n".join(lines)


TOTAL_STEPS = 2  # folder, voice memos (the prompts section after them asks nothing)


def _is_free(folder: Path) -> bool:
    """True if a journal can be moved to `folder`: it doesn't exist yet, or is an empty folder."""
    if not folder.exists():
        return True
    return folder.is_dir() and not any(folder.iterdir())


class _Wizard:
    """One run of the wizard: gathers answers as pending changes, then saves once at the end."""

    def __init__(self, ask: Callable[[str], str], say: Callable[[str], None]):
        self.ask = ask
        self.say = say
        self.raw = load_raw()
        self.changes: dict[str, tuple[object, object]] = {}  # key -> (old, new)
        self.moved_from: Path | None = None  # the old folder, if it has files and a new one was chosen
        self.move = False  # move the old folder to the new place when saving
        self.saved = False  # the config file was written in this run
        self.download: str | None = None  # a whisper model to fetch after saving

    # -- small helpers --------------------------------------------------------------------
    def _q(self, question: str, suffix: str) -> str:
        """A styled input() prompt: a magenta marker, the question in bold, the options in cyan."""
        mark = ui.style(ui.glyph("ask"), "bold", "magenta")
        text = f" {mark} {ui.style(question, 'bold')} {ui.style(suffix, 'cyan')} "
        return ui.readline_safe(text)

    def heading(self, number: int, title: str) -> None:
        self.say("\n" + ui.step(number, TOTAL_STEPS, title))

    def info(self, *lines: str) -> None:
        self.say(ui.gutter(list(lines)))

    def yes_no(self, question: str, default: bool) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self.ask(self._q(question, suffix)).strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.say(ui.warn("Please answer y or n."))

    def current(self, key: str):
        return settings.current(self.raw, settings.lookup(key))[0]

    def propose(self, key: str, new) -> None:
        old = self.current(key)
        if new != old:
            self.changes[key] = (old, new)

    # -- steps ----------------------------------------------------------------------------
    def welcome(self, report: dict) -> None:
        self.say(ui.banner("rythe setup"))
        self.say(ui.style(
            " A few quick questions; press Enter to accept the default shown. Nothing is saved\n"
            " until the end, and you can run this again any time.", "dim"))
        for c in report["checks"]:
            if not c["found"] and c["name"] in ("editor", "fzf", "pager"):
                needed = " (needed)" if c["name"] == "editor" else ""
                self.say(" " + ui.warn(f"{c['name']} not found{needed}. {c['hint']}"))

    def folder(self) -> None:
        current = store.data_dir()
        count = store.count_entries()
        self.heading(1, "Where should your journal live?")
        if os.environ.get("RYTHE_DIR"):
            self.info(
                f"It's {ui.style(str(current), 'bold')}.",
                ui.style(
                    "The $RYTHE_DIR environment variable is set and overrides the storage.dir "
                    "setting, so there's nothing to choose here. Unset it to use the setting.",
                    "dim",
                ),
            )
            return
        entries = f" ({count} {'entry' if count == 1 else 'entries'})" if count else ""
        self.info(
            ui.style(
                "Entries are plain text files in one folder, together with audio and drafts. A "
                "folder you already back up (a synced one, say) is a good home.",
                "dim",
            ),
            "",
            f"{ui.style('Right now', 'bold')}  {ui.style(str(current), 'cyan')}{entries}",
        )
        if self.yes_no("Keep it here?", True):
            return
        setting = settings.lookup("storage.dir")
        while True:
            value = self.ask(self._q("Folder", "(absolute, or starting with ~; Enter to keep it)")).strip()
            if not value:
                return
            try:
                new = settings.coerce(setting, [value])
            except ValueError as exc:
                self.say(ui.warn(str(exc)))
                continue
            break
        target = Path(new).expanduser()
        if target == current:
            return
        self.propose("storage.dir", new)
        if _is_free(current):
            return  # nothing in the old folder to bring along
        self.moved_from = current
        if not _is_free(target):
            self.say(" " + ui.warn(
                f"{target} already has files in it, so rythe will use what's there and your "
                f"current journal stays in {current}."
            ))
        else:
            self.move = self.yes_no(f"Move your journal{entries} there too?", True)

    def voice_memos(self) -> None:
        self.heading(2, "Voice memos?")
        self.info(
            ui.style(
                "rythe can turn a recording into an entry, transcribing it on this computer with "
                "whisper.cpp (no audio ever leaves it).",
                "dim",
            )
        )
        # Someone who already downloaded their model is using voice memos.
        in_use = self._model_file(self.current("transcribe.model")).exists()
        if not self.yes_no("Will you use voice memos?", in_use):
            return
        for name in ("ffmpeg", "whisper-cli"):
            if shutil.which(name) is None:
                hint = next(c["hint"] for c in environment_report()["checks"] if c["name"] == name)
                self.say(" " + ui.warn(f"{name} not found. {hint}."))
        rows = [
            ui.style(
                "Pick a speech model. Bigger ones are more accurate but slower and larger to "
                "download. All of them understand many languages and run entirely on this computer.",
                "dim",
            ),
            "",
        ]
        for name in transcribe.KNOWN_MODELS:
            tags = []
            if name == transcribe.RECOMMENDED_MODEL:
                tags.append(ui.style("[recommended]", "green"))
            if self._model_file(name).exists():
                tags.append(ui.style("[downloaded]", "cyan"))
            rows.append(
                f"{ui.style(f'{name:<7}', 'bold')} {transcribe.format_size(name):<8} "
                f"{ui.style(transcribe.MODEL_NOTES[name], 'dim')} {' '.join(tags)}".rstrip()
            )
        self.info(*rows)
        model_setting = settings.lookup("transcribe.model")
        default = self.current("transcribe.model")
        while True:
            answer = self.ask(self._q("Which model?", f"[{default}]")).strip() or default
            try:
                model = settings.coerce(model_setting, [answer])
                break
            except ValueError as exc:
                self.say(ui.warn(str(exc)))
        self.propose("transcribe.model", model)

        language_setting = settings.lookup("transcribe.language")
        default = self.current("transcribe.language")
        while True:
            answer = (self.ask(self._q("Language spoken in your memos?", f"(a code like en, de, es, or auto) [{default}]"))
                      .strip() or default)
            try:
                language = settings.coerce(language_setting, [answer])
                break
            except ValueError as exc:
                self.say(ui.warn(str(exc)))
        self.propose("transcribe.language", language)

        if self._model_file(model).exists():
            self.say(" " + ui.ok(f"The {model} model is already downloaded."))
        elif self.yes_no(f"Download the {model} model now ({transcribe.format_size(model)})?", True):
            self.download = model
        else:
            self.say(" " + ui.warn(f"Voice memos won't work until it's downloaded: `rythe model download {model}`."))

    def _model_file(self, model: str) -> Path:
        """Where `model` will live: under the folder chosen in this run, if it changed. A journal
        that is being moved there brings its models along, so those are looked up where they are now.
        """
        folder = None if self.move else self.changes.get("storage.dir")
        base = Path(folder[1]).expanduser() if folder else store.data_dir()
        return base / "models" / transcribe.KNOWN_MODELS[model]

    def prompts_info(self) -> None:
        extra = load_config().prompts
        self.say("\n" + ui.heading("Writing prompts"))
        rows = [ui.style("Always optional; a bare `rythe` is a blank page.", "dim"), ""]
        for name in sorted(prompts.available(extra)):
            rows.append(f"{ui.style(f'{name:<9}', 'bold', 'cyan')} {prompts.SUMMARIES.get(name, 'your own set')}")
        rows += ["", ui.style("Try one with `rythe write --prompt hard`; `rythe prompts list` says more.", "dim")]
        self.info(*rows)

    def summary_and_save(self) -> bool:
        """Show the pending changes and save them if confirmed. Returns True if anything was saved."""
        if not self.changes:
            self.say("\n" + ui.style(" Nothing to change; your settings stay as they are.", "dim"))
            return False
        width = max(len(key) for key in self.changes)
        rows = []
        for key, (old, new) in self.changes.items():
            setting = settings.lookup(key)
            rows.append(
                f"{ui.style(f'{key:<{width}}', 'bold')}  {ui.style(_fmt(old, setting), 'dim')} "
                f"{ui.style(ui.glyph('arrow'), 'magenta')} {ui.style(_fmt(new, setting), 'bold', 'green')}"
            )
        if self.move:
            rows.append(ui.style(f"your journal folder moves from {self.moved_from}", "dim"))
        self.say("\n" + ui.box("Here's what will change", rows))
        if not self.yes_no("Save these?", True):
            self.say(" " + ui.warn("Nothing was saved."))
            return False
        for key, (_, new) in self.changes.items():
            settings.set_in(self.raw, key, new)
        backup = write_raw(self.raw)
        self.saved = True
        self.say(" " + ui.ok(f"Saved to {config_path()}"))
        if backup:
            self.say(" " + ui.warn(f"Your file had comments, which rewriting drops; the old one is at {backup}."))
        if self.move:
            self._move_journal()
        elif self.moved_from is not None:
            new_dir = store.data_dir()
            self.say(
                "\n" + ui.gutter(
                    [
                        f"Your existing entries are still in {self.moved_from}. To bring them along,",
                        "copy what's inside that folder into the new one:",
                        "",
                        f"    {ui.style(f'cp -a {self.moved_from}/. {new_dir}/', 'bold')}",
                    ]
                )
            )
        return True

    def _move_journal(self) -> None:
        """Move the old folder to the one just saved. If that fails, put the setting back, so the
        journal is never left pointing at a folder its entries aren't in."""
        old, new = self.moved_from, store.data_dir()
        try:
            if not _is_free(new):
                raise OSError(f"{new} is no longer empty")
            new.parent.mkdir(parents=True, exist_ok=True)
            if new.exists():
                new.rmdir()
            shutil.move(str(old), str(new))
        except OSError as exc:
            previous = self.changes.pop("storage.dir")[0]
            if previous is None:
                settings.unset_in(self.raw, "storage.dir")
            else:
                settings.set_in(self.raw, "storage.dir", previous)
            write_raw(self.raw)
            self.move = False
            self.say(" " + ui.warn(
                f"Couldn't move your journal ({exc}), so it stays in {old} and storage.dir is unchanged."
            ))
            return
        self.say(" " + ui.ok(f"Moved your journal to {new}"))


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
        say("")
        wiz.welcome(environment_report())
        wiz.folder()
        wiz.voice_memos()
        wiz.prompts_info()
        saved = wiz.summary_and_save()
        if wiz.download:
            if "storage.dir" in wiz.changes and not saved:
                say(" " + ui.warn(f"Skipped the {wiz.download} download, since the new folder wasn't saved."))
            else:
                say(f"\n Downloading the {wiz.download} model...")
                try:
                    download(wiz.download)
                    say(" " + ui.ok("Done."))
                except transcribe.TranscribeError as exc:
                    say(" " + ui.warn(f"Couldn't download it: {exc}"))
                    say(f"   Try again later with `rythe model download {wiz.download}`.")
        say("")
        code = 0
        which = "your first entry" if store.count_entries() == 0 else "an entry"
        if start_entry is not None and wiz.yes_no(f"Write {which} now?", False):
            code = start_entry()
        commands = [
            ("rythe add <words>", "capture a thought in one line"),
            ("rythe read", "reread your recent entries"),
            ("rythe docs", "the built-in guide"),
        ]
        rows = [f"{ui.style(f'{cmd:<20}', 'bold', 'cyan')} {text}" for cmd, text in commands]
        say("\n" + ui.box("You're set. Good next commands", rows))
        return code
    except (EOFError, KeyboardInterrupt):
        if wiz.saved:
            say("\n " + ui.warn("Stopped. Your settings were already saved."))
        else:
            say("\n " + ui.warn("Nothing was changed."))
        return 130
