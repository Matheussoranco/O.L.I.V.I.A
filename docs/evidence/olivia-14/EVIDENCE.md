# Evidence Pack — O.L.I.V.I.A #14 (`T6: Flashcard/Worksheet/Quiz Generation from PDF/arXiv`)

- **Trace:** `olivia-14-t6`
- **Issue:** `Matheussoranco/O.L.I.V.I.A#14` (parent `#8`)
- **Author:** Gemini 4 Neon (High)
- **Branch / Worktree:** `feat/14-study-pdf-arxiv` (`O.L.I.V.I.A-wt14`, branched from `origin/main` @ `c1d797c5d7f5850caf00f8ba11a285cf86b2494d`)
- **Verification Verdict:** **PASS** (offline deterministic + mocked arXiv/LLM; live network/LLM not exercised)

---

## 1. Acceptance Criteria Mapping

| Criterion (`#14`) | Implementation | Verified By | Status |
|---|---|---|---|
| `olivia study cards "Krebs cycle" --content-file paper.pdf -n 15` → 15 cards, saved to SM-2 deck | `src/olivia/study/sources.py` (`extract_pdf_text`, `load_study_content`), multi-pass non-stopword `_cloze_cards` in `src/olivia/study/flashcards.py`, CLI wiring in `src/olivia/__main__.py` | `test_cli_study_cards_from_pdf_generates_15_grounded_cards_in_sm2_deck` (compressed FlateDecode 2-page PDF → 15 unique cards saved to `Deck("Krebs cycle")`, `answer_in_source == 100%`) | **PASS** |
| `olivia study worksheet "quadratic equations" --content-file paper.pdf -n 8` → 8 problems + answer key | Added `--content-file`, `--arxiv`, `--network` to `study worksheet`, `content: str = ""` to `generate_worksheet()`, strict source-grounded `_extract_content_problems()` (never falls back to generic templates when `content` is supplied), AND `_is_grounded_in_content()` filtering in `_llm_worksheet()` rejecting off-topic/ungrounded provider output | `test_cli_study_worksheet_from_pdf_generates_8_solved_problems_and_answer_key`, `test_worksheet_source_grounded_never_falls_back_to_generic_topic_templates`, `test_worksheet_llm_rejects_off_topic_ungrounded_exercises` | **PASS** |
| `olivia study quiz "Bayesian statistics" --content-file paper.pdf` → interactive quiz, grades answers | Updated `study quiz` CLI to load PDF/HTML/text/arXiv via `load_study_content`, multi-pass cloze fallback in `src/olivia/study/quiz.py` | `test_cli_study_quiz_from_pdf_interactive_grading` (interactive `CliRunner` prompts + `grade_quiz` output `Score: 2/2 graded (100.0%) — 3 questions total`) | **PASS** |
| arXiv support (`--arxiv <id_or_url>`) respecting offline-first security policy | `normalize_arxiv_id()` allowlist + `fetch_arxiv_content()` gated by `literature._network_enabled` & `_get` (`_safe_url`) | `test_normalize_arxiv_id_valid`, `test_normalize_arxiv_id_rejects_invalid_and_non_arxiv_urls`, `test_fetch_arxiv_content_blocks_when_network_disabled`, `test_fetch_arxiv_content_parses_atom_xml` | **PASS** |
| Content grounded in source (`generation.answer_in_source >= 95%`) | Stopword-filtered verbatim cloze extraction with `clean_extracted_text()` | `olivia eval --check`: `generation.answer_in_source = 100.0% (36/36)`, `generation.quiz_answer_not_in_prompt = 100.0% (36/36)`, `generation.front_grounded = 100.0% (36/36)` | **PASS** |

---

## 2. Commands Actually Executed & Observed Results (Round 2)

| Command | Result |
|---|---|
| `uv run --python 3.12 --extra dev --extra science ruff check src tests` | `All checks passed!` |
| `uv run --python 3.12 --extra dev --extra science ruff format --check src tests` | `92 files already formatted` |
| `uv run --python 3.12 --extra dev --extra science mypy src/olivia` | `Success: no issues found in 66 source files` |
| `uv run --python 3.12 --extra dev --extra science pytest tests/ -q` | `399 passed, 2 skipped in 17.56s` (22 tests in `tests/test_study/test_sources_and_cli.py`, including source-grounding non-fallback regression) |
| `uv run --python 3.12 --extra dev --extra science olivia eval --check` | `All gates hold.` (`study` suite: `100.0%` across all SM-2, grading, flashcard fidelity, and `quiz_answer_not_in_prompt` metrics) |

---

## 3. Architecture, Security & Known Limitations

- **Zero new required dependencies:** `extract_pdf_text` prefers PyMuPDF (`fitz`, declared in `olivia[docs]`) when installed and falls back to a linear-time stdlib PDF stream parser supporting uncompressed and `/FlateDecode` text streams (`Tj`, `TJ`, `'`, `"`, literal escapes, hex/UTF-16 strings), bounded at 50 MiB file size and 10 MiB decompressed stream size to mitigate zip-bomb PDFs.
- **Honest degradation:** Encrypted PDFs, scanned/image-only PDFs, and unsupported stream filters raise `StudySourceError` with clear guidance pointing to `pip install 'olivia[docs]'` rather than silently returning garbage.
- **Network safety:** `--arxiv` validates IDs/URLs against an explicit arXiv host & ID allowlist and stays blocked offline unless `--network` or `OLIVIA_NETWORK_ENABLED=true` is explicitly provided.
- **Limitations:** PyMuPDF (`fitz`) and live `export.arxiv.org` network calls were not exercised in this offline environment; the pure-Python PDF fallback and mocked Atom XML parser were exercised end-to-end.
