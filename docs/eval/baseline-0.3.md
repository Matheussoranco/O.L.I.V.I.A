# O.L.I.V.I.A. eval run

LLM backend: `none`

## research

| metric | value | n | note |
|---|---|---|---|
| `symbolic.catch_rate` | 26.3% | 19 | flawed cycles sent for revision |
| `symbolic.false_alarm_rate` | 0.0% | 8 | sound controls wrongly flagged |
| `symbolic.balanced_accuracy` | 63.2% | 27 | 0.5 for a critic that always (or never) flags |
| `symbolic.youden_j` | 26.3% | 27 | 0.0 for either degenerate critic |
| `symbolic.catch.circular` | 0.0% | 4 |  |
| `symbolic.catch.contradicted_by_evidence` | 0.0% | 4 |  |
| `symbolic.catch.overfit_n1_semantic` | 0.0% | 2 |  |
| `symbolic.catch.overfit_n1_structural` | 100.0% | 2 |  |
| `symbolic.catch.unfalsifiable_semantic` | 0.0% | 4 |  |
| `symbolic.catch.unfalsifiable_structural` | 100.0% | 3 |  |
| `llm.measured` | 0.0% | 27 | no LLM backend |

- symbolic critic missed 14 flawed cycles, in: circular, contradicted_by_evidence, overfit_n1_semantic, unfalsifiable_semantic
- LLM critic not measured: no LLM backend configured

<details><summary>failing cases</summary>

- `unf-sem-001` [wrong] expected `needs_revision` got `clean` Ad hoc immunisation: any failure is reattributed to misidentification of the style, so no result can count against it.
- `unf-sem-002` [wrong] expected `needs_revision` got `clean` The posited entity has no independent trace: the only evidence for the field is the outcome it is invoked to explain.
- `unf-sem-003` [wrong] expected `needs_revision` got `clean` The key term is defined by the outcome: 'truly learned' just means 'retained', so no forgetting can ever count against it.
- `unf-sem-004` [wrong] expected `needs_revision` got `clean` Every possible outcome confirms it: any schedule that helps is evidence, and individual variation absorbs every schedule that does not.
- `circ-001` [wrong] expected `needs_revision` got `clean` 'Effective study' is operationalised as 'study that yields better grades', so the hypothesis states an identity.
- `circ-002` [wrong] expected `needs_revision` got `clean` Dormitive-virtue explanation: the cause is named after the effect it is supposed to explain.
- `circ-003` [wrong] expected `needs_revision` got `clean` The independent variable is identified by the dependent variable, so the prediction cannot fail.
- `circ-004` [wrong] expected `needs_revision` got `clean` The refutation test is stated in terms that the hypothesis's own definitions make impossible to satisfy.
- `contra-001` [wrong] expected `needs_revision` got `clean` A null result with a tight interval is carried forward as support; the hypothesis is marked supported at 0.85 confidence.
- `contra-002` [wrong] expected `needs_revision` got `clean` The measured effect runs opposite to the prediction and is significant, yet the hypothesis is retained at 0.9 confidence.
- `contra-003` [wrong] expected `needs_revision` got `clean` A null result is reported and the hypothesis is nonetheless left standing as supported.
- `contra-004` [wrong] expected `needs_revision` got `clean` Disconfirming evidence is present in evidence_against and ignored in the hypothesis's status and confidence.
- `ofit-sem-001` [wrong] expected `needs_revision` got `clean` A universal claim rests on an analysis of one participant, while the plan on paper claims a sample of 40.
- `ofit-sem-002` [wrong] expected `needs_revision` got `clean` A single classroom's result is generalised to every subject and every age group.

</details>

## study

| metric | value | n | note |
|---|---|---|---|
| `sm2.sequence_exact` | 95.8% | 24 | all steps match |
| `sm2.step_exact` | 98.7% | 157 | per-review |
| `sm2.lapse_step_exact` | 100.0% | 39 | q<3 only |
| `sm2.ease_exact` | 100.0% | 157 |  |
| `sm2.interval_exact` | 98.7% | 157 |  |
| `sm2.repetitions_exact` | 100.0% | 157 |  |
| `sm2.due_exact` | 98.7% | 157 |  |
| `grading.accuracy` | 100.0% | 20 |  |
| `generation.card_yield` | 100.0% | 36 | cards per card requested |
| `generation.answer_in_source` | 100.0% | 36 |  |
| `generation.answer_not_in_front` | 100.0% | 36 |  |
| `generation.blank_present` | 100.0% | 36 |  |
| `generation.front_grounded` | 100.0% | 36 |  |
| `generation.deck_unique_fronts` | 100.0% | 6 |  |
| `generation.quiz_answer_not_in_prompt` | 0.0% | 36 | question does not give away its answer |
| `generation.llm_measured` | 0.0% | 0 | no LLM backend |

