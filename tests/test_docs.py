import json
from datetime import datetime, timezone

import pytest

from rythe import docs, settings
from rythe.cli import _entry_to_dict, build_parser, main
from rythe.entry import Entry


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_every_topic_renders():
    for name in docs.TOPICS:
        assert docs.render_topic(name).startswith("# rythe"), name


def test_list_json_and_unknown_topic(capsys):
    code, out = run(capsys, "docs", "--list", "--json")
    assert [r["topic"] for r in json.loads(out)] == list(docs.TOPICS)
    assert run(capsys, "docs", "nope")[0] == 2


def test_default_is_overview_with_topic_list_and_all_prints_everything(capsys):
    out = run(capsys, "docs")[1]
    assert out.startswith("# rythe: overview") and "Topics:" in out

    out = run(capsys, "docs", "--all")[1]
    assert all(f"# rythe: {t}" in out or t == "overview" for t in ("concepts", "commands", "configuration", "writing prompts"))
    payload = json.loads(run(capsys, "docs", "config", "--json")[1])
    assert payload["topics"] == ["config"] and "resurface.enabled" in payload["markdown"]


def test_commands_doc_covers_every_command_and_subcommand():
    text = docs.render_commands()
    parser = build_parser()
    sub = docs._subparsers_action(parser)
    for name, child in sub.choices.items():
        assert f"`rythe {name}`" in text, name
        child_sub = docs._subparsers_action(child)
        for grand in (child_sub.choices if child_sub else []):
            assert f"`rythe {name} {grand}`" in text, (name, grand)


def test_no_flag_is_documented_with_a_blank_description():
    for line in docs.render_commands().splitlines():
        assert not line.endswith("`:"), line
        if line.startswith("- `-"):
            assert ": " in line, f"flag without help: {line}"


def test_config_doc_covers_every_setting_and_env_var():
    text = docs.render_config()
    assert all(f"`{s.key}`" in text for s in settings.SETTINGS)
    assert "`prompts.<name>`" in text
    assert all(f"`{name}`" in text for name, _ in settings.ENV_VARS)


def test_prompts_doc_covers_every_builtin_set():
    from rythe import prompts

    text = docs.render_prompts()
    for name, items in prompts.BUILTIN.items():
        assert f"`{name}`" in text and prompts.DESCRIPTIONS[name] in text
        assert items[0].splitlines()[0] in text


def test_json_doc_mentions_every_entry_field_and_exit_code():
    entry = Entry(id="x", created=datetime(2026, 1, 1, tzinfo=timezone.utc), body="b")
    text = docs.render_topic("json")
    for key in _entry_to_dict(entry):
        assert f'"{key}"' in text, key
    for code in "0123":
        assert f"| {code} |" in text


def test_overview_links_every_other_topic():
    text = docs.render_topic("overview")
    for name in docs.TOPICS:
        if name != "overview":
            assert f"rythe docs {name}" in text, name


def test_concepts_explains_choosing_and_moving_the_data_folder():
    text = docs.render_topic("concepts")
    assert "storage.dir" in text and "RYTHE_DIR" in text and "Moving your journal" in text
