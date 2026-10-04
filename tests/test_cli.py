import json
from pathlib import Path

import pytest

from journal import store, transcribe
from journal.cli import main


def test_ingest_text_creates_entry(capsys, tmp_path):
    text_file = tmp_path / "transcript.txt"
    text_file.write_text("pulled in from a file #ingested")

    assert main(["ingest", "text", str(text_file), "--json"]) == 0
    entry = json.loads(capsys.readouterr().out)

    assert entry["source"] == "text"
    assert "ingested" in entry["tags"]


def test_ingest_text_missing_file_returns_exit_code_2(capsys):
    assert main(["ingest", "text", "/no/such/file.txt"]) == 2


def test_ingest_text_duplicate_message_id_returns_exit_code_3(capsys, tmp_path):
    text_file = tmp_path / "transcript.txt"
    text_file.write_text("first")

    main(["ingest", "text", str(text_file), "--message-id", "<dup@mail>"])
    capsys.readouterr()

    assert main(["ingest", "text", str(text_file), "--message-id", "<dup@mail>"]) == 3


def test_ingest_seen_reports_true_and_exit_0_when_ingested(capsys, tmp_path):
    text_file = tmp_path / "transcript.txt"
    text_file.write_text("body")
    main(["ingest", "text", str(text_file), "--message-id", "<found@mail>"])
    capsys.readouterr()

    assert main(["ingest", "seen", "<found@mail>"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["seen"] is True
    assert "id" in payload


def test_ingest_seen_reports_false_and_exit_1_when_not_ingested(capsys):
    assert main(["ingest", "seen", "<never@mail>"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"seen": False}


def test_ingest_audio_transcribes_and_creates_entry(capsys, tmp_path, monkeypatch, journal_dir):
    transcribe.models_dir().mkdir(parents=True)
    (transcribe.models_dir() / "ggml-small.bin").write_bytes(b"fake model")

    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio")

    monkeypatch.setattr(
        "journal.ingest.transcribe_audio", lambda path, *, model, language: "a transcribed memo"
    )

    assert main(["ingest", "audio", str(audio_file), "--json"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["source"] == "memo"
    assert entry["body"].strip() == "a transcribed memo"
    assert entry["audio"] == f"audio/{entry['id']}.m4a"


def test_ingest_audio_missing_model_returns_exit_1_with_clear_message(capsys, tmp_path, journal_dir):
    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio")

    assert main(["ingest", "audio", str(audio_file)]) == 1
    assert "isn't downloaded" in capsys.readouterr().err


def test_model_list_shows_all_known_models(capsys, journal_dir):
    assert main(["model", "list", "--json"]) == 0
    models = json.loads(capsys.readouterr().out)
    assert {m["name"] for m in models} == set(transcribe.KNOWN_MODELS)
    assert all(m["downloaded"] is False for m in models)


def test_model_download_writes_file(capsys, journal_dir, monkeypatch):
    class FakeResponse:
        headers = {"Content-Length": "5"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b""

    monkeypatch.setattr("journal.transcribe.urllib.request.urlopen", lambda url: FakeResponse())

    assert main(["model", "download", "tiny"]) == 0
    out = capsys.readouterr().out
    assert "downloaded tiny" in out
    assert (transcribe.models_dir() / "ggml-tiny.bin").exists()


def test_new_accepts_natural_language_at(capsys):
    assert main(["new", "--at", "yesterday", "--text", "backfilled", "--json"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["created"]  # parsed to *some* valid ISO timestamp, not rejected


def test_new_editor_composes_entry_from_editor_content(capsys, monkeypatch, journal_dir):
    def fake_editor(path):
        with open(path, "w") as f:
            f.write("written in the editor #composed\n")
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: fake_editor(command[-1]))

    assert main(["new", "--editor", "--json"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["body"].strip() == "written in the editor #composed"
    assert entry["tags"] == ["composed"]


def test_new_editor_passes_a_markdown_tmpfile_to_editor_command(capsys, monkeypatch, journal_dir):
    calls = []

    def fake_call(command):
        calls.append(command)
        Path(command[-1]).write_text("content\n")
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", fake_call)
    monkeypatch.setenv("EDITOR", "nvim --clean")

    assert main(["new", "--editor"]) == 0
    assert calls[0][:2] == ["nvim", "--clean"]
    assert calls[0][-1].endswith(".txt")


def test_new_editor_empty_file_aborts_without_creating_entry(capsys, monkeypatch, journal_dir):
    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: 0)  # editor writes nothing

    assert main(["new", "--editor"]) == 1
    assert "no entry created" in capsys.readouterr().err
    assert main(["list"]) == 0
    assert capsys.readouterr().out == ""


def test_new_editor_temp_file_is_cleaned_up(monkeypatch, journal_dir):
    seen_path = {}

    def fake_call(command):
        seen_path["path"] = Path(command[-1])
        seen_path["path"].write_text("hello\n")
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", fake_call)

    main(["new", "--editor"])
    assert not seen_path["path"].exists()


def test_no_subcommand_opens_editor_same_as_new_editor(capsys, monkeypatch, journal_dir):
    monkeypatch.setattr(
        "journal.cli.subprocess.call",
        lambda command: Path(command[-1]).write_text("from bare journal\n"),
    )

    assert main([]) == 0
    entry_id = capsys.readouterr().out.split()[-1]

    assert main(["show", entry_id, "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["body"].strip() == "from bare journal"


def test_write_subcommand_is_the_same_as_new_editor(capsys, monkeypatch, journal_dir):
    monkeypatch.setattr(
        "journal.cli.subprocess.call",
        lambda command: Path(command[-1]).write_text("from journal write\n"),
    )

    assert main(["write"]) == 0
    entry_id = capsys.readouterr().out.split()[-1]

    assert main(["show", entry_id, "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["body"].strip() == "from journal write"


def test_list_since_accepts_natural_language(capsys):
    main(["new", "--text", "today's entry"])
    capsys.readouterr()

    assert main(["list", "--since", "today"]) == 0
    out = capsys.readouterr().out
    assert "[cli]" in out


def test_bad_date_returns_clean_error_not_traceback(capsys):
    rc = main(["list", "--since", "not a real date, sorry"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "could not parse" in err


def test_new_and_show_json(capsys):
    assert main(["new", "--text", "hello #test", "--json"]) == 0
    created = json.loads(capsys.readouterr().out)

    assert main(["show", created["id"], "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)

    assert shown["body"].strip() == "hello #test"
    assert shown["tags"] == ["test"]


def test_new_reads_stdin_when_no_text(monkeypatch, capsys):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("typed from stdin"))
    assert main(["new"]) == 0
    entry_id = capsys.readouterr().out.split()[-1]

    assert main(["show", entry_id, "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["body"].strip() == "typed from stdin"


def test_show_missing_entry_returns_exit_code_2(capsys):
    assert main(["show", "2026-01-01T000000"]) == 2


def test_list_plain_output_shows_source(capsys):
    main(["new", "--text", "a"])
    capsys.readouterr()

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "[cli]" in out


def test_list_plain_output_shows_body_preview_when_no_title(capsys):
    main(["new", "--text", "Had a great run this morning along the river #running"])
    capsys.readouterr()

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "Had a great run this morning along the river" in out


def test_list_plain_output_prefers_title_over_preview(capsys):
    main(["new", "--title", "Morning Run", "--text", "completely different body text"])
    capsys.readouterr()

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "Morning Run" in out
    assert "completely different body text" not in out


def test_search_with_only_tag_finds_entry_without_a_query(capsys):
    main(["new", "--text", "morning run #running"])
    main(["new", "--text", "quiet evening #reading"])
    capsys.readouterr()

    assert main(["search", "--tag", "running"]) == 0
    out = capsys.readouterr().out
    assert "morning run" in out
    assert "quiet evening" not in out


def test_search_plain_output_header_shows_preview(capsys):
    main(["new", "--title", "Trail Day", "--text", "a coffee stop on the trail #coffee"])
    capsys.readouterr()

    assert main(["search", "coffee"]) == 0
    out = capsys.readouterr().out
    first_line = out.splitlines()[0]
    assert "Trail Day" in first_line


def test_search_with_no_query_and_no_filters_returns_usage_error(capsys):
    assert main(["search"]) == 1
    assert "needs a query" in capsys.readouterr().err


def test_search_regex_without_query_returns_usage_error(capsys):
    assert main(["search", "--regex"]) == 1
    assert "--regex needs a query" in capsys.readouterr().err


def test_list_on_exact_date(capsys):
    main(["new", "--at", "2026-09-30T08:00:00+02:00", "--text", "today"])
    main(["new", "--at", "2026-10-01T08:00:00+02:00", "--text", "tomorrow"])
    capsys.readouterr()

    assert main(["list", "--on", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "2026-09-30T080000" in out
    assert "2026-10-01T080000" not in out


def test_list_exclude_tag(capsys):
    main(["new", "--text", "a #work"])
    main(["new", "--text", "b #personal"])
    capsys.readouterr()

    assert main(["list", "--exclude-tag", "work"]) == 0
    out = capsys.readouterr().out
    assert out.count("[cli]") == 1


def test_list_untagged(capsys):
    main(["new", "--text", "no tags"])
    main(["new", "--text", "#work tagged"])
    capsys.readouterr()

    assert main(["list", "--untagged"]) == 0
    out = capsys.readouterr().out
    assert out.count("[cli]") == 1


def test_on_this_day_groups_by_year(capsys):
    main(["new", "--at", "2025-09-30T09:00:00+02:00", "--text", "last year"])
    main(["new", "--at", "2024-09-30T09:00:00+02:00", "--text", "two years ago"])
    main(["new", "--at", "2025-10-01T09:00:00+02:00", "--text", "wrong day"])
    capsys.readouterr()

    assert main(["on-this-day", "--date", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "2025:" in out
    assert "2024:" in out
    assert "2025-09-30T090000" in out
    assert "2025-10-01T090000" not in out
    assert out.index("2025:") < out.index("2024:")
    assert "last year" in out
    assert "two years ago" in out


def test_on_this_day_no_matches(capsys):
    assert main(["on-this-day", "--date", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "nothing written" in out


def test_on_this_day_json(capsys):
    main(["new", "--at", "2025-09-30T09:00:00+02:00", "--text", "last year #work"])
    capsys.readouterr()

    assert main(["on-this-day", "--date", "2026-09-30", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["tags"] == ["work"]


def test_tag_command_appends_and_reports(capsys):
    main(["new", "--text", "no tags yet", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    assert main(["tag", entry_id, "gratitude", "focus"]) == 0
    capsys.readouterr()

    main(["show", entry_id, "--json"])
    shown = json.loads(capsys.readouterr().out)
    assert set(shown["tags"]) == {"gratitude", "focus"}


def test_path_prints_data_dir(capsys, journal_dir):
    assert main(["path"]) == 0
    assert capsys.readouterr().out.strip() == str(journal_dir)


def test_top_level_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "journal" in capsys.readouterr().out


def test_subcommand_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["new", "--help"])
    assert exc.value.code == 0


def test_delete_moves_entry_and_reports(capsys, journal_dir):
    main(["new", "--text", "gone soon", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    assert main(["delete", entry_id]) == 0
    out = capsys.readouterr().out
    assert entry_id in out
    assert "trash" in out

    assert main(["show", entry_id]) == 2


def test_delete_missing_returns_exit_code_2(capsys):
    assert main(["delete", "2026-01-01T000000"]) == 2


def test_edit_missing_returns_exit_code_2(capsys):
    assert main(["edit", "2026-01-01T000000"]) == 2


def test_edit_invokes_editor_on_the_body_only_and_sets_updated(monkeypatch, capsys, journal_dir):
    main(["new", "--text", "before edit", "--title", "kept", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    calls = []

    def fake_call(command):
        calls.append((command, Path(command[-1]).read_text()))
        with open(command[-1], "a") as f:
            f.write("added by the editor #edited\n")
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", fake_call)
    monkeypatch.setenv("EDITOR", "nvim --clean")

    assert main(["edit", entry_id]) == 0
    assert capsys.readouterr().out.strip() == f"edited {entry_id}"

    command, seen = calls[0]
    assert command[:2] == ["nvim", "--clean"]
    assert "---" not in seen and "created:" not in seen  # no frontmatter exposed
    assert seen.strip() == "before edit"

    main(["show", entry_id, "--json"])
    shown = json.loads(capsys.readouterr().out)
    assert "edited" in shown["tags"]
    assert shown["title"] == "kept"
    assert shown["updated"] is not None


def test_edit_with_no_changes_leaves_updated_none(monkeypatch, capsys, journal_dir):
    main(["new", "--text", "untouched", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: 0)

    assert main(["edit", entry_id]) == 0
    out = capsys.readouterr().out
    assert "no changes" in out

    main(["show", entry_id, "--json"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["updated"] is None


def test_edit_emptied_body_is_refused_and_entry_untouched(monkeypatch, capsys, journal_dir):
    main(["new", "--text", "keep me", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: Path(command[-1]).write_text(""))

    assert main(["edit", entry_id]) == 1
    assert "journal delete" in capsys.readouterr().err
    main(["show", entry_id, "--json"])
    assert json.loads(capsys.readouterr().out)["body"].strip() == "keep me"


def test_new_bad_at_fails_before_opening_the_editor(capsys, monkeypatch, journal_dir):
    calls = []
    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: calls.append(command))

    assert main(["new", "--editor", "--at", "next blursday"]) == 1
    assert calls == []


def test_failed_save_keeps_the_draft_and_the_next_write_resumes_it(capsys, monkeypatch, journal_dir):
    monkeypatch.setattr(
        "journal.cli.subprocess.call",
        lambda command: Path(command[-1]).write_text("precious words\n"),
    )

    def boom(**kwargs):
        raise OSError("disk full")

    real_create = store.create
    monkeypatch.setattr("journal.cli.store.create", boom)
    with pytest.raises(OSError):
        main(["new", "--editor"])
    assert len(store.list_drafts()) == 1

    monkeypatch.setattr("journal.cli.store.create", real_create)
    seen = []

    def resume(command):
        seen.append(Path(command[-1]).read_text())
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", resume)
    assert main(["new", "--editor", "--json"]) == 0
    captured = capsys.readouterr()
    assert seen == ["precious words\n"]
    assert "resuming an unsaved draft" in captured.err
    assert json.loads(captured.out)["body"].strip() == "precious words"
    assert store.list_drafts() == []


def _make(at, body="x"):
    main(["new", "--at", at, "--text", body, "--json"])


def test_show_accepts_last_today_and_unique_prefix(capsys):
    _make("2026-09-30T08:00:00+02:00", "older")
    _make("2026-10-01T09:00:00+02:00", "newer")
    capsys.readouterr()

    for ref, expected in (("last", "newer"), ("2026-09-30", "older"), ("2026-10-01T0900", "newer")):
        assert main(["show", ref, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["body"].strip() == expected


def test_today_ref_means_newest_entry_written_today(capsys):
    _make("2026-09-30T08:00:00+02:00")
    capsys.readouterr()
    assert main(["show", "today"]) == 2  # nothing written today


def test_ambiguous_prefix_lists_candidates_and_exits_1(capsys):
    _make("2026-09-30T08:00:00+02:00")
    _make("2026-09-30T09:00:00+02:00")
    capsys.readouterr()

    assert main(["show", "2026-09-30"]) == 1
    err = capsys.readouterr().err
    assert "matches 2 entries" in err and "2026-09-30T080000" in err and "2026-09-30T090000" in err


def test_unknown_ref_exits_2_and_empty_journal_has_no_last(capsys):
    assert main(["show", "last"]) == 2
    assert main(["delete", "2026-01"]) == 2


def test_edit_without_id_edits_the_last_entry(monkeypatch, capsys):
    _make("2026-09-30T08:00:00+02:00", "old")
    _make("2026-10-01T09:00:00+02:00", "new")
    capsys.readouterr()
    monkeypatch.setattr("journal.cli.shutil.which", lambda name: None)  # no fzf
    monkeypatch.setattr(
        "journal.cli.subprocess.call", lambda command: Path(command[-1]).write_text("new, revised\n")
    )

    assert main(["edit"]) == 0
    captured = capsys.readouterr()
    assert "using the last entry" in captured.err
    main(["show", "last", "--json"])
    assert json.loads(capsys.readouterr().out)["body"].strip() == "new, revised"


def test_tag_and_delete_accept_refs(capsys):
    _make("2026-09-30T08:00:00+02:00")
    capsys.readouterr()
    assert main(["tag", "last", "x"]) == 0
    assert main(["delete", "2026-09-30"]) == 0


def test_add_joins_words_and_appends_tags(capsys):
    assert main(["add", "had", "coffee", "with", "Sam", "-t", "friends", "-t", "#morning", "--json"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["body"].splitlines()[0] == "had coffee with Sam"
    assert entry["tags"] == ["friends", "morning"]
    assert entry["source"] == "cli"


def test_add_does_not_duplicate_a_tag_already_in_the_text(capsys):
    main(["add", "quoted #friends text", "-t", "friends", "--json"])
    assert json.loads(capsys.readouterr().out)["body"].count("#friends") == 1


def test_add_reads_stdin_without_words_and_refuses_empty(monkeypatch, capsys):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("from a pipe"))
    assert main(["add", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["body"].strip() == "from a pipe"

    monkeypatch.setattr("sys.stdin", io.StringIO("  \n"))
    assert main(["add"]) == 1


def test_status_empty_journal(capsys):
    assert main(["status"]) == 0
    assert capsys.readouterr().out.strip() == "no entries yet"
    assert main(["status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "last_entry_id": None,
        "last_entry_at": None,
        "days_since": None,
        "week_count": 0,
        "on_this_day_count": 0,
    }


def test_status_reports_last_entry_week_count_and_on_this_day(capsys):
    from datetime import datetime, timedelta, timezone

    from journal.cli import _status

    now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    for at in ("2026-10-01T08:00:00+00:00", "2026-09-10T08:00:00+00:00", "2025-10-04T08:00:00+00:00"):
        main(["new", "--at", at, "--text", "x"])
    capsys.readouterr()

    status = _status(now)
    assert status["last_entry_id"] == "2026-10-01T080000"
    assert status["days_since"] == 3
    assert status["week_count"] == 1
    assert status["on_this_day_count"] == 1


def test_status_plain_output(capsys):
    from datetime import datetime, timedelta

    main(["new", "--at", (datetime.now().astimezone() - timedelta(days=3)).isoformat(), "--text", "x"])
    capsys.readouterr()
    main(["status"])
    out = capsys.readouterr().out
    assert "last entry: 3 days ago" in out and "this week: 1 entry" in out


def test_help_documents_new_behaviour(capsys):
    def help_of(*argv):
        with pytest.raises(SystemExit):
            main([*argv, "--help"])
        return " ".join(capsys.readouterr().out.split())

    assert "journal config list" in help_of() and "journal docs" in help_of()
    assert "frontmatter" in help_of("edit") and "fzf" in help_of("edit")
    assert "--raw" in help_of("show") or "raw" in help_of("show")
    assert "on_this_day_count" in help_of("status")
    assert "review" in help_of("write") and "#review" in help_of("review")
