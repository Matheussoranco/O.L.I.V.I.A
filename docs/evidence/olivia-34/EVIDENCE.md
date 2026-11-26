# Evidence Pack: O.L.I.V.I.A. #34 (text ingestion hangs on untrusted input)

| Field | Value |
|---|---|
| Ticket | [#34](https://github.com/Matheussoranco/O.L.I.V.I.A/issues/34) |
| Trace id | `olivia-34-ingest` |
| Author | Claude Code (Sonnet 5.5) |
| Base | `origin/main` @ `1762482367b58345a1c7fc33a5ab8921e84708e6` |
| Revision verified | `1599f4015ca476c19c4fbc5feeeefb23e5a41e62` (branch `fix/34-linear-text-ingestion`); the commit adding this pack changes only `docs/evidence/` |
| Interpreter | CPython 3.12.10, venv built from the project's declared dependencies |
| Independent reviewer | **Pending** (Gemini requested) |
| Status | Implemented, gates pass. **Not reviewed.** |

## 1. How this was found

#30 merged with the `<script>` regex replaced by `html.parser`, **which I had
recommended in review after testing only that one input shape.** Revalidating
on `main` showed the recommendation was incomplete: `html.parser` is quadratic
on unterminated comments and attribute quotes in CPython 3.12.10 and 3.13.5
(not in 3.14.7). `fetch_url` had never been changed at all.

## 2. Acceptance → proof

| Criterion (#34) | Proof | Result |
|---|---|---|
| One shared extractor, linear by construction, independent of interpreter patch level and `bs4` | `tools/html_text.py`; both callers use it; neither imports `html.parser` or `bs4` | PASS |
| Hostile shapes at >= 1 MB finish in seconds; tests isolated with a hard timeout | `test_hostile_input_finishes_quickly_everywhere`: 15 shapes × both callers at 1 MB plus 7 clean-up lines at 300k, each <= 5 s, in a child process with a 150 s cap | PASS |
| No super-linear input found by search | `logs/scaling-search.txt`: 2,304 shapes, 0 candidates | PASS (see §4) |
| No input raises an undocumented error | 60 random-garbage cases; three huge-reference cases | PASS |
| Clean-up linear, normal output unchanged | `logs/probe-after.txt`; page-number and problem-line tests | PASS |
| Same output as before on well-formed HTML | 150 generated documents against `html.parser` as oracle; `logs/differential-real-html.txt`: **600 of 600** real HTML files already installed on this machine give the same word sequence | PASS |

## 3. Before and after (`logs/probe-before.txt`, `logs/probe-after.txt`)

| Input | before | after |
|---|---|---|
| `fetch_url`, unclosed `<script>`, 160 KB, default install | 42.7 s | 0.00 s |
| `fetch_url`, unclosed `<!--`, 160 KB, with `bs4` | 43.5 s | 0.00 s |
| `fetch_url`, unclosed `<a href="`, 80 KB, with `bs4` | killed at 45 s | 0.00 s |
| clean-up, `problem` + 20k spaces | 8.6 s | 0.00 s |
| `.html` with a 5000-digit character reference | raw `ValueError` | loads |

## 4. Limits of what was shown

- **Linear, with a constant.** The slowest shape the search found (`&<`
  repeated) costs about 4 µs per character: about 4 s per MB, 3 minutes for a
  file at the 50 MB study cap. It cannot grow worse than linearly, but it is
  not instant.
- **`fetch_url` still downloads the whole response** before extracting; there is
  no response size cap. Pre-existing and out of scope.
- **Timing on this machine is noisy** (the same input varied about 5× between
  runs). Where a ratio looked super-linear I re-measured across 3-5 sizes with
  CPU time, and for the one persistent case counted function calls: exactly
  2.00× for 2× input. A step in per-character cost between about 1 and 2
  million characters of `<` remains unexplained; taking runs of `<` in one step
  made that shape instant.
- The search covers ordered pairs of 24 atoms in two arrangements. It is strong
  evidence, not a proof; the argument for linearity is the single forward scan
  documented in the module.
- Only the HTML extraction and clean-up paths were examined. Flashcard and quiz
  generation on very large text was not.

## 5. Behaviour changes

- `fetch_url` no longer uses BeautifulSoup when installed.
- An unterminated tag, comment, `script` or `style` discards the rest of the
  document, as a browser does at end of file. The old default-install
  `fetch_url` regex leaked unterminated script text into the result.
- Literature requests send `User-Agent: olivia-research-agent/0.1` with no
  contact. `OLIVIA_CONTACT_EMAIL` opts in. The owner chose this when asked.
  **Earlier commits still contain the old address**; rewriting history was not
  done and is the owner's call.

## 6. Verification commands

See `logs/gates.txt`: ruff and format clean, mypy 0 issues in 69 files, **746
passed, 2 skipped**, `eval --check` holds, bandit 0 High / 0 Medium (6 Low,
identical to `main`).

Reproduce the search and the differential with
`PYTHONPATH=src python docs/evidence/olivia-34/scaling_search.py 30000` and
`PYTHONPATH=src python docs/evidence/olivia-34/differential_real_html.py`.

Mutation check on the identity test: with a synthetic address planted in the
package, `test_package_source_contains_no_personal_address` fails; removed, it
passes.
