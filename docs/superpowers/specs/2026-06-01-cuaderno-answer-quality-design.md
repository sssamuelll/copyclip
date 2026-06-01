# Cuaderno Answer Quality — Groundedness, Responsiveness, Language, and Honest Typing

**Status:** Design (approved 2026-06-01) — ready for implementation planning
**Surface:** `src/copyclip/intelligence/cuaderno/` + `frontend/src/components/cuaderno/`
**Author:** Samuel + Claude Code, stress-tested by the council (Halberg / Serrano / Voronov)

---

## 1. Motivation — the triggering incident

The question **"como funciona?"** (Spanish) produced this answer:

> *"CopyClip is a local-first project intelligence CLI that scans your codebase, surfaces what AI agents changed while you were away, tracks architectural decisions, and lets you ask grounded questions through an LLM tutor called the cuaderno."*

It fails on **three independent axes**, none of which is "it is short":

1. **Ungrounded.** A generic, README-flavored summary with **zero citations**, produced without really reading the code — a direct violation of the system's own Hard Rule #1 (`prompts.py`: "NEVER invent. Every claim … anchored to evidence"). The tool whose entire identity is evidence-anchored answers accepted and persisted exactly the hallucinated answer it exists to never give.
2. **Non-responsive.** The user asked *how it works* (mechanism); the model answered *what it is* (definition).
3. **Wrong language.** Spanish question, English answer. CopyClip should mirror the language the user writes in.

The deeper structural problem (per Voronov, two prior rounds): the cuaderno **computes a verdict about an answer, uses it once, and discards it** — it has no owned, persisted notion of "is this a real answer?". A non-answer is archived indistinguishably from a real one and re-presented on restore as legitimate.

## 2. Goals

- An answer that makes code claims **without consulting the code at all** must never be sealed as a confident answer.
- The cuaderno must **adapt to the user's language**.
- When the model answers the **wrong question** (the responsiveness defect), the system should catch it when it cheaply can and give the model one chance to correct.
- The verdict about answer quality must be **persisted into the frame's type**, distinguishing a real answer from the different ways an answer can fail — and distinguishing *"the project genuinely lacks the evidence"* from *"the tutor did not look."*
- Be **honest about what is guaranteed vs. hoped** (§9).

## 3. Non-goals

- Guaranteeing citation *relevance* or answer *responsiveness* deterministically. These are semantic; we improve them (judge + prompt) and name the residual, but do not claim a guarantee.
- A `contradiction_detected` verdict (present in the older `AskResponse` surface). Out of scope here; Hard Rule #4 remains in the prompt. (See §10, finding S11.)
- Re-architecting the agentic loop, the streaming transport, or the provider abstraction.
- Multi-user / distributed concerns. This is a local, single-user, single-process tool.

## 4. Architecture — two layers, separate custodians

The three defects have **three different custodians** and must not be folded into one deterministic gate (Voronov: "a single verdict over heterogeneous custody is a category error"). The design splits the work accordingly:

```
compose answer (existing agentic loop, streaming blocks live)
        │
        ▼
[ CHEAP LAYER · always · deterministic ]
   language    : detect the question's language → does the answer mirror it?   (true gate — a pure function of bytes)
   grounding   : were there ≥1 CONTENT-BEARING reads?  do answer citations
                 reference paths actually read?  → emits a SUSPICION signal
                 (NOT a hard verdict, except language)
        │
        ├─ no suspicion ───────────────────────► seal status = answer
        │
        └─ suspicion ──► [ JUDGE · short 2nd-pass LLM call · separate custodian ]
                           classifies the question (code-comprehension vs meta)
                           judges: responsive to the question? anchored to what
                           was read? correct language?
                           verdict → ok | retry(reason) | insufficient(world)
                                │
                    ┌───────────┼─────────────────────┐
                    ▼           ▼                      ▼
              status=answer   one directed retry   seal honest status
                              (grounding round)    (see §5 taxonomy)
```

