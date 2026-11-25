"""HTML to readable text, in linear time, for input we do not trust.

``html_to_text`` serves both fetched web pages and local study files.  It is a
scanner for *finding the text*, not a validating HTML parser.

Why not use something existing: a ``<script>.*?</script>`` regex, the standard
library's ``html.parser`` and BeautifulSoup on top of it all take quadratic time
or worse on constructs that never terminate (``<!--``, ``<a href="`` ...).  The
``html.parser`` cases are fixed only in recent CPython releases, and this project
supports older ones, so the guarantee has to live here.

The linearity argument: there is one forward pass; every search starts where the
previous one stopped; and a construct that never terminates ends the scan, as
end-of-file does in a browser.  So no character is examined more than a constant
number of times.
"""

from __future__ import annotations

import html
import re

_DROPPED_ELEMENTS = ("nav", "footer")
"""Ordinary elements whose whole content is chrome rather than text."""

_RAW_END = {name: re.compile(rf"</{name}(?=[\s/>])", re.IGNORECASE) for name in ("script", "style")}
"""Elements whose content is not markup: only their own end tag closes them."""

_TAG_NAME = re.compile(r"[A-Za-z][^\s/>]*")
_TAG_DELIMITER = re.compile(r"[>=]")
_SPACE = re.compile(r"\s*")
_LT_RUN = re.compile(r"<+")
# ``html.unescape`` turns the digits into an int first, and Python refuses to do
# that beyond 4300 of them.  Anything over 7 significant digits is past the end of
# Unicode anyway.
_LONG_DECIMAL_REF = re.compile(r"&#([0-9]{8,})")


def _bounded_ref(match: re.Match[str]) -> str:
    digits = match.group(1).lstrip("0") or "0"
    return "�" if len(digits) > 7 else f"&#{digits}"


def _decode_references(text: str) -> str:
    return html.unescape(_LONG_DECIMAL_REF.sub(_bounded_ref, text))


def _end_of_start_tag(markup: str, pos: int) -> int:
    """Index of the ``>`` closing the start tag whose name ends at ``pos``.

    A ``>`` inside a quoted attribute value does not close the tag.  Returns -1
    when the tag never closes.
    """
    while found := _TAG_DELIMITER.search(markup, pos):
        if found.group() == ">":
            return found.start()
        value = _SPACE.match(markup, found.end()).end()  # type: ignore[union-attr]
        quote = markup[value : value + 1]
        if quote in ('"', "'"):
            closing = markup.find(quote, value + 1)
            if closing == -1:
                return -1
            pos = closing + 1
        else:
            pos = value
    return -1


def html_to_text(markup: str) -> str:
    """Return the readable text of ``markup``; tags become single spaces.

    The content of ``script``, ``style``, ``nav`` and ``footer`` elements is
    dropped.  Whitespace is not normalised; callers do that their own way.
    Never raises, whatever the input.
    """
    parts: list[str] = []
    open_dropped = dict.fromkeys(_DROPPED_ELEMENTS, 0)

    def visible() -> bool:
        return not any(open_dropped.values())

    def emit(chunk: str) -> None:
        if chunk and visible():
            parts.append(_decode_references(chunk) if "&" in chunk else chunk)

    def separate() -> None:
        if visible():
            parts.append(" ")

    pos, end = 0, len(markup)
    while pos < end:
        start = markup.find("<", pos)
        if start == -1:
            emit(markup[pos:])
            break
        emit(markup[pos:start])
        marker = markup[start + 1 : start + 2]

        if markup.startswith("<!--", start):
            closing = markup.find("-->", start + 2)  # +2 so "<!-->" closes itself
            if closing == -1:
                break
            pos = closing + 3
        elif marker in ("!", "?", "/"):  # doctype, CDATA, processing instruction, end tag
            closing = markup.find(">", start + 2)
            if closing == -1:
                break
            name = _TAG_NAME.match(markup, start + 2) if marker == "/" else None
            separate()
            if name and open_dropped.get(name.group().lower()):
                open_dropped[name.group().lower()] -= 1
                separate()
            pos = closing + 1
        elif name := _TAG_NAME.match(markup, start + 1):
            closing = _end_of_start_tag(markup, name.end())
            if closing == -1:
                break
            tag = name.group().lower()
            # "<nav/>" or "<script src=x />" but not "<script src=/path/>".
            slash = closing - 1
            self_closing = markup[slash] == "/" and (
                slash == name.end() or markup[slash - 1] in " \t\r\n\f\"'"
            )
            separate()
            pos = closing + 1
            if self_closing:
                continue
            if tag in open_dropped:
                open_dropped[tag] += 1
            elif tag in _RAW_END:
                found = _RAW_END[tag].search(markup, pos)
                closing = markup.find(">", found.end()) if found else -1
                if closing == -1:
                    break
                pos = closing + 1
        else:  # a "<" that starts no tag, as in "1 < 2"
            # Take a long run in one step, but leave its last "<": it may open a tag.
            run_end = _LT_RUN.match(markup, start).end()  # type: ignore[union-attr]
            after = max(start + 1, run_end - 1)
            emit(markup[start:after])
            pos = after

    return "".join(parts)
