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
    transcribe: TranscribeConfig = field(default_factory=TranscribeConfig)
    memo: MemoConfig = field(default_factory=MemoConfig)


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()

    with path.open("rb") as f:
        raw = tomllib.load(f)

    return Config(
        transcribe=TranscribeConfig(**raw.get("transcribe", {})),
        memo=MemoConfig(**raw.get("memo", {})),
    )
