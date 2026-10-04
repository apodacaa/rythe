import json

import pytest

from journal import ui
from journal.cli import main


def test_style_is_plain_when_color_is_off_and_ansi_when_on():
    ui.set_color(False)
    assert ui.style("hi", "bold", "cyan") == "hi"
    ui.set_color(True)
    styled = ui.style("hi", "bold", "cyan")
    assert styled.startswith("\x1b[1;36m") and styled.endswith("\x1b[0m")
    assert ui.strip_ansi(styled) == "hi"


def test_nested_styles_keep_the_outer_style_after_an_inner_reset():
    ui.set_color(True)
    text = ui.style("a " + ui.style("b", "red") + " c", "bold")
    assert text.count("\x1b[1m") == 2  # re-applied after the inner reset
    assert ui.strip_ansi(text) == "a b c"


def test_decision_order_setting_then_no_color_then_force_then_terminal(monkeypatch):
    assert ui._decide("auto") is False  # pytest's stdout isn't a terminal
    assert ui._decide("never") is False
    assert ui._decide("always") is True
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert ui._decide("auto") is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui._decide("auto") is False  # NO_COLOR beats FORCE_COLOR
    assert ui._decide("always") is True  # an explicit setting beats the environment


def test_layout_helpers_line_up_with_and_without_color():
    for color in (False, True):
        ui.set_color(color)
        lines = ui.box("Summary", ["short", "a longer row of text"]).splitlines()
        assert len({ui.visible_len(line) for line in lines}) == 1  # a perfect rectangle
        banner = ui.banner("journal setup").splitlines()
        assert len({ui.visible_len(line) for line in banner}) == 1
        assert "J O U R N A L" in ui.strip_ansi(banner[1])


def test_step_and_gutter_and_rule():
    ui.set_color(False)
    assert ui.step(2, 5, "History").strip().endswith("2/5  HISTORY")
    assert ui.gutter(["a", ""]).splitlines()[1].strip() == ui.glyph("gutter")
    assert "Day" in ui.rule("Day")


def test_ascii_fallback_when_the_terminal_is_not_utf8(monkeypatch):
    class Latin:
        encoding = "latin-1"

    monkeypatch.setattr("journal.ui.sys.stdout", Latin())
    assert ui.glyph("arrow") == "->" and ui.glyph("ok") == "+"
    assert ui.glyph("box")[0] == "+"


def test_readline_safe_wraps_escapes_only_when_readline_is_loaded(monkeypatch):
    ui.set_color(True)
    prompt = ui.style("Keep it?", "bold")
    monkeypatch.delitem(__import__("sys").modules, "readline", raising=False)
    assert ui.readline_safe(prompt) == prompt
    monkeypatch.setitem(__import__("sys").modules, "readline", object())
    assert "\x01\x1b[1m\x02" in ui.readline_safe(prompt)


def test_appearance_color_setting_controls_main(capsys):
    main(["config", "set", "appearance.color", "always"])
    capsys.readouterr()
    assert ui.color() is False  # not yet configured for this run
    main(["config", "path"])
    assert ui.color() is True
    main(["config", "set", "appearance.color", "never"])
    main(["config", "path"])
    assert ui.color() is False


