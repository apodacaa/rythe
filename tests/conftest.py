import pytest


@pytest.fixture(autouse=True)
def journal_dir(tmp_path, monkeypatch):
    """Every test gets an isolated RYTHE_DIR — never touch the real journal."""
    data_dir = tmp_path / "journal"
    monkeypatch.setenv("RYTHE_DIR", str(data_dir))
    monkeypatch.setenv("RYTHE_CONFIG", str(tmp_path / "config-does-not-exist.toml"))
    yield data_dir


@pytest.fixture(autouse=True)
def reset_color(monkeypatch):
    """Styling decisions never leak between tests; tests start with color off (not a terminal)."""
    from rythe import ui

    for name in ("NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)
    ui.set_color(None)
    yield
    ui.set_color(None)
