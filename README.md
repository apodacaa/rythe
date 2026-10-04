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
- **Your words are safe.** Unsaved drafts survive a crash, every write is committed to a local git
  history, deletes only move files to a trash folder, and an edit never exposes the file's
  metadata to the editor.
- **Rereading is the point.** Ordinary days are worth more later than they seem. `journal read`,
  `journal on-this-day`, an older entry shown after you save a new one, and a weekly
  `journal review` are all built in.
- **It's plain files.** Entries are `.txt` files you can read, grep and back up without this
  tool, in a folder you control.
- **People and agents both can drive it.** Every command has `--help` and most have `--json`, and
  the tool documents itself (see [Documentation](#documentation)).

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
cd path/to/journal           # a checkout of this repository
uv tool install .            # puts `journal` on your PATH (use --editable while developing)
```

Optional, each with a plain fallback if missing: `git` (history), `fzf` (an entry picker for
`journal edit` and `journal show`), a pager such as `less`, and `ffmpeg` plus `whisper-cpp` for
voice memos.

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
journal config explain history.enabled
journal config set history.enabled false
journal config unset history.enabled
```

The file is `~/.config/journal/config.toml` (override with `JOURNAL_CONFIG`). Entries live in
`~/.local/share/journal` (override with `JOURNAL_DIR`).

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
