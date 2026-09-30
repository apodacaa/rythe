from journal.config import load_config


def test_defaults_when_no_config_file():
    config = load_config()
    assert config.theme == "tokyo-night"
    assert config.start_mode == "insert"
    assert config.transcribe.model == "small"
    assert config.memo.subject_prefix == "record-memo:"


def test_loads_overrides_from_toml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
theme = "gruvbox"
start_mode = "normal"

[transcribe]
model = "medium"
language = "auto"

[memo]
subject_prefix = "voice-memo:"
"""
    )
    monkeypatch.setenv("JOURNAL_CONFIG", str(config_file))

    config = load_config()

    assert config.theme == "gruvbox"
    assert config.start_mode == "normal"
    assert config.transcribe.model == "medium"
    assert config.transcribe.language == "auto"
    assert config.memo.subject_prefix == "voice-memo:"
