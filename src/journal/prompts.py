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
    "review": [
        "Looking back over this stretch:\n"
        "  - Where did your energy go? Was that where you wanted it to go?\n"
        "  - What small progress are you glad about?\n"
        "  - What's still unresolved, and what is one next step that's in your hands?\n"
        "  - What do you see differently now than when it happened?"
    ],
}


# What each built-in set is for, shown by `journal prompts list` and `journal docs prompts`.
DESCRIPTIONS: dict[str, str] = {
    "today": (
        "A light daily prompt (the default for --prompt): what stood out, a small win, a moment "
        "worth remembering. Based on diary research (Amabile's progress principle) showing that "
        "noting one small event a day makes the days easy to look back on."
    ),
    "hard": (
        "Expressive writing about something stressful or unresolved (Pennebaker). Research finds "
        "it helps most when written privately, for about 15 minutes, about recent events, ideally "
        "over several days. It isn't a substitute for support if it stirs up more than you want "
        "to handle alone."
    ),
    "distance": (
        "Self-distancing (Kross): write about a problem as an outside observer, using your own "
        "name or \"you\" instead of \"I\". It reduces how strongly you react and helps you reason "
        "about the problem. Skip it when you're feeling very low: one study found it can worsen "
        "mood for people at high risk of depression."
    ),
    "review": (
        "Used by `journal review`: reflection questions for looking back over a stretch of "
        "entries (where your energy went, small progress, what's unresolved, what looks "
        "different now)."
    ),
}


def source_of(name: str, extra: dict[str, list[str]] | None = None) -> str:
    """"built-in", "config" (your own set) or "config (replaces built-in)"."""
    in_config = name in (extra or {})
    if name in BUILTIN:
        return "config (replaces built-in)" if in_config else "built-in"
    return "config"


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
