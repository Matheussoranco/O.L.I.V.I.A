"""Study source ingestion (PDF/HTML/text/arXiv) and CLI end-to-end tests (#14)."""

from __future__ import annotations

import importlib.util
import json
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from olivia.__main__ import app
from olivia.eval.study_eval import _score_card
from olivia.llm.client import NullClient
from olivia.study import (
    Deck,
    StudySourceError,
    clean_extracted_text,
    extract_pdf_text,
    fetch_arxiv_content,
    generate_flashcards,
    generate_quiz,
    generate_worksheet,
    load_study_content,
    normalize_arxiv_id,
)

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None
_needs_sympy = pytest.mark.skipif(not _HAS_SYMPY, reason="sympy not installed")

runner = CliRunner()


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _make_minimal_pdf(pages: list[list[str]], *, compress: bool = False) -> bytes:
    """Build a valid, standards-compliant synthetic PDF with literal text streams."""
    objects: list[bytes] = []
    # 1: Catalog, 2: Pages, 3: Font
    page_ids: list[int] = []
    next_id = 4
    page_objs: list[tuple[int, int, bytes]] = []
    for lines in pages:
        content_ops = ["BT", "/F1 12 Tf", "72 720 Td"]
        for idx, line in enumerate(lines):
            if idx > 0:
                content_ops.append("0 -16 Td")
            content_ops.append(f"({_escape_pdf_text(line)}) Tj")
        content_ops.append("ET")
        stream_data = "\n".join(content_ops).encode("latin-1")
        page_id = next_id
        stream_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        page_objs.append((page_id, stream_id, stream_data))

    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids).encode("ascii")
    objects.append(
        b"2 0 obj\n<< /Type /Pages /Kids ["
        + kids
        + f"] /Count {len(page_ids)} >>\nendobj\n".encode()
    )
    objects.append(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    for page_id, stream_id, stream_data in page_objs:
        objects.append(
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>\n"
            f"endobj\n".encode("ascii")
        )
        if compress:
            payload = zlib.compress(stream_data)
            header = f"<< /Length {len(payload)} /Filter /FlateDecode >>".encode("ascii")
        else:
            payload = stream_data
            header = f"<< /Length {len(payload)} >>".encode("ascii")
        objects.append(
            f"{stream_id} 0 obj\n".encode("ascii")
            + header
            + b"\nstream\n"
            + payload
            + b"\nendstream\nendobj\n"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


_KREBS_PAGES = [
    [
        "The citric acid cycle runs inside the mitochondrial matrix of eukaryotic cells.",
        "Acetyl coenzyme condenses with oxaloacetate to produce six-carbon citrate.",
        "Aconitase isomerizes citrate into isocitrate via cis-aconitate intermediate.",
        "Isocitrate dehydrogenase catalyzes oxidative decarboxylation releasing NADH.",
        "Alpha-ketoglutarate dehydrogenase forms high-energy succinyl thioester.",
        "1",
    ],
    [
        "Succinyl synthetase couples phosphorylation to generate guanosine triphosphate.",
        "Succinate dehydrogenase oxidizes succinate to fumarate reducing flavin cofactor.",
        "Fumarase hydrates fumarate double bonds to yield stereospecific malate.",
        "Malate dehydrogenase regenerates oxaloacetate and yields reducing equivalents.",
        "Pyruvate dehydrogenase bridges cytosolic glycolysis with mitochondrial respiration.",
        "2",
    ],
]

_BAYESIAN_PAGES = [
    [
        "Bayesian inference updates prior probability distributions as observations arrive.",
        "The posterior density equals the normalized product of likelihood and prior belief.",
        "Conjugate priors yield closed-form posteriors without numerical quadrature.",
        "Markov chain Monte Carlo approximates intractable normalizing constants cleanly.",
        "Credible intervals summarize posterior parameter uncertainty given observations.",
        "Hierarchical models share statistical strength across grouped hyperpriors.",
    ]
]


# ---------------------------------------------------------------------------
# PDF extraction & normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("compress", [False, True])
def test_extract_pdf_text_reads_uncompressed_and_flatedecode(tmp_path: Path, compress: bool):
    pdf = tmp_path / "krebs.pdf"
    pdf.write_bytes(_make_minimal_pdf(_KREBS_PAGES, compress=compress))

    text = extract_pdf_text(pdf)
    assert "mitochondrial matrix" in text
    assert "oxaloacetate" in text
    assert "guanosine triphosphate" in text
    # Bare page numbers stripped cleanly.
    assert "\n1\n" not in text and "\n2\n" not in text


def test_clean_extracted_text_rejoins_hyphenated_line_wraps():
    raw = (
        "Mitochondrial phos-\nphorylation powers cellular respira-\ntion.\n\n"
        "Page 3\n\nNext paragraph."
    )
    cleaned = clean_extracted_text(raw)
    assert "phosphorylation" in cleaned
    assert "respiration." in cleaned
    assert "Page 3" not in cleaned


def test_load_study_content_strips_html(tmp_path: Path):
    html = tmp_path / "notes.html"
    html.write_text(
        "<html><body><script>evil()</script><p>Entropy measures thermodynamic disorder.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    text = load_study_content(content_file=html)
    assert "Entropy measures thermodynamic disorder." in text
    assert "evil()" not in text


def test_extract_pdf_text_rejects_invalid_and_encrypted_pdfs(tmp_path: Path):
    not_pdf = tmp_path / "fake.pdf"
    not_pdf.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(StudySourceError, match="not a valid PDF"):
        extract_pdf_text(not_pdf)

    encrypted = tmp_path / "locked.pdf"
    encrypted.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n%%EOF\n")
    with pytest.raises(StudySourceError, match="encrypted"):
        extract_pdf_text(encrypted)

    with pytest.raises(StudySourceError, match="does not exist"):
        load_study_content(content_file=tmp_path / "missing.pdf")


def test_extract_pdf_handles_tj_kerning_and_hex_strings(tmp_path: Path):
    stream = (
        b"BT /F1 12 Tf 72 720 Td "
        b"[(Bayes) -150 (theorem) -150 (updates)] TJ 0 -16 Td "
        b"<506f73746572696f72> Tj ET"
    )
    raw = (
        b"%PDF-1.4\n1 0 obj\n<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF\n"
    )
    pdf = tmp_path / "tj_hex.pdf"
    pdf.write_bytes(raw)
    text = extract_pdf_text(pdf)
    assert "Bayes theorem updates" in text
    assert "Posterior" in text


# ---------------------------------------------------------------------------
# arXiv normalization & guarded fetching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2301.07041", "2301.07041"),
        ("arXiv:1706.03762v7", "1706.03762v7"),
        ("https://arxiv.org/abs/1706.03762", "1706.03762"),
        ("https://arxiv.org/pdf/2301.07041v2.pdf", "2301.07041v2"),
        ("hep-th/9901001", "hep-th/9901001"),
    ],
)
def test_normalize_arxiv_id_valid(raw: str, expected: str):
    assert normalize_arxiv_id(raw) == expected


@pytest.mark.parametrize("bad", ["", "https://evil.example/abs/1706.03762", "../../etc/passwd"])
def test_normalize_arxiv_id_rejects_invalid_and_non_arxiv_urls(bad: str):
    with pytest.raises(StudySourceError):
        normalize_arxiv_id(bad)


def test_fetch_arxiv_content_blocks_when_network_disabled():
    with pytest.raises(StudySourceError, match="network access"):
        fetch_arxiv_content("1706.03762", allow_network=False)


def test_fetch_arxiv_content_parses_atom_xml(monkeypatch: pytest.MonkeyPatch):
    atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Attention Is All You Need</title>
        <summary>
          Dominant sequence models rely on recurrent or convolutional layers.
          The Transformer architecture relies solely on self-attention mechanisms.
        </summary>
      </entry>
    </feed>"""

    monkeypatch.setattr(
        "olivia.tools.literature._get",
        lambda url, params=None, allow_network=None: SimpleNamespace(text=atom_xml),
    )
    text = fetch_arxiv_content("https://arxiv.org/abs/1706.03762", allow_network=True)
    assert "Attention Is All You Need" in text
    assert "self-attention mechanisms" in text

    # CLI --arxiv --network end-to-end check
    res = runner.invoke(
        app,
        ["study", "cards", "Transformers", "--arxiv", "1706.03762", "--network", "-n", "3"],
    )
    assert res.exit_code == 0, res.output
    assert "Added 3 new cards to deck 'Transformers'" in res.output


# ---------------------------------------------------------------------------
# Acceptance Criteria End-to-End CLI Tests (#14)
# ---------------------------------------------------------------------------


def test_cli_study_cards_from_pdf_generates_15_grounded_cards_in_sm2_deck(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(_make_minimal_pdf(_KREBS_PAGES, compress=True))

    res = runner.invoke(
        app,
        ["study", "cards", "Krebs cycle", "--content-file", str(pdf), "-n", "15"],
    )
    assert res.exit_code == 0, res.output
    assert "Added 15 new cards to deck 'Krebs cycle' (15 total)." in res.output

    deck = Deck("Krebs cycle")
    assert len(deck.cards) == 15
    source_text = extract_pdf_text(pdf)
    scores = [_score_card(card, source_text) for card in deck.cards]
    answer_in_source = sum(s["answer_in_source"] for s in scores) / len(scores)
    assert answer_in_source >= 0.95
    assert all(s["blank_present"] and s["answer_not_in_front"] for s in scores)
    assert len({c.front for c in deck.cards}) == 15


@_needs_sympy
def test_cli_study_worksheet_from_pdf_generates_8_solved_problems_and_answer_key(tmp_path: Path):
    pdf = tmp_path / "quadratics.pdf"
    pdf.write_bytes(
        _make_minimal_pdf(
            [
                [
                    "Quadratic Equations Practice Sheet",
                    "solve x**2 - 5*x + 6 = 0 for x",
                    "solve x**2 - 9 = 0 for x",
                    "Every monic quadratic factors over its roots.",
                ]
            ],
            compress=True,
        )
    )
    out_md = tmp_path / "worksheet.md"

    res = runner.invoke(
        app,
        [
            "study",
            "worksheet",
            "quadratic equations",
            "--content-file",
            str(pdf),
            "-n",
            "8",
            "--output",
            str(out_md),
        ],
    )
    assert res.exit_code == 0, res.output
    rendered = out_md.read_text(encoding="utf-8")
    assert "# Worksheet: quadratic equations" in rendered
    assert "## Answer key" in rendered
    assert rendered.count("**Answer:**") == 8
    assert "x**2 - 5*x + 6 = 0" in rendered


def test_cli_study_quiz_from_pdf_interactive_grading(tmp_path: Path):
    pdf = tmp_path / "bayesian.pdf"
    pdf.write_bytes(_make_minimal_pdf(_BAYESIAN_PAGES, compress=True))

    source_text = extract_pdf_text(pdf)
    expected_questions = generate_quiz(
        "Bayesian statistics", content=source_text, client=NullClient(), n=3
    )
    assert len(expected_questions) == 3
    # Every question hides its answer from its prompt.
    assert all(q.answer_text.casefold() not in q.prompt.casefold() for q in expected_questions)

    # Answer Q1 and Q2 correctly, Q3 with a free-form mismatch (ungraded).
    stdin_answers = (
        f"{expected_questions[0].answer_text}\n{expected_questions[1].answer_text}\nwrong_guess\n"
    )
    res = runner.invoke(
        app,
        ["study", "quiz", "Bayesian statistics", "--content-file", str(pdf), "-n", "3"],
        input=stdin_answers,
    )
    assert res.exit_code == 0, res.output
    assert "Score: 2/2 graded (100.0%) — 3 questions total" in res.output


def test_worksheet_llm_receives_grounded_content(fake_client):
    payload = {"problems": ["solve 2*x + 4 = 10 for x"]}
    client = fake_client(json.dumps(payload))
    sheet = generate_worksheet(
        "linear equations",
        n=1,
        client=client,
        content="Notes on solving linear equations in one variable.",
    )
    assert len(sheet) == 1
    assert "Notes on solving linear equations" in client.calls[0][0]["content"]


def test_flashcards_offline_multi_pass_reaches_requested_count_without_duplicates():
    short_content = (
        "Mitochondria synthesize adenosine triphosphate via oxidative phosphorylation. "
        "Chloroplasts capture electromagnetic radiation inside thylakoid membranes."
    )
    cards = generate_flashcards("bioenergetics", content=short_content, client=NullClient(), n=6)
    assert len(cards) == 6
    assert len({c.front for c in cards}) == 6
    for card in cards:
        scored = _score_card(card, short_content)
        assert all(scored.values()), scored
