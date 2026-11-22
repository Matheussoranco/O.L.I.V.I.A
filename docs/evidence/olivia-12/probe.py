"""Before/after probe for #12 — run with PYTHONPATH pointing at the tree under test.

    PYTHONPATH=<tree>/src python docs/evidence/olivia-12/probe.py [problem ...]

Prints method and final answer per problem, offline (NullClient).  The two
exponent cases stall origin/main for over a minute, so run those one at a time
under ``timeout`` there.
"""

import sys

from olivia.llm.client import NullClient
from olivia.study.solver import solve_problem

PROBES = [
    # Acceptance criteria (#12)
    "the system 2x + y = 10 and x - y = 2",
    "solve 2x + y = 10, x - y = 2",
    "x^2 - 5x + 6 = 0",
    "2*x + 3 = 7",
    # Notation and system variants
    "solve 2x + y = 10; x - y = 2",
    "solve for x and y: 2x + y = 10, x - y = 2",
    "solve x + y + z = 6, 2x - y + z = 3, x + 2y - z = 2",
    "x² − 5x + 6 = 0",
    "2×x + 3 = 7",
    "solve x1 + x2 = 3 and x1 - x2 = 1",
    "solve v = u + a*t for t",
    # Defects on origin/main
    "the value 2x = 4",
    "solve x + 1 = x + 1",
    "solve 3j = 6",
    "solve 0x + y = 1 and x + 0y = 2",
    # Must stay with other solvers
    "balance H2 + O2 = H2O",
    "If f(x) = 3x^2 + 2x, what is f'(x)?",
]

for problem in sys.argv[1:] or PROBES:
    solution = solve_problem(problem, client=NullClient())
    print(f"{problem!r:55} -> {solution.method:9} {solution.final_answer!r}")
