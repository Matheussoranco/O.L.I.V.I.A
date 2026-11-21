"""Reproduce Gemini's PR #22 findings, one subprocess per case with a hard timeout."""

import subprocess
import sys
import time

CASES = {
    "B1 nested parens": "solve 2^(((999999999))) = x",
    "B2 tower 2^3^20": "solve 2^3^20 = x",
    "B2 tower 2^2^2^2^2": "solve 2^2^2^2^2 = x",
    "NB1 one eq, two unknowns": "solve x + y = 5 for x and y",
    "NB2 identity, absent unknown": "solve x + 1 = x + 1 for y",
}
SNIPPET = """
import sys
from olivia.study.equations import solve_equations
from olivia.study.solver import solve_problem
from olivia.llm.client import NullClient
p = sys.argv[1]
try:
    s = solve_equations(p)
    print("solve_equations ->", None if s is None else repr(s.final_answer))
except Exception as e:
    print("solve_equations raised", type(e).__name__, str(e)[:90])
s = solve_problem(p, client=NullClient())
print("solve_problem   ->", s.method, repr(s.final_answer))
"""
for label, problem in CASES.items():
    start = time.perf_counter()
    try:
        out = subprocess.run(
            [sys.executable, "-c", SNIPPET, problem], capture_output=True, text=True, timeout=15
        )
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        result = " | ".join(lines) or out.stderr.strip().splitlines()[-1]
    except subprocess.TimeoutExpired:
        result = "TIMEOUT (>15 s)"
    print(f"{label:30} {time.perf_counter() - start:5.1f}s  {result}")
