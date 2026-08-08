# O.L.I.V.I.A. — Roadmap to 1.0 ("a study agent you can check")

> Status: drafted at **0.3.0** (2026-08-07), the release that added the
> evaluation harness. Every version line below is gated behind a **number this
> repository can reproduce**, not an adjective. The numbers in section 0 are
> the real 0.3 baseline, including the ones that are embarrassing.

Reproduce everything here with:

```bash
pip install -e ".[dev,science]"
olivia eval --check --json results.json --markdown scoreboard.md
```

---

## 0. Honest starting point (what 0.3.0 actually measures)

Three held-out suites, 195 scored cases, all offline. Measured 2026-08-07 on
Python 3.10.11 with `provider=none` and the `science` extra installed. Full run
in [`docs/eval/baseline-0.3.md`](eval/baseline-0.3.md).

### 0.1 Symbolic solving — 64 cases

| metric | value | n |
|---|---|---|
| `symbolic.accuracy` | **62.5%** | 64 |
| `symbolic.precision` (accuracy over cases it answered) | **97.6%** | 41 |
| `symbolic.coverage` (cases a deterministic solver claimed) | **64.1%** | 64 |
| `symbolic.wrong_rate` (answered, and wrong) | **1.6%** | 64 |
| `symbolic.abstain_rate` | **35.9%** | 64 |
| core tier — math / chemistry / physics / units | **100% / 100% / 100% / 100%** | 18 / 8 / 6 / 7 |
| reach tier — math / chemistry / physics / units | **0% / 16.7% / 0% / 0%** | 10 / 6 / 6 / 3 |
| `fallback.*` (the LLM path) | **not measured** — no backend | 23 |

Read honestly: **on the capabilities the README advertises, the symbolic path
is perfect — 39/39.** The 62.5% headline is entirely the reach tier, where it
scores **1/25**. OLIVIA does not do word problems, stoichiometry, applied
kinematics, or alternative phrasings of things it can do; it abstains, which is
the honest failure mode, and the design's "no LLM, no answer" contract holds.

The one exception is the number that matters most. `math-020`, "d/dx of e^x",
returns **`e**x*f*o*log(e)` with `method="symbolic"` and `confidence=0.9`.
Implicit multiplication parsed the English word "of" as `o*f`. A single
confidently wrong answer, dressed in the highest confidence the solver emits,
is worth more attention than the twenty-three honest abstentions around it.

### 0.2 Research-cycle critique — 27 cases (19 flawed, 8 sound controls)

| metric | value | n |
|---|---|---|
| `catch_rate` | **26.3%** | 19 |
| `false_alarm_rate` | **0.0%** | 8 |
| `balanced_accuracy` | **63.2%** | 27 |
| `youden_j` | **26.3%** | 27 |

Per flaw family:

| family | caught | designed for? |
|---|---|---|
| `unfalsifiable_structural` (no predictions / no refutation test) | **3/3** | yes |
| `overfit_n1_structural` (sample size below threshold) | **2/2** | yes |
| `unfalsifiable_semantic` (fields filled, content unfalsifiable) | **0/4** | no |
| `circular` (prediction restates the hypothesis) | **0/4** | no |
| `contradicted_by_evidence` (own analysis disconfirms it) | **0/4** | no |
| `overfit_n1_semantic` (universal claim from one case) | **0/2** | no |

Read honestly: the symbolic critic catches **exactly what it was built to
catch, and nothing else**. It is a schema validator, not a Popperian critic.
A hypothesis with a filled-in but vacuous falsification test, a dormitive-virtue
explanation, or a claim its own null result contradicts all pass untouched. The
0% false-alarm rate is genuine and worth keeping — it is not the artefact of a
critic that never flags, because the structural families prove it flags — but
`youden_j = 0.263` is the number that says how much signal is actually there.

### 0.3 Study tools — 104 scored cases

| metric | value | n |
|---|---|---|
| `sm2.sequence_exact` | **95.8%** | 24 |
| `sm2.step_exact` | **98.7%** | 157 |
| `sm2.lapse_step_exact` (q < 3 branch) | **100%** | 39 |
| `sm2.ease_exact` / `sm2.repetitions_exact` | **100% / 100%** | 157 |
| `grading.accuracy` | **100%** | 20 |
| `generation.card_yield` | **100%** | 36 |
| `generation.answer_in_source` | **100%** | 36 |
| `generation.answer_not_in_front` | **100%** | 36 |
| `generation.front_grounded` | **100%** | 36 |
| `generation.quiz_answer_not_in_prompt` | **0.0%** | 36 |

Read honestly. Two findings, one good and one bad.

The good: the SM-2 lapse path is exact, 39/39, against an independent reference
implementation written from the published algorithm — the v0.2.1 lapse fix
holds under multi-step replay, not just single reviews. Ease factors and
repetition counts never diverge at all.

