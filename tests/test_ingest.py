from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rythe import ingest, store

TZ = timezone(timedelta(hours=2))


def dt(h, m=0, s=0):
    return datetime(2026, 9, 30, h, m, s, tzinfo=TZ)


def test_ingest_text_creates_entry(journal_dir, tmp_path):
    text_file = tmp_path / "transcript.txt"
    text_file.write_text("a transcribed thought #reflect")

    entry = ingest.ingest_text(text_file, created=dt(9))

    assert entry.source == "text"
    assert entry.body.strip() == "a transcribed thought #reflect"
    assert store.get(entry.id).body.strip() == "a transcribed thought #reflect"


def test_ingest_text_with_message_id_dedupes(journal_dir, tmp_path):
    text_file = tmp_path / "transcript.txt"
    text_file.write_text("first")

    ingest.ingest_text(text_file, created=dt(9), message_id="<abc@mail>")

    with pytest.raises(store.DuplicateMessageError):
        ingest.ingest_text(text_file, created=dt(10), message_id="<abc@mail>")


def test_ingest_audio_transcribes_copies_audio_and_sets_fields(journal_dir, tmp_path, monkeypatch):
    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio bytes")

    monkeypatch.setattr(
        "rythe.ingest.transcribe_audio",
        lambda path, *, model, language: f"transcribed from {path.name} using {model}/{language}",
    )

    entry = ingest.ingest_audio(audio_file, created=dt(9), model="small", language="en")

    assert entry.source == "memo"
    assert entry.body.strip() == "transcribed from memo.m4a using small/en"
    assert entry.transcriber == "whisper.cpp small"
    assert entry.audio == f"audio/{entry.id}.m4a"

    copied = journal_dir / entry.audio
    assert copied.exists()
    assert copied.read_bytes() == b"fake audio bytes"


def test_ingest_audio_skips_transcription_on_duplicate(journal_dir, tmp_path, monkeypatch):
    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio bytes")

    calls = []
    monkeypatch.setattr(
        "rythe.ingest.transcribe_audio",
        lambda path, *, model, language: calls.append(1) or "transcribed",
    )

    ingest.ingest_audio(audio_file, created=dt(9), message_id="<xyz@mail>")
    assert len(calls) == 1

    with pytest.raises(store.DuplicateMessageError):
        ingest.ingest_audio(audio_file, created=dt(10), message_id="<xyz@mail>")

    # transcription was not attempted a second time for the duplicate
    assert len(calls) == 1


def test_ingest_audio_uses_config_defaults_when_not_specified(journal_dir, tmp_path, monkeypatch):
    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio bytes")

    seen = {}

    def fake_transcribe(path, *, model, language):
        seen["model"] = model
        seen["language"] = language
        return "text"

    monkeypatch.setattr("rythe.ingest.transcribe_audio", fake_transcribe)

    ingest.ingest_audio(audio_file, created=dt(9))

    assert seen == {"model": "small", "language": "en"}
