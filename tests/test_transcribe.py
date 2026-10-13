from pathlib import Path

import pytest

from rythe import transcribe


def test_model_path_unknown_name_raises():
    with pytest.raises(transcribe.TranscribeError, match="unknown model"):
        transcribe.model_path("not-a-real-model")


def test_model_path_known_name():
    path = transcribe.model_path("small")
    assert path.name == "ggml-small.bin"
    assert path.parent == transcribe.models_dir()


def test_list_models_reports_download_state(journal_dir):
    transcribe.models_dir().mkdir(parents=True)
    (transcribe.models_dir() / "ggml-tiny.bin").write_bytes(b"fake model bytes")

    models = transcribe.list_models()
    by_name = {m["name"]: m["downloaded"] for m in models}

    assert by_name["tiny"] is True
    assert by_name["small"] is False
    assert set(by_name) == set(transcribe.KNOWN_MODELS)


def test_download_model_skips_if_already_present(journal_dir, monkeypatch):
    transcribe.models_dir().mkdir(parents=True)
    existing = transcribe.models_dir() / "ggml-tiny.bin"
    existing.write_bytes(b"already here")

    def fail_if_called(*a, **k):
        raise AssertionError("should not attempt a download when the model already exists")

    monkeypatch.setattr("rythe.transcribe.urllib.request.urlopen", fail_if_called)

    path = transcribe.download_model("tiny")
    assert path == existing
    assert path.read_bytes() == b"already here"


def test_download_model_writes_file_and_reports_progress(journal_dir, monkeypatch):
    chunks = [b"hello ", b"world", b""]

    class FakeResponse:
        headers = {"Content-Length": "11"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return chunks.pop(0) if chunks else b""

    monkeypatch.setattr("rythe.transcribe.urllib.request.urlopen", lambda url: FakeResponse())

    seen = []
    path = transcribe.download_model("tiny", progress=lambda done, total: seen.append((done, total)))

    assert path.read_bytes() == b"hello world"
    assert seen[-1] == (11, 11)
    assert not path.with_name(path.name + ".part").exists()


def test_transcribe_raises_when_model_not_downloaded(journal_dir):
    with pytest.raises(transcribe.TranscribeError, match="isn't downloaded"):
        transcribe.transcribe(Path("/tmp/does-not-matter.m4a"), model="small")


def test_transcribe_runs_ffmpeg_then_whisper_cli(journal_dir, monkeypatch, tmp_path):
    transcribe.models_dir().mkdir(parents=True)
    (transcribe.models_dir() / "ggml-small.bin").write_bytes(b"fake model")

    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio")

    calls = []

    def fake_run(cmd, *, capture_output, text):
        calls.append(cmd)

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        if "ffmpeg" in cmd[0]:
            # write the wav path ffmpeg was asked to produce, so the pipeline has something
            wav_path = Path(cmd[-1])
            wav_path.write_bytes(b"fake wav")
        elif "whisper-cli" in cmd[0]:
            of_index = cmd.index("-of")
            out_stem = Path(cmd[of_index + 1])
            out_stem.with_suffix(".txt").write_text("this is the transcript")
        return Result()

    monkeypatch.setattr("rythe.transcribe.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("rythe.transcribe.subprocess.run", fake_run)

    text = transcribe.transcribe(audio_file, model="small", language="en")

    assert text == "this is the transcript"
    assert "ffmpeg" in calls[0][0]
    assert "whisper-cli" in calls[1][0]
    assert "-l" in calls[1] and "en" in calls[1]


def test_transcribe_raises_transcribe_error_when_ffmpeg_missing(journal_dir, monkeypatch):
    transcribe.models_dir().mkdir(parents=True)
    (transcribe.models_dir() / "ggml-small.bin").write_bytes(b"fake model")

    monkeypatch.setattr("rythe.transcribe.shutil.which", lambda name: None)

    with pytest.raises(transcribe.TranscribeError, match="not found"):
        transcribe.transcribe(Path("/tmp/whatever.m4a"), model="small")


def test_transcribe_raises_on_nonzero_exit(journal_dir, monkeypatch, tmp_path):
    transcribe.models_dir().mkdir(parents=True)
    (transcribe.models_dir() / "ggml-small.bin").write_bytes(b"fake model")
    audio_file = tmp_path / "memo.m4a"
    audio_file.write_bytes(b"fake audio")

    def fake_run(cmd, *, capture_output, text):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "boom: unsupported codec"

        return Result()

    monkeypatch.setattr("rythe.transcribe.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("rythe.transcribe.subprocess.run", fake_run)

    with pytest.raises(transcribe.TranscribeError, match="boom: unsupported codec"):
        transcribe.transcribe(audio_file, model="small")