The cheap layer **never hard-fails on its own** except for language (which is deterministic). It only raises *suspicion*. The judge — which can read semantics and classify the question — adjudicates. This attacks the responsiveness defect only when warranted, keeping cost at zero in the common (clean) case.

### 4.1 "Content-bearing read" (resolves Halberg C1 / Serrano S1)

A read tool call counts as a content-bearing read iff its dispatched result:
- has **no `error` key**, AND
- carries a **non-empty payload** for its kind: `lines` (read_file), `symbols` (grep_symbols), `entries` (list_dir), `commits` (git_log), `callers`/`callees`, `tests`, etc.

Rationale: today an anchor that returns `{"error": ...}` is ack'd as a *successful* tool call (`compositor.py` only sets `is_error` when `dispatch_tool` raises), and an empty `grep_symbols` (the **normal** path on an unanalyzed project) returns `{"symbols": []}` with no error. Neither is evidence. The compositor must accumulate a per-turn **read ledger**: the set of `(tool, target)` pairs that produced content-bearing results, plus the set of file paths actually read.

### 4.2 Suspicion signals (cheap layer → judge trigger)

The judge is invoked when **any** of:
- zero content-bearing reads on the turn, OR
- zero **well-formed** citations in the answer (a citation block whose `citation` has a non-null `path` or `commit`; resolves S13), OR
- an answer citation references a path **not** in the read ledger (resolves S6 / Halberg Contradiction 2), OR
- detected answer language ≠ detected question language (this one is *also* a deterministic fail; the judge is still consulted to decide retry vs. seal), OR
- the answer is suspiciously short relative to the question's scope (heuristic; tunable).

No suspicion → seal `answer` with no judge call.

### 4.3 The judge (semantic, on suspicion)

A single short LLM call (same provider) given: the question, the answer blocks, and the read ledger. It returns a structured verdict:
- `question_kind`: `code_comprehension | meta | conceptual`
- `responsive`: bool (does it answer *what was asked*)
- `grounded`: bool (claims supported by what was read)
- `language_ok`: bool
- `decision`: `ok | retry | insufficient`
- `world` (when `insufficient`): `consulted_empty` | `not_consulted`
- `retry_directive` (when `retry`): a short instruction for the corrective round

For `meta`/`conceptual` questions the judge may return `ok` even with zero reads (resolves S7) — a meta-answer is not required to cite code.

## 5. Verdict taxonomy (resolves Voronov's "two worlds" + Serrano S3/S4)

`Frame` gains a `status` field. The states distinguish the *fact about the project* from the *fact about the tutor*:

| status | meaning | produced by |
|---|---|---|
| `answer` | a normal, grounded answer | clean path / judge `ok` |
| `insufficient_evidence` | **consulted the code and there genuinely is none** (World A — a fact about the project; the UI says *what would need to exist*) | judge `insufficient(consulted_empty)`, or loop after real reads |
| `ungrounded` | **did not consult / refused to look** (World B — a fact about the tutor; the UI says *the tutor did not read; re-ask or rephrase*) | judge `insufficient(not_consulted)` / cheap layer |
| `partial` | interrupted mid-composition (client disconnect, stream error) | `ask_stream.py` terminal paths |
| `fallback` | the model produced no blocks / tool-round budget exhausted | loop fallback |
| `legacy` | pre-existing frames with no recorded status (default on read) | migration |

This makes a non-answer **never** archived indistinguishably from a real one, and prevents `insufficient_evidence` from lying ("your code is opaque") when the truth was `ungrounded` ("the tutor was lazy") — opposite remedies for the user.

## 6. The closing-round collision — resolved (Halberg BP1 / Violation 1 & 2)

**Problem.** The existing final round (`round_i == max_tool_rounds - 1`) does two things at once: it **forces an answer** *and* **strips the research tools** (`round_tools = answer_only`) while injecting a directive saying the tools are gone. The grounding retry wants the opposite — *more reading* — exactly when reading has been amputated. The two issue contradictory instructions in the same user turn.

