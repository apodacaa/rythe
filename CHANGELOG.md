# Changelog

What changed in each version, newest first. The version is in `src/rythe/__init__.py` and
`rythe --version` prints it. Versions follow [semantic versioning](https://semver.org): from
1.0.0 on, a change that breaks the `--json` output, a flag, an exit code or an editor file name
is a new major version.

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