The bad: **every offline quiz question contains its own expected answer,
verbatim. 0/36.** `generate_quiz` builds the prompt by quoting a source
sentence and then sets `answer_text` to that same sentence, so the question
gives itself away. This is a study tool whose offline quiz cannot test anything.

The 2/157 SM-2 interval divergence is minor and fully characterised: Python's
`round()` is half-to-even, so a card at the 1.3 ease floor with a 425-day
interval gets `425 × 1.3 = 552.5 → 552` days where the conventional half-up
reading gives 553. Left unfixed deliberately, so the 0.3 baseline measures the
code as it stood rather than the code as the eval prompted it to become.

### 0.4 What is not measured yet

- Every `fallback.*`, `llm.*` and `generation.llm_*` metric. No key was present
  for this run, so the LLM solver fallback, the LLM critic and LLM-generated
  cards are **unmeasured, not passing**.
- `olivia ask`, `research`, `tutor` and `lab` end to end. No suite scores the
  cognitive graph, the MoE router or the multi-agent seminar.
- Literature retrieval, the MCP tool surface, and the meta-learner.

---

## 1. Definition of Done for 1.0 (the exit checklist)

1.0 ships only when **all** of these hold, each with a number in this file:

- [ ] **Symbolic solving**: `symbolic.accuracy >= 0.90` on the held-out set,
      with `symbolic.wrong_rate <= 0.01` — abstention is acceptable, silent
      wrongness is not.
- [ ] **Fallback measured**: `fallback.accuracy` reported for a named model on
      a named date, and the symbolic path shown to beat it on the core tier.
- [ ] **Critique**: `youden_j >= 0.70` with `false_alarm_rate <= 0.10` on the
      held-out critique set, and non-zero catch on **every** flaw family.
- [ ] **Study tools**: `sm2.step_exact == 1.00` against the reference, and
      `generation.quiz_answer_not_in_prompt == 1.00`.
- [ ] **Coverage of the product surface**: `ask`, `research` and `tutor` scored
      by a suite, not just the libraries beneath them.
- [ ] **Reproducibility**: `olivia eval` reproduces every published number from
      a clean checkout on py3.10–3.12, offline.
- [ ] **Honest docs**: capability table marked stable/beta/experimental, a
      `LIMITATIONS.md`, and no claim anywhere without a cited measurement.

---

## 2. Workstreams

### WS1 — Evaluation & measurement  *(done at 0.3, and never finished)*
**Goal:** every claim about OLIVIA is a number someone else can reproduce.
- ✅ `olivia eval` with three held-out suites, gates in both directions
      (floors for accuracy, ceilings for wrong-answer and false-alarm rates).
- ✅ Offline suites gated on every PR; LLM suites weekly and skip-green.
- Extend to the product surface: `ask` / `research` / `tutor` end-to-end.
- Add a second critique set authored by someone other than the harness author,
      to test whether the flaw taxonomy generalises.
**Acceptance:** a reader can reproduce every number in section 0 in one command.

### WS2 — Close the symbolic-solving gap  *(fixes: reach tier scores 1/25)*
**Goal:** the solver covers what a study agent is actually asked.
- **Kill the confidently-wrong path first.** `_sympify` applies implicit
      multiplication to prose, turning "of" into `o*f`. Strip intent words
      before parsing, and refuse to emit `confidence=0.9` on an expression
      containing single-letter symbols that came from English.
- Word-problem extraction: quantity + unit + relation, then dispatch to the
      existing deterministic tools rather than to prose.
- Stoichiometry (mass ↔ moles ↔ mass through a balanced equation) and applied
      kinematics/energy on top of `tools.units` and `tools.physics`.
- Phrasing robustness: "find the roots of", "derivative of X with respect to Y",
      "how many X in Y" — measured, not guessed.
**Acceptance:** `symbolic.reach.*` above 0.50 overall with `wrong_rate` still
`<= 0.01`; core tier stays at 1.00.

### WS3 — Make the critic Popperian  *(fixes: 0/14 on epistemic flaws)*
**Goal:** the critique earns the word "Popperian".
- Symbolic checks for what is mechanically detectable: a hypothesis whose
      `status == "supported"` while its analyses report
      `supports_hypothesis is False`, or an effect size straddling zero — that
      alone is 4 of the 14 misses, with no model required.
- Circularity: overlap between the statement and its own predictions /
      falsification test, above a measured threshold.
- Scope-vs-evidence: a universal quantifier in the statement against the
      `n` actually analysed — the `overfit_n1_semantic` family.
- Only then the LLM critic, scored on the same set with its own metric names,
      so the model's contribution is visible rather than assumed.
**Acceptance:** non-zero catch on all six families; `youden_j >= 0.50` with
`false_alarm_rate <= 0.10`.

### WS4 — Study tools that actually test the learner
**Goal:** a generated question tests recall, not reading.
- **Fix the offline quiz.** A question that quotes the sentence containing its
      own answer is not a question. Blank the target span, or ask about the
      sentence rather than quoting it whole.
