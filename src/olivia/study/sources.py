"""Study source loading — plain text, Markdown, HTML, PDF, and arXiv papers.

Provides a single deterministic loader for ``olivia study cards | worksheet | quiz``
so local files (including ``.pdf``) and arXiv identifiers can ground study material
without crashing on binary encodings.

PDF extraction prefers PyMuPDF (``fitz``, from the ``olivia[docs]`` extra) when
installed and falls back to a pure-Python standard-library extractor for
uncompressed and FlateDecode text PDFs so minimal/offline installs remain usable.
"""

from __future__ import annotations

import importlib
import logging
import re
import zlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from olivia.core.errors import OliviaError

logger = logging.getLogger(__name__)

_MAX_STREAM_BYTES = 10 * 1024 * 1024  # 10 MiB safety cap per FlateDecode stream
_MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MiB file-size cap

_ARXIV_NEW_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$", re.IGNORECASE)
_ARXIV_OLD_RE = re.compile(r"^[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?$")

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_ATOM = "{http://www.w3.org/2005/Atom}"


class StudySourceError(OliviaError):
    """Raised when a study source file or arXiv reference cannot be loaded."""


_STANDALONE_LINE_RE = re.compile(
    r"^(?:(?:problem|exercise|question)\s*\d*\s*[:.)-]|"
    r"(?:solve|differentiate|integrate|factor|simplify|expand|convert|balance)\b|"
    r"\d{1,3}[.)]\s+)",
    re.IGNORECASE,
)


