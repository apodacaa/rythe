# rythe

A personal, date/time-based journal. Two front doors onto the same data:

- **`rythe` with no args (or `rythe write`)**: opens `$EDITOR` on a new entry — same as
  `rythe new --editor`. This is for the human, not Claude. There's no custom TUI: a real
  editor (vim/nvim, whatever `$EDITOR` resolves to) already does modal editing, themes, help
  and crash recovery better than a hand-rolled one would.
- **CLI** (`rythe <command>`): this is the tool Claude uses. It never calls Claude or any
  API itself — it's plain data plumbing (create/list/show/search/tag/ingest). Every command has
  `--help`; most support `--json`.

Voice memos arrive by email (subject `record-memo: <ISO timestamp>`, one audio attachment) and
get swept in on demand via the `journal-sweep` skill, which transcribes locally with
`whisper-cpp` and calls `rythe ingest audio`. That skill lives globally in
`~/.claude/skills/journal-sweep`, not in this repo — it's a client of the CLI.

This repo lives in the `~/Work/journal` hub as `cli/`, beside its clients (`nvim/` is
`rythe.nvim`). The hub's `CLAUDE.md` has the rules that span them.

## Design rules

- **Skills are clients of the app, not part of it.** `journal-sweep` is one way to drive the
  CLI; features live in the CLI so any user (or agent) gets them. Don't add app behaviour that
  only works through a skill.
- **Cross-platform is a goal.** Nothing OS- or desktop-specific ships in this repo (no Hyprland,
  systemd, notify-send). Optional external tools (`fzf`, a pager) need a plain fallback
  when missing. Triggers like reminders are the user's to wire up via `rythe status`.
- **The tool documents itself, by construction.** Every setting is in `src/rythe/settings.py`
  (name, type, default, description, example) and every built-in prompt set has a description in
  `prompts.py`. `rythe config`, `rythe prompts` and `rythe docs` are generated from those
  and from the argparse parser, and tests fail if something exists undocumented. So: adding a
  field to `config.py` means adding a `Setting` (a rule beyond its kind, like the language-code
  check, goes in its `check` function, so `config set` and the wizard both apply it); a new
  built-in prompt set needs a `DESCRIPTIONS` entry; a new command needs a `help=` (and flags need
  help text). Static guide
  pages are `src/rythe/docs/*.md` (overview, concepts, json, agents): update them when
  behaviour changes. `rythe docs --all` is the agent guide; the README is the human one.
- **The setup wizard is a thin layer.** `rythe setup` (interactive, people only) asks about the
  settings in `setup.WIZARD_KEYS` and saves through the same validation and writer as
  `rythe config set`; `rythe setup --check --json` is the agent-friendly equivalent. It never
  launches on its own: the only nudge is a one-line tip after a person's first entry while no
  config file exists. New wizard questions must use registry settings (a test checks). The one
  thing it does beyond settings: when the folder changes it offers to move the journal there on
  save, and puts `storage.dir` back if the move fails. Only the questions are numbered steps.
- **Styling lives in `ui.py` only.** Human-facing output may use bold, color, boxes and glyphs via
  `ui` (the terminal's own 16 colors, so it follows the theme), never in `--json`, and
  `rythe docs` prints raw markdown to anything but a terminal. Every styled command belongs in
  `COMMANDS` in `tests/test_ui.py`, and `--help` is styled by `helpstyle.RytheParser` (build every
  parser with it); that test proves that stripping the escape codes yields exactly
  the plain output, so pipes and scripts never change. Don't nest the same quote type inside an
  f-string (`f"{x['a']}"` is fine, `f'{x['a']}'` breaks on Python 3.11, which we support).
- **A bare `rythe` is a blank page.** Prompts are always opt-in (`--prompt`).
- **Never lose writing.** Editor drafts live in `<data>/drafts` until the entry is saved;
  `--at` is parsed before the editor opens; edits show the editor only the body.
- **Editor file names are a contract.** Every file the editor is opened on is named
  `rythe-new-*.txt` (drafts `<data>/drafts/rythe-new-<time>.txt`, edit copies
  `rythe-new-edit-<id>-*.txt` in the temp dir). Other tools match journal writing by that name,
  so don't rename them; `tests/test_cli.py` pins them.

## Data lives outside this repo

Entries are in `~/.local/share/rythe` by default (the `storage.dir` setting changes it;
`RYTHE_DIR` overrides both), **never** in this repo.
Tests must set `RYTHE_DIR` to a temp directory — never touch the real journal in a test, and
don't read the real journal during development unless the user asks for it.

rythe doesn't manage backups (no git history, no sync): it's one folder of plain text and
users back it up however they like. Don't add backup or version-control features.

## CLI JSON contract

- `--json` output is stable; treat its shape as an API. `rythe --help` and
  `rythe <command> --help` list each command's flags and output (the original design plan
  describes a TUI that no longer exists, so don't use it as a reference).
- Plain-text output (`read`, `show`, `status`, `review`) is for people and may change; scripts
  use `--json`.
- `rythe status --json` → `{last_entry_id, last_entry_at, days_since, week_count,
  on_this_day_count}` (nulls/zeros for an empty journal).
- Entry refs: `show`/`edit`/`tag`/`delete` take an id, `last`, `today`, or a unique prefix.
  Ambiguous prefix → exit `1`; no match → exit `2`.
- `config`, `prompts` and `docs` shapes are in `rythe docs json` (a test keeps the entry
  fields and exit codes in that page in sync).
- Exit codes: `0` ok, `1` usage error, `2` not found, `3` duplicate (`ingest` with a
  `message_id` that already exists — retry with `--force` only if that's actually wanted).

## Working here

- Install/reinstall after code changes: `uv tool install --editable .` (puts `rythe` on
  `~/.local/bin`, which is already on PATH; this project's `bin/` holds only `bin/release`).
- Tests: `uv run pytest`.
- Git: the remote is `github.com/apodacaa/rythe` (public). Work lands on `main` through a pull
  request: branch, commit, push, `gh pr create`. The user decides when to merge (`gh pr merge
  --merge`, keeping each commit). Don't commit straight to `main`.

## Versions and releases

People install from GitHub and get whatever `main` is at, so **`main` always equals a released
version**.

- The version is written once, in `src/rythe/__init__.py`; `pyproject.toml` reads it from there
  and `rythe --version` prints it.
- A pull request that changes anything a user or a client can see bumps the version and adds an
  entry at the top of `CHANGELOG.md`, in that same pull request. A test fails if the two disagree.
  Changes nobody outside can see (tests, refactors, this file) don't bump it.
- Semantic versioning. Before 1.0.0 a breaking change bumps the minor number. From 1.0.0 on, the
  `--json` shapes, flags, exit codes and editor file names are frozen: breaking one is a new major
  version.
- After the pull request merges, `bin/release` on an up-to-date `main` runs the tests, tags
  `v<version>`, pushes the tag and creates the GitHub release from the changelog entry.
  `bin/release --dry-run` checks everything and publishes nothing. Tagging is the user's call, like
  merging.
- The clients (`../nvim`, `../omarchy-plugin`) each name the lowest CLI version they need in their
  README. A client that needs something new waits for the CLI release that has it.