**Resolution — decouple "force an answer" from "strip read tools," and separate two distinct triggers:**

1. **"Model won't stop exploring"** (the original purpose of the closing round): a model still calling research tools at the budget edge. Here we keep the existing behavior — strip tools, force an answer — but if that forced answer is ungrounded, it is sealed with an **honest status** (`ungrounded`/`insufficient_evidence`), never as a normal `answer` frame.
2. **"Model answered but ungrounded"** (the new grounding retry): when the model attempts `finish` ungrounded **and budget remains** (`round_i < max_tool_rounds - 1`), inject a corrective directive **without stripping tools** and consume one normal round. The directive explicitly supersedes the standing "STOP reading / 1–4 reads" guidance for that round (resolves S8).

**The single retry slot carries a composed directive.** The one allowed corrective round (§4 diagram) is driven by whichever checks failed: a grounding instruction ("go read X and cite it") and/or a language instruction ("answer in `<language>`"). Only *grounding* failures drive an honest seal (`ungrounded`/`insufficient_evidence`); a residual *language*-only mismatch after the retry seals as `answer` (language is cosmetic relative to grounding — best-effort, per §10).

**Bound (Halberg FailureMode B / FailureMode C):**
- The grounding retry fires **at most once per question**, gated by a `grounding_retry_used` flag set outside the retryable path. Worst case remains bounded by `max_tool_rounds` (no extra-iteration blowup, no unbounded retry hang).
- A `finish` with **zero emitted blocks** is `fallback` (model produced nothing), never conflated with `ungrounded` (model emitted uncited claims) — distinct pathologies, distinct status (resolves FailureMode C).

## 7. Persistence, all terminal paths, migration (resolves S3/S4/S9/S10)

- `status` lives **inside `frame_json`**: extend the `Frame` dataclass + `frame_to_dict` (writes `status`) and `frame_from_dict` (reads it, **defaulting absent → `legacy`**). No `ALTER TABLE` / column migration needed. *(Decision: JSON over a DB column — simpler for a personal tool. Revisit if status-based querying is ever needed.)*
- **Every terminal path sets a status**, including the three that currently bypass the finish gate: clean finish (`answer`/judged), budget-exhausted fallback (`fallback`), and `_persist_partial` on error/disconnect (`partial`). The "never archived indistinguishably" guarantee becomes true for all paths.
- **Restore** reads `status` from the stored frame and trusts it (no recomputation); legacy rows render as `legacy` (treated as a plain answer but never *claimed* grounded). Live-vs-restore parity is preserved because the verdict is stored, not recomputed.

## 8. UI — honest rendering (resolves S5/S14)

- For `status != answer`, `FrameDynamic`/`Cuaderno` render an honest marker stating what happened — and for `insufficient_evidence`, *what would need to exist to answer*.
- **`got_it` is suppressed** on non-answer statuses: "does this answer the question?" is incoherent once the system has declared it does not, and a non-answer must not be filable into the "this matters" collection. (`legacy` keeps the current got_it behavior.)
- **Streaming vs verdict:** blocks stream live and are *provisional*; the terminal `frame` event carries the authoritative `status` and its blocks replace the provisional render. On a retry, the provisional (ungrounded) blocks are replaced by the corrected/ sealed frame.

## 9. Language (resolves S12)

- Detect the question's language from the question text. On short/ambiguous input, instruct the model to "answer in the same language as the question" rather than forcing a guessed label.
- Internationalize the **fixed prompt literals** that are currently hardcoded English (block `kicker`s, follow-up labels, the "go deeper" cap) so a Spanish answer is not stitched together with English chrome.
- A cheap post-hoc language check on the answer is the deterministic arm of the cheap layer (§4.2); a mismatch routes through the judge for retry-vs-seal.

## 10. What is GUARANTEED vs. HOPED (Voronov's "error bars," named)

