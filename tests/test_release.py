"""The version is written once and the changelog keeps up with it."""
import re
from pathlib import Path

import pytest

from rythe import __version__
from rythe.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_version_flag_prints_the_package_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"rythe {__version__}\n"


def test_the_version_is_three_numbers():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_the_newest_changelog_entry_is_the_current_version():
    headings = re.findall(r"^## (\S+)", (ROOT / "CHANGELOG.md").read_text(), flags=re.M)
    assert headings, "CHANGELOG.md has no version headings"
    assert headings[0] == __version__, "bump the version and add its changelog entry together"


def test_the_version_is_not_repeated_in_pyproject():
    assert not re.search(r'^version\s*=', (ROOT / "pyproject.toml").read_text(), flags=re.M)
