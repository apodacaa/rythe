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
