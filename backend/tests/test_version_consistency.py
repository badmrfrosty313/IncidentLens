"""One release version everywhere: backend package, API, frontend package and its lockfile."""

import json
import re
from pathlib import Path

from app import __version__

REPO = Path(__file__).resolve().parents[2]


def test_versions_agree_across_the_repository():
    pyproject = (REPO / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    py_version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    package = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((REPO / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    assert {__version__, py_version, package["version"], lock["version"], lock["packages"][""]["version"]} == {__version__}


def test_release_notes_exist_for_the_current_version():
    assert (REPO / "docs" / f"RELEASE_NOTES_v{__version__}.md").is_file()
