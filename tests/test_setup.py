import json

from journal import setup
from journal.cli import main


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_check_json_shape_and_checks(capsys, monkeypatch):
    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: f"/usr/bin/{name}")

    code, out, _ = run(capsys, "setup", "--check", "--json")
    report = json.loads(out)
    assert code == 0
    assert set(report) == {"checks", "data_dir", "config_path", "config_exists", "entries"}
    names = [c["name"] for c in report["checks"]]
    assert names[:6] == ["editor", "git", "fzf", "pager", "ffmpeg", "whisper-cli"]
    assert names[6].startswith("whisper model")
    assert all(set(c) == {"name", "found", "detail", "needed_for", "hint"} for c in report["checks"])
    assert report["entries"] == 0 and report["config_exists"] is False


def test_missing_tools_are_reported_with_what_they_enable(capsys, monkeypatch):
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: None)
    monkeypatch.setattr("journal.cli.shutil.which", lambda name: None)
    monkeypatch.setenv("EDITOR", "no-such-editor")

    report = json.loads(run(capsys, "setup", "--check", "--json")[1])
    by_name = {c["name"]: c for c in report["checks"]}
    assert not by_name["editor"]["found"] and "EDITOR" in by_name["editor"]["hint"]
    assert not by_name["git"]["found"] and "history" in by_name["git"]["needed_for"]
    assert not by_name["whisper-cli"]["found"] and "voice memos" in by_name["whisper-cli"]["needed_for"]


def test_check_counts_entries(capsys):
    main(["add", "one"])
    main(["add", "two", "--at", "2026-01-01T08:00:00+00:00"])
    capsys.readouterr()
    assert json.loads(run(capsys, "setup", "--check", "--json")[1])["entries"] == 2


def test_plain_check_output(capsys, monkeypatch):
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: None if name == "fzf" else f"/usr/bin/{name}")
    out = run(capsys, "setup", "--check")[1]
    assert "Your setup:" in out and "missing  fzf" in out and "ok       git" in out
    assert "journal folder:" in out and "not created yet" in out


def test_setup_without_a_terminal_refuses_and_points_to_alternatives(capsys):
    code, _, err = run(capsys, "setup")  # pytest's stdin/stdout are not terminals
    assert code == 1 and "needs a terminal" in err and "config set" in err
    assert run(capsys, "setup", "--json")[0] == 1