def clean_extracted_text(text: str) -> str:
    """Normalize extracted document text for sentence-level study generation."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Rejoin words split across PDF line wraps: "photo-\nsynthesis" -> "photosynthesis".
    normalized = re.sub(r"([A-Za-zÀ-ÿ])-\n([a-zà-ÿ])", r"\1\2", normalized)
    cleaned_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        # Drop bare page numbers ("12", "Page 12", "- 4 -") that fragment sentences.
        if re.fullmatch(r"(?:page\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?", line, re.IGNORECASE):
            continue
        cleaned_lines.append(line)

    # Collapse wrapped prose lines while keeping blank lines and standalone problem/equation lines.
    paragraphs: list[str] = []
    current: list[str] = []
    for line in cleaned_lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        is_standalone = bool(_STANDALONE_LINE_RE.match(line)) or ("=" in line and len(line) <= 120)
        if is_standalone:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            paragraphs.append(line)
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))

    joined = "\n\n".join(paragraphs)
    return re.sub(r"[ \t]{2,}", " ", joined).strip()


# ---------------------------------------------------------------------------
# Pure-Python PDF text extraction fallback (stdlib only)
# ---------------------------------------------------------------------------


def _decode_pdf_literal(raw: bytes, start: int) -> tuple[str, int]:
    """Decode a PDF literal string starting at '(' and return (text, next_index)."""
    out = bytearray()
    depth = 1
    i = start + 1
    n = len(raw)
    while i < n and depth > 0:
        b = raw[i]
        if b == 0x5C:  # backslash escape
            i += 1
            if i >= n:
                break
            esc = raw[i]
            if esc == ord("n"):
                out.append(0x0A)
            elif esc == ord("r"):
                out.append(0x0D)
            elif esc == ord("t"):
                out.append(0x09)
            elif esc == ord("b"):
                out.append(0x08)
            elif esc == ord("f"):
                out.append(0x0C)
            elif esc in (ord("("), ord(")"), ord("\\")):
                out.append(esc)
            elif esc == 0x0D:
                if i + 1 < n and raw[i + 1] == 0x0A:
                    i += 1
            elif esc == 0x0A:
                pass  # line continuation
            elif 0x30 <= esc <= 0x37:  # octal \ddd (1 to 3 digits)
                digits = [esc]
                for _ in range(2):
                    if i + 1 < n and 0x30 <= raw[i + 1] <= 0x37:
                        i += 1
                        digits.append(raw[i])
                    else:
                        break
                out.append(int(bytes(digits), 8) & 0xFF)
            else:
                out.append(esc)
            i += 1
        elif b == ord("("):
            depth += 1
            out.append(b)
            i += 1
        elif b == ord(")"):
            depth -= 1
            if depth > 0:
                out.append(b)
            i += 1
        else:
            out.append(b)
            i += 1
    return _bytes_to_pdf_text(bytes(out)), i


def _decode_pdf_hex(raw: bytes, start: int) -> tuple[str, int]:
    """Decode a PDF hex string starting at '<' and return (text, next_index)."""
    end = raw.find(b">", start + 1)
    if end == -1:
        return "", len(raw)
    hex_chars = re.sub(rb"\s+", b"", raw[start + 1 : end])
    if len(hex_chars) % 2 == 1:
        hex_chars += b"0"
    try:
        decoded = bytes.fromhex(hex_chars.decode("ascii"))
    except ValueError:
        return "", end + 1
    return _bytes_to_pdf_text(decoded), end + 1


def _bytes_to_pdf_text(data: bytes) -> str:
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="ignore")
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="ignore")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


def _extract_text_from_content_stream(stream: bytes) -> str:
    """Extract text runs from BT...ET blocks inside a single PDF content stream."""
    chunks: list[str] = []
    for block_match in re.finditer(rb"\bBT\b(.*?)\bET\b", stream, re.DOTALL):
        block = block_match.group(1)
        block_parts: list[str] = []
        tokens: list[tuple[str, Any]] = []
        i = 0
        n = len(block)
        while i < n:
            b = block[i]
            if b in (0x09, 0x0A, 0x0C, 0x0D, 0x20):
                i += 1
            elif b == ord("%"):  # comment to end of line
                nl = block.find(b"\n", i)
                i = n if nl == -1 else nl + 1
            elif b == ord("("):
                text, i = _decode_pdf_literal(block, i)
                tokens.append(("str", text))
            elif b == ord("<") and i + 1 < n and block[i + 1] != ord("<"):
                text, i = _decode_pdf_hex(block, i)
                tokens.append(("str", text))
            elif b == ord("["):
                arr_parts: list[str] = []
                i += 1
                while i < n and block[i] != ord("]"):
                    c = block[i]
                    if c == ord("("):
                        text, i = _decode_pdf_literal(block, i)
                        arr_parts.append(text)
                    elif c == ord("<") and i + 1 < n and block[i + 1] != ord("<"):
                        text, i = _decode_pdf_hex(block, i)
                        arr_parts.append(text)
                    elif c in (ord("+"), ord("-"), ord(".")) or 0x30 <= c <= 0x39:
                        j = i + 1
                        while j < n and (block[j] in (ord("."),) or 0x30 <= block[j] <= 0x39):
                            j += 1
                        try:
                            kern = float(block[i:j])
                            # Large negative kerning in TJ arrays represents a word space.
                            if kern <= -120.0:
                                arr_parts.append(" ")
                        except ValueError:
                            pass
                        i = j
                    else:
                        i += 1
                if i < n and block[i] == ord("]"):
                    i += 1
                tokens.append(("arr", "".join(arr_parts)))
            else:
                j = i + 1
                while j < n and block[j] not in b" \t\r\n\f()<>[]/%":
                    j += 1
                op = block[i:j].decode("latin-1", errors="ignore")
                if op in ("Tj", "'", '"'):
                    for kind, val in reversed(tokens):
                        if kind == "str":
                            if op in ("'", '"') and block_parts:
                                block_parts.append("\n")
                            block_parts.append(val)
                            break
                    tokens.clear()
                elif op == "TJ":
                    for kind, val in reversed(tokens):
                        if kind == "arr":
                            block_parts.append(val)
                            break
                    tokens.clear()
                elif op in ("Td", "TD", "T*"):
                    if block_parts and not block_parts[-1].endswith(("\n", " ")):
                        block_parts.append("\n")
                    tokens.clear()
                else:
                    tokens.append(("op", op))
                i = j
        if block_parts:
            chunks.append("".join(block_parts))
    return "\n".join(chunks)


def _decompress_bounded(data: bytes, max_bytes: int = _MAX_STREAM_BYTES) -> bytes | None:
    """Inflate zlib stream with a strict output ceiling against zip-bomb PDFs."""
    try:
        decomp = zlib.decompressobj()
        out = decomp.decompress(data, max_bytes + 1)
        if len(out) > max_bytes:
            logger.warning("Skipping oversized FlateDecode PDF stream (> %d bytes)", max_bytes)
            return None
        return out
    except zlib.error:
        return None


def _extract_pdf_text_stdlib(raw: bytes) -> str:
    """Pure-Python fallback PDF text extractor for uncompressed/FlateDecode PDFs."""
    if re.search(rb"/Encrypt\b", raw):
        raise StudySourceError(
            "PDF is encrypted and cannot be extracted without PyMuPDF "
            "(install with: pip install 'olivia[docs]')."
        )

    extracted: list[str] = []
    pos = 0
    total = len(raw)
    while pos < total:
        idx = raw.find(b"stream", pos)
        if idx == -1:
            break
        # Must be a standalone keyword followed by LF or CRLF.
        if idx > 0 and raw[idx - 1 : idx] not in b" \t\r\n>":
            pos = idx + 6
            continue
        after = idx + 6
        if raw[after : after + 2] == b"\r\n":
            data_start = after + 2
        elif raw[after : after + 1] == b"\n":
            data_start = after + 1
        else:
            pos = after
            continue

        end_idx = raw.find(b"endstream", data_start)
        if end_idx == -1:
            break
        body = raw[data_start:end_idx]
        if body.endswith(b"\r\n"):
            body = body[:-2]
        elif body.endswith(b"\n"):
            body = body[:-1]

        # Inspect only the enclosing object dictionary preceding this stream.
        obj_start = raw.rfind(b"obj", max(0, idx - 2048), idx)
        header = raw[obj_start if obj_start != -1 else max(0, idx - 512) : idx]
        pos = end_idx + 9

        if b"/FlateDecode" in header:
            inflated = _decompress_bounded(body)
            if inflated is None:
                continue
            payload = inflated
        elif b"/Filter" in header:
            # Unsupported filter (e.g., LZW, DCTDecode image) — skip safely.
            continue
        else:
            payload = body

        if b"BT" in payload and b"ET" in payload:
            text = _extract_text_from_content_stream(payload)
            if text.strip():
                extracted.append(text)

    return clean_extracted_text("\n\n".join(extracted))


def extract_pdf_text(path: str | Path, *, max_chars: int = 200_000) -> str:
    """Extract clean readable text from a local PDF file."""
    pdf_path = Path(path)
    try:
        size = pdf_path.stat().st_size
    except OSError as exc:
        raise StudySourceError(f"Cannot access PDF {pdf_path}: {exc}") from exc

    if size > _MAX_PDF_BYTES:
        raise StudySourceError(
            f"PDF {pdf_path} is too large ({size} bytes; limit is {_MAX_PDF_BYTES} bytes)."
        )

    try:
        raw = pdf_path.read_bytes()
    except OSError as exc:
        raise StudySourceError(f"Cannot read PDF {pdf_path}: {exc}") from exc

    if not raw.lstrip().startswith(b"%PDF-"):
        raise StudySourceError(f"{pdf_path} is not a valid PDF file (missing %PDF- header).")

    try:
        fitz: Any = importlib.import_module("fitz")
    except ImportError:
        fitz = None

    if fitz is not None:
        try:
            with fitz.open(pdf_path) as doc:
                if getattr(doc, "is_encrypted", False):
                    raise StudySourceError(f"PDF {pdf_path} is encrypted and cannot be read.")
                pages = [page.get_text("text") for page in doc]
            text = clean_extracted_text("\n\n".join(pages))
        except StudySourceError:
            raise
        except Exception as exc:
            raise StudySourceError(f"PyMuPDF failed to read {pdf_path}: {exc}") from exc
    else:
        text = _extract_pdf_text_stdlib(raw)

    if not text:
        raise StudySourceError(
            f"No extractable text found in {pdf_path}. For complex or scanned PDFs, "
            "install PyMuPDF: pip install 'olivia[docs]'."
        )
    return text[:max_chars]


# ---------------------------------------------------------------------------
# arXiv fetching (guarded by literature network policy)
# ---------------------------------------------------------------------------


def normalize_arxiv_id(raw: str) -> str:
    """Validate and normalize an arXiv identifier or arXiv URL."""
    cleaned = raw.strip()
    if not cleaned:
        raise StudySourceError("arXiv reference cannot be empty.")

    if cleaned.lower().startswith("arxiv:"):
        cleaned = cleaned[6:].strip()
    elif cleaned.lower().startswith(("http://", "https://")):
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower()
        if host not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            raise StudySourceError(f"Not an arXiv URL: {raw!r}")
        path = parsed.path.strip("/")
        if path.startswith(("abs/", "pdf/")):
            cleaned = path.split("/", 1)[1]
            if cleaned.lower().endswith(".pdf"):
                cleaned = cleaned[:-4]
        else:
            raise StudySourceError(f"Unsupported arXiv URL path: {raw!r}")

    if _ARXIV_NEW_RE.match(cleaned) or _ARXIV_OLD_RE.match(cleaned):
        return cleaned
    raise StudySourceError(
        f"Invalid arXiv identifier {raw!r}. Expected e.g. '2301.07041', 'hep-th/9901001', "
        "or an https://arxiv.org/abs/... URL."
    )


def _parse_xml_root(xml_text: str) -> Any:
    """Parse XML safely, preferring defusedxml when installed."""
    try:
        defused_et = importlib.import_module("defusedxml.ElementTree")
        return defused_et.fromstring(xml_text)
    except ImportError:
        import xml.etree.ElementTree as ET  # nosec B405

        return ET.fromstring(xml_text)  # nosec B314


def fetch_arxiv_content(
    arxiv_ref: str,
    *,
    allow_network: bool | None = None,
    max_chars: int = 200_000,
) -> str:
    """Fetch an arXiv paper's title and abstract via the guarded Atom API."""
    from olivia.tools.literature import _get, _network_enabled

    arxiv_id = normalize_arxiv_id(arxiv_ref)
    if not _network_enabled(allow_network):
        raise StudySourceError(
            "Fetching arXiv papers requires network access "
            "(pass --network or set OLIVIA_NETWORK_ENABLED=true)."
        )

    response = _get(
        "https://export.arxiv.org/api/query",
        params={"id_list": arxiv_id, "max_results": 1},
        allow_network=True,
    )
    if response is None:
        raise StudySourceError(f"Could not fetch arXiv paper '{arxiv_id}' from export.arxiv.org.")

    try:
        root = _parse_xml_root(response.text)
    except Exception as exc:
        raise StudySourceError(f"Invalid XML response from arXiv for '{arxiv_id}': {exc}") from exc

    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        raise StudySourceError(f"No arXiv entry found for '{arxiv_id}'.")

    title = re.sub(r"\s+", " ", (entry.findtext(f"{_ATOM}title") or "").strip())
    summary = re.sub(r"\s+", " ", (entry.findtext(f"{_ATOM}summary") or "").strip())
    if not title or title.lower() == "error" or not summary:
        raise StudySourceError(f"arXiv paper '{arxiv_id}' returned no usable content.")

    combined = clean_extracted_text(f"{title}.\n\n{summary}")
    return combined[:max_chars]


