"""Styled `--help`.

Python's argument parser lays the help out using the plain text's column widths, so color codes
inside it would throw the alignment off. Instead we let it produce the plain help and style the
finished text line by line: that can only add escape codes, never change the layout or the words
(a test checks that stripping them gives back the plain help).
"""
from __future__ import annotations

import argparse
import re
import sys

from . import ui

_ARGS_HEADINGS = {"positional arguments:", "options:", "optional arguments:"}
_ARG_LINE = re.compile(r"^( {2}| {4})(\S.*?)(?= {2,}|$)")  # name or flags, then 2+ spaces or the end
_EXAMPLE_LINE = re.compile(r"^  (\S.*?)(\s+)(# .*)$|^  (\S.*)$")


def style_help(text: str) -> str:
    if not ui.color():
        return text
    out: list[str] = []
    in_args = False
    for line in text.split("\n"):
        if line.startswith("usage:"):
            out.append(ui.style("usage:", "bold", "cyan") + line[len("usage:"):])
            in_args = False
        elif line and not line.startswith(" ") and line.rstrip().endswith(":"):
            in_args = line.strip() in _ARGS_HEADINGS
            out.append(ui.style(line, "bold", "cyan"))
        elif not line.strip():
            in_args = False
            out.append(line)
        elif in_args and (m := _ARG_LINE.match(line)):
            # 4-space entries are the sub-commands under `{new,add,…}`; 2-space ones are flags
            colors = ("bold", "cyan") if len(m.group(1)) == 4 else ("bold",)
            out.append(m.group(1) + ui.style(m.group(2), *colors) + line[m.end():])
        elif not in_args and (m := _EXAMPLE_LINE.match(line)):
            if m.group(3):  # an example with a trailing `# comment`
                out.append("  " + ui.style(m.group(1), "bold") + m.group(2) + ui.style(m.group(3), "dim"))
            else:
                out.append("  " + ui.style(m.group(4), "bold"))
        else:
            out.append(line)
    return "\n".join(out)


class RytheParser(argparse.ArgumentParser):
    """rythe's parser (and, via add_subparsers, every sub-command's), with styled help."""

    def __init__(self, *args, **kwargs):
        if sys.version_info >= (3, 14):
            kwargs.setdefault("color", False)  # we do our own styling; avoid doubling up
        super().__init__(*args, **kwargs)

    def format_help(self) -> str:
        return style_help(super().format_help())

    def error(self, message: str):
        # argparse exits 2 here; rythe's exit 2 means "not found", and a usage error is 1.
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")
