import json
from dataclasses import fields

import pytest

from journal import prompts, settings
from journal.cli import main
from journal.config import Config, config_path, load_config, load_raw


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_registry_covers_every_config_field_and_nothing_else():
    registered = {s.key for s in settings.SETTINGS}
    declared = set()
    for section in fields(Config):
        if section.name == "prompts":
            continue
        for f in fields(section.default_factory()):
            declared.add(f"{section.name}.{f.name}")
    assert registered == declared  # add a Setting when you add a field, and vice versa


def test_registry_defaults_match_the_dataclass_defaults():
    config = load_config()
    for s in settings.SETTINGS:
        section, name = s.key.split(".")
        assert getattr(getattr(config, section), name) == s.default, s.key


def test_list_defaults_then_json(capsys):
    code, out, _ = run(capsys, "config", "list")
    assert code == 0 and "not created yet" in out and "resurface.enabled" in out

    code, out, _ = run(capsys, "config", "list", "--json")
    payload = json.loads(out)
    assert payload["exists"] is False and payload["unknown_keys"] == []
    row = next(r for r in payload["settings"] if r["key"] == "transcribe.model")
    assert row["value"] == "small" and row["source"] == "default" and "medium" in row["choices"]


def test_set_get_unset_round_trip(capsys):
    assert run(capsys, "config", "set", "resurface.enabled", "off")[0] == 0
    assert load_raw() == {"resurface": {"enabled": False}}
    assert load_config().resurface.enabled is False

    code, out, _ = run(capsys, "config", "get", "resurface.enabled", "--json")
    assert json.loads(out) == {"key": "resurface.enabled", "value": False, "default": True, "source": "config file"}

    code, out, _ = run(capsys, "config", "list")
    assert "(config file; default true)" in out

    assert run(capsys, "config", "unset", "resurface.enabled")[0] == 0
    assert load_raw() == {}  # empty section removed
    assert "already at its default" in run(capsys, "config", "unset", "resurface.enabled")[1]


def test_set_validates_values(capsys):
    assert run(capsys, "config", "set", "resurface.enabled", "maybe")[0] == 1
    code, _, err = run(capsys, "config", "set", "transcribe.model", "huge")
    assert code == 1 and "tiny" in err
    assert run(capsys, "config", "set", "transcribe.language", "")[0] == 1
    assert run(capsys, "config", "set", "transcribe.language", "a", "b")[0] == 1
    assert not config_path().exists()  # nothing was written


def test_unknown_key_suggests_and_exits_1(capsys):
    code, _, err = run(capsys, "config", "set", "histroy.enabled", "true")
    assert code == 1 and "unknown setting" in err and "resurface.enabled" in err
    assert run(capsys, "config", "get", "nope")[0] == 1
    assert run(capsys, "config", "explain", "nope")[0] == 1


def test_prompts_set_takes_several_values_and_is_used(capsys):
    assert run(capsys, "config", "set", "prompts.gratitude", "Thankful for?", 'Who "helped" me?')[0] == 0
    assert load_config().prompts == {"gratitude": ["Thankful for?", 'Who "helped" me?']}  # quotes survive TOML
    code, out, _ = run(capsys, "config", "get", "prompts.gratitude")
    assert out.splitlines() == ["Thankful for?", 'Who "helped" me?']
    assert "prompts.gratitude" in run(capsys, "config", "list")[1]
    assert run(capsys, "config", "set", "prompts.bad name", "x")[0] == 1