- Cloze quality beyond "the longest word": prefer the term the sentence is
      about; refuse cards whose answer is a stopword or appears twice.
- Decide the SM-2 rounding convention explicitly, document it, and make
      `sm2.step_exact` 1.00 against the reference.
- Distractor generation for MCQs offline (siblings from the same source), so
      the no-key path produces gradeable questions at all.
**Acceptance:** `generation.quiz_answer_not_in_prompt == 1.00`,
`sm2.step_exact == 1.00`, card-fidelity metrics still 1.00.

### WS5 — Measure the model paths
**Goal:** know what the LLM adds, per path, rather than assuming it helps.
- Run the weekly LLM job and publish `fallback.accuracy`,
      `llm.catch_rate`/`llm.false_alarm_rate`, and `generation.llm_*`.
- **Ablation that matters:** does the LLM fallback beat abstention? A fallback
      that answers 23 abstained cases at 40% accuracy has traded 23 honest
      "I don't know"s for 14 confident errors, and the harness must say so.
- Small-model viability on the local box (RTX 3050 6GB): score a quantised
      local model on the same suites and publish the gap.
**Acceptance:** every `*.llm_*` metric has a number, a model name and a date.

### WS6 — Product-surface coverage
**Goal:** score what users actually run.
- End-to-end suites for `ask` (routing correctness), `research` (does a cycle
      terminate with a report containing its own falsification tests) and
      `tutor` (does it ask before it tells).
- Persist run traces; `olivia eval --report` over a results DB.
**Acceptance:** each of the three commands has a scored suite with a baseline.

### WS7 — Honest positioning
**Goal:** the README matches section 0.
- Capability table marked stable / beta / experimental against measured numbers.
- `LIMITATIONS.md`: the reach tier, the critic's blind spots, the offline quiz.
- Replace any adjective in the README that a number could replace.
**Acceptance:** no capability claim without a cited measurement.

---

## 3. Milestone plan

| Release | Theme | Workstreams | Exit criteria (measured) |
|---|---|---|---|
| **0.3.0** | Measured | WS1 | ✅ three suites, 195 cases, gated in CI, baseline published |
| **0.4.0** | Fix what the eval found | WS4, WS3 (symbolic half) | `quiz_answer_not_in_prompt == 1.00`; `sm2.step_exact == 1.00`; `catch.contradicted_by_evidence >= 0.75`; `youden_j >= 0.45` |
| **0.5.0** | Solve what students ask | WS2 | `symbolic.reach.*` overall `>= 0.50`; `wrong_rate <= 0.01`; core tier still 1.00 |
| **0.6.0** | Know the model's worth | WS5, WS3 (LLM half) | every `llm.*` metric published with model + date; fallback-vs-abstention ablation |
| **0.7.0** | Score the product | WS6 | `ask` / `research` / `tutor` suites with baselines |
| **1.0.0** | Freeze & prove | WS7 | every box in section 1 ticked, numbers in the README |

---

## 4. The claim gate (explicit rule)

Do **not** describe OLIVIA as "accurate", "rigorous", "Popperian" or
"state-of-the-art" in any public artefact until the corresponding number is in
this file and reproducible by `olivia eval`.

Concretely, as of 0.3:

- ✅ "solves school-level algebra, calculus, molar mass, equation balancing,
  constant lookup and unit conversion" — **39/39 on the core tier**.
- ✅ "abstains rather than guessing" — **35.9% abstain, 1.6% wrong**.
- ✅ "SM-2 spaced repetition, including the lapse path" — **100% on 39 lapse
  reviews against an independent reference**.
- ❌ "Popperian critique" — **26.3% catch rate, 0/14 on epistemic flaws**. The
  honest description today is *"a structural validator for research plans"*.
- ❌ "generates quizzes" (offline) — **0/36 questions withhold their answer**.
- ❌ any claim about the LLM paths — **unmeasured**.

Until WS3 lands, the honest one-line description is: **"a study and research
agent with a verified symbolic core, a structural (not yet epistemic) research
critic, and correct spaced repetition."**

---

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| The eval gets tuned until it looks good | Gates are floors/ceilings that only ratchet up; dataset honesty rules are asserted in `tests/test_eval/`; construction protocol documented in each dataset's `held_out` field |
| Proxy metrics lie (a loss of 0.051 on a model that scores 0% behaviourally) | Every metric scores an observable behaviour — a produced answer, a revision decision, a scheduled interval — never an internal score |
| A green suite hides a skipped suite | The registry short-circuit that did exactly this was fixed at 0.3 and is covered by a test asserting all three suites register |
| LLM evals make CI flaky or expensive | Separate workflow, weekly, no `--check`, skips green without a secret |
| The reach tier gets quietly deleted to raise the headline | `tests/test_eval` asserts the reach tier is at least 20 cases and both tiers exist |
