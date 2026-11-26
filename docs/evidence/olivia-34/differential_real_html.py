"""Differential: new extractor vs the previous stdlib one on real HTML files already on disk."""

import itertools
import os
from html.parser import HTMLParser
from pathlib import Path

from olivia.tools.html_text import html_to_text

SKIP = {"script", "style", "nav", "footer"}


class Old(HTMLParser):
    """Exactly the previous study-loader behaviour."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in SKIP:
            self.depth += 1
        elif self.depth == 0:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag.lower() in SKIP:
            self.depth = max(0, self.depth - 1)
        elif self.depth == 0:
            self.parts.append(" ")

    def handle_data(self, data):
        if self.depth == 0 and data:
            self.parts.append(data)


def files():
    roots = [Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Python", Path.home() / ".unsloth", Path.home() / "Documents" / "Code" / "M.I.R.A" / ".venv"]
    for root in roots:
        if root.is_dir():
            yield from root.rglob("*.htm*")


seen = same = 0
different = []
for path in itertools.islice((p for p in files() if p.is_file() and p.stat().st_size < 1_500_000), 600):
    markup = path.read_text(encoding="utf-8", errors="replace")
    old = Old()
    try:
        old.feed(markup)
        old.close()
    except Exception:  # noqa: BLE001
        continue
    a, b = "".join(old.parts).split(), html_to_text(markup).split()
    seen += 1
    if a == b:
        same += 1
    else:
        i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        different.append((len(a), len(b), path.name, a[i : i + 6], b[i : i + 6]))
print(f"real HTML files compared: {seen} | identical word sequence: {same} | different: {len(different)}")
for na, nb, name, x, y in different[:8]:
    print(f"- {name}: old {na} words, new {nb}\n    old: {x}\n    new: {y}")
