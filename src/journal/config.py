"""Load ~/.config/journal/config.toml. Every key is optional; missing keys fall back to defaults."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def config_path() -> Path:
    override = os.environ.get("JOURNAL_CONFIG")
    return Path(override) if override else Path.home() / ".config/journal/config.toml"


@dataclass
class TranscribeConfig:
    model: str = "small"
    language: str = "en"


@dataclass
class MemoConfig:
    subject_prefix: str = "record-memo:"


@dataclass
class Config:
    theme: str = "tokyo-night"
    start_mode: str = "insert"
    transcribe: TranscribeConfig = field(default_factory=TranscribeConfig)
    memo: MemoConfig = field(default_factory=MemoConfig)
    # keys[mode][action] = ["k1", "k2", ...] overrides for src/journal/tui/keymap.py
    keys: dict[str, dict[str, list[str]]] = field(default_factory=dict)


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()

    with path.open("rb") as f:
        raw = tomllib.load(f)

    return Config(
        theme=raw.get("theme", "tokyo-night"),
        start_mode=raw.get("start_mode", "insert"),
        transcribe=TranscribeConfig(**raw.get("transcribe", {})),
        memo=MemoConfig(**raw.get("memo", {})),
        keys=raw.get("keys", {}),
    )
