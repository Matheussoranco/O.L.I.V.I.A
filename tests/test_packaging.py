"""The package metadata must state the licence that LICENSE actually grants."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_declared_licence_matches_the_licence_file():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert licence.lstrip().startswith("Apache License")
    assert re.search(r'^license = "Apache-2\.0"$', pyproject, re.MULTILINE)
    assert re.search(r'^license-files = \["LICENSE"\]$', pyproject, re.MULTILINE)
    # PEP 639: an SPDX expression replaces the trove classifiers, which could
    # otherwise contradict it.
    assert "License ::" not in pyproject
