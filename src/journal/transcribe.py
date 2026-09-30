"""Audio transcription: ffmpeg resamples to 16kHz mono, then local whisper.cpp (whisper-cli)
turns that into text. Entirely offline — no audio or transcript ever leaves this machine.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from . import store

# Multilingual ggml models from the canonical whisper.cpp model repo, smallest first.
KNOWN_MODELS = {
    "tiny": "ggml-tiny.bin",
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
    "large": "ggml-large-v3.bin",
}
_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"


class TranscribeError(Exception):
    pass


def models_dir() -> Path:
    return store.data_dir() / "models"


def model_path(name: str) -> Path:
    if name not in KNOWN_MODELS:
        raise TranscribeError(f"unknown model {name!r}; choose one of {', '.join(KNOWN_MODELS)}")
    return models_dir() / KNOWN_MODELS[name]


def list_models() -> list[dict]:
    return [
        {"name": name, "file": filename, "downloaded": (models_dir() / filename).exists()}
        for name, filename in KNOWN_MODELS.items()
    ]


def download_model(
    name: str, *, force: bool = False, progress: Callable[[int, int], None] | None = None
) -> Path:
    path = model_path(name)
    if path.exists() and not force:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{_MODEL_BASE_URL}/{KNOWN_MODELS[name]}"
    tmp_path = path.with_name(path.name + ".part")
    try:
        with urllib.request.urlopen(url) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while chunk := response.read(1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise TranscribeError(f"failed to download model {name!r}: {exc}") from exc

    tmp_path.rename(path)
    return path


def _require(command: str, *, package_hint: str) -> str:
    found = shutil.which(command)
    if not found:
        raise TranscribeError(f"{command!r} not found ({package_hint})")
    return found


def _run(cmd: list[str], *, what: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise TranscribeError(f"{what} failed: {detail}")


def transcribe(audio_path: Path, *, model: str = "small", language: str = "en") -> str:
    path = model_path(model)
    if not path.exists():
        raise TranscribeError(f"model {model!r} isn't downloaded yet; run `journal model download {model}`")

    ffmpeg = _require("ffmpeg", package_hint="install the ffmpeg package")
    whisper_cli = _require("whisper-cli", package_hint="install the whisper-cpp package")

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "audio.wav"
        _run(
            [ffmpeg, "-y", "-i", str(audio_path), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)],
            what="ffmpeg",
        )

        out_stem = Path(tmp) / "out"
        _run(
            [whisper_cli, "-m", str(path), "-l", language, "-otxt", "-of", str(out_stem), "-np", "-f", str(wav_path)],
            what="whisper-cli",
        )

        return out_stem.with_suffix(".txt").read_text().strip()
