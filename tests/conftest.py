import pytest


@pytest.fixture(autouse=True)
def journal_dir(tmp_path, monkeypatch):
    """Every test gets an isolated JOURNAL_DIR — never touch the real journal."""
    data_dir = tmp_path / "journal"
    monkeypatch.setenv("JOURNAL_DIR", str(data_dir))
    monkeypatch.setenv("JOURNAL_CONFIG", str(tmp_path / "config-does-not-exist.toml"))
    yield data_dir
