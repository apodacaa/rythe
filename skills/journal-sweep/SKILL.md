---
name: journal-sweep
description: >
  Sweep the mailbox for voice memos and pull them into the journal. Use when the user asks to
  sweep/check for new journal memos, ingest voice memos, or runs /journal-sweep. Looks for
  unread-or-not mail whose subject starts with "record-memo:" (configurable), downloads the
  audio attachment, transcribes it locally with whisper.cpp via `journal ingest audio`, and
  never modifies the mailbox (no read/flag/delete/send).
---

# journal-sweep

Pulls voice-memo emails into the journal. Runs on demand, not on a schedule.

## How memos arrive

You record a voice memo, then email it to yourself with the subject
`record-memo: <ISO timestamp>` (e.g. `record-memo: 2026-09-30T16:46:08+02:00`), one audio
attachment, no body. Email is read via `himalaya` (account `mailbox`) — see
`~/Work/omarchy/notes/email.md`. `envelope list`/`message read` run without a permission
prompt; anything containing "send" is denied outright.

## Steps

1. **Find the subject prefix.** Default `record-memo:`. If
   `~/.config/journal/config.toml` exists and sets `[memo] subject_prefix`, use that instead.

2. **List candidates.**
   ```
   himalaya envelope list -s 50 --json
   ```
   `envelope list --json` already includes a `message-id` field per envelope — no need for a
   separate `message read` just to get it. Keep envelopes whose `subject` starts with the
   prefix (case-insensitive). The text after the prefix, trimmed, is the entry's timestamp —
   pass it straight through as `--at` (it's already ISO, e.g. `2026-09-30T16:46:08+02:00`).

3. **Skip what's already in the journal.** For each candidate, by its `message-id`:
   ```
   journal ingest seen "<message-id>"
   ```
   Exit `0` → already ingested, skip (note it as skipped in the report). Exit `1` → not seen,
   continue to step 4.

4. **Download attachments** for each not-yet-seen candidate, into a fresh temp directory under
   your scratchpad (never the project or the real journal dir):
   ```
   himalaya attachment download <envelope-id> --dir <scratchpad>/sweep-<envelope-id>
   ```
   This does not mark the message read — nothing about this skill ever does. Filenames can
   contain spaces (e.g. `Audio Recording 2026-09-30 at 16.45.59.m4a`); quote them.

5. **Ingest each downloaded file**, by extension:
   - Audio (`.m4a .mp3 .wav .aac .caf .ogg .flac`):
     ```
     journal ingest audio "<file>" --at "<timestamp from subject>" --message-id "<message-id>"
     ```
   - Text (`.txt .vtt .srt`):
     ```
     journal ingest text "<file>" --at "<timestamp from subject>" --message-id "<message-id>"
     ```
   - No attachment but a non-empty body: use the body as the entry text instead —
     `journal new --source text --at "<timestamp>" --text "<body>"` (no `--message-id` support
     on `new`; rely on the envelope's `message-id` only mattering for the dedupe path above, so
     re-running the sweep will re-create this one — call this out in the report as a known gap
     rather than silently duplicating it every run).

   `ingest audio` exit codes: `0` ingested, `1` transcription failed (e.g. no model downloaded —
   report the exact error, don't retry), `2` file missing, `3` duplicate (a race with another
   sweep; treat like "skip, already there").

6. **Suggest tags.** From each newly ingested entry's transcript (the `body` field of the
   `ingest audio`/`ingest text` JSON output), suggest 2–5 relevant `#tags` and apply them:
   ```
   journal tag <entry-id> tag-one tag-two
   ```
   List what you applied in the report so the user can correct them.

7. **Clean up** the scratchpad download directory once its files are ingested.

8. **Report**, grouped by outcome: ingested (with entry ids and the tags you applied), skipped
   as duplicate, failed (with the reason). Keep it short — a few lines, not a transcript dump.

## Hard rules

- Never mark a message read, flag it, move it, or delete it.
- Never send mail — this skill only reads and downloads.
- Dedupe is entirely by `message-id` inside the journal (`journal ingest seen`); the mailbox
  itself is never touched to track what's been swept, so re-running this skill is always safe.
- If `journal ingest audio` fails because no whisper model is downloaded, say so plainly
  (`journal model download small`) rather than silently skipping the memo.

## First-run friction

Each `himalaya attachment download` and `journal ingest` call will prompt for permission until
allow-listed. If this skill gets used regularly, offer — don't just do — adding rules to
`~/.claude/settings.json`, e.g. `Bash(himalaya attachment download *)` and
`Bash(journal ingest *)`.
