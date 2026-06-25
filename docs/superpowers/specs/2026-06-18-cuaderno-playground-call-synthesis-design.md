# Cuaderno Playground — Automatic Call Synthesis — Design Spec

**Date**: 2026-06-18
**Status**: **IMPLEMENTED (Core Stage 1)** on branch `feat/cuaderno-call-synthesis` → PR #178 (2026-06-25). Plan: `docs/superpowers/plans/2026-06-25-cuaderno-playground-call-synthesis.md`. The deferred fabricated-example mode (§9) is NOT built. — v2, recut after a unanimous 5/5 roster direction-check (Lyra, Cassian, Voronov, Vex, Serrano)
**Relationship**: Extends the guided step-through (`2026-06-16-cuaderno-playground-stepthrough-design.md`). Makes the playground **configure the input itself** so the developer goes straight to the execution, instead of handing them an empty `name()` template to fill in by hand (the live-testing rejection that triggered this).

---

## 0. Revision note (2026-06-18) — what the roster cut and why

The original v1 of this spec proposed a **four-stage cascade** (model-proposed > call-site extraction > LLM synthesis > type-hint synthesis > manual). All five roster lenses independently landed on the same verdict: **that is over-built, and the Core/Additive split was along the wrong joint.**

The real seam is **reads real usage vs fabricates usage** — not deterministic-vs-LLM:

