"""Opt-in writing prompts, shown below a "scissors" line in the editor draft.

The prompt is never part of the entry: everything from the scissors line down is stripped when
the draft is saved, like the comment block in a git commit message. Prompts are always opt-in
(`--prompt`) — a bare `journal` stays a blank page.
"""
from __future__ import annotations

from datetime import date

SCISSORS = "~~~~ journal: everything from this line down is removed when you save ~~~~"

BUILTIN: dict[str, list[str]] = {
    "today": [
        "What stood out today, and why?",
        "What is one small thing that went well today?",
        "What is one moment from today you'd like to remember?",
    ],
    "hard": [
        "Write about something that has been on your mind: what happened, how it felt, and what\n"
        "you make of it now. About 15 minutes works well; don't stop to polish.",
        "Write about something you haven't told anyone: what happened, what you felt, and what you\n"
        "understand about it now. About 15 minutes works well; don't stop to polish.",
    ],
    "distance": [
        "Write about something that's been bothering you as if it were happening to someone else,\n"
        "using your own name or \"you\" instead of \"I\". What would you notice from the outside?\n"
        "(Skip this one if you're feeling very low.)",
    ],
}


def available(extra: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    return {**BUILTIN, **(extra or {})}


def pick(name: str, today: date, extra: dict[str, list[str]] | None = None) -> str:
    """One prompt from the named set. The choice is seeded by the date, so reopening the editor
    on the same day shows the same prompt.
    """
    sets = available(extra)
    if name not in sets or not sets[name]:
        raise ValueError(f"unknown prompt set {name!r} (available: {', '.join(sorted(sets))})")
    options = sets[name]
    return options[today.toordinal() % len(options)]


def draft_text(prompt: str) -> str:
    return f"\n{SCISSORS}\n{prompt}\n"


def strip_scissors(text: str) -> str:
    """Drop the scissors line and everything after it."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == SCISSORS:
            return "".join(lines[:i])
    return text
