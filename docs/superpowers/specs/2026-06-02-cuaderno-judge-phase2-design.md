# Cuaderno Answer Quality — Phase 2: The Semantic Judge

**Status:** Design (approved 2026-06-02) — ready for implementation planning
**Builds on:** `docs/superpowers/specs/2026-06-01-cuaderno-answer-quality-design.md` (Phase 1, shipped in #125)
**Surface:** `src/copyclip/intelligence/cuaderno/` + `frontend/src/components/cuaderno/`
**Author:** Samuel + Claude Code, reframed across three rounds by Voronov

---

## 1. Motivation — the residuals Phase 1 named but could not close

Phase 1 shipped a deterministic groundedness gate and honest typing. By §10 of the Phase-1 spec it was honest about what it could NOT do:

1. **Responsiveness is uncustodied.** The founding incident — "como funciona?" answered with *what it is*, not *how it works* — is a **responsiveness** failure. Responsiveness is a relation between two intents (the question's and the answer's); no cheap deterministic signal detects it. Phase 1 left it to the prompt, i.e. in the model's own custody.
2. **World A is never produced.** Phase 1 seals `ungrounded` (World B — *the tutor didn't look*) but never `insufficient_evidence` (World A — *the project genuinely lacks the evidence*). Distinguishing them requires semantic judgment.
3. **`answer` over-claims.** In Phase 1 `answer` means *"consulted the code and cited nothing it failed to read"* — weaker than *"every claim follows from the evidence."* A code answer that does one irrelevant read and emits no citations seals `answer`.

Phase 2 adds the **semantic judge**: a second, separately-prompted inference over the *finished* answer. Per Voronov's custody thesis, this is the only possible custodian of responsiveness, because it is the only station from which the question-intent ↔ answer-intent relation can be read — and it is a genuinely different custodian than the model judging its own composition mid-stream (it is not invested in the answer having succeeded, it operates on a closed object, and it can return a verdict the author is structurally incapable of producing: *"this answers a different question than was asked."*)

## 2. Goals

- A non-responsive answer (grounded, cited, right language, but answers the wrong question) is **detected and corrected** — closing the founding incident's exact defect.
- `insufficient_evidence` (World A) is **produced**: the judge distinguishes *consulted-and-empty* from *did-not-look*.
- The frame's record carries the **full multi-axis verdict** (grounding × responsiveness × language), not just the projected disposition.
- The judge is an **enhancement, never a new way to hang or lock** the answer: if the judge call fails, the system seals the already-streamed grounded answer (fail-open).

## 3. Non-goals

- A deterministic responsiveness check (impossible; responsiveness is semantic — the judge is the custodian, and it is fallible by an *error-bar*, not by structural blindness).
- Replacing the Phase-1 cheap layer. The cheap layer still hard-seals the cardinal cases (zero reads, fabricated citations, language) deterministically; the judge runs only when the cheap layer would otherwise seal `answer`.
- UI-chrome i18n ("you asked" / "go deeper" fixed literals) — a separate trivial follow-up.
- Streaming the judge's deliberation, or a `contradiction_detected` verdict (still deferred).

## 4. Architecture — the judge as the responsiveness custodian

The governing law, established across three Voronov rounds:

> **A custodian owns the full arc of its property — detection, activation, AND correction — each bounded to one shot, none fungible with another custodian's. A custodian that cannot decide when it looks, or cannot act on what it finds, is not a custodian: it is surveillance.**

```
compose answer (existing loop) ──► cheap layer (Phase 1, deterministic)
                                        │
            ┌───────────────────────────┴───────────────────────────┐
            ▼ hard-fail (zero reads / fabricated cites / language)   ▼ would seal `answer`
      seal ungrounded / retry (grounding latch)              [ JUDGE · haiku · post-stream ]
                                                              question + blocks + ledger summary
                                                                          │
                                          ┌───────────────┬──────────────┴───────────┐
                                          ▼ ok            ▼ retry                     ▼ insufficient(world)
                                    seal `answer`   responsiveness retry        seal insufficient_evidence
                                                    (own latch) → re-judge       (consulted_empty)
                                                          │ still bad             OR ungrounded
                                                          ▼ (latch spent)         (not_consulted)
                                                    seal `off_target`
```

### 4.1 Firing policy — Option A (the judge owns its activation)

The judge runs **whenever the cheap layer would seal `answer`** — i.e. on every successful, clean-looking answer. It does NOT run when the cheap layer already hard-failed (the disposition is already determined; there is nothing for the responsiveness custodian to add to an answer that is being re-grounded).

Rationale (Voronov): responsiveness has no cheap signal, so gating the judge on cheap *suspicion* would point the responsiveness custodian at every answer **except** the clean-looking ones — which is precisely where "what-not-how" hides. Gating the judge on groundedness's alarm would not custody responsiveness; it would abolish it and keep the nameplate.

### 4.2 The judge call

A new module `judge.py`: `judge_answer(*, client, question, blocks, ledger, model) -> JudgeVerdict`.

- **Input:** the question, the emitted answer blocks, and a **ledger summary** (the set of paths/tools that returned content this turn — `ReadLedger.content_bearing_count`, `read_paths`, and the tool names used). The summary lets the judge assess `grounded` and the `world` (consulted-empty vs not-consulted).
- **Call shape:** a SINGLE non-streaming completion (no agentic tools) that asks for a structured JSON verdict, against a dedicated `JUDGE_PROMPT`. Model: `claude-haiku-4-5` by default (configurable; the answer model is unchanged). This needs a provider method for a one-shot structured/JSON completion — see §11.
- **Output (`JudgeVerdict`):**
  - `question_kind`: `code_comprehension | meta | conceptual`
  - `grounded`: bool (claims supported by what was read)
  - `responsive`: bool (answers *what was asked* — how vs. what)
  - `language_ok`: bool
  - `decision`: `ok | retry | insufficient`
  - `world`: `consulted_empty | not_consulted` (only when `decision == insufficient`)
  - `retry_directive`: a short instruction for the corrective round (only when `decision == retry`)
  - `reason`: a short human-readable justification
- For `meta`/`conceptual` questions the judge may return `ok` with zero reads — a meta-answer need not cite code.
- **Fail-open:** if the judge call errors, times out, or returns unparseable output, treat it as `decision == ok` and seal `answer`. The answer already streamed and already passed the deterministic gate; a judge outage must never block, hang, or downgrade it. (This is the §124-class invariant: the terminal `frame` must always be reached.)

### 4.3 Action mapping

- `ok` → seal `answer`.
- `retry` → fire the **responsiveness retry** (its own latch, §4.4): inject `retry_directive`, emit `reset`, spend one normal round; the corrected answer replaces the prior one; then **re-judge** the corrected answer once. If the responsiveness latch is already spent (the retry already happened and it is *still* non-responsive) → seal **`off_target`**.
- `insufficient` → seal `insufficient_evidence` (`world == consulted_empty`) or `ungrounded` (`world == not_consulted`). **This is where World A is finally produced.**

## 5. Correction — per-property, non-fungible (Voronov's "standing, not budget")

The single Phase-1 latch `grounding_retry_used` is split into **per-property latches**:

- `grounding_retry_used` — the cheap layer's shot (grounding / language).
- `responsiveness_retry_used` — the judge's shot.

Each fires **at most once**, for **its own** property; **neither can consume the other's**. Both sit under the unchanged ceiling `can_retry = round_i < max_tool_rounds - 2`. A grounding failure cannot exhaust the judge's only means to correct a non-responsive answer.

**Bound:** total model rounds ≤ base loop + (one per custodian), with `max_tool_rounds` as the hard ceiling regardless. Today (two custodians) that is "up to two corrective rounds" — but the invariant is *one-shot per distinct property*, so a future third custodian (e.g. citation-relevance) brings its own shot without renegotiation. The unit is the **property**, not the round.

## 6. Status + verdict — projection over a persisted record

Voronov's reframe: **`Frame.status` is the *disposition* axis** ("may the user rely on this, and if not, in what shape do I disclose the failure?") — already a mix of facts-about-project, facts-about-tutor, facts-about-process. It is a **projection** of the multi-axis truth onto the one axis the UI acts on.

Two changes:

1. **Add `off_target` to the disposition enum** (`schema.py` `KNOWN_FRAME_STATUSES`): *grounded, but answers a different question than was asked.* It earns the same treatment as `ungrounded` — an honest banner, `got_it` suppressed, restore-trusted.

2. **`Frame` gains a `verdict` field** — the persisted multi-axis pre-image. The disposition `status` is the shadow; the `verdict` is the object that casts it. Without persisting it, the system re-commits the original sin (compute a verdict, use it once, discard it) one level up: the first time a frame is both `ungrounded` AND off-target, the flat `status` must choose one word, and only the persisted verdict remembers both were true.

   `Frame.verdict: Optional[dict]` carries: `grounded`, `responsive`, `language_ok`, `question_kind`, `world`, `reason`, and `source` (`cheap` | `judge`). It rides inside `frame_json` (like `status`); `frame_from_dict` defaults it to `None` for legacy/pre-existing frames. Every freshly-sealed frame carries the verdict that produced its status: cheap-only seals carry the cheap layer's partial verdict (grounded/language known; responsive unknown); judge seals carry the full seven-field verdict.

The UI consumes `status` (one disposition); the record keeps `verdict` (the pre-image). Collapse the view; never collapse the record.

## 7. UX — post-stream, fail-open, honest

- The answer streams as today (provisional blocks). The judge runs **synchronously in the compositor terminal, before the `frame` event is yielded** — composing with the existing `reset` / SSE-close machinery (the close still happens after the terminal `frame`, preserving the #124 unlock invariant). The composer stays `disabled` during the judge call (the answer is not yet final), ~1–2s on haiku, hidden behind the user reading the already-streamed answer.
- **`ok`** (common case): the terminal `frame` seals `answer`; the provisional render becomes authoritative with no visible change.
- **`retry`**: a `reset` clears the provisional render; the corrected answer streams; re-judged once.
- **`off_target` / `insufficient_evidence` / `ungrounded`**: the terminal `frame` carries the honest banner. `off_target`'s banner: *"This is grounded, but it answers a different question than you asked. Re-ask to redirect."* — got_it suppressed.
- A subtle "checking…" affordance during the judge call is **optional polish** (default: none; the existing midstream/loading treatment suffices).

## 8. What is GUARANTEED vs HOPED (updated from Phase-1 §10)

- **Guaranteed (deterministic, unchanged from Phase 1):** answer language; no zero-content-bearing-read code answer sealed `answer`; no fabricated-citation answer sealed `answer`; the verdict persisted on every terminal path.
- **Custodied but fallible (new — the judge):** responsiveness, World A vs World B, and a semantic groundedness recheck now have a real custodian that owns detection, activation, and correction. The judge is fallible — it will occasionally miss a non-responsive answer or flag a responsive one. This is an **error-bar** (named, honest, the §10 standard), categorically different from Phase 1's *structural blindness* on these axes: the judge can be wrong; the prior architecture could not even be *asked*.
- **Still hoped (deferred):** citation-relevance beyond what the judge's `grounded` recheck covers; a `contradiction_detected` verdict.

## 9. Components / file structure

- **New:** `src/copyclip/intelligence/cuaderno/judge.py` — `JudgeVerdict` dataclass + `judge_answer(...)`; JSON parse + fail-open.
- **New:** `JUDGE_PROMPT` in `prompts.py` (instructs the structured verdict; emphasizes question-intent ↔ answer-intent, how-vs-what, and consulted-empty vs not-consulted).
- **Modify `schema.py`:** add `FRAME_STATUS_OFF_TARGET = "off_target"` to `KNOWN_FRAME_STATUSES`; add `Frame.verdict: Optional[dict]`; `frame_to_dict`/`frame_from_dict` carry it (default `None`).
- **Modify `compositor.py`:** at the terminal, when the cheap verdict would be `answer`, call `judge_answer`; map its decision (§4.3); split the latch into `grounding_retry_used` / `responsiveness_retry_used`; seal with the projected status AND the persisted verdict. Thread the judge model + client through.
- **Modify `provider.py` / client adapters:** add a one-shot structured/JSON completion method (a non-streaming `complete_json` or equivalent) for the judge, and resolve the judge model (default haiku).
- **Modify `quality.py`:** `assess` already returns a partial verdict; expose it as the `verdict` pre-image for cheap-only seals (so even non-judge seals persist a verdict).
- **Frontend:** add `'off_target'` to `FrameStatus`; add its `STATUS_BANNER` entry; add `Frame.verdict?` to the type (read-only, for future surfacing — not rendered in Phase 2 beyond the banner). Got_it suppression already keys on `status !== 'answer' && !== 'legacy'`, so `off_target` is suppressed automatically.

## 10. Suggested implementation phases

- **2a (judge plumbing, deterministic-testable):** `JudgeVerdict` + `judge_answer` with a **mock/stub client** (no live LLM); the provider `complete_json` method; `JUDGE_PROMPT`. Unit-test the parse + fail-open paths.
- **2b (compositor integration):** wire the judge into the terminal; per-property latches; `off_target` + verdict persistence; action mapping. Test with `StubStream` + a stub judge (scripted verdicts) — no live LLM.
- **2c (frontend):** `off_target` status type + banner; verdict type. `tsc -b`.
- **2d (live, key-gated):** one e2e parity test behind the existing key gate.

## 11. Testing strategy

- **Deterministic, no LLM:** `judge.py` JSON parse (valid / malformed → fail-open `ok`); `JudgeVerdict` defaults; `Frame.verdict` round-trip incl. legacy `None`; `off_target` in the status enum + `frame_to_dict`/`from_dict`.
- **Compositor with `StubStream` + a stub judge** (the judge call is injected, returns scripted `JudgeVerdict`s): (a) judge `ok` → `answer`; (b) judge `retry` → reset + re-compose → re-judge `ok` → `answer` with the corrected blocks; (c) judge `retry`, still non-responsive, latch spent → `off_target`; (d) judge `insufficient(consulted_empty)` → `insufficient_evidence`; (e) judge `insufficient(not_consulted)` → `ungrounded`; (f) **fail-open**: judge raises → `answer` (never hangs); (g) **per-property latch**: a grounding retry already fired AND the judge wants a responsiveness retry → the judge still gets its shot (non-fungible); both latches respect the `can_retry` ceiling; total rounds bounded.
- **Verdict persistence:** every sealed terminal (answer / off_target / insufficient / ungrounded / fallback / partial) carries a `verdict` (or `None` only for legacy reads).
- **Frontend:** `off_target` banner renders; got_it suppressed (typecheck-level + the existing render path).

## 12. Reasoning traceability (Voronov, three rounds)

- **Firing = Option A:** "A property's custodian must own its own activation, or it is an instrument of whatever owns the trigger." Responsiveness has no cheap signal; gating on groundedness blinds the responsiveness custodian to the clean-looking answers where "what-not-how" hides → §4.1.
- **Correction = per-property non-fungible:** "Custody is the full arc: detection, activation, correction — each one-shot, none fungible." Shared latch re-subordinates (one layer down); the unit is the property, not the round → §5.
- **Status = projection over a persisted record:** "`status` is the disposition view; the verdict is the truth. Collapse the view, never the record." → §6.

## 13. Out of scope (separate follow-ups)

UI-chrome i18n ("you asked" / "go deeper"); a "checking…" indicator; citation-relevance beyond the judge's `grounded` recheck; `contradiction_detected`. Vex Rune's Phase-1 cleanups (the `_sealed_frame` helper, dead guards) remain available but are not part of this spec.

## 14. Open questions

None blocking. Deferred by decision: surfacing the persisted `verdict` to the user beyond the banner (Phase 3); `contradiction_detected` (§13); judge model is configurable, default `claude-haiku-4-5`.
