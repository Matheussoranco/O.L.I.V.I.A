"""#34: text ingestion must be linear and must not crash on untrusted input.

The hostile cases run in a child process with a hard timeout, so a regression
fails in seconds instead of hanging the suite.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
from html.parser import HTMLParser

import pytest

from olivia.study.sources import clean_extracted_text, load_study_content
from olivia.tools import literature
from olivia.tools.html_text import html_to_text


def _words(markup: str) -> list[str]:
    return html_to_text(markup).split()


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("markup", "words"),
    [
        ("<p>Hello <b>world</b></p>", ["Hello", "world"]),
        ("a<br>b<br/>c", ["a", "b", "c"]),
        ("x &amp; y &lt; z &#65; &#x42; &nbsp;end", ["x", "&", "y", "<", "z", "A", "B", "end"]),
        ("<!DOCTYPE html><?xml v?><p>t</p>", ["t"]),
        ("a <!-- hidden <p> --> b", ["a", "b"]),
        ("wo<!-- split -->rd", ["word"]),  # a comment is not whitespace
        ("a <!--> b <!---> c", ["a", "b", "c"]),
        ("<![CDATA[ gone ]]>kept", ["kept"]),
        ("<a title=\"x > y\" data-k='>'>link</a>", ["link"]),
        ("<a href=/p?q=1>go</a>", ["go"]),
        ("<p it's>odd quote outside a value</p>", ["odd", "quote", "outside", "a", "value"]),
        ("1 < 2 and 3 > 2", ["1", "<", "2", "and", "3", ">", "2"]),
        ("<<<<p>after a run</p>", ["<<<", "after", "a", "run"]),
        ("x << y <<= z", ["x", "<<", "y", "<<=", "z"]),
        ("<SCRIPT>var a = '</p>';</ScRiPt >after", ["after"]),
        ("<style>p{color:red}</style>text", ["text"]),
        ("<script>if (a < b) x('</scripted>')</script>ok", ["ok"]),
        ("<nav>menu<nav>deeper</nav>still menu</nav>body", ["body"]),
        ("<footer>legal</footer><p>body</p>", ["body"]),
        ("<nav/>visible", ["visible"]),
        ("<script src=x />visible", ["visible"]),
        ("<script src=/js/>var hidden = 1;</script>seen", ["seen"]),
        ("", []),
    ],
)
def test_extracts_readable_text(markup, words):
    assert _words(markup) == words


@pytest.mark.parametrize(
    "tail",
    ["<!-- never closed", "<!DOCTYPE never", '<a href="never', "<p", "</p", "<script>never"],
)
def test_unterminated_construct_discards_the_rest_like_a_browser(tail):
    assert _words(f"<p>before</p>{tail} after") == ["before"]


@pytest.mark.parametrize(
    "reference", ["&#" + "1" * 5000 + ";", "&#" + "0" * 5000 + "65;", "&#x" + "1" * 5000 + ";"]
)
def test_huge_character_references_do_not_raise(reference):
    out = html_to_text(f"<p>a {reference} b</p>").split()
    assert out[0] == "a" and out[-1] == "b"


def test_padded_but_valid_reference_still_decodes():
    assert _words("&#000000000065;") == ["A"]


# ---------------------------------------------------------------------------
# Differential check on well-formed documents, where html.parser is the oracle
# ---------------------------------------------------------------------------


class _Oracle(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.hidden += tag in {"script", "style", "nav", "footer"}
        self.parts.append(" ")

    def handle_endtag(self, tag):
        self.hidden -= tag in {"script", "style", "nav", "footer"}
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _document(rng: random.Random, depth: int = 0) -> str:
    pieces = []
    for _ in range(rng.randint(1, 5)):
        kind = rng.choice(["text", "text", "element", "comment", "raw", "void", "entity"])
        if kind == "text":
            pieces.append(rng.choice(["alpha ", "beta\n", "x = 1; ", "ção ", " 3.14 "]))
        elif kind == "entity":
            pieces.append(rng.choice(["&amp;", "&lt;", "&eacute;", "&#955;", "&#x3b1;"]))
        elif kind == "comment":
            pieces.append(f"<!-- {rng.choice(['c', '<p>', 'a - b'])} -->")
        elif kind == "void":
            pieces.append(rng.choice(["<br>", "<hr/>", '<img alt="a>b">', "<input value='<'>"]))
        elif kind == "raw":
            tag = rng.choice(["script", "style"])
            pieces.append(f"<{tag}>if (a<b && c>d) {{}} </{tag}>")
        elif depth < 4:
            tag = rng.choice(["p", "div", "span", "nav", "footer", "li", "h1"])
            attr = rng.choice(["", ' class="a b"', " data-x='1>0'", " hidden", " id=k"])
            pieces.append(f"<{tag}{attr}>{_document(rng, depth + 1)}</{tag}>")
    return "".join(pieces)


@pytest.mark.parametrize("seed", range(150))
def test_matches_html_parser_on_well_formed_documents(seed):
    markup = _document(random.Random(seed))
    oracle = _Oracle()
    oracle.feed(markup)
    oracle.close()
    assert _words(markup) == "".join(oracle.parts).split(), markup


@pytest.mark.parametrize("seed", range(60))
def test_random_garbage_never_raises(seed):
    rng = random.Random(seed)
    alphabet = [
        "<",
        ">",
        "/",
        "!",
        "-",
        "=",
        '"',
        "'",
        "&",
        "#",
        ";",
        " ",
        "a",
        "script",
        "nav",
        "\n",
    ]
    markup = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
    assert isinstance(html_to_text(markup), str)


# ---------------------------------------------------------------------------
# Both callers, and the text clean-up that follows them
# ---------------------------------------------------------------------------


class _Response:
    status_code = 200

    def __init__(self, text: str) -> None:
        self.text = text


def test_fetch_url_and_study_loader_share_the_extractor(monkeypatch, tmp_path):
    markup = "<nav>menu</nav><p>Chlorophyll absorbs <b>light</b>.</p><script>x()</script>"
    monkeypatch.setattr(literature, "_get", lambda url, **kw: _Response(markup))
    path = tmp_path / "page.html"
    path.write_text(markup, encoding="utf-8")

    fetched = literature.fetch_url("http://example.org")
    loaded = load_study_content(content_file=path)

    assert fetched.split() == loaded.split() == ["Chlorophyll", "absorbs", "light", "."]


@pytest.mark.parametrize("line", ["12", "Page 12", "page12", "- 4 -", "— 7", "7 —", "Page - 3 -"])
def test_page_number_lines_are_still_dropped(line):
    assert clean_extracted_text(f"before\n{line}\nafter") == "before after"


@pytest.mark.parametrize(
    "line", ["Problem 3: add", "exercise 12 ) add", "Question: why", "problem-solving"]
)
def test_problem_lines_still_stand_alone(line):
    assert clean_extracted_text(f"intro\n{line}\noutro").split("\n\n")[1] == line


_CHILD = r"""
import sys, tempfile, time
from pathlib import Path
from olivia.study.sources import clean_extracted_text, load_study_content
from olivia.tools import literature

