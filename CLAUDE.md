# journal

A personal, date/time-based journal. Two front doors onto the same data:

- **`journal` with no args (or `journal write`)**: opens `$EDITOR` on a new entry — same as
  `journal new --editor`. This is for the human, not Claude. There's no custom TUI: a real
  editor (vim/nvim, whatever `$EDITOR` resolves to) already does modal editing, themes, help
  and crash recovery better than a hand-rolled one would.
- **CLI** (`journal <command>`): this is the tool Claude uses. It never calls Claude or any
  API itself — it's plain data plumbing (create/list/show/search/tag/ingest). Every command has
  `--help`; most support `--json`.

Voice memos arrive by email (subject `record-memo: <ISO timestamp>`, one audio attachment) and
get swept in on demand via the `journal-sweep` skill, which transcribes locally with
`whisper-cpp` and calls `journal ingest audio`. That skill lives globally in
`~/.claude/skills/journal-sweep`, not in this repo — it's a client of the CLI.

## Design rules

- **Skills are clients of the app, not part of it.** `journal-sweep` is one way to drive the
  CLI; features live in the CLI so any user (or agent) gets them. Don't add app behaviour that
  only works through a skill.
- **Cross-platform is a goal.** Nothing OS- or desktop-specific ships in this repo (no Hyprland,
  systemd, notify-send). Optional external tools (`git`, `fzf`, a pager) need a plain fallback
  when missing. Triggers like reminders are the user's to wire up via `journal status`.
- **The tool documents itself, by construction.** Every setting is in `src/journal/settings.py`
  (name, type, default, description, example) and every built-in prompt set has a description in
  `prompts.py`. `journal config`, `journal prompts` and `journal docs` are generated from those
  and from the argparse parser, and tests fail if something exists undocumented. So: adding a
  field to `config.py` means adding a `Setting`; a new built-in prompt set needs a
  `DESCRIPTIONS` entry; a new command needs a `help=` (and flags need help text). Static guide
  pages are `src/journal/docs/*.md` (overview, concepts, json, agents): update them when
  behaviour changes. `journal docs --all` is the agent guide; the README is the human one.
- **The setup wizard is a thin layer.** `journal setup` (interactive, people only) asks about the
  settings in `setup.WIZARD_KEYS` and saves through the same validation and writer as
  `journal config set`; `journal setup --check --json` is the agent-friendly equivalent. It never
  launches on its own: the only nudge is a one-line tip after a person's first entry while no
  config file exists. New wizard questions must use registry settings (a test checks).
- **A bare `journal` is a blank page.** Prompts are always opt-in (`--prompt`).
- **Never lose writing.** Editor drafts live in `<data>/drafts` until the entry is saved;
  `--at` is parsed before the editor opens; edits show the editor only the body.

## Data lives outside this repo

Entries are in `~/.local/share/journal` by default (the `storage.dir` setting changes it;
`JOURNAL_DIR` overrides both), **never** in this repo.
Tests must set `JOURNAL_DIR` to a temp directory — never touch the real journal in a test, and
don't read the real journal during development unless the user asks for it.

Every write is also committed to a local git repo in the data dir (`[history] enabled = false`
in `~/.config/journal/config.toml` turns that off). It is never pushed anywhere.

## CLI JSON contract

- `--json` output is stable; treat its shape as an API. `journal --help` and
  `journal <command> --help` list each command's flags and output (the original design plan
  describes a TUI that no longer exists, so don't use it as a reference).
- Plain-text output (`read`, `show`, `status`, `review`) is for people and may change; scripts
  use `--json`.
- `journal status --json` → `{last_entry_id, last_entry_at, days_since, week_count,
  on_this_day_count}` (nulls/zeros for an empty journal).
- Entry refs: `show`/`edit`/`tag`/`delete` take an id, `last`, `today`, or a unique prefix.
  Ambiguous prefix → exit `1`; no match → exit `2`.
- `config`, `prompts` and `docs` shapes are in `journal docs json` (a test keeps the entry
  fields and exit codes in that page in sync).
- Exit codes: `0` ok, `1` usage error, `2` not found, `3` duplicate (`ingest` with a
  `message_id` that already exists — retry with `--force` only if that's actually wanted).

## Working here

- Install/reinstall after code changes: `uv tool install --editable .` (puts `journal` on
  `~/.local/bin`, which is already on PATH — this project's own `bin/` is not used).
- Tests: `uv run pytest`.
- Git: local only for now, no GitHub remote. Work on a branch per milestone; the user decides
  when to merge. Don't commit straight to `main`.
