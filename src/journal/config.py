"""Load ~/.config/journal/config.toml. Every key is optional; missing keys fall back to defaults."""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field, fields
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
class HistoryConfig:
    enabled: bool = True


@dataclass
class ResurfaceConfig:
    enabled: bool = True


@dataclass
class StorageConfig:
    dir: str | None = None  # None means the default location (see store.data_dir)


@dataclass
class AppearanceConfig:
    color: str = "auto"  # auto | always | never


@dataclass
class Config:
    transcribe: TranscribeConfig = field(default_factory=TranscribeConfig)
    memo: MemoConfig = field(default_factory=MemoConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    resurface: ResurfaceConfig = field(default_factory=ResurfaceConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)
    prompts: dict[str, list[str]] = field(default_factory=dict)


def load_raw() -> dict:
    """The config file as a plain dict ({} if there is none). Raises ValueError if it isn't
    valid TOML, so callers can report it instead of crashing.
    """
    path = config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path} is not valid TOML: {exc}") from None


def _known(cls, table: dict) -> dict:
    """Only the keys `cls` defines: a stray or misspelled key is ignored instead of crashing
    every command (`journal config list` reports such keys).
    """
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in table.items() if k in names}


def load_config() -> Config:
    raw = load_raw()
    return Config(
        transcribe=TranscribeConfig(**_known(TranscribeConfig, raw.get("transcribe", {}))),
        memo=MemoConfig(**_known(MemoConfig, raw.get("memo", {}))),
        history=HistoryConfig(**_known(HistoryConfig, raw.get("history", {}))),
        resurface=ResurfaceConfig(**_known(ResurfaceConfig, raw.get("resurface", {}))),
        storage=StorageConfig(**_known(StorageConfig, raw.get("storage", {}))),
        appearance=AppearanceConfig(**_known(AppearanceConfig, raw.get("appearance", {}))),
        prompts={name: list(items) for name, items in raw.get("prompts", {}).items()},
    )


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def render_toml(raw: dict) -> str:
    """Serialize a config dict: one [table] per section of scalars and lists. Comments are not
    preserved (see `write_raw`).
    """
    blocks = []
    for section, table in raw.items():
        if not table:
            continue
        lines = [f"[{section}]"] + [f"{key} = {_toml_value(value)}" for key, value in table.items()]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_raw(raw: dict) -> Path | None:
    """Write the config file. If the existing file has comment lines (which rewriting drops), a
    copy is kept next to it as `config.toml.bak`; returns that path, else None.
    """
    path = config_path()
    backup = None
    if path.exists():
        text = path.read_text()
        if any(line.lstrip().startswith("#") for line in text.splitlines()):
            backup = path.with_name(path.name + ".bak")
            backup.write_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_toml(raw))
    return backup
