# Changelog

What changed in each version, newest first. The version is in `src/journal/__init__.py` and
`journal --version` prints it. Versions follow [semantic versioning](https://semver.org): from
1.0.0 on, a change that breaks the `--json` output, a flag, an exit code or an editor file name
is a new major version.

## 0.1.0

The first tagged version.

- Write in `$EDITOR` (`journal`, `journal write`), or in one line (`journal add`).
- Read, list, search, tag, edit and delete entries; `on-this-day`, `status` and `review`.
- Voice memos and text files become entries with `journal ingest`, transcribed on this computer.
- A guided `journal setup`, settings through `journal config`, and writing prompts.
- `--json` on most commands, and a built-in guide (`journal docs`).
- `journal --version`.
