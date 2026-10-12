import json
from pathlib import Path

import pytest

from journal import setup, settings, transcribe, ui
from journal.config import config_path, load_raw
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
    assert names[:5] == ["editor", "fzf", "pager", "ffmpeg", "whisper-cli"]
    assert names[5].startswith("whisper model")
    assert all(set(c) == {"name", "found", "detail", "needed_for", "hint"} for c in report["checks"])
    assert report["entries"] == 0 and report["config_exists"] is False


def test_missing_tools_are_reported_with_what_they_enable(capsys, monkeypatch):
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: None)
    monkeypatch.setattr("journal.cli.shutil.which", lambda name: None)
    monkeypatch.setenv("EDITOR", "no-such-editor")

    report = json.loads(run(capsys, "setup", "--check", "--json")[1])
    by_name = {c["name"]: c for c in report["checks"]}
    assert not by_name["editor"]["found"] and "EDITOR" in by_name["editor"]["hint"]
    assert not by_name["fzf"]["found"] and "picker" in by_name["fzf"]["needed_for"]
    assert not by_name["whisper-cli"]["found"] and "voice memos" in by_name["whisper-cli"]["needed_for"]


def test_check_counts_entries(capsys):
    main(["add", "one"])
    main(["add", "two", "--at", "2026-01-01T08:00:00+00:00"])
    capsys.readouterr()
    assert json.loads(run(capsys, "setup", "--check", "--json")[1])["entries"] == 2


def test_plain_check_output(capsys, monkeypatch):
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: None if name == "fzf" else f"/usr/bin/{name}")
    out = run(capsys, "setup", "--check")[1]
    assert "Your setup" in out
    assert any("missing" in l and "fzf" in l for l in out.splitlines())
    assert any(" ok " in l and "ffmpeg" in l for l in out.splitlines())
    assert "journal folder:" in out and "not created yet" in out


