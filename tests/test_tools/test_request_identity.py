"""Outbound literature requests carry no personal data unless the user opts in."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import olivia
from olivia.config import settings
from olivia.config.settings import Settings
from olivia.tools import literature

# Reserved example domains are fine in source; anything else that looks like an
# address is somebody's.
_ADDRESS = re.compile(
    r"[A-Za-z0-9._%+-]+@(?!example\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,}"
)


def test_default_user_agent_names_no_contact(monkeypatch):
    monkeypatch.setattr(settings, "contact_email", "")
    assert literature._request_headers() == {"User-Agent": "olivia-research-agent/0.1"}


def test_contact_is_sent_only_when_the_user_sets_it(monkeypatch):
    monkeypatch.setattr(settings, "contact_email", "reader@example.org")
    assert literature._request_headers()["User-Agent"].endswith("(mailto:reader@example.org)")


@pytest.mark.parametrize(
    "value",
    ["not an address", "a@example.org\r\nX-Evil: 1", "a@example.org) (mailto:b@example.org", "@"],
)
def test_malformed_contact_is_never_put_in_a_header(monkeypatch, value):
    monkeypatch.setattr(settings, "contact_email", value)
    assert literature._request_headers() == {"User-Agent": "olivia-research-agent/0.1"}


def test_contact_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("OLIVIA_CONTACT_EMAIL", "reader@example.org")
    assert Settings(_env_file=None).contact_email == "reader@example.org"


def test_package_source_contains_no_personal_address():
    root = Path(olivia.__file__).parent
    found = [
        f"{path.relative_to(root)}"
        for path in root.rglob("*.py")
        if _ADDRESS.search(path.read_text(encoding="utf-8"))
    ]
    assert not found, f"e-mail address in package source: {found}"
