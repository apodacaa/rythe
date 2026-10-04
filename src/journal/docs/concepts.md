# journal: concepts

## Entries and ids

An entry is a text file. Its id is its creation time in the entry's own local time zone:
`YYYY-MM-DDTHHMMSS` (for example `2026-09-30T164608`). If two entries share a second, the second
gets a `-2` suffix. Timestamps always keep their UTC offset, so travelling never scrambles order.

Refs accepted by `show`, `edit`, `tag` and `delete`:

- a full id;
- `last`, the newest entry; `today`, the newest entry written today;
- any unique left-anchored prefix, like `2026-09-30` or `2026-10-01T09`.

An ambiguous prefix lists the candidates and exits 1; no match exits 2. `show` and `edit` with no
ref open an fzf picker on a terminal when fzf is installed, otherwise they use `last`.

## Dates

Flags like `--since`, `--until`, `--on` and `--at` take an ISO date or timestamp
(`2026-09-30`, `2026-09-30T16:46:08+02:00`). Natural language also works for people typing by
hand (`yesterday`, `3 days ago`, `monday`), but agents should always use ISO. A bare date as
`--since`/`--until` means the whole day.

## Tags

Tags are `#words` inside the entry text (letters, digits, `_` and `-`, starting with a letter),
matched case-insensitively. `journal tag <ref> <tag>…` appends missing tags as a final line.
`journal tags` counts them. A `#` in a shell is a comment, so quote text or use `add -t`.

## Sources

`cli` is anything written through the CLI or editor. `memo` is a voice memo transcribed with
whisper.cpp (`journal ingest audio`); the original audio is kept. `text` is a file imported with
`journal ingest text`. Ingests can carry a `--message-id` for de-duplication: re-ingesting the
same id exits 3 unless `--force` is given.

## Safety nets

- **Drafts:** the editor works on a file in `<data>/drafts`. It's deleted only after the entry is
  saved. If anything goes wrong (a crash, a killed editor, a failed save), the next `journal
  write` resumes the draft.
- **History:** every write is committed to a local git repo in the data directory (setting
  `history.enabled`). It is never pushed anywhere.
- **Trash:** `journal delete` moves an entry (and its audio) to `<data>/.trash`; nothing is
  purged.
- **Edits show only the body.** The editor never sees the frontmatter, so an edit can't corrupt
  it, and `updated` is stamped only when the text really changed. Emptying an entry is refused.

## Rereading

- `journal read` prints a range as prose, oldest first, through your pager (default: the last 7
  days). `journal show` prints one entry the same way (`--raw` for the stored file).
- `journal on-this-day` lists entries from today's date in earlier years.
- After a new entry is saved on a terminal, one older entry is shown (same day in a past year,
  else a month ago, else a week ago). Setting `resurface.enabled` controls it.
- `journal review` shows the period and then opens the editor with reflection questions. The
  result is saved as a titled entry tagged `#review`.
- `journal status` says when you last wrote and how many entries this week (also `--json`), cheap
  enough for a shell prompt or a scheduler.

## Data layout

The data folder defaults to `~/.local/share/journal`. Choose another with
`journal config set storage.dir <folder>` (absolute, or starting with `~`); the `JOURNAL_DIR`
environment variable overrides that when set. `journal path` prints the folder in use.

```
~/.local/share/journal/        (storage.dir, or JOURNAL_DIR)
  entries/2026/09/2026-09-30T164608.txt
  audio/2026-09-30T164608.m4a      original voice memos
  models/ggml-small.bin            whisper models (not in history)
  drafts/                          unsaved editor drafts (not in history)
  .trash/                          deleted entries (not in history)
  .git/                            local history
~/.config/journal/config.toml      settings (override with JOURNAL_CONFIG)
```

Entry files are a small frontmatter block (`created`, `updated`, `source`, `title`, …) followed by
the text.

## Moving your journal

Changing `storage.dir` only changes where the journal looks; it does not move files. To relocate
an existing journal, move the whole folder (it contains the entries, audio and the git history),
then point the setting at it:

```
journal path                                   # the current folder, e.g. ~/.local/share/journal
mv ~/.local/share/journal ~/Documents/journal
journal config set storage.dir ~/Documents/journal
journal list --limit 3                         # your entries are there
```

If `JOURNAL_DIR` is set in your shell it wins over the setting, so unset it (or change it) too.
`journal config set storage.dir` warns about both situations. Programs not started from your
shell (an agent, a scheduler) don't see shell variables, which is why the setting is the reliable
choice.