- **Core (this work) = Stage 1 (lift a real call from the codebase's call-sites/tests, with local AST re-verification of the callee binding) + the existing `manual` needs_args floor.** Two honest provenance values: `tests` | `manual`.
- **Type-hint synthesis (old Stage 3) and LLM synthesis (old Stage 2) are CUT from Core** → a deferred, flag-gated **"fabricated example" mode** (separate, clearly labeled), built only if real usage shows a meaningful fraction of targets have no liftable call-site. Type-hint synthesis is *fabrication*, not Core — `str → "example"`, `int → 1` produces a call that runs but exercises nothing the author intended, and a `signature` chip on it would let the user trust a trace of a value the code never sees.
- The **model-proposed path** (`emit_fold`, existing) is **not a synthesis "stage"** — it is the path that runs when the model already delivered args. The synthesizer runs only when it did not. Re-listing the model path as "precedence 0" of a new cascade quietly re-blesses the exact unreliable path the pivot reacted to; don't.

## 1. Why — and what the recording is a reading OF

Voronov's ontology fix (the sentence both prior specs left unwritten): **the recorded execution is a reading of how this function is actually used in this codebase.** That definition ranks the input sources:

- A call **lifted from real usage** is *evidence about the system* — the same category as the trace itself.
- A **fabricated** call (type-hint- or LLM-invented) is a *hypothesis the codebase never supplies* — a different artifact that, rendered in the identical stepper chrome, the developer reads as real. The dangerous case is a fabricated call that runs **clean**: it teaches the developer something false about their system, silently, wearing the same pixels as a true trace.

So Core synthesizes **only real usage**. Fabrication is deferred, flag-gated, and visibly labeled as fabrication.

## 2. The synthesizer (Stage 1 — real-usage extraction)

A new backend unit `src/copyclip/intelligence/cuaderno/call_synth.py`:

```python
@dataclass(frozen=True)
class SynthesizedCall:
    args: list            # JSON-serializable literals
    kwargs: dict          # JSON-serializable literals
    ctor: dict | None     # {args, kwargs} for a method's instance, else None — also all literals
    arg_source: str       # "tests"  (the only value this function emits)

def synthesize_call(resolved, conn, project_root) -> SynthesizedCall | None:
    """Lift a runnable call to `resolved` from a verified, fully-literal real call-site.
    Returns None when no such call-site exists — the floor then emits the `manual`
    needs_args widget. Best-effort: any failure falls through to None."""
```

### 2.1 Find candidate call-sites

`symbol_edges` rows where `to_symbol_id = <target> AND edge_type = 'calls'` → each caller `from_symbol_id` → its `file_path` + `line_start..line_end` from `symbols`. Prefer callers under `tests/`.

### 2.2 Re-verify the binding (Serrano BLOCKER — the central engineering)

**The call graph is a name-based heuristic, not a verified binding.** `analyzer.py:761-787` resolves callees by bare name with a first-match-wins global fallback, so a `calls` edge into the target can actually point at a **same-named function in another module**. Lifting those args and labelling them `arg_source="tests"` (trustworthy) would be *confidently wrong input wearing a trust chip* — worse than honest manual entry.

So: for each candidate caller, re-parse its source span with `ast`, find the `ast.Call` node(s) whose callee resolves to the target's **name**, and **confirm it binds to THIS symbol** — same module/file and (for a method) same class — using the caller's import/def context. **Only a confirmed call-site is trusted.** An unconfirmed edge is discarded, never lifted. This is where the engineering budget goes.

### 2.3 Require self-contained literal args (Serrano — the fixture concern)

Lift a call **only if** its args/kwargs (and, for a method, the instance construction) are `ast.literal_eval`-able literals with **no free names / fixtures**. Tests usually call with fixtures or constructed objects (`f(conn, built_obj)`), whose names do not exist in a fresh capture — lifting them would `NameError` at capture, breaking the "Step through, no typing" promise. Such a call-site is **skipped**. If no candidate is fully literal → `None` → `manual`. This guarantees a lifted call actually runs self-contained.

### 2.4 Selection when call-sites disagree

Among confirmed, fully-literal candidates: prefer `tests/` callers; among those, pick the call with the **most non-degenerate literal args** (avoid an empty/`None`-only call that teaches nothing), tie-broken by `file:line` for determinism. The chosen call is shown via the chip and is fully editable (the preview ✎ + the stepper's re-edit/re-run loop), so a wrong guess is one edit away from corrected — the selection need not be perfect, only honest and runnable.

## 3. Where it runs

The **floor** (`_construct_playground_floor`, `cuaderno/compositor.py`) calls `synthesize_call(...)` when the model did not already supply a call. On a `SynthesizedCall`, fold it into the widget's `call` (reuse `emit_fold` for `call_text`). On `None`, emit the existing `manual` needs_args widget. `synthesize_call` is pure and unit-testable (DB + `ast`, no model, no network).

## 4. Widget contract

`arg_source` (optional): **`"tests"` | `"manual"`** in this work. (The deferred fabrication mode adds `"fabricated"`, never silently defaulted.)

- Stage 1 success → `call` + pre-rendered `call_text` + `arg_source: "tests"`, no `needs_args`.
- Stage 1 `None` → the existing `needs_args: true` widget (2026-06-18 fix), `arg_source: "manual"`.

## 5. Preview UX (frontend)

- Pre-filled, runnable `call_text`; **Step-through enabled** (no typing for the `tests` case). A **provenance chip — exactly two values**: `tests` → "args de `test_…`" / "from `test_…`" (real usage, trustworthy); `manual` → "completa la llamada" / "complete the call" (the needs_args gated editor). The ✎ correction and the stepper re-edit/re-run loop are unchanged.

## 6. Consent & security

Core ships only **real-usage** input (`tests`, injected as the repr-literal-guarded structured descriptor) and **user-typed** input (`manual`, the free-text exec path). **No AI-guessed input ships in Core**, so the "input may be unrepresentative" risk is absent from Core by construction — it can only return with the deferred fabrication mode, which carries its own distinct chip and is flag-gated. The capture caps and the two consent paths (2026-06-16 §10) are unchanged.

## 7. Error handling

Each step is best-effort: no edge, un-parseable caller, unconfirmed binding, no fully-literal call → `synthesize_call` returns `None` and the floor falls to `manual`. It never raises into the floor. Because lifted calls are required to be self-contained literals (§2.3), a `tests` call that raises at capture is a **genuine behavior of the function** (an honest `raise` step), not a synthesis artifact — the two are not conflated.

## 8. Testing

- **Re-verification:** a fixture project with two same-named functions in different modules; a `calls` edge into one — the synthesizer must NOT lift the other's call-site (binding confirmed by file/class).
- **Extraction:** target called in a test with literal args → lifted args match, `arg_source="tests"`; a method with a literal-constructed instance → `ctor` lifted; a call with fixture/non-literal args → skipped; no call-site → `None`.
- **Floor integration:** an arity>0 function with a liftable literal test-call emits a pre-filled `tests` widget (no `needs_args`); a function with no liftable call-site emits the `manual` needs_args widget.
- **Frontend:** the chip renders for `tests` and `manual` only (no third value in this work).

## 9. Scope

- **This work (Core):** `call_synth.py` Stage 1 (candidate-finding + AST re-verification + literal-only lift + selection), the floor wiring, the `tests`/`manual` contract, and the two-value preview chip.
- **Deferred — fabricated-example mode (NOT this work):** LLM synthesis + type-hint synthesis, behind a feature flag, as a separate mode labeled "no real call-site found — here is a fabricated example" (`arg_source: "fabricated"`). Build only if telemetry on the `tests`/`manual` split shows a meaningful fraction of run-requests have no liftable call-site. (Lyra: measure before building the catch for a miss you have not counted.)

## 10. Acceptance criteria

- [ ] A run-request for a function called somewhere with fully-literal args yields a widget **pre-filled** from that call-site (`arg_source="tests"`), with the binding **confirmed** (not a same-named function in another module); the user clicks Step-through **with no typing** and the stepper walks the trace.
- [ ] A method with a literal-constructed test instance is pre-filled with both `ctor` and method args.
- [ ] A target with **no confirmed, fully-literal** call-site falls to the existing `manual` needs_args widget — **never** a fabricated call; no LLM/type-hint synthesis ships in this work.
- [ ] A lifted `tests` call is self-contained (no fixture/free-name `NameError` at capture); a raise from it is the function's real behavior.
- [ ] The provenance chip has exactly two values (`tests` | `manual`); `synthesize_call` is unit-tested incl. the cross-module same-name re-verification case; `pytest -q` + the frontend suite pass.
- [ ] No change to the capture caps, the trace schema, or the consent model beyond adding the `arg_source` field.

## 11. References

- `2026-06-16-cuaderno-playground-stepthrough-design.md` — the step-through, the call descriptor, `needs_args`, the §10 consent model, the caps.
- Roster direction-check (2026-06-18, unanimous 5/5 `ship-core-now-defer-synthesis`): Lyra (opportunity cost — ship the core, then reassess the quarter), Cassian (ship #177; stage-1 fast-follow), Voronov (real-usage vs fabrication is the seam; define what the recording reads), Vex (one source earns its keep; cut the rest), Serrano (the call graph is a heuristic — re-verify the binding; require self-contained literals).
- Analyzer: `symbol_edges` (`edge_type='calls'`, `from_symbol_id`→`to_symbol_id`), `symbols` (`file_path`, `line_start`, `line_end`, `parent_symbol_id`), `analyzer.py:761-787` (the name-based callee resolution this spec re-verifies against).
- Code: `cuaderno/compositor.py` (floor), `cuaderno/emit_fold.py` (invocation rendering), `cuaderno/schema.py` (Widget), `playground.py` / `capture.py` (resolve + capture), `frontend/.../PreviewCall.tsx` + `types/api.ts`.
