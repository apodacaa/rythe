import json
from datetime import datetime, timedelta
from pathlib import Path

from journal import prompts, store
from journal.cli import main


def _fake_editor(monkeypatch, answer="what I make of it\n"):
    seen = []

    def call(command):
        path = Path(command[-1])
        seen.append(path.read_text())
        path.write_text(answer + path.read_text())
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", call)
    return seen


def test_review_shows_the_week_then_saves_a_titled_tagged_entry(capsys, monkeypatch):
    now = datetime.now().astimezone()
    store.create(created=now - timedelta(days=2), body="monday stuff")
    store.create(created=now - timedelta(days=20), body="long ago")
    seen = _fake_editor(monkeypatch)

    assert main(["review", "--no-pager"]) == 0
    out = capsys.readouterr().out
    assert "monday stuff" in out and "long ago" not in out
    assert prompts.SCISSORS in seen[0] and "next step" in seen[0]

    main(["list", "--tag", "review", "--json"])
    (entry,) = json.loads(capsys.readouterr().out)
    start = (now - timedelta(days=6)).date()
    assert entry["title"] == f"Week of {start:%b} {start.day} – {now:%b} {now.day}"
    assert "review" in entry["tags"]
    assert entry["body"].startswith("what I make of it") and "next step" not in entry["body"]


def test_review_no_read_skips_the_period(capsys, monkeypatch):
    store.create(created=datetime.now().astimezone(), body="should not be printed")
    _fake_editor(monkeypatch)

    assert main(["review", "--no-read"]) == 0
    assert "should not be printed" not in capsys.readouterr().out


def test_review_custom_range_title_and_excludes_past_reviews(capsys, monkeypatch):
    store.create(created=datetime(2026, 9, 10, 9).astimezone(), body="entry in range")
    store.create(created=datetime(2026, 9, 11, 9).astimezone(), body="old reflection #review")
    _fake_editor(monkeypatch)

    assert main(["review", "--since", "2026-09-01", "--until", "2026-09-30", "--no-pager"]) == 0
    out = capsys.readouterr().out
    assert "entry in range" in out and "old reflection" not in out
    main(["list", "--tag", "review", "--json"])
    titles = [e["title"] for e in json.loads(capsys.readouterr().out)]
    assert "Review of Sep 1 – Sep 30" in titles


def test_empty_review_is_not_saved(capsys, monkeypatch):
    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: 0)

    assert main(["review", "--no-read"]) == 1
    assert "no entry created" in capsys.readouterr().err
