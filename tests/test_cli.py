import json

import pytest

from journal.cli import main


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
