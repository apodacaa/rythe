# journal

A personal, date/time-based journal. Two front doors onto the same data:

- **TUI** (`journal`, no args): open, type, save, quit. This is for the human, not Claude.
  Modal vim keybindings — see `src/journal/tui/keymap.py` for the full binding table, or `?`
  inside the app.
- **CLI** (`journal <command>`): this is the tool Claude uses. It never calls Claude or any
  API itself — it's plain data plumbing (create/list/show/search/tag/ingest). Every command has
  `--help`; most support `--json`.

Voice memos arrive by email (subject `record-memo: <ISO timestamp>`, one audio attachment) and
get swept in on demand via the `journal-sweep` skill, which transcribes locally with
`whisper-cpp` and calls `journal ingest audio`.

## Data lives outside this repo

Entries are in `~/.local/share/journal` (override with `JOURNAL_DIR`), **never** in this repo.
Tests must set `JOURNAL_DIR` to a temp directory — never touch the real journal in a test, and
don't read the real journal during development unless the user asks for it.

## CLI JSON contract

- `--json` output is stable; treat its shape as an API. See the command table in
  `~/.claude/plans/write-up-the-plan-vectorized-truffle.md` (or `journal <command> --help`) for
  each command's flags and output.
- Exit codes: `0` ok, `1` usage error, `2` not found, `3` duplicate (`ingest` with a
  `message_id` that already exists — retry with `--force` only if that's actually wanted).

## Working here

- Install/reinstall after code changes: `uv tool install --editable .` (puts `journal` on
  `~/.local/bin`, which is already on PATH — this project's own `bin/` is not used).
- Tests: `uv run pytest`.
- Install the email-sweep skill: symlink `skills/journal-sweep` into `~/.claude/skills/`.
- Git: local only for now, no GitHub remote. Work on a branch per milestone; the user decides
  when to merge. Don't commit straight to `main`.
