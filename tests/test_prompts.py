import json
from datetime import date
from pathlib import Path

import pytest

from journal import prompts
from journal.cli import main


def test_strip_scissors_removes_the_marker_and_everything_after():
    text = "my words\n" + prompts.draft_text("a question?")
    assert prompts.strip_scissors(text).strip() == "my words"
    assert prompts.strip_scissors("no marker here") == "no marker here"


def test_pick_is_stable_within_a_day_and_rejects_unknown_sets():
    day = date(2026, 10, 4)
    assert prompts.pick("today", day) == prompts.pick("today", day)
    with pytest.raises(ValueError, match="available"):
        prompts.pick("nope", day)


def test_config_sets_extend_and_override_builtins():
    day = date(2026, 10, 4)
    assert prompts.pick("mine", day, {"mine": ["custom?"]}) == "custom?"
    assert prompts.pick("today", day, {"today": ["overridden?"]}) == "overridden?"


def test_prompt_is_shown_in_the_draft_but_not_saved(capsys, monkeypatch):
    seen = []

    def fake_editor(command):
        path = Path(command[-1])
        seen.append(path.read_text())
        path.write_text("my answer\n" + path.read_text())  # user writes above the scissors line
        return 0

    monkeypatch.setattr("journal.cli.subprocess.call", fake_editor)

    assert main(["write", "--prompt", "hard"]) == 0
    assert prompts.SCISSORS in seen[0] and "15 minutes" in seen[0]
    entry_id = capsys.readouterr().out.split()[-1]
    main(["show", entry_id, "--json"])
    body = json.loads(capsys.readouterr().out)["body"]
    assert body.strip() == "my answer" and "15 minutes" not in body


def test_prompt_only_draft_aborts_as_empty(capsys, monkeypatch):
    monkeypatch.setattr("journal.cli.subprocess.call", lambda command: 0)  # leaves the draft as-is

    assert main(["new", "--editor", "--prompt"]) == 1
    assert "no entry created" in capsys.readouterr().err


def test_prompt_requires_editor_and_known_set(capsys):
    assert main(["new", "--text", "x", "--prompt"]) == 1
    assert main(["new", "--editor", "--prompt", "nope"]) == 1
    assert "unknown prompt set" in capsys.readouterr().err


def test_config_prompts_load(tmp_path, monkeypatch):
    from journal.config import load_config

    cfg = tmp_path / "c.toml"
    cfg.write_text('[prompts]\nmine = ["one?", "two?"]\n')
    monkeypatch.setenv("JOURNAL_CONFIG", str(cfg))
    assert load_config().prompts == {"mine": ["one?", "two?"]}
