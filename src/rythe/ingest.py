"""Turn external content — a voice memo, a transcript file — into a journal entry."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from . import store
from .config import load_config
from .entry import Entry
from .transcribe import transcribe as transcribe_audio

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".caf", ".ogg", ".flac"}


def ingest_audio(
    audio_path: Path,
    *,
    created: datetime,
    message_id: str | None = None,
    title: str = "",
    model: str | None = None,
    language: str | None = None,
    force: bool = False,
) -> Entry:
    # Check for a duplicate before transcribing — transcription is the expensive part, no point
    # doing it just to have store.create() reject the result.
    if message_id and not force:
        existing = store.find_by_message_id(message_id)
        if existing is not None:
            raise store.DuplicateMessageError(message_id, existing.id)

    config = load_config()
    model = model or config.transcribe.model
    language = language or config.transcribe.language

    text = transcribe_audio(audio_path, model=model, language=language)

    entry = store.create(
        created=created,
        body=text,
        source="memo",
        title=title,
        message_id=message_id,
        transcriber=f"whisper.cpp {model}",
        force=force,
    )

    dest_dir = store.audio_root()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{entry.id}{audio_path.suffix}"
    shutil.copy2(audio_path, dest)

    return store.set_audio(entry.id, f"audio/{dest.name}")


def ingest_text(
    text_path: Path,
    *,
    created: datetime,
    message_id: str | None = None,
    title: str = "",
    force: bool = False,
) -> Entry:
    return store.create(
        created=created,
        body=text_path.read_text(),
        source="text",
        title=title,
        message_id=message_id,
        force=force,
    )