def test_json_output_is_never_styled_even_with_color_forced(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    main(["add", "hello #x", "--json"])
    out = capsys.readouterr().out
    assert "\x1b" not in out and json.loads(out)["tags"] == ["x"]
    main(["config", "list", "--json"])
    assert "\x1b" not in capsys.readouterr().out


COMMANDS = [
    ["list"],
    ["list", "--tag", "work"],
    ["search", "coffee"],
    ["search", "co+", "--regex"],
    ["on-this-day", "--date", "2025-10-04"],
    ["tags"],
    ["status"],
    ["model", "list"],
    ["config", "list"],
    ["config", "explain", "history.enabled"],
    ["config", "explain"],
    ["prompts", "list"],
    ["prompts", "show", "hard"],
    ["setup", "--check"],
    ["docs", "--list"],
    ["show", "last", "--no-pager"],
    ["read", "--since", "2020-01-01", "--no-pager"],
]


@pytest.fixture
def seeded(capsys):
    main(["new", "--at", "2025-10-04T09:00:00+02:00", "--text", "coffee and code #work", "--source", "memo"])
    main(["new", "--at", "2026-10-03T21:30:00+02:00", "--title", "Late", "--text", "a coffee, again #home"])
    main(["config", "set", "history.enabled", "false"])
    capsys.readouterr()


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda a: " ".join(a))
def test_styling_only_adds_escape_codes_never_changes_the_text(argv, seeded, capsys, monkeypatch):
    assert main(argv) == 0
    plain = capsys.readouterr().out
    assert "\x1b" not in plain

    monkeypatch.setenv("FORCE_COLOR", "1")
    assert main(argv) == 0
    colored = capsys.readouterr().out
    assert "\x1b[" in colored, f"{argv} printed no styling"
    assert ui.strip_ansi(colored) == plain


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda a: " ".join(a))
def test_no_color_env_and_never_setting_both_keep_output_plain(argv, seeded, capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    main(argv)
    assert "\x1b" not in capsys.readouterr().out

    monkeypatch.delenv("NO_COLOR")
    main(["config", "set", "appearance.color", "never"])
    capsys.readouterr()
    main(argv)
    assert "\x1b" not in capsys.readouterr().out


def test_reading_views_highlight_tags_and_labels(seeded, capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    main(["read", "--since", "2020-01-01", "--no-pager"])
    out = capsys.readouterr().out
    assert ui.style("#work", "cyan") in out and ui.style("#home", "cyan") in out
    assert ui.style("voice memo", "magenta") in out
    assert ui.style("9:00 AM", "bold") in out


SAMPLE_MD = """# Title

Some **bold** text and `code` here.

## Section

- a bullet with `journal add`
1. a numbered step

> a quoted note

```
journal read --tag work
```

| Code | Meaning |
|---|---|
| 0 | ok |

---

### Small heading
"""


def test_style_markdown_renders_instead_of_showing_markup():
    from journal import docs

    ui.set_color(True)
    out = docs.style_markdown(SAMPLE_MD)
    plain = ui.strip_ansi(out)
    assert "\x1b[" in out
    for markup in ("```", "**", "`code`", "# Title", "## Section", "### Small"):
        assert markup not in plain, markup
    for text in ("Title", "Section", "Small heading", "journal read --tag work", "a bullet with journal add",
                 "1. a numbered step", "a quoted note", "bold", "code"):
        assert text in plain, text
    assert "\n\n\n" not in plain  # no runs of blank lines


def test_docs_on_a_terminal_are_styled_but_pipes_always_get_raw_markdown(capsys, monkeypatch):
    from journal import docs

    monkeypatch.setattr("journal.docs._on_terminal", lambda: True)
    monkeypatch.setenv("FORCE_COLOR", "1")
    main(["docs", "json", "--no-pager"])
    styled = capsys.readouterr().out
    plain = ui.strip_ansi(styled)
    assert "\x1b[" in styled and "```" not in plain and "# journal: JSON" not in plain
    assert "journal: JSON output and exit codes" in plain  # the heading text is still there

    monkeypatch.undo()
    monkeypatch.setenv("FORCE_COLOR", "1")  # color forced, but stdout is a pipe here
    main(["docs", "json"])
    raw = capsys.readouterr().out
    assert "\x1b" not in raw and raw.startswith("# journal: JSON output and exit codes")
    assert "```" in raw  # untouched markdown, exactly what agents rely on


def test_docs_json_is_never_styled(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    main(["docs", "config", "--json"])
    out = capsys.readouterr().out
    assert "\x1b" not in out and json.loads(out)["topics"] == ["config"]
