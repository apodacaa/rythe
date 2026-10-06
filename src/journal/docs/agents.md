# journal: notes for agents

You are driving a person's private journal. These rules keep it safe and keep you accurate.

1. **Learn from the tool, not the source.** `journal docs --all` prints everything; `journal
   <command> --help` has the flags; `journal config explain` and `journal prompts list` explain
   settings and prompt sets.
2. **Use `--json`** whenever you will parse the output. Plain output is for people. Dates you
   pass should be ISO. Output piped to you is never styled (no color codes) and `journal docs`
   gives you raw markdown; only a person's terminal gets the styled version.
3. **Never edit files in the data directory yourself** (entries, audio or anything else). Use
   `journal new/add/edit/tag/delete`. They stamp `updated` and avoid corrupting
   frontmatter. To change an entry's text use `journal edit <id> --stdin` (or `--text`), never
   plain `journal edit`, which opens an editor. `journal path` shows where the data lives (for information only).
4. **Don't read the journal unless asked.** It's private. When you do, use the narrowest query
   (`list --since … --tag …`, `search`), not a dump of everything.
5. **Writing as the person:** `journal write` and `journal review` open an editor and are for the
   human. Don't call them. To create an entry on someone's behalf, use `journal add` or
   `journal new --text`, and only when they asked.
6. **Changing settings:** use `journal config set <key> <value>` and `journal config unset <key>`
   instead of editing `config.toml`. `config set` rewrites the file; if it had comments, they're
   saved to `config.toml.bak` and you should tell the person. Confirm with `journal config get`.
7. **Don't run `journal setup`.** It's an interactive wizard for the person (it refuses to run
   without a terminal anyway). To learn what the machine has, use `journal setup --check
   --json`; to change settings, use `journal config set`.
8. **Prompts are opt-in and personal.** Don't add `--prompt` unless asked. `distance` should be
   skipped for someone who is feeling very low (see `journal docs prompts`).
9. **Deletes are soft** (moved to `.trash`), but still ask before deleting.
10. **Exit codes carry meaning** (`journal docs json`): 2 means not found, 3 means a duplicate
   ingest: don't retry with `--force` unless that is actually wanted.
11. **Be honest about what you see.** If a command fails, report the exact message.
