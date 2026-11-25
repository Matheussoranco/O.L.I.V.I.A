"""Search for super-linear inputs: every ordered pair of atoms, repeated; time N vs 4N."""

import itertools
import sys
import time

from olivia.study.sources import clean_extracted_text
from olivia.tools.html_text import html_to_text

HTML_ATOMS = ["<", ">", "/", "!", "-", "=", '"', "'", " ", "a", "<!--", "-->", "</", "<a", "<script", "</script",
              "<nav>", "</nav>", "<![CDATA[", "&", "#", "1", ";", "\n"]
TEXT_ATOMS = [" ", "\t", "\n", "-", "a", "1", "=", ".", ")", ":", "page", "problem", "exercise", "question",
              "solve", "\r", "a-\n", "—", "x", "12", "page ", "problem ", "1 ", "- "]


def measure(fn, data):
    best = float("inf")
    for _ in range(2):
        t = time.perf_counter()
        fn(data)
        best = min(best, time.perf_counter() - t)
    return best


def search(name, fn, atoms, base):
    worst, offenders, count = (0.0, None), [], 0
    for a, b in itertools.product(atoms, repeat=2):
        for shape, make in (
            ("repeat", lambda n, a=a, b=b: (a + b) * (n // len(a + b))),
            ("prefix", lambda n, a=a, b=b: a + b * (n // len(b)) + "x"),
        ):
            count += 1
            small, large = measure(fn, make(base)), measure(fn, make(base * 4))
            if large > worst[0]:
                worst = (large, (shape, a, b))
            # linear is about 4x; only judge when the large run is measurable
            if large > 0.05 and large / max(small, 1e-4) > 9:
                offenders.append((shape, a, b, round(small, 4), round(large, 4)))
    print(f"{name}: {count} shapes, slowest {worst[0]:.2f}s at {base * 4 // 1000} KB {worst[1]!r}")
    print(f"  super-linear candidates: {len(offenders)}")
    for o in offenders[:8]:
        print("   ", o)
    return offenders


bad = search("html_to_text", html_to_text, HTML_ATOMS, int(sys.argv[1]))
bad += search("clean_extracted_text", clean_extracted_text, TEXT_ATOMS, int(sys.argv[1]))
print("TOTAL candidates:", len(bad))
