"""Terminal styling for human-facing output.

Colors are the terminal's own 16 ANSI colors, never fixed RGB values, so everything automatically
matches whatever theme the terminal uses (Omarchy's included). Styling is switched off when output
isn't a terminal, with NO_COLOR, with TERM=dumb, or via the `appearance.color` setting, and it is
never applied to --json or to the markdown that `journal docs` prints to a pipe, so scripts and
agents always see plain text.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

_RESET = "\x1b[0m"
_CODES = {
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "gray": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_color: bool | None = None  # None: decide from the environment on each call


def set_color(value: bool | None) -> None:
    global _color
    _color = value


def _decide(setting: str = "auto") -> bool:
    if setting == "never":
        return False
    if setting == "always":
        return True
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def configure(setting: str = "auto") -> None:
    """Fix the color decision for this run from the `appearance.color` setting (auto|always|never)
    plus the environment. Called once at startup.
    """
    set_color(_decide(setting))


def color() -> bool:
    return _color if _color is not None else _decide()


def style(text: str, *names: str) -> str:
    """Wrap `text` in the named styles (bold, dim, cyan…), or return it untouched if color is
    off. Nested styles survive: an inner reset re-applies the outer style.
    """
    if not names or not color():
        return text
    start = "\x1b[" + ";".join(_CODES[n] for n in names) + "m"
    return f"{start}{text.replace(_RESET, _RESET + start)}{_RESET}"


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def readline_safe(text: str) -> str:
    """For input() prompts: when the readline module is loaded, escape sequences must be wrapped
    in \\001…\\002 so it can measure the prompt; otherwise leave them alone.
    """
    if "readline" not in sys.modules:
        return text
    return _ANSI_RE.sub(lambda m: f"\x01{m.group(0)}\x02", text)


# -- glyphs: Unicode where the terminal can show it, plain ASCII otherwise ---------------------

_UNICODE = {
    "bar": "▌", "gutter": "┃", "arrow": "➜", "ok": "✔", "bad": "✖", "star": "✦", "dot": "·", "ask": "❯",
    "rule": "─", "dbl": ("╔", "╗", "╚", "╝", "═", "║"), "box": ("┏", "┓", "┗", "┛", "━", "┃"),
}
_ASCII = {
    "bar": "|", "gutter": "|", "arrow": "->", "ok": "+", "bad": "x", "star": "*", "dot": "-", "ask": ">",
    "rule": "-", "dbl": ("+", "+", "+", "+", "=", "|"), "box": ("+", "+", "+", "+", "-", "|"),
}


def glyph(name: str):
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return (_UNICODE if encoding.startswith("utf") else _ASCII)[name]


def width() -> int:
    return max(50, min(shutil.get_terminal_size((80, 24)).columns, 90))


# -- layout helpers (they return plain strings, styled where color is on) ---------------------

def banner(title: str) -> str:
    tl, tr, bl, br, h, v = glyph("dbl")
    spaced = " ".join(title.upper())  # letter-spaced title
    inner = f"  {glyph('star')}  {spaced}  {glyph('star')}  "
    bar = h * visible_len(inner)
    return "\n".join(
        [
            style(f"{tl}{bar}{tr}", "cyan"),
            style(v, "cyan") + style(inner, "bold", "bright_cyan") + style(v, "cyan"),
            style(f"{bl}{bar}{br}", "cyan"),
        ]
    )


def step(number: int, total: int, title: str) -> str:
    return (
        " " + style(glyph("bar"), "magenta") + style(f"{number}/{total}", "bold", "magenta")
        + "  " + style(title.upper(), "bold")
    )


def gutter(lines: list[str]) -> str:
    bar = style(glyph("gutter"), "gray")
    return "\n".join(f" {bar}  {line}" if line else f" {bar}" for line in lines)


def box(title: str, rows: list[str]) -> str:
    tl, tr, bl, br, h, v = glyph("box")
    inner = max([visible_len(r) for r in rows] + [visible_len(title) + 4]) + 2
    head = f"{h} {title} "
    top = style(f"{tl}{head}{h * (inner - len(head))}{tr}", "cyan")
    body = [
        style(v, "cyan") + " " + row + " " * (inner - visible_len(row) - 1) + style(v, "cyan") for row in rows
    ]
    return "\n".join([top, *body, style(f"{bl}{h * inner}{br}", "cyan")])


def rule(label: str = "") -> str:
    line = glyph("rule")
    if not label:
        return style(line * width(), "gray")
    return style(f"{line}{line} {label} ", "bold", "cyan") + style(line * max(3, width() - len(label) - 4), "gray")


def ok(text: str) -> str:
    return style(glyph("ok"), "bold", "green") + " " + text


def warn(text: str) -> str:
    return style("!", "bold", "yellow") + " " + style(text, "yellow")
