# Cuaderno Eval Harness — A Deterministic Bench for a Non-Deterministic Tutor

**Status:** Design (approved 2026-06-02) — ready for implementation planning
**Surface:** new `copyclip bench` subcommand + `src/copyclip/intelligence/cuaderno/` (read-only consumers) + `src/copyclip/llm/metrics.py` (fix)
**Builds on:** `2026-06-01-cuaderno-answer-quality-design.md` (Phase 1, #125) and `2026-06-02-cuaderno-judge-phase2-design.md` (Phase 2, #126)
**Author:** Samuel + Claude Code, informed by a landscape sweep (RAGAS / DeepEval / TruLens / promptfoo / Braintrust / OpenAI Evals / LLM-as-judge & variance literature — see Appendix A)

---

## 1. Motivation

The cuaderno's answer is non-deterministic: the same question, same config, can produce different blocks, different reads, different citations run to run. CopyClip has already built an unusually disciplined *semantics* of answer quality — a deterministic grounding gate (`quality.assess`), a semantic judge (`judge_answer`), a two-world abstention split, and a persisted multi-axis `verdict` per frame. What it does **not** have is any way to *measure* that semantics over a fixed set of questions and get a comparable number.

Concretely, today:

- The verdict is computed per frame, persisted, and **never aggregated or compared across runs**. There is no fixed-corpus runner.
- There is no before/after signal. After every prompt / judge / model change (and #122–#126 were many) the only feedback is the developer's own impression. "Did this help?" is answered by feeling.
- Run-to-run variance is invisible. The system is single-run; nobody has measured how much the same question's output moves on its own.
- The cost/latency numbers that exist are **fiction** (see §11): tokens are word-count approximations, the price table omits the models actually in use, and a `NameError` breaks the summary path.

This spec adds the missing spine: a deterministic bench that runs a fixed corpus against a pinned snapshot, scores each answer through a typed assertion engine plus the harvested in-system verdict, and produces a per-run scorecard and a paired regression report. It is the instrument that turns "I think the prompt got better" into a number with a stated error bar.

The decision driver, chosen up front: the *instrument* (across its phases) serves **regression** ("did my change help or hurt?"), **variance characterization** ("how much does the same question move?"), and **calibration** ("can I trust the answers, on average?"). **Scope A delivers calibration and large-delta regression now; variance characterization is Phase B** (§4, §15) — A cannot answer "how much does it move" because it runs once per build. Provider-vs-provider comparison is explicitly out of scope.

## 2. Goals

- A **fixed, SHA-pinned corpus** of canonical questions, each carrying deterministic assertions about the answer it should produce.
- A **runner** that drives each corpus question end-to-end through the real `iter_compose_events` loop and captures a structured per-question record.
- A **typed assertion engine** — the deterministic correctness oracle CopyClip lacks — where each assertion returns `{pass, score, reason}`.
- A **per-run scorecard** (calibration): per-axis rates, status distribution, an abstention confusion matrix, and a cost/latency rollup grouped by question-type and model.
- A **paired regression report** that diffs two runs property-by-property with a named significance test (McNemar), honest about which deltas it can and cannot resolve.
- **Truthful cost/latency** as a precondition: fix `metrics.py` so a cost regression cannot hide behind fictional numbers.
- Multiple **independent oracle layers** (self-signal, property-assertion, harvested-verdict) kept **separable** — never collapsed into one scalar. When two oracles disagree, that disagreement is the most valuable signal.

## 3. Non-goals (this phase — Scope A)

- **No run-to-run variance / noise floor.** The bench runs the corpus once per build. This is deferred to Phase B (§15) and has a direct consequence named in §13: A's regression resolves only *large* deltas.
- **No external regression judge.** No separate, different-family LLM judge, no pairwise A/B with position-swap. Deferred to Phase C (§15).
- **No fact-decomposition scoring** (Essential Recall / lie-penalized helpfulness) and **no judge calibration set** (Cohen's kappa). Deferred to Phase C.
- **No CI-on-every-PR.** The bench is run manually, on demand (single-user, token-cost-conscious). Its *internals* are unit-tested in CI; the *corpus run* is not.
- **No provider/model comparison** as a first-class mode (the artifact records the model, so it is possible later, but it is not a goal now).
- **No re-architecture** of the cuaderno, the judge, the streaming transport, or the provider abstraction. The bench is a read-only consumer of `iter_compose_events`; the only production code it modifies is `metrics.py`.

## 4. Scope decision and its honest limitation

Three ambition levels were considered (A: deterministic spine; B: A + noise floor; C: B + external judge + fact-recall + kappa). **Scope A** is chosen and specified here.

The honest consequence, stated plainly per the project's "guaranteed vs hoped" discipline: **without a measured noise floor, a single run per build cannot separate "my change moved the metric" from "this run's sampling luck."** Therefore A's regression report (§10) is trustworthy only for deltas large enough not to need a noise floor (e.g. a rate that moves from 0.6 to 0.9, or an assertion that flips from pass to fail on many questions). Small deltas are reported but explicitly marked *not resolvable at Scope A*. Phase B closes this by measuring the floor. The bench is built A→B→C, each phase a named increment, mirroring the answer-quality Phase 1 / Phase 2 split.

## 5. Architecture — the spine

```
corpus.jsonl (SHA-pinned questions + typed asserts)
        │
        ▼
[ RUNNER ]  for each item: check out / assert the pinned SHA, drive the real
            iter_compose_events loop, collect the terminal Frame + ReadLedger
            + per-call metrics → one per-question record
        │
        ▼
[ SCORER ]  run each item's asserts[] against its record (deterministic);
            harvest the persisted Frame.verdict axes; emit {pass,score,reason}
            per assertion + a per-question rollup
        │
        ▼
[ run artifact ]  .copyclip/bench/runs/<run_id>.json   (one file per run)
        │
        ├──► [ SCORECARD ]   single-run aggregate (calibration)
        │
        └──► [ REGRESSION ]  copyclip bench --baseline <run_id>:
                             paired diff of two artifacts, per-property
                             green/red + McNemar significance
```

Three oracle layers feed the scorer, kept separable in storage:

1. **self-signal** (deterministic, free): status, content-bearing read count, cited-path set, latency, real tokens, cost — read straight off the record. No correctness judgment; characterizes behavior.
2. **property-assertion** (deterministic, the new oracle): the `asserts[]` vocabulary in §7. Per-question expected properties.
3. **harvested-verdict** (LLM, already produced): the `Frame.verdict` axes (`grounded`, `responsive`, `language_ok`, `question_kind`, `world`, `source`) the cuaderno already emits and persists. Free to harvest (no new LLM call); circular only if used to grade the judge itself (it is not, at Scope A).

The external-judge layer (independent grader) is **defined but deferred** to Phase C.

## 6. The corpus

**Substrate (the "both, layered" decision, landed for A):**

- **Primary blank: a SHA-pinned snapshot of CopyClip itself (dogfood).** Each corpus item names a `commit_sha`; the runner asserts the working tree is at that SHA (or runs against a checkout/worktree of it) before asking. Realistic — the author knows the answers — and freezing the SHA is the cheap fix for "ground truth over a living codebase": it lets a real regression be told apart from code drift.
- **Frozen toy fixture repo: for the harness's own unit tests only** (the assertion engine and scorer, §14), not for the answer corpus yet. This satisfies "both substrates" without doubling the corpus to maintain. Promoting fixture questions into the answer corpus is a later option.

**Item shape (JSONL, OpenAI-Evals-flavored):**

```json
{
  "id": "howto-vs-whatis-compositor-01",
  "question": "¿cómo funciona el compositor del cuaderno?",
  "category": "what_vs_how",
  "commit_sha": "e4400af",
  "question_lang": "es",
  "expected_question_kind": "code_comprehension",
  "asserts": [
    {"type": "status_in", "value": ["answer", "off_target"]},
    {"type": "language_is", "value": "es"},
    {"type": "min_content_bearing_reads", "value": 1},
    {"type": "cites_path_matching", "value": "compositor\\.py$"},
    {"type": "harvested_responsive", "value": true}
  ],
  "notes": "founding incident: a 'qué es' definition must FAIL responsive on this 'cómo' question"
}
```

**Categories (~20–30 items total, ~2–4 per category):**

1. **what_vs_how** — pairs over the same symbol: "¿qué es X?" vs "¿cómo funciona X?". A definition answering a *how* question must fail the (harvested) `responsive` axis — the exact defect `judge.py` exists to catch.
2. **grounded_happy_path** — answerable from a small file set; assert expected cited paths and a `mentions` of a key symbol.
3. **must_abstain (consulted_empty)** — about a real subsystem the code genuinely lacks; correct behavior is `insufficient_evidence`, not fabrication.
4. **must_not_fabricate (fictional referent)** — about a nonexistent symbol/feature; correct behavior is to decline, never invent.
5. **fabricated_grounding_bait** — a question whose plausible answer tempts citing an unread/nonexistent path or an out-of-range line; exercises `no_unread_citations` and `cited_lines_within_eof`.
6. **meta_about_tutor** — "¿qué te puedo preguntar?"; a zero-read answer is *legitimate* and must NOT seal `ungrounded`.
7. **language_fidelity** — Spanish (including accent-free Spanish that stresses the stopword vote) and English; assert `language_is` matches the question.
8. **temporal_causal (the wedge)** — "¿qué decidimos sobre X y por qué?", "muéstrame el commit que cambió Y"; assert a commit/decision citation is present (`cites_commit`).
9. **multi_hop_cross_file** — requires reads across 2+ files; assert `min_content_bearing_reads ≥ 2`.

## 7. The assertion engine

The deterministic oracle CopyClip lacks today. A small, typed vocabulary; each assertion is a pure function of the per-question record and returns `{pass: bool, score: float, reason: str}`. A question's rollup at Scope A is **all-pass** (every assert passes) plus the per-assert detail retained (never collapsed). A weighted rollup is a later option, not now.

| `type` | semantics | layer | source field |
|---|---|---|---|
| `status_in` / `status_is` | terminal `Frame.status` ∈ set / == value | property | record.status |
| `cites_path_matching` | ≥1 citation whose `path` matches the regex | property | record.cited_paths |
| `cites_commit` | ≥1 citation carrying a non-null `commit` | property | record.citations |
| `mentions` | answer block text contains the string/symbol (case-folded) | property | record.blocks |
| `language_is` | detected answer language == value (reuse `language.py`) | property | record.answer_lang |
| `min_content_bearing_reads` | `ReadLedger.content_bearing_count ≥ value` | self-signal | record.content_bearing_count |
| `no_unread_citations` | every cited path ∈ `read_paths` (no fabricated grounding) | property | record.cited_paths, read_paths |
| `cited_lines_within_eof` | every citation line range lies within the cited file's length **at the pinned SHA** | property | record.citations + git show |
| `harvested_responsive` | `Frame.verdict.responsive == value` (None → assert is *inconclusive*, not fail) | harvested | record.verdict |
| `harvested_grounded` | `Frame.verdict.grounded == value` (None → inconclusive) | harvested | record.verdict |

Notes:
- `cited_lines_within_eof` is the one cheap borrow from Phase C pulled forward (the field names "out-of-EOF citation" as a distinct mechanically-catchable hallucination class). Implementation must confirm the citation block schema carries `line_start`/`line_end`; if a given citation has no line range, the assert passes vacuously for that citation. File length is read from the **pinned SHA** (`git show <sha>:<path>`), not the working tree.
- **`None`/unobserved harvested axes are `inconclusive`, never `fail`.** This mirrors the system's own "never default an absent axis to True" discipline. An inconclusive assert does not fail the question but is counted separately in the scorecard (so a corpus that is silently un-judged is visible, not hidden as green).
- The `mentions` assert is deliberately weak (substring), used only where a specific symbol name is the load-bearing fact; it is not a proxy for correctness.

## 8. The run artifact

One JSON file per run at `.copyclip/bench/runs/<run_id>.json`:

```
run_id, started_at, corpus_path, corpus_sha (hash of corpus file),
answer_model, judge_model, provider, copyclip_version,
items: [
  { id, category, commit_sha,
    status, verdict (full multi-axis dict),
    cited_paths, citations (path/commit/line range), content_bearing_count,
    answer_lang, blocks (text only, for mentions/inspection),
    latency_ms, input_tokens, output_tokens, cost_usd, cost_estimated,  # latency REAL; tokens/cost are FLAGGED ESTIMATES in A (real-usage deferred, §11)
    asserts: [ { type, pass, score, reason } ],
    question_rollup: { all_pass: bool, n_pass, n_fail, n_inconclusive } }
]
```

`run_id` is a sortable id derived from the start timestamp + a short corpus/model hash (no `Date.now()`-style nondeterminism concern — this is a CLI, the timestamp is real). The artifact is the single source for both the scorecard and regression; nothing is recomputed against the live cuaderno after the run.

## 9. Scorecard (calibration)

`copyclip bench` (no `--baseline`) prints and writes a single-run scorecard:

- **Per-axis rates:** grounded-rate, responsive-rate, language-ok-rate (over the questions where the axis is conclusive), and overall question all-pass rate.
- **Status distribution:** counts of `answer` / `ungrounded` / `insufficient_evidence` / `off_target` / `partial` / `fallback` per run.
- **Abstention confusion matrix:** over the `must_abstain` + `must_not_fabricate` + answerable categories, a 2×2 of {should-answer, should-abstain} × {answered, abstained} → **false-answer rate** (fabricated when it should have declined) and **false-abstention rate** (declined when it should have answered). CopyClip has the richest abstention *typing* in the field but has never measured the *rate*; this turns honesty into a tracked number.
- **Cost/latency rollup:** total and per-`category`, per-`answer_model` — sum tokens, derive $, report latency **median + p90** (latency is skewed; mean lies). Latency is real; cost is shown with an `estimated` marker in A (§11) so a fictional number is never read as truth.
- **Inconclusive count:** questions where a harvested axis was `None` — surfaced, never silently green.

## 10. Regression report (paired)

`copyclip bench --baseline <run_id>` runs the corpus on the current build and diffs against a stored baseline artifact, **paired by question id**:

- **Per-property green/red** with improvement/regression counts, sortable by biggest drop (Braintrust-style UX, terminal table).
- **Significance:** for each binary rate (grounded-rate, language-ok-rate, abstention-correct-rate, per-assert pass-rate), report **McNemar** on the discordant pairs: χ² = (b − c)² / (b + c), with an exact/mid-p variant when discordant counts are small. Paired + McNemar exploits same-question difficulty — far cheaper than independent samples, the right lever for a solo budget.
- **The Scope-A caveat, rendered in the report itself:** a banner stating that without a measured noise floor (Phase B), a delta below an unmeasured threshold is *not resolvable* — only large, consistent shifts are called. The report must not present a small green/red as significant when it cannot know.

Comparison arithmetic is fully deterministic even though the underlying answers are not.

## 11. `metrics.py` fix (precondition for the cost axis)

`src/copyclip/llm/metrics.py` has three confirmed bugs that make cost a fiction:

1. **Word-count token proxy** (`len(text.split()) * 1.3`, lines 34–35) instead of real token counts. **Correction to an earlier draft:** the cuaderno adapters (`anthropic_client.py` / `openai_client.py`) do **not** capture a `usage` object today and do **not** call `log_llm_call` at all — the 12 `log_llm_call` sites live in the legacy `llm_client.py` (the minimization path), not the cuaderno. Capturing real usage is therefore *new* work (touch both adapters; OpenAI streaming additionally needs `stream_options={"include_usage": True}`). **Scope-A decision (slim):** extend `log_llm_call` to *accept* optional real `input_tokens`/`output_tokens` (used when present) and add an honest `estimated: bool` field on the row; in A the bench logs the word-count **estimate** (flagged `estimated=True`), while **latency is real** (`perf_counter` around the loop). Capturing real usage in the adapters is **deferred to the next increment** (§15) — cost was the least-urgent of the three goals and is honestly labeled until then.
2. **Stale price table** (lines 71–80): `anthropic` lists only `claude-3-5-sonnet`; the models actually in use (`claude-sonnet-4-5`, `claude-haiku-4-5`) and per-model DeepSeek fall through to `{'input': 0, 'output': 0}` → **cost silently computes to 0 for the cuaderno's real models.** Fix: refresh the table to the models in use; make an unknown model log a visible warning rather than silently cost 0.
3. **Missing `import sys`** (lines 65, 103–129 use `file=sys.stderr`): `print_summary()` and the debug print raise `NameError`. Fix: `import sys`.

Plus: add a **per-run / per-question-type / per-model rollup** API the scorecard consumes (the collector is a module-global singleton today; the bench needs to scope metrics to one run — give the collector a way to snapshot/reset per run, or have the runner read the per-call rows it just produced). At Scope A the **only** production code the bench changes outside its own package is `metrics.py` (§11) and a **2-line backward-compatible `ledger` injection parameter** on `compositor.iter_compose_events` (so the runner owns the `ReadLedger` and can read `content_bearing_count`/`read_paths` after draining — these are internal today and surfaced in no event; default `None` preserves current behavior exactly). No adapter changes in A. Everything else the bench touches it only reads.

## 12. Components / file structure

- **New package** `src/copyclip/intelligence/cuaderno/bench/` (or `src/copyclip/bench/` — implementation choice):
  - `corpus.py` — load + validate the JSONL corpus (schema, known assert types, SHA presence).
  - `runner.py` — drive `iter_compose_events` per item against the pinned SHA; assemble the per-question record. Reuses the existing key-gated live pattern for the LLM calls.
  - `asserts.py` — the typed assertion vocabulary (§7); each `(record, assert) → {pass, score, reason}`. Pure, no I/O except the git-show in `cited_lines_within_eof`.
  - `score.py` — per-question rollup + the single-run scorecard (§9).
  - `regress.py` — paired diff + McNemar (§10).
  - `artifact.py` — read/write the run artifact (§8).
- **New** `corpus/cuaderno-bench.jsonl` (or under `tests/fixtures/`) — the corpus itself.
- **New CLI wiring:** `copyclip bench [--baseline <run_id>] [--corpus <path>] [--limit N]` in the existing CLI entrypoint.
- **Modified:** `src/copyclip/llm/metrics.py` (§11) and a 2-line backward-compatible `ledger: Optional[ReadLedger] = None` parameter on `compositor.iter_compose_events` (line 153: `ledger = ledger if ledger is not None else ReadLedger()`). **No adapter changes in A** (real-usage capture deferred, §11/§15).
- **Read-only consumers** (unchanged): `quality.assess`, `read_ledger.ReadLedger` (constructed by the runner, passed in), `schema.Frame`/`frame_to_dict`/`frame_from_dict`, `judge.judge_answer`, `language.detect_language`, `provider.resolve_cuaderno_provider`/`build_cuaderno_client`/`resolve_judge_model`.

## 13. What is GUARANTEED vs HOPED (Scope A)

- **Guaranteed (deterministic):** the assertion engine's verdicts are pure functions of the captured record — given a fixed record, every `status_*` / `cites_*` / `language_is` / `min_content_bearing_reads` / `no_unread_citations` / `cited_lines_within_eof` assert is reproducible; the scorecard rates and the McNemar arithmetic are deterministic; **latency is real**, and **cost is an honestly-flagged estimate in A** (`estimated=True`; real token capture deferred, §11); no harvested-axis `None` is ever counted as a pass.
- **Hoped / limited (named, not hidden):**
  - **Regression resolves only large deltas.** Single-run-per-build conflates the change with sampling luck for any delta smaller than the (unmeasured) noise floor. The report says so. Phase B fixes it.
  - **Harvested-verdict axes are the in-system judge's opinion**, not an independent oracle — a `harvested_responsive` assert inherits the judge's fallibility and its self-preference exposure (judge and answer model are the same family, §16). At Scope A this is a *measurement of what the system believes about itself*, useful for regression of the answer model against a fixed judge, circular for judging the judge. Phase C adds the independent grader.
  - **Confidently-wrong-but-grounded answers can pass.** A grounded, responsive, correctly-cited answer that is *factually* wrong has no Scope-A oracle. Phase C's fact-recall closes part of this.
  - **No semantic correctness, no factual accuracy** is asserted by A. The `mentions` assert is a weak symbol-presence proxy, explicitly not a correctness check.

## 14. Testing strategy

- **Deterministic, no LLM:** each assert type against synthetic `Frame`/record fixtures, including the edge cases the answer-quality spec already cares about — a tool result with `{"error": ...}`, an empty `{"symbols": []}`, a citation with a line range past EOF, a citation to an unread path, a `None` harvested axis (→ inconclusive, not fail). The scorer rollup; the McNemar math (known discordant tables → known χ²/p, including the small-count exact path); artifact read/write round-trip.
- **Harness integration against the frozen fixture repo:** the runner with a **scripted/stub compositor** (no live LLM) producing known frames → assert the artifact and scorecard match expectations; a known baseline+candidate pair → assert the regression diff and significance calls are correct.
- **Corpus validation:** every corpus item parses, names a resolvable `commit_sha`, and uses only known assert types (a CI-able test that does not call any LLM).
- **One key-gated live test** (parity with the existing key-gated e2e pattern): run ~3 corpus questions end-to-end through the real loop, assert the artifact is well-formed and the obvious asserts hold. Not in default CI.
- **`metrics.py`:** real-usage threading produces nonzero cost for `claude-sonnet-4-5` / `claude-haiku-4-5`; unknown model warns; `print_summary()` no longer raises.

## 15. Suggested phases

- **Phase A (this spec):** corpus + runner (with the `ledger` injection) + assertion engine + artifact + scorecard + paired regression (McNemar, large-delta) + `metrics.py` bug fix + `cited_lines_within_eof`. Deterministic and harvested-verdict oracles only. Single run per build. **Cost is a flagged estimate; latency is real.**
  - *Delivered:* paired McNemar over the three harvested verdict axes (`grounded`/`responsive`/`language_ok`); the scorecard's status distribution, abstention confusion matrix, axis rates, total cost (flagged), latency median/p90, and surfaced inconclusive count.
  - *Deferred within A (additive follow-ups, no behavior change):* paired McNemar over the **abstention-correct rate** and **per-assert pass-rate** (§10 names these; the harness pairs verdict-axis booleans today — extending to the abstention/per-assert extractors is purely additive); the **per-category / per-answer-model** cost-and-latency breakdown in the scorecard (§9 names it; the total is delivered and the per-model split rides in the artifact's `metrics_rollup`, which is empty until Phase A.5 logs real usage).
- **Phase A.5 (real cost — small, deferred from A):** capture real `usage` in both cuaderno adapters (Anthropic `.usage`; OpenAI `stream_options={"include_usage": True}` + final-chunk usage), surface it in the `message_stop` event, and have the runner log it via the already-extended `log_llm_call`; flip the artifact's `cost_estimated` to `False`. Makes the cost axis real without re-touching the bench.
- **Phase B (noise floor — makes regression trustworthy):** run the corpus N times (N≈5) on an unchanged build; per question compute modal-share + normalized entropy for categorical signals (status, judge decision, question_kind, language), mean pairwise **Jaccard** over cited-path sets, CV/IQR for latency+cost; document the resolvable floor; gate regression only on deltas exceeding it; report pass^k. Adds bounded, on-demand LLM cost.
- **Phase C (semantic + independent oracles):** external regression judge (different model family, pairwise A/B with position-swap, authorship obfuscated); fact-decomposition scoring (curated essential facts → Essential Recall + lie-penalized helpfulness); judge calibration set with Cohen's kappa; optional SEU (1 − mean pairwise cosine of N answer-body embeddings) for free-text semantic dispersion.

## 16. Open questions

None blocking. Deferred by decision: bench package location (`cuaderno/bench/` vs top-level `bench/`) — an implementation-plan call; weighted assert rollup vs all-pass (start all-pass); promoting fixture questions into the answer corpus; the noise floor and everything in Phases B/C. Flagged risk carried forward: the in-system judge (`claude-haiku-4-5`) and the answer model (`claude-sonnet-4-5`) are the **same family** — harvested-verdict axes carry self-preference exposure; the independent grader that dodges it is Phase C.

---

## Appendix A — Landscape comparison (the research that informed this)

A five-front sweep (RAG-eval, general eval/regression tooling, codebase-QA tools, LLM-as-judge methodology, non-determinism/variance) synthesized against CopyClip's current stack. Kept here so the rationale is not lost.

### Where CopyClip is AHEAD of the field

- **Two-world abstention split** — `insufficient_evidence` (consulted_empty, a fact about the *project*) vs `ungrounded` (not_consulted, a fact about the *tutor*). Every surveyed tool collapses "can't answer" into one bucket.
- **Honest typing of unobserved axes** — `JudgeVerdict` axes are `Optional`, never defaulted to `True`; a fail-open seal is `source='unjudged'` with every axis `None`. No surveyed harness documents this "never claim an unobserved axis" discipline.
- **Grounding measured at the evidence-acquisition layer** — content-bearing reads (non-error, non-empty payload); "I looked" cannot be faked with a directory listing. Commercial tools stop at retrieval-provenance *display* (Copilot References, Bloop/Phind citations).
- **Per-call nonce fence** around the judged answer (stronger than static delimiters), and **answer-language as an evaluated axis** (no surveyed codebase-QA tool measures response-language correctness at all).
- **Collapse the view, never the record** — single `status` for the UI, full multi-axis `verdict` persisted. The field tends to ship one blended score.

### Where CopyClip is BEHIND / ABSENT (= the work in this spec)

| Capability | Field best practice | CopyClip today | This spec |
|---|---|---|---|
| Property-based per-question assertions | Typed `assert[]` with per-assert `{pass,score,reason}` (promptfoo) | None for the cuaderno; only a structural fixture on the old Ask Project surface | §7 |
| Regression delta | Paired before/after on a fixed corpus, green/red, CI gate (Braintrust/DeepEval/RAGAS) | Absent — verdicts persisted, never aggregated/compared | §10 |
| Run-to-run variance / noise floor | N repeats, entropy/Jaccard/CV, gate above the floor | Absent — single run only | Phase B |
| Cost/latency aggregation | Real tokens × maintained price table, per-tag rollup, median+p90 | `metrics.py` is fiction (word-count tokens, stale prices, `NameError`) | §11 |
| Groundedness measurement | Decompose into atomic claims, verify each (RAGAS/DeepEval/TruLens; SummaC/FActScore lineage) | Binary gate + judge boolean; no claim decomposition | Phase C (fact-recall) |
| LLM-judge reliability | Different-family judge, position-swap, verbosity guard, kappa-calibrated | Same-family judge; no calibration, no kappa | Phase C |

### Borrow list, mapped to phase

- **A:** fixed SHA-pinned corpus runner; typed assertion engine; abstention confusion matrix; `metrics.py` real tokens + price refresh + rollup; `cited_lines_within_eof`; paired McNemar regression.
- **B:** noise floor (entropy / Jaccard / CV); pass^k; gate-above-floor.
- **C:** external different-family pairwise judge; Essential Recall + lie-penalized helpfulness; judge kappa calibration; SEU semantic dispersion.

### Methodological risks to avoid (carried into the spec's "guaranteed vs hoped")

- Treating temp=0 / single-run as determinism — hosted models have no seed; batch-invariance and MoE routing shift output under load (documented: ~80 unique completions in 1000 temp=0 runs). → Phase B reports distributions, not point estimates.
- Self-enhancement bias — a same-family judge inflates same-family answers (causal; Panickssery 2024). → §13, §16; Phase C uses a different family.
- Collapsing the multi-axis verdict into one scalar — discards CopyClip's genuine edge. → kept separable in §5/§7/§8.
- Eval saturation on happy-path-only corpora — masks real regressions. → §6 includes must-abstain, must-not-fabricate, what-vs-how traps.
- Cost-metric fiction masking a cost regression — → §11 is a precondition, not optional.
- Trusting judge scores without reading transcripts — for a solo tool, periodically eyeball a sample. → noted; the artifact retains block text for inspection.