class Session:
    """Scripted stand-in for a terminal: answers are consumed in order; running out acts like
    EOF (Ctrl-D), which the wizard must treat as a cancel."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []
        self.said = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def say(self, text):
        self.said.append(text)

    @property
    def text(self):
        return "\n".join(self.prompts + self.said)

    def run(self, **kw):
        return setup.run_wizard(self.ask, self.say, **kw)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake HOME with no JOURNAL_DIR, so the default data dir is inside tmp_path."""
    monkeypatch.delenv("JOURNAL_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: f"/usr/bin/{name}")
    return tmp_path


def test_accepting_every_default_changes_nothing(home):
    s = Session("", "", "", "")  # keep folder, resurface, no voice memos, no first entry
    assert s.run(start_entry=lambda: 0) == 0
    assert not config_path().exists()
    assert "Nothing to change" in s.text and "journal docs" in s.text


def test_changing_one_answer_writes_only_that_key(home):
    s = Session("", "n", "", "y", "")  # resurfacing off, no voice memos, then save
    assert s.run() == 0
    assert load_raw() == {"resurface": {"enabled": False}}
    line = next(l for l in s.text.splitlines() if "resurface.enabled" in l and "true" in l)
    assert "false" in line and ui.glyph("arrow") in line


ENTRY = Path("entries") / "2026" / "01" / "2026-01-01T080000.txt"


def _journal_with_one_entry(home) -> Path:
    old = home / ".local" / "share" / "journal"
    (old / ENTRY).parent.mkdir(parents=True)
    (old / ENTRY).write_text("---\ncreated: 2026-01-01T08:00:00+00:00\n---\nhi\n")
    return old


def test_bad_folder_is_asked_again_then_the_journal_moves_on_save(home):
    old = _journal_with_one_entry(home)
    new = home / "Documents" / "journal"

    s = Session("n", "relative/path", str(new), "", "", "", "y", "")  # ..., move (default yes), ...
    assert s.run() == 0
    assert "must be an absolute path" in s.text
    assert any("Move your journal (1 entry) there too? [Y/n]" in p for p in s.prompts)
    assert load_raw() == {"storage": {"dir": str(new)}}
    assert (new / ENTRY).exists() and not old.exists()
    assert "Moved your journal" in s.text and "journal folder moves from" in s.text


def test_nothing_moves_when_the_final_save_is_declined(home):
    old = _journal_with_one_entry(home)
    new = home / "Documents" / "journal"
    s = Session("n", str(new), "", "", "", "n", "")
    assert s.run() == 0
    assert (old / ENTRY).exists() and not new.exists() and not config_path().exists()


def test_declining_the_move_leaves_the_entries_and_says_how_to_copy_them(home):
    old = _journal_with_one_entry(home)
    new = home / "Documents" / "journal"
    s = Session("n", str(new), "n", "", "", "y", "")
    assert s.run() == 0
    assert load_raw() == {"storage": {"dir": str(new)}}
    assert (old / ENTRY).exists()
    assert f"cp -a {old}/. {new}/" in s.text  # works whether or not the new folder exists yet


def test_a_folder_that_already_has_files_is_used_as_is_and_nothing_moves(home):
    old = _journal_with_one_entry(home)
    new = home / "Documents" / "journal"
    (new / "entries").mkdir(parents=True)
    s = Session("n", str(new), "", "", "y", "")  # no move question this time
    assert s.run() == 0
    assert not any("Move your journal" in p for p in s.prompts)
    assert "already has files in it" in s.text and f"cp -a {old}/. {new}/" in s.text
    assert (old / ENTRY).exists() and load_raw() == {"storage": {"dir": str(new)}}


def test_a_failed_move_puts_the_folder_setting_back(home, monkeypatch):
    old = _journal_with_one_entry(home)
    new = home / "Documents" / "journal"

    def failing(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("journal.setup.shutil.move", failing)
    s = Session("n", str(new), "", "n", "", "y", "")  # move yes, resurfacing off, save
    assert s.run() == 0
    assert "Couldn't move your journal (disk full)" in s.text
    assert load_raw() == {"resurface": {"enabled": False}}  # the other answer is kept
    assert (old / ENTRY).exists()


def test_a_model_in_a_journal_that_is_moving_counts_as_downloaded(home):
    old = _journal_with_one_entry(home)
    (old / "models").mkdir()
    (old / "models" / "ggml-small.bin").write_bytes(b"x")
    new = home / "Documents" / "journal"
    calls, download = _downloads()
    s = Session("n", str(new), "", "", "", "", "", "y", "")  # move, resurface, voice (default yes), model, language, save
    assert s.run(download=download) == 0
    assert "already downloaded" in s.text and calls == []
    assert (new / "models" / "ggml-small.bin").exists()


def test_journal_dir_env_skips_the_folder_question(tmp_path, monkeypatch):
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: f"/usr/bin/{name}")
    s = Session("", "", "")  # resurface, voice, first entry (conftest sets JOURNAL_DIR)
    assert s.run(start_entry=lambda: 0) == 0
    assert "overrides the storage.dir setting" in s.text
    assert not any("Keep it here" in p for p in s.prompts)


def test_cancelling_before_the_summary_changes_nothing(home):
    s = Session("", "n")  # then EOF
    assert s.run() == 130
    assert "Nothing was changed" in s.text and not config_path().exists()


def test_declining_the_final_save_writes_nothing(home):
    s = Session("", "n", "", "n", "")
    assert s.run() == 0
    assert "Nothing was saved" in s.text and not config_path().exists()


def test_rerun_shows_current_values_as_the_defaults(home):
    main(["config", "set", "resurface.enabled", "false"])
    s = Session("", "", "", "")
    s.run()
    assert any("Show an older entry after I save one? [y/N]" in p for p in s.prompts)
    assert load_raw() == {"resurface": {"enabled": False}}  # unchanged by accepting defaults


def test_stopping_after_the_save_does_not_claim_nothing_changed(home):
    s = Session("", "n", "", "y")  # saved, then EOF at the first-entry question
    assert s.run(start_entry=lambda: 0) == 130
    assert load_raw() == {"resurface": {"enabled": False}}
    assert "already saved" in s.text and "Nothing was changed" not in s.text


def test_the_closing_question_only_says_first_entry_for_an_empty_journal(home):
    s = Session("", "", "", "")
    s.run(start_entry=lambda: 0)
    assert any("Write your first entry now?" in p for p in s.prompts)

    _journal_with_one_entry(home)
    s = Session("", "", "", "")
    s.run(start_entry=lambda: 0)
    assert any("Write an entry now?" in p for p in s.prompts)
    assert not any("first entry" in p for p in s.prompts)


def test_an_entry_written_from_the_wizard_gets_no_setup_tip(capsys, monkeypatch):
    import sys

    monkeypatch.setattr("journal.cli._interactive", lambda: True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("journal.setup.run_wizard", lambda start_entry: main(["add", "first, from setup"]))

    assert main(["setup"]) == 0
    assert "journal setup" not in capsys.readouterr().out
    assert not config_path().exists()


def test_first_entry_is_offered_and_started_on_yes(home):
    started = []
    Session("", "", "", "y").run(start_entry=lambda: started.append(1) or 0)
    assert started == [1]
    started.clear()
    Session("", "", "", "n").run(start_entry=lambda: started.append(1) or 0)
    assert started == []


def test_every_key_the_wizard_asks_about_is_in_the_registry():
    for key in setup.WIZARD_KEYS:
        assert settings.lookup(key) is not None, key


def test_setup_without_a_terminal_refuses_and_points_to_alternatives(capsys):
    code, _, err = run(capsys, "setup")  # pytest's stdin/stdout are not terminals
    assert code == 1 and "needs a terminal" in err and "config set" in err
    assert run(capsys, "setup", "--json")[0] == 1


def test_every_builtin_prompt_set_has_a_one_line_summary():
    from journal import prompts

    assert set(prompts.BUILTIN) == set(prompts.SUMMARIES)


def _downloads():
    calls = []
    return calls, lambda model: calls.append((model, config_path().exists()))


def test_voice_memo_answers_are_saved_and_download_can_be_declined(home):
    calls, download = _downloads()
    s = Session("", "", "y", "medium", "auto", "n", "y", "")  # ... model, language, no download, save
    assert s.run(download=download) == 0
    assert load_raw() == {"transcribe": {"model": "medium", "language": "auto"}}
    assert calls == []
    assert "~1.5 GB" in s.text and "~470 MB" in s.text  # sizes are shown before choosing


def test_download_runs_after_the_config_is_saved_in_the_new_folder(home):
    calls, download = _downloads()
    new = home / "Documents" / "journal"
    s = Session("n", str(new), "", "y", "", "", "y", "y", "")  # folder, voice(small, en), download, save
    assert s.run(download=download) == 0
    assert calls == [("small", True)]  # config already written when the download starts
    assert load_raw()["storage"]["dir"] == str(new)


def test_download_is_skipped_when_a_new_folder_was_not_saved(home):
    calls, download = _downloads()
    new = home / "elsewhere"
    s = Session("n", str(new), "", "y", "", "", "y", "n", "")  # ... download yes, save NO
    s.run(download=download)
    assert calls == [] and "Skipped the small download" in s.text


def test_already_downloaded_model_is_not_offered_again(home):
    model = home / ".local" / "share" / "journal" / "models" / "ggml-small.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"x")
    calls, download = _downloads()
    s = Session("", "", "y", "", "", "")  # voice yes, defaults, then first entry
    s.run(download=download)
    assert "already downloaded" in s.text and calls == []
    assert not any("Download the" in p for p in s.prompts)


def test_bad_model_and_language_are_asked_again(home):
    s = Session("", "", "y", "gigantic", "tiny", "english", "ES", "n", "y", "")
    s.run(download=_downloads()[1])
    assert "must be one of" in s.text and "short language code" in s.text
    assert load_raw() == {"transcribe": {"model": "tiny", "language": "es"}}


def test_config_set_checks_the_language_the_same_way_the_wizard_does(capsys):
    code, _, err = run(capsys, "config", "set", "transcribe.language", "english")
    assert code == 1 and "short language code" in err
    assert run(capsys, "config", "set", "transcribe.language", "DE")[0] == 0
    assert load_raw() == {"transcribe": {"language": "de"}}


def test_voice_memo_defaults_follow_what_is_already_there(home):
    s = Session("", "", "y", "", "", "", "")  # voice yes, model, language, download (default), first entry
    calls, download = _downloads()
    s.run(download=download)
    assert any("Will you use voice memos? [y/N]" in p for p in s.prompts)
    assert any("Download the small model now" in p and "[Y/n]" in p for p in s.prompts)
    assert calls == [("small", False)]

    model = home / ".local" / "share" / "journal" / "models" / "ggml-small.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"x")
    s = Session("", "", "", "", "", "")
    s.run(download=download)
    assert any("Will you use voice memos? [Y/n]" in p for p in s.prompts)


def test_missing_voice_tools_are_explained(home, monkeypatch):
    monkeypatch.setattr("journal.setup.shutil.which", lambda name: None if name in ("ffmpeg", "whisper-cli") else "/x")
    s = Session("", "", "y", "", "", "n", "")
    s.run(download=_downloads()[1])
    assert "ffmpeg not found" in s.text and "whisper-cli not found" in s.text


def test_failed_download_is_reported_and_setup_carries_on(home):
    from journal.transcribe import TranscribeError

    def failing(model):
        raise TranscribeError("network down")

    s = Session("", "", "y", "", "", "y", "", "")
    assert s.run(download=failing) == 0
    assert "network down" in s.text and "journal model download small" in s.text


def test_saying_no_to_voice_memos_asks_nothing_more(home):
    s = Session("", "", "", "")
    s.run()
    assert not any("Which model" in p for p in s.prompts)


def test_first_entry_gets_a_one_time_setup_tip(capsys, monkeypatch):
    monkeypatch.setattr("journal.cli._interactive", lambda: True)

    main(["add", "my first entry"])
    assert "journal setup" in capsys.readouterr().out

    main(["add", "my second entry"])
    assert "journal setup" not in capsys.readouterr().out


def test_no_tip_once_a_config_file_exists_or_with_json_or_when_piped(capsys, monkeypatch):
    monkeypatch.setattr("journal.cli._interactive", lambda: True)
    main(["config", "set", "resurface.enabled", "true"])  # creates the config file
    capsys.readouterr()
    main(["add", "first, but configured"])
    assert "journal setup" not in capsys.readouterr().out


def test_no_tip_with_json_or_non_terminal(capsys, monkeypatch):
    monkeypatch.setattr("journal.cli._interactive", lambda: True)
    main(["add", "x", "--json"])
    assert "journal setup" not in capsys.readouterr().out


def test_docs_describe_setup_for_people_and_agents():
    from journal import docs

    assert "journal setup" in docs.render_topic("overview")
    assert "journal setup --check" in docs.render_topic("agents")
    json_doc = docs.render_topic("json")
    for key in setup.environment_report():
        assert f'"{key}"' in json_doc, key


def test_every_whisper_model_has_a_plain_language_note():
    from journal import transcribe

    assert set(transcribe.MODEL_NOTES) == set(transcribe.KNOWN_MODELS)
    assert transcribe.RECOMMENDED_MODEL in transcribe.KNOWN_MODELS


def test_model_list_in_the_wizard_explains_each_model_and_marks_downloaded(home):
    from journal import transcribe

    present = home / ".local" / "share" / "journal" / "models" / "ggml-base.bin"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"x")

    s = Session("", "", "y", "", "", "n", "")
    s.run(download=_downloads()[1])
    for name, note in transcribe.MODEL_NOTES.items():
        assert note in s.text, name
    assert "[recommended]" in s.text and "[downloaded]" in s.text
    line = next(l for l in s.text.splitlines() if "base" in l and transcribe.MODEL_NOTES["base"] in l)
    assert "[downloaded]" in line


def test_declining_a_download_says_how_to_do_it_later(home):
    s = Session("", "", "y", "medium", "", "n", "")
    s.run(download=_downloads()[1])
    assert "journal model download medium" in s.text


def test_wizard_is_styled_when_color_is_on_and_plain_text_underneath(home):
    ui.set_color(True)
    s = Session("", "n", "", "y", "")
    s.run()
    assert "\x1b[" in s.text  # styled
    plain = ui.strip_ansi(s.text)
    assert "J O U R N A L   S E T U P" in plain and "1/3  WHERE SHOULD YOUR JOURNAL LIVE?" in plain
    assert "WRITING PROMPTS" in plain and "You're set" in plain
    assert "Saved to" in plain

    lines = plain.splitlines()
    top = next(i for i, l in enumerate(lines) if "Here's what will change" in l)
    bottom = next(i for i in range(top, len(lines)) if lines[i].startswith(ui.glyph("box")[2]))
    assert len({len(l) for l in lines[top : bottom + 1]}) == 1  # the summary box is a clean rectangle


def test_wizard_has_no_escape_codes_when_color_is_off(home):
    ui.set_color(False)
    s = Session("", "", "", "")
    s.run()
    assert "\x1b" not in s.text and "\x01" not in s.text


def test_only_the_steps_that_ask_something_are_numbered(home):
    s = Session("", "", "", "")
    s.run()
    plain = s.text
    positions = [plain.index(f"{n}/3") for n in range(1, 4)] + [plain.index("WRITING PROMPTS")]
    assert positions == sorted(positions)
    assert "4/" not in plain