SIZE = 1_000_000
shapes = ["<script>", "<style>", "<!--", '<a href="', "<a x='", "</", "<![CDATA[", "<", "<a ",
          "<a = ", "<nav>", "&#", "<!", "</script", "<script></"]
tmp = Path(tempfile.mkdtemp())

class R:
    status_code = 200

def run(label, fn):
    started = time.perf_counter()
    fn()
    print(f"{time.perf_counter() - started:.2f}\t{label!r}", flush=True)

for unit in shapes:
    R.text = "<p>real</p>" + unit * (SIZE // len(unit))
    literature._get = lambda url, **kw: R()
    run("fetch_url " + unit, lambda: literature.fetch_url("http://example.org"))
    path = tmp / "page.html"
    path.write_text(R.text, encoding="utf-8")
    run("study html " + unit, lambda: load_study_content(content_file=path))

for lead in ["page", "problem", "exercise", "question", "-", "7", "Page 7"]:
    line = lead + " " * 300_000 + "x"
    run("clean " + lead, lambda: clean_extracted_text(line))
"""


def test_hostile_input_finishes_quickly_everywhere():
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    try:
        child = subprocess.run(
            [sys.executable, "-c", _CHILD],
            capture_output=True,
            text=True,
            timeout=150,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        done = exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout
        pytest.fail(f"hung after:\n{done}")
    assert child.returncode == 0, child.stderr[-2000:]
    rows = [line.split("\t") for line in child.stdout.splitlines() if "\t" in line]
    assert len(rows) == 15 * 2 + 7
    slow = [(label, seconds) for seconds, label in rows if float(seconds) > 5.0]
    assert not slow, slow
