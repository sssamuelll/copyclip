# Cuaderno Playground — Automatic Call Synthesis — Design Spec

**Date**: 2026-06-18
**Status**: Approved for spec (brainstorm complete)
**Relationship**: Extends the guided step-through (`2026-06-16-cuaderno-playground-stepthrough-design.md`). That spec already says *"the cuaderno's model proposes a complete call (args + kwargs + ctor)"* (§3/§4) and added a `needs_args` editable-template fallback when it doesn't. This spec makes the **input configure itself** so the developer goes straight to watching the function run — the manual `needs_args` template becomes a rare last resort, not the main path.

---

## 1. Why

The step-through is only valuable if there's a **runnable call** to step through. The 2026-06-16 design relied on the cuaderno's conversational model to propose the call's args. Live testing exposed that this is unreliable: a weaker provider (deepseek-chat) answered a run-request in prose, the floor couldn't recover, and the user was handed an **empty `name()` template to fill in by hand** — exactly the boilerplate the product owner does not want. The directive: *the playground should configure the input itself (args, kwargs, constructor) so we go straight to the important thing — the execution.*

So input synthesis must be **robust and mostly deterministic**, not dependent on a model volunteering well-formed args. Manual editing remains, but only to *correct* a pre-filled call, never to author it from scratch.

## 2. The synthesis cascade

A new backend unit `src/copyclip/intelligence/cuaderno/call_synth.py`:

```python
@dataclass(frozen=True)
class SynthesizedCall:
    args: list            # JSON-serializable literals
    kwargs: dict          # JSON-serializable literals
    ctor: dict | None     # {args, kwargs} for a method's instance, else None
    arg_source: str       # "model" | "tests" | "signature"  (provenance)

def synthesize_call(resolved, conn, project_root, *, model=None) -> SynthesizedCall | None:
    """Best-effort: returns a runnable call for `resolved`, or None if no source could
    produce one. Each stage is wrapped so a failure falls through to the next."""
```

**Precedence** (first to succeed wins; `arg_source` records which):

0. **Model-proposed (existing path).** If the cuaderno's model already emitted a playground descriptor carrying real args (`emit_fold`), use it — it read the code and may be contextual. `arg_source="model"`. (No `synthesize_call` call needed in this case.)
1. **Call-site / test extraction (deterministic — primary fallback).** The best inputs are *real usage*. Using the analyzer call graph — `symbol_edges` rows where `to_symbol_id = target AND edge_type = 'calls'` — resolve each caller's `file_path` + `line_start..line_end` (from `symbols`), read that source span, `ast.parse` it, and find the `ast.Call` node(s) whose callee resolves to the target. Lift the call's args/keywords when they are **literals** (`ast.literal_eval`-able: str/num/bool/None/list/dict/tuple of literals). Prefer callers under `tests/` and calls with the most fully-literal args. For a **method**, prefer a call-site that also constructs the instance, and lift the constructor's literal args into `ctor`. `arg_source="tests"`.
2. **LLM arg-synthesis (fallback for code with no usable call-site).** A *focused, structured* model call (NOT the conversational turn that proved unreliable): given the function's signature + body, force a `StructuredOutput` of `{args, kwargs, ctor}` as JSON literals. Behind an injectable `model` boundary so it is mockable in tests and can be feature-flagged / skipped. `arg_source="model"`. Fires only when (1) found nothing.
3. **Type-hint synthesis (deterministic floor).** From the signature's annotations, generate plausible literals per type: `str → "example"` (or a path-shaped sample for params named like a path/file), `int → 1`, `float → 1.0`, `bool → True`, `list → []`, `dict → {}`, `bytes → b""`, defaulted params skipped. Unannotated / un-synthesizable types (objects, connections, callables) → this stage returns `None` for that param, and if any required param can't be synthesized, the stage as a whole returns `None`. `arg_source="signature"`.
4. **Last resort — `needs_args` editable (rare).** If 0–3 all fail (e.g. a required parameter is an un-synthesizable object/connection), emit the `needs_args` template (per 2026-06-16): the editable preview pre-filled with the best partial call we have, `Step through` gated until the user supplies the missing args. `arg_source="manual"`.

## 3. Where it runs

- The **floor** (`_construct_playground_floor`, `cuaderno/compositor.py`) calls `synthesize_call(...)` when the model did not already supply a call (precedence 0). The synthesized `args/kwargs/ctor` are folded into the widget's `call` (reuse the `emit_fold` invocation rendering for `call_text`) so the widget arrives **pre-filled and runnable**.
- `synthesize_call` is pure and unit-testable: stages 1 and 3 are deterministic (DB + `ast`); stage 2 takes an injected `model` (mock in tests, real provider in prod). The floor stays thin — it orchestrates, it does not parse.

## 4. Widget contract

The playground widget the cuaderno emits gains one field:

```
arg_source: "model" | "tests" | "signature" | "manual"   (optional; absent ⇒ "model")
```

It always carries a complete `call` + pre-rendered `call_text` (from §2.0–§2.3), **except** the §2.4 last resort which carries the partial call + `needs_args: true` (the existing 2026-06-16 field). `needs_args` and a non-`manual` `arg_source` are mutually exclusive.

## 5. Preview UX (frontend)