- SM-2 interval diverged from the reference on 2/157 reviews
- every offline quiz question contains its own expected answer verbatim: the prompt quotes the source sentence and answer_text is that same sentence
- LLM-generated card fidelity not measured: no LLM backend configured

<details><summary>failing cases</summary>

- `sm2-021` [wrong] expected `matches SM-2 reference at every step` got `2 divergent steps` step 11 (q=3): ease 1.3000 vs 1.3000, interval 552 vs 553, reps 11 vs 11; step 12 (q=3): ease 1.3000 vs 1.3000, interval 718 vs 719, reps 12 vs 12
- `src-photosynthesis-quiz1` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Photosynthesis converts l` answer appears verbatim in the prompt
- `src-photosynthesis-quiz2` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The light-dependent react` answer appears verbatim in the prompt
- `src-photosynthesis-quiz3` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Water is split there, rel` answer appears verbatim in the prompt
- `src-photosynthesis-quiz4` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The resulting ATP and NAD` answer appears verbatim in the prompt
- `src-photosynthesis-quiz5` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Carbon dioxide is fixed b` answer appears verbatim in the prompt
- `src-photosynthesis-quiz6` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The overall process is th` answer appears verbatim in the prompt
- `src-plate-tectonics-quiz1` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The lithosphere is broken` answer appears verbatim in the prompt
- `src-plate-tectonics-quiz2` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Plates diverge at mid-oce` answer appears verbatim in the prompt
- `src-plate-tectonics-quiz3` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “They converge at subducti` answer appears verbatim in the prompt
- `src-plate-tectonics-quiz4` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Transform boundaries occu` answer appears verbatim in the prompt
- `src-plate-tectonics-quiz5` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Most earthquakes and volc` answer appears verbatim in the prompt
- `src-plate-tectonics-quiz6` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The theory replaced older` answer appears verbatim in the prompt
- `src-tcp-handshake-quiz1` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “A TCP connection begins w` answer appears verbatim in the prompt
- `src-tcp-handshake-quiz2` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The client sends a segmen` answer appears verbatim in the prompt
- `src-tcp-handshake-quiz3` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The server replies with a` answer appears verbatim in the prompt
- `src-tcp-handshake-quiz4` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The client completes the ` answer appears verbatim in the prompt
- `src-tcp-handshake-quiz5` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Only then may application` answer appears verbatim in the prompt
- `src-tcp-handshake-quiz6` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The handshake establishes` answer appears verbatim in the prompt
- `src-insulin-quiz1` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Insulin is a peptide horm` answer appears verbatim in the prompt
- `src-insulin-quiz2` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Its release is triggered ` answer appears verbatim in the prompt
- `src-insulin-quiz3` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Insulin promotes glucose ` answer appears verbatim in the prompt
- `src-insulin-quiz4` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “It also stimulates glycog` answer appears verbatim in the prompt
- `src-insulin-quiz5` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Glucagon opposes these ac` answer appears verbatim in the prompt
- `src-insulin-quiz6` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The two hormones together` answer appears verbatim in the prompt
- `src-bayes-quiz1` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Bayes' theorem relates th` answer appears verbatim in the prompt
- `src-bayes-quiz2` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The posterior is proporti` answer appears verbatim in the prompt
- `src-bayes-quiz3` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “A test with high sensitiv` answer appears verbatim in the prompt
- `src-bayes-quiz4` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “This happens because the ` answer appears verbatim in the prompt
- `src-bayes-quiz5` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Reasoning that ignores th` answer appears verbatim in the prompt
- `src-bayes-quiz6` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Updating beliefs proporti` answer appears verbatim in the prompt
- `src-french-revolution-quiz1` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “By 1788 the French crown ` answer appears verbatim in the prompt
- `src-french-revolution-quiz2` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Wars, including support f` answer appears verbatim in the prompt
- `src-french-revolution-quiz3` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The privileged orders wer` answer appears verbatim in the prompt
- `src-french-revolution-quiz4` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Attempts at fiscal reform` answer appears verbatim in the prompt
- `src-french-revolution-quiz5` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “Louis the Sixteenth summo` answer appears verbatim in the prompt
- `src-french-revolution-quiz6` [wrong] expected `prompt does not contain its own answer` got `Explain in your own words: what does this describe? — “The assembly that followe` answer appears verbatim in the prompt