def test_set_keeps_other_settings_and_backs_up_comments(capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text('# my notes\n[transcribe]\nmodel = "medium"\n')

    code, _, err = run(capsys, "config", "set", "resurface.enabled", "false")
    backup = config_path().with_name(config_path().name + ".bak")
    assert code == 0 and str(backup) in err
    assert load_raw() == {"transcribe": {"model": "medium"}, "resurface": {"enabled": False}}
    assert "# my notes" in backup.read_text()


def test_unknown_keys_in_the_file_are_ignored_but_reported(capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("[resurface]\nenabled = false\ntypo = 1\n[mystery]\nx = 1\n")

    assert load_config().resurface.enabled is False  # no crash
    payload = json.loads(run(capsys, "config", "list", "--json")[1])
    assert set(payload["unknown_keys"]) == {"resurface.typo", "mystery.x"}


def test_invalid_toml_is_a_clean_error(capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("[history\n")
    code, _, err = run(capsys, "config", "list")
    assert code == 1 and "not valid TOML" in err


def test_explain_one_and_all(capsys):
    code, out, _ = run(capsys, "config", "explain", "resurface.enabled")
    assert "older entry" in out and "default: true" in out and "now: true (default)" in out

    out = run(capsys, "config", "explain")[1]
    assert all(s.key in out for s in settings.SETTINGS) and "prompts.<name>" in out
    assert len(json.loads(run(capsys, "config", "explain", "--json")[1])) == len(settings.SETTINGS) + 1


def test_config_path_prints_the_file(capsys):
    assert run(capsys, "config", "path")[1].strip() == str(config_path())


def test_prompts_list_and_show(capsys):
    rows = json.loads(run(capsys, "prompts", "list", "--json")[1])
    by_name = {r["name"]: r for r in rows}
    assert set(prompts.BUILTIN) <= set(by_name) and by_name["distance"]["source"] == "built-in"
    assert "Kross" in by_name["distance"]["description"] and "very low" in by_name["distance"]["description"]

    run(capsys, "config", "set", "prompts.today", "mine?")
    run(capsys, "config", "set", "prompts.extra", "another?")
    by_name = {r["name"]: r for r in json.loads(run(capsys, "prompts", "list", "--json")[1])}
    assert by_name["today"]["source"] == "config (replaces built-in)" and by_name["today"]["count"] == 1
    assert by_name["extra"]["source"] == "config"

    shown = json.loads(run(capsys, "prompts", "show", "extra", "--json")[1])
    assert shown["prompts"] == ["another?"]
    assert "1. mine?" in run(capsys, "prompts", "show", "today")[1]
    assert run(capsys, "prompts", "show", "nope")[0] == 2


def test_every_builtin_prompt_set_has_a_description():
    assert set(prompts.BUILTIN) == set(prompts.DESCRIPTIONS)


def test_data_dir_precedence_env_then_setting_then_default(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    from journal import store

    monkeypatch.delenv("JOURNAL_DIR")
    assert store.data_dir() == Path("~/.local/share/journal").expanduser()

    chosen = tmp_path / "elsewhere"
    assert run(capsys, "config", "set", "storage.dir", str(chosen))[0] == 0
    assert store.data_dir() == chosen

    monkeypatch.setenv("JOURNAL_DIR", str(tmp_path / "from-env"))
    assert store.data_dir() == tmp_path / "from-env"


def test_storage_dir_expands_tilde_and_is_used_for_entries(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("JOURNAL_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert run(capsys, "config", "set", "storage.dir", "~/notes/journal")[0] == 0

    assert main(["new", "--text", "stored under the configured dir"]) == 0
    assert list((tmp_path / "notes" / "journal" / "entries").rglob("*.txt"))
    capsys.readouterr()
    assert run(capsys, "path")[1].strip() == str(tmp_path / "notes" / "journal")


def test_storage_dir_must_be_absolute_or_tilde(capsys):
    code, _, err = run(capsys, "config", "set", "storage.dir", "relative/path")
    assert code == 1 and "absolute" in err
    assert not config_path().exists()


def test_changing_storage_dir_warns_that_entries_are_not_moved(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("JOURNAL_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    old = tmp_path / ".local" / "share" / "journal"
    (old / "entries").mkdir(parents=True)
    (old / "entries" / "x.txt").write_text("hi")

    code, _, err = run(capsys, "config", "set", "storage.dir", str(tmp_path / "new"))
    assert code == 0 and "were not moved" in err and str(old) in err


def test_journal_dir_env_overrides_and_set_says_so(tmp_path, capsys):
    code, _, err = run(capsys, "config", "set", "storage.dir", str(tmp_path / "x"))  # conftest sets JOURNAL_DIR
    assert code == 0 and "$JOURNAL_DIR is set and takes precedence" in err


def test_storage_dir_shows_its_default_in_list_and_explain(capsys):
    assert "~/.local/share/journal" in run(capsys, "config", "list")[1]
    out = run(capsys, "config", "explain", "storage.dir")[1]
    assert "default: ~/.local/share/journal" in out and "JOURNAL_DIR" in out


def test_a_leftover_history_section_from_an_older_version_is_ignored_and_can_be_removed(capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text('[history]\nenabled = false\n\n[transcribe]\nmodel = "medium"\n')

    assert load_config().transcribe.model == "medium"  # no crash from the removed option
    payload = json.loads(run(capsys, "config", "list", "--json")[1])
    assert payload["unknown_keys"] == ["history.enabled"]

    code, out, _ = run(capsys, "config", "unset", "history.enabled")
    assert code == 0 and "unused setting" in out
    assert load_raw() == {"transcribe": {"model": "medium"}}
    assert run(capsys, "config", "unset", "history.enabled")[0] == 1  # now it's simply unknown
