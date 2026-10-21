# rythe: overview

`rythe` is a personal, date/time-based journal that lives in plain text files on your own
machine. Nothing is sent anywhere, and the CLI never calls an AI or any API.

There are two front doors onto the same data:

- **Writing (for a person):** run `rythe` with no arguments (same as `rythe write`). It opens
  `$EDITOR` on a blank page. Save and quit to keep the entry; an empty page is discarded.
- **Everything else (for people and agents):** `rythe <command>`. Every command has `--help`,
  and most have `--json`. An agent should use the CLI, never edit the files directly.

## The ideas in one minute

- An **entry** is one piece of writing with a timestamp. Its **id** is that time, like
  `2026-09-30T164608`. Anywhere an id is wanted you can also say `last`, `today`, or a unique
  prefix such as `2026-09-30`.
- **Tags** are `#hashtags` written inside the text. There is no separate tag field.
- Every entry has a **source**: `cli` (typed or piped), `memo` (a transcribed voice memo), or
  `text` (imported from a file).
- Writing is made safe: unsaved editor drafts are kept, and deletes only move files to a trash
  folder. Backing up the data folder is up to you (see `rythe docs concepts`).
- Rereading is built in: `rythe read`, and `rythe review`, a weekly look-back that ends with
  you writing a reflection.
- Prompts are always opt-in. A bare `rythe` is a blank page; `--prompt` adds a question below
  it (see `rythe docs prompts`).

## Where to go next

Run `rythe docs --list` for all topics. The usual path:

0. `rythe setup`: a short guided setup for people (re-runnable; nothing is saved until you
   confirm). `rythe setup --check [--json]` reports what the machine has, for anyone.
1. `rythe docs concepts`: ids, tags, time zones, drafts, the data layout, backups.
2. `rythe docs commands`: every command and flag (generated from the CLI itself).
3. `rythe docs config`: every setting, what it does, and how to change it.
4. `rythe docs prompts`: the writing prompt sets and what each is for.
5. `rythe docs json`: the stable machine-readable output and exit codes.
6. `rythe docs agents`: rules of thumb for agents driving the CLI.