</details>

## symbolic

| metric | value | n | note |
|---|---|---|---|
| `symbolic.accuracy` | 62.5% | 64 |  |
| `symbolic.precision` | 97.6% | 41 | over answered cases |
| `symbolic.wrong_rate` | 1.6% | 64 | confidently wrong |
| `symbolic.abstain_rate` | 35.9% | 64 |  |
| `symbolic.core.chemistry.accuracy` | 100.0% | 8 |  |
| `symbolic.core.math.accuracy` | 100.0% | 18 |  |
| `symbolic.core.physics.accuracy` | 100.0% | 6 |  |
| `symbolic.core.units.accuracy` | 100.0% | 7 |  |
| `symbolic.reach.chemistry.accuracy` | 16.7% | 6 |  |
| `symbolic.reach.math.accuracy` | 0.0% | 10 |  |
| `symbolic.reach.physics.accuracy` | 0.0% | 6 |  |
| `symbolic.reach.units.accuracy` | 0.0% | 3 |  |
| `routed_to.chemistry` | 14.1% | 64 |  |
| `routed_to.none` | 35.9% | 64 |  |
| `routed_to.physics` | 9.4% | 64 |  |
| `routed_to.symbolic` | 29.7% | 64 |  |
| `routed_to.units` | 10.9% | 64 |  |
| `symbolic.coverage` | 64.1% | 64 | cases a solver claimed |
| `fallback.measured` | 0.0% | 23 | no LLM backend — see notes |

- fallback path not measured: no LLM backend configured (23 cases would have been routed to it)

<details><summary>failing cases</summary>

- `math-019` [abstain] expected `2*x` got `` no solver matched and no fallback available
- `math-020` [wrong] expected `exp(x)` got `e**x*f*o*log(e)` 
- `math-021` [abstain] expected `3, 4` got `` no solver matched and no fallback available
- `math-022` [abstain] expected `6*x + 2` got `` no solver matched and no fallback available
- `math-023` [abstain] expected `72` got `` no solver matched and no fallback available
- `math-024` [abstain] expected `36` got `` no solver matched and no fallback available
- `math-025` [abstain] expected `5050` got `` no solver matched and no fallback available
- `math-026` [abstain] expected `1` got `` no solver matched and no fallback available
- `math-027` [abstain] expected `x = 4, y = 2` got `` no solver matched and no fallback available
- `math-028` [abstain] expected `0.375` got `` no solver matched and no fallback available
- `chem-010` [abstain] expected `1.998` got `` no solver matched and no fallback available
- `chem-011` [abstain] expected `29.22` got `` no solver matched and no fallback available
- `chem-012` [abstain] expected `88.81` got `` no solver matched and no fallback available
- `chem-013` [abstain] expected `+6` got `` no solver matched and no fallback available
- `chem-014` [abstain] expected `27.43` got `` no solver matched and no fallback available
- `phys-007` [abstain] expected `15` got `` no solver matched and no fallback available
- `phys-008` [abstain] expected `9` got `` no solver matched and no fallback available
- `phys-009` [abstain] expected `20` got `` no solver matched and no fallback available
- `phys-010` [abstain] expected `413.3` got `` no solver matched and no fallback available
- `phys-011` [abstain] expected `19.61` got `` no solver matched and no fallback available
- `phys-012` [abstain] expected `2.006` got `` no solver matched and no fallback available
- `unit-008` [abstain] expected `77` got `` no solver matched and no fallback available
- `unit-009` [abstain] expected `4828.03` got `` no solver matched and no fallback available
- `unit-010` [abstain] expected `12.346` got `` no solver matched and no fallback available

</details>