- **Guaranteed (deterministic):** correct answer language; that a code-comprehension answer with **zero content-bearing reads** is never sealed as a confident `answer`; that the verdict is persisted and distinguishes the failure worlds; that no terminal path archives a non-answer as an answer.
- **Hoped (best-effort via judge + prompt, explicitly NOT guaranteed):** citation *relevance*; answer *responsiveness* (how vs. what). The judge attacks these and a failed judgment triggers a retry/seal, but both are semantic — declared as residuals, not guarantees. This honesty is itself part of the design: the gap between the checked term and the named property is acknowledged, not hidden.

## 11. Suggested implementation phases

The spec is one coherent feature but can ship incrementally:

- **Phase 1 (deterministic core, no judge):** `Frame.status` + persistence + all terminal paths + migration default; the cheap layer (content-bearing read ledger, language detection, suspicion signals); the closing-round decoupling + grounding-retry-once; honest UI rendering; prompt fixes (language mirroring, ground-before-answer, answer-the-question-asked, i18n literals). Without the judge, a sustained grounding failure seals directly from the **read ledger**: **zero** content-bearing reads → `ungrounded` (World B / not_consulted); reads happened but the answer is still unsupported → `insufficient_evidence` (World A / consulted_empty). The world distinction is thus available in Phase 1; the judge (Phase 2) only *refines* it and adds responsiveness.
- **Phase 2 (semantic judge):** add the judge call on suspicion; it refines retry-vs-seal and adds the `world` (consulted_empty vs not_consulted) and responsiveness verdict. Phase 1's direct seals become judge-adjudicated.

## 12. Testing strategy

- **Deterministic, no LLM:** unit tests for the read-ledger ("content-bearing" classification across anchor return shapes incl. `{"error":...}` and empty `{"symbols":[]}`); citation-vs-ledger cross-check; language detection; `frame_to_dict`/`frame_from_dict` round-trips incl. legacy default; status assignment on each terminal path (clean / fallback / budget / partial / disconnect); the grounding-retry bound (fires at most once); the closing-round decoupling (ungrounded forced answer → honest status, not `answer`).
- **Compositor loop with a mock client:** scripted model turns reproducing (a) the pyrrhic incident (zero reads, confident claims → `ungrounded`); (b) genuinely-unanswerable question after real reads → `insufficient_evidence`; (c) honest short answer to a meta question → `answer` (not falsely sealed); (d) ungrounded-finish-with-budget → grounding retry → grounded `answer`.
- **Judge:** mock-judge unit tests for each `decision`/`world`; one key-gated live test (parity with the existing key-gated e2e pattern).
- **Frontend:** render tests for each status (honest marker, got_it suppression); streamed-provisional → authoritative-frame replacement.

## 13. Council review & resolutions (traceability)

Stress-tested before approval; every BLOCKER/HIGH resolved or explicitly deferred:

- **Halberg BP1 (closing-round collision):** §6.
- **Halberg "successful read" undefined / citation validity:** §4.1, §4.2.
- **Halberg liveness bound / empty-emit vs ungrounded:** §6 (bound + `fallback` vs `ungrounded`).
- **Halberg verdict lost at persistence / universality (degenerate bar on unanalyzed/non-Python):** §7; the degenerate-bar limitation is why the semantic judge (§4.3) carries responsiveness/relevance, and is named in §10.
- **Serrano S1–S15:** S1/§4.1; S2/§4 (cheap=suspicion, judge=responsiveness); S3/§5,§7; S4/§7; S5/§8; S6/§4.2; S7/§4.3; S8/§6; S9,S10/§7; S11/§3 (distinct, smaller enum; `contradiction_detected` deferred); S12/§9; S13/§4.2; S14/§8; S15/§10 (residual named; judge covers it).
- **Voronov (proxy vs property; heterogeneous custody; two worlds; persist the honesty, not just the verdict):** §4 (separate custodians), §5 (two worlds), §10 (guaranteed vs hoped named).

## 14. Open questions

None blocking. Deferred by decision: `contradiction_detected` verdict (§3); status as DB column vs JSON (§7, revisit only if querying needed).
