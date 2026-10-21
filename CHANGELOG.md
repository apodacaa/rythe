# Changelog

What changed in each version, newest first. The version is in `src/rythe/__init__.py` and
`rythe --version` prints it. Versions follow [semantic versioning](https://semver.org): from
1.0.0 on, a change that breaks the `--json` output, a flag, an exit code or an editor file name
is a new major version.

## 0.3.0

**"On this day" is gone.** Nothing in the research on journaling shows that being shown old entries
helps, and it can feed rumination, so rythe no longer surfaces them. Rereading stays: `rythe read`
and the weekly `rythe review`. This is a breaking change, so check these:

- **`rythe on-this-day` is removed.** It now fails as an unknown command (exit `1`).
- **No older entry after you save.** The `resurface.enabled` setting, the matching question in
  `rythe setup` (the wizard now has two steps, not three) and the `resurfaced` key in
  `new --json` and `add --json` are all removed.
- **`rythe status --json` no longer has `on_this_day_count`**, and the plain `status` output no
  longer prints an "on this day" line. The other four fields are unchanged.
- A `[resurface]` section left in your settings file is harmless: `rythe config list` reports it
  under `unknown_keys`, and you can delete it.

## 0.2.1

Fixes and small hints for people and agents driving the CLI.

- **Usage errors exit `1`**, as the docs always said. A missing argument, a bad flag or an
  unknown command used to exit `2`, which is also "not found", so a script couldn't tell them
  apart.
- **A bare `rythe config`** (also `prompts`, `ingest` and `model`) prints its sub-commands
  instead of an error.
- **`rythe config list --json`** has an `in_setup` field on each setting: true for the ones
  `rythe setup` asks about, so an agent knows where to start. `config explain` and
  `rythe docs config` say so too.

## 0.2.0

**Renamed from `journal` to `rythe`.** "Journal" collided with too much, systemd's own journal
included. A rythe is a small stream (say "rye-th"). Everything that carried the old name changed:

- The command and the Python package are `rythe`.
- The default folders are `~/.local/share/rythe` and `~/.config/rythe`.
- The environment variables are `RYTHE_DIR` and `RYTHE_CONFIG`.
- The files the editor is opened on are named `rythe-new-*.txt`.
- Errors start with `rythe:`.

Nothing is moved for you. Coming from 0.1.0, with no `storage.dir` setting and no `JOURNAL_DIR`:

```
mv ~/.local/share/journal ~/.local/share/rythe
mv ~/.config/journal ~/.config/rythe
```

The entries, the `--json` output and the exit codes are unchanged.

## 0.1.0

Released under the name `journal`; the commands below are as they were then.

The first tagged version.

- Write in `$EDITOR` (`journal`, `journal write`), or in one line (`journal add`).
- Read, list, search, tag, edit and delete entries; `on-this-day`, `status` and `review`.
- Voice memos and text files become entries with `journal ingest`, transcribed on this computer.
- A guided `journal setup`, settings through `journal config`, and writing prompts.
- `--json` on most commands, and a built-in guide (`journal docs`).
- `journal --version`.
