import subprocess
from datetime import datetime, timezone

from journal import store
from journal.cli import main


def dt(h, m=0):
    return datetime(2026, 9, 30, h, m, tzinfo=timezone.utc)


def _log(root):
    out = subprocess.run(
        ["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout
    return out.splitlines()


def test_each_write_makes_a_commit(journal_dir):
    entry = store.create(created=dt(8), body="hello")
    store.update_body(entry.id, "changed\n", dt(9))
    store.add_tags(entry.id, ["x"])
    store.delete(entry.id)

    assert _log(journal_dir) == [
        f"delete {entry.id}",
        f"tag {entry.id}",
        f"edit {entry.id}",
        f"new {entry.id}",
    ]


def test_history_ignores_models_drafts_and_trash(journal_dir):
    store.create(created=dt(8), body="hello")
    assert set((journal_dir / ".gitignore").read_text().split()) == {"models/", "drafts/", ".trash/"}


def test_history_disabled_makes_no_repo(journal_dir, tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("[history]\nenabled = false\n")
    monkeypatch.setenv("JOURNAL_CONFIG", str(config))

    store.create(created=dt(8), body="hello")
    assert not (journal_dir / ".git").exists()


def test_write_succeeds_without_git(journal_dir, monkeypatch, capsys):
    monkeypatch.setattr("journal.history.shutil.which", lambda name: None)

    assert main(["new", "--text", "no git here"]) == 0
    assert not (journal_dir / ".git").exists()