# ---------------------------------------------------------------------------
# Unified loader
# ---------------------------------------------------------------------------


def _extract_html_text(raw_html: str) -> str:
    try:
        bs4 = importlib.import_module("bs4")
        soup = bs4.BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return clean_extracted_text(str(soup.get_text(" ", strip=True)))
    except ImportError:
        stripped = _TAG_RE.sub(" ", _SCRIPT_RE.sub(" ", raw_html))
        return clean_extracted_text(stripped)


def load_study_content(
    *,
    content_file: str | Path = "",
    arxiv: str = "",
    allow_network: bool | None = None,
    max_chars: int = 200_000,
) -> str:
    """Load study content from a local file (text/Markdown/HTML/PDF) and/or arXiv."""
    parts: list[str] = []

    if content_file:
        path = Path(content_file)
        if not path.exists():
            raise StudySourceError(f"Cannot read {path}: file does not exist.")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            parts.append(extract_pdf_text(path, max_chars=max_chars))
        else:
            try:
                raw_text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise StudySourceError(f"Cannot read {path}: {exc}") from exc
            if suffix in {".html", ".htm"}:
                parts.append(_extract_html_text(raw_text))
            else:
                parts.append(clean_extracted_text(raw_text))

    if arxiv:
        parts.append(fetch_arxiv_content(arxiv, allow_network=allow_network, max_chars=max_chars))

    return "\n\n".join(part for part in parts if part)[:max_chars]
