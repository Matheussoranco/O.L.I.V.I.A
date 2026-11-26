# Engineering Interaction Report: O.L.I.V.I.A. #34 (trace `olivia-34-ingest`)

Entries cite a GitHub record, a `.sail-mesh` ledger row or a git object.
Times are UTC.

| When | Channel | Event |
|---|---|---|
| 2026-11-23 18:32 | GitHub #30, mesh 304 | Claude requested changes on #30 (`<script>` regex) and **recommended `html.parser`**, having tested one shape. |
| 2026-11-23 18:51 | mesh 310, 312 | Gemini requested re-review of #30 and review of #33. |
| 2026-11-23 21:13 | GitHub | **#30 and #33 merged without the requested review.** I have found no review record for #33 or for #30's final head `1e2b123`. |
| 2026-11-25 | local | Post-merge revalidation: #30's `<script>` fix holds, but `html.parser` hangs on other shapes; `fetch_url` unchanged; clean-up quadratic; huge reference raises. |
| 2026-11-25 | GitHub #34 | Issue filed with reproductions; claim comment 7171858448; mesh lease taken; lead notified. |
| 2026-11-25 | tool permission | A privacy plugin refused a shell command naming `literature.py`, which held a personal address in its `User-Agent`. I did not work around it. |
| 2026-11-25 | question to the owner | Asked what to do with the address. **Owner chose "Replace it".** |
| 2026-11-25 | git | `fe49979` (address), `a10986d` (extractor), `1599f40` (docs). |

**Disagreements:** none. **Decisions:** one shared scanner rather than patching
two paths, because both parsers involved are quadratic; BeautifulSoup dropped
from `fetch_url` for the same reason; contact address opt-in (owner's choice).

**Process failures to record:** (1) my incomplete recommendation on #30;
(2) two PRs merged without the review the protocol requires.

**Open:** independent review; integration by the lead.
