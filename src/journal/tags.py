"""Hashtag extraction from entry bodies.

Tags always live in the body text, never in frontmatter, so there is nothing to keep in sync:
`extract_tags` is the single source of truth and is cheap enough to run on every read.
"""
from __future__ import annotations

import re

# A '#' not preceded by a word character, another '#', or '/' (so URL fragments and '##' are
# skipped), followed by a letter and then word characters/hyphens. "# Heading" never matches:
# there's a space between '#' and the letter.
_TAG_RE = re.compile(r"(?<![\w#/])#([A-Za-z][\w-]*)")


def extract_tags(body: str) -> list[str]:
    seen: list[str] = []
    for match in _TAG_RE.finditer(body):
        tag = match.group(1).lower()
        if tag not in seen:
            seen.append(tag)
    return seen


def normalize_tag(tag: str) -> str:
    return tag.lstrip("#").lower()
