import json
from pathlib import Path

import pytest

from journal import transcribe
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
    assert calls[0][-1].endswith(".md")


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


def test_edit_invokes_editor_appends_content_and_sets_updated(monkeypatch, capsys, journal_dir):
    main(["new", "--text", "before edit", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    calls = []

    def fake_call(command):
        calls.append(command)
        with open(command[-1], "a") as f:
            f.write("added by the editor #edited\n")
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", fake_call)
    monkeypatch.setenv("EDITOR", "nvim --clean")

    assert main(["edit", entry_id]) == 0
    out = capsys.readouterr().out
    assert out.strip() == f"edited {entry_id}"

    assert len(calls) == 1
    command = calls[0]
    assert command[:2] == ["nvim", "--clean"]
    assert command[-1].endswith(f"{entry_id}.md")

    main(["show", entry_id, "--json"])
    shown = json.loads(capsys.readouterr().out)
    assert "edited" in shown["tags"]
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


def test_edit_reports_corruption_without_reverting(monkeypatch, capsys, journal_dir):
    main(["new", "--text", "before edit", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    def corrupt_the_file(command):
        path = command[-1]
        with open(path, "w") as f:
            f.write("no frontmatter here")
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", corrupt_the_file)

    assert main(["edit", entry_id]) == 1
    err = capsys.readouterr().err
    assert "may be corrupted" in err
