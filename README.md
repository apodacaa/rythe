# journal

A personal, date-and-time-based journal that lives in plain text files on your own computer.
You write in your normal editor; a small command-line tool handles everything else. Nothing is
uploaded, and the tool never calls an AI or any web service.

```
$ journal                      # opens $EDITOR on a blank page; save and quit to keep it
$ journal add had coffee with Sam -t friends
$ journal read                 # the last 7 days, as prose
$ journal review               # read your week, then write a reflection
```

## Why it works this way

- **A blank page is the default.** `journal` with no arguments opens your own editor (vim, nvim,
  whatever `$EDITOR` is). Prompts exist, but only when you ask for them.
- **Your words are safe.** Unsaved drafts survive a crash, deletes only move files to a trash
  folder, and an edit never exposes the file's metadata to the editor. Backups are yours to choose:
  the journal is one folder of plain text, so any way you already back up a folder works.
- **Rereading is the point.** Ordinary days are worth more later than they seem. `journal read`,
  `journal on-this-day`, an older entry shown after you save a new one, and a weekly
  `journal review` are all built in.
- **It's plain files.** Entries are `.txt` files you can read, grep and back up without this
  tool, in a folder you control.
- **It looks the part.** On a terminal you get bold headers, a colored guided setup, highlighted
  tags and search matches, and a rendered built-in guide. Colors come from your terminal's own
  palette, so they follow your theme, and they switch off by themselves when output is piped.
- **People and agents both can drive it.** Every command has `--help` and most have `--json`, and
  the tool documents itself (see [Documentation](#documentation)).

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/apodacaa/journal && cd journal
uv tool install .            # puts `journal` on your PATH (use --editable while developing)
```

`journal --version` says which version you have, and [CHANGELOG.md](CHANGELOG.md) what changed in
each.

Optional, each with a plain fallback if missing: `fzf` (an entry picker for
`journal edit` and `journal show`), a pager such as `less`, and `ffmpeg` plus `whisper-cpp` for
voice memos.

## Getting started

There's nothing you have to set up: the first `journal` or `journal add` creates the folders it
needs. If you'd like a guided tour of the few choices that matter (where the journal lives,
voice memos), run:

```
journal setup                        # a short, re-runnable wizard; nothing is saved until you confirm
journal setup --check                # just report what this machine has (editor, fzf, ffmpeg…)
```

| What | Default location | Change it |
|---|---|---|
| Your entries (plus audio, drafts and trash) | `~/.local/share/journal` | `journal config set storage.dir ~/Documents/journal` |
| Settings file | `~/.config/journal/config.toml` | the `JOURNAL_CONFIG` environment variable |

Check where things are with `journal path` (the journal folder) and `journal config path` (the
settings file).

**Choosing a different folder:** do it before you start, or move your files along with it.
`storage.dir` changes where the journal *looks*; it doesn't move anything. To relocate an existing
journal:

```
mv ~/.local/share/journal ~/Documents/journal      # the whole folder
journal config set storage.dir ~/Documents/journal
```

`journal setup` does both steps for you: pick a new folder there and it offers to move the journal.

The `JOURNAL_DIR` environment variable also works and takes precedence, but it only applies to
programs started from a shell that exports it, so the setting is the safer choice. A good place
for the folder is somewhere you already back up (a synced folder, for example).

## A quick tour

**Write**

```
journal                              # blank page in $EDITOR
journal write --prompt               # with a question below the page (removed when you save)
journal add had coffee with Sam -t friends
echo "typed from a script" | journal new
journal new --at yesterday --text "backfilling an entry"
```

Tags are `#words` inside the text. In a shell, `#` starts a comment, so quote the text or use
`add -t`.

**Read and find**

```
journal read                         # the last 7 days, oldest first, through your pager
journal read --since 2026-09-01 --tag work
journal on-this-day                  # entries from today's date in earlier years
journal search "coffee" --tag morning
journal show last                    # or today, or a prefix like 2026-09-30
journal status                       # when you last wrote; handy in a prompt or a scheduler
```

**Look back**

```
journal review                       # shows your week, then opens the editor with questions;
                                     # saved as an entry tagged #review
```

**Change something**

```
journal edit                         # pick an entry (fzf) or edit the last one
journal tag last gratitude
journal delete 2026-09-30T164608     # moved to .trash, not purged
```

## Writing prompts

`journal prompts list` shows the built-in sets and what each is for: `today` (a light daily
question), `hard` (expressive writing about something heavy), `distance` (write about a problem
as an outside observer), and `review` (used by `journal review`). Add your own:

```
journal config set prompts.gratitude "What am I grateful for today?" "Who helped me this week?"
journal write --prompt gratitude
```

## Configuration

Everything is optional. See and change settings from the CLI instead of hunting for a file:

```
journal config list                  # every setting: value, default, where it came from
journal config explain resurface.enabled
journal config set resurface.enabled false
journal config unset resurface.enabled
```

Appearance: colors and bold are on for terminals and off when piped, with `--json`, or when
`NO_COLOR` is set. Force a choice with `journal config set appearance.color always` (or `never`).

The file is `~/.config/journal/config.toml` (override with `JOURNAL_CONFIG`). Entries live in
`~/.local/share/journal` unless you set `storage.dir` (see [Getting started](#getting-started)).

## Voice memos

`journal ingest audio memo.m4a` transcribes a recording locally with whisper.cpp (download a
model first with `journal model download small`) and saves it as an entry, keeping the original
audio. `journal ingest text file.txt` imports a text file. Both accept `--at` for the time and
`--message-id` to avoid importing the same item twice. Getting recordings to your computer, for
example from an email inbox, is left to whatever tool you prefer; a separate agent skill can
automate it.

## Documentation

The guide is built into the tool, so it's available offline and to any agent without repo access:

```
journal docs                         # overview
journal docs --list                  # topics: concepts, commands, config, prompts, json, agents
journal docs --all                   # everything in one go
```

The `commands`, `config` and `prompts` topics are generated from the program itself, so they
can't fall out of date.

## Development

```
uv run pytest                        # tests (they use a temporary journal, never your real one)
uv tool install --editable .         # reinstall after code changes
```

Project rules and design decisions are in [CLAUDE.md](CLAUDE.md).
