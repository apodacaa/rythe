# journal: JSON output and exit codes

`--json` output is a stable contract: its shape is treated as an API. Plain-text output (`read`,
`show`, `status`, `review`, listings) is for people and may change, so scripts and agents should
use `--json`.

## Entry object

Returned by `new`, `add`, `show`, `tag`, `ingest audio|text` and inside `list`:

```
{
  "id": "2026-09-30T164608",
  "created": "2026-09-30T16:46:08+02:00",
  "updated": null,            // ISO timestamp once the text has been edited
  "source": "cli",            // cli | memo | text
  "title": "",
  "message_id": null,
  "audio": null,              // e.g. "audio/<id>.m4a" for memos
  "transcriber": null,        // e.g. "whisper.cpp small"
  "tags": ["work"],           // parsed from #tags in the body
  "body": "text of the entry\n"
}
```

## Other shapes

- `list --json`, `on-this-day --json`: an array of entry objects, newest first.
- `search --json`: `[{"id", "created", "matches": [matching lines]}]`.
- `tags --json`: `{"tag": count, …}`, most used first.
- `delete --json`: `{"id", "trashed_at"}`.
- `ingest seen`: always prints `{"seen": true, "id": "…"}` or `{"seen": false}`; exit 0 if seen, 1
  if not.
- `status --json`: `{"last_entry_id", "last_entry_at", "days_since", "week_count",
  "on_this_day_count"}` (nulls and zeros for an empty journal).
- `config list --json`: `{"path", "exists", "settings": [{"key", "kind", "value", "default",
  "source", "choices", "description", "example"}], "unknown_keys": []}`.
- `config get --json`: `{"key", "value", "default", "source"}`; `config set --json`:
  `{"key", "value"}`; `config explain --json`: the same setting objects as `config list`.
- `prompts list --json`: `[{"name", "source", "count", "description"}]`;
  `prompts show --json`: `{"name", "source", "description", "prompts": []}`.

`read`, `show` (without `--json`), `review`, `write` and `edit` are for people. There is no JSON
form of `read`; use `list --json`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | usage error (bad flag, bad date, unknown setting, ambiguous ref, empty entry) |
| 2 | not found (no such entry, file, or prompt set) |
| 3 | duplicate (`ingest` with a `message_id` that already exists; retry with `--force` only if wanted) |

Errors go to stderr as `journal: <message>`.