- The preview opens showing the **pre-filled, runnable** `call_text`; **`Step through` is enabled** (the call is complete). The developer goes straight to it.
- A small **provenance chip** states where the args came from, using `arg_source`:
  - `tests` → "args de `test_…`" / "args from `test_…`" (trustworthy — real usage)
  - `model` → "ejemplo propuesto por IA" / "example proposed by AI" (review before running)
  - `signature` → "desde la firma" / "from the signature" (generic sample)
- The `✎` edit affordance stays for **correction** (editing → free-text path, per 2026-06-16 §10). The `needs_args` gated-template behavior (2026-06-16 + the dirty-flag) stays only for `arg_source="manual"`.
- The stepper's "edit the call" re-run loop (added 2026-06-18) stays, so any input can be tweaked and re-run.

## 6. Consent & security

Unchanged trust model (2026-06-16 §10), and the cascade fits it cleanly:
- A **synthesized, un-edited** call is a structured descriptor (args as JSON literals) → the **repr-literal-guarded structured path**. Safe against a garbled synthesis.
- An **edited** call → the free-text exec path (the user's own code, explicit confirm).
- The **provenance chip is informed consent**: `arg_source="model"` (AI-guessed, possibly unrepresentative — Serrano's concern) is visibly distinguished from `tests` (real). The user reviews before clicking `Step through`.
- A synthesized arg that turns out wrong fails as an **honest `raise` step** (the call still ran under the caps); the user edits and re-runs.

## 7. Error handling

- Each cascade stage is wrapped: any exception (DB miss, un-parseable caller, AST edge case, model error, un-annotated type) falls through to the next stage. `synthesize_call` never raises into the floor.
- The floor never blocks on synthesis: stage 2 (LLM) has a timeout; on timeout it falls through to stage 3.
- Capture caps (2026-06-16 §5) are unchanged and apply to whatever call is run.

## 8. Testing

- **Stage 1 (extraction):** a fixture project where `target` is called in a test with literal args → assert the lifted `args`/`kwargs` match; a method call-site with a constructed instance → assert `ctor`; a call with non-literal args → that call-site is skipped; prefer-tests ordering.
- **Stage 2 (LLM):** injected mock model returns a `{args,kwargs,ctor}` → assert it's used and `arg_source="model"`; model error/timeout → falls through.
- **Stage 3 (type synth):** `(file_path: str)` → a sample str; `(n: int, flag: bool=False)` → `[1]` (defaulted skipped); an un-annotated/object param → stage returns None.
- **Cascade ordering:** with all sources available, `tests` wins; with no call-site, the LLM mock wins; with neither, signature; with none, `needs_args`/`manual`.
- **Floor integration:** a run-request for an arity>0 function with a test call-site emits a widget pre-filled from `tests` (no `needs_args`); the breadcrumb + widget validation still pass.
- **Frontend:** the provenance chip renders per `arg_source`; `Step through` enabled for a synthesized call; `needs_args`/`manual` still gates per the 2026-06-18 fix.

## 9. Scope & phases

- **Core (this spec):** the `call_synth` module with stages **1 (extraction) and 3 (type synth)**, the cascade + `arg_source` contract, the floor wiring, and the preview provenance chip. This alone fixes the directive deterministically for a well-tested codebase.
- **Additive:** stage **2 (LLM synthesis)** behind the injectable `model` boundary — lands in the same module with a feature flag, so it can be staged or disabled without touching stages 1/3 or the contract.
- Out of scope: synthesizing genuinely un-synthesizable runtime objects (live connections, sockets) — those fall to the `manual` last resort by design.

## 10. Acceptance criteria

- [ ] A run-request for an arity>0 function **that is called somewhere in the codebase** (e.g. `_module_from_file`, called by its tests) produces a widget **pre-filled** with a runnable call lifted from that call-site (`arg_source="tests"`); the user clicks `Step through` with **no typing** and the stepper walks the trace.
- [ ] A method with a test call-site that constructs the instance is pre-filled with both `ctor` and method args.
- [ ] A function with **no** call-site falls through to LLM synthesis (when enabled) or type-hint synthesis; only a genuinely un-synthesizable required param reaches the `manual` `needs_args` template.
- [ ] The preview shows the correct **provenance chip**; `Step through` is enabled for a synthesized call; editing routes to the free-text path; `manual` still gates per the 2026-06-18 fix.
- [ ] `synthesize_call` stages are individually unit-tested; the LLM stage is mocked; `pytest -q` and the frontend suite pass.
- [ ] No change to the capture caps, the trace schema, or the consent/security model beyond adding `arg_source`.

## 11. References

- `2026-06-16-cuaderno-playground-stepthrough-design.md` — the step-through, the call descriptor, `needs_args`, the §10 consent model, the capture caps.
- Analyzer: `symbol_edges` (`edge_type='calls'`, `from_symbol_id`→`to_symbol_id`), `symbols` (`file_path`, `line_start`, `line_end`, `parent_symbol_id`).
- Code: `cuaderno/compositor.py` (the floor), `cuaderno/emit_fold.py` (invocation rendering), `cuaderno/schema.py` (Widget), `playground.py` / `capture.py` (resolve + capture), `frontend/.../PreviewCall.tsx` + `types/api.ts` (the preview + contract).
