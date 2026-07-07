# Cruces / Junctions v0.1 — executed-arm overlay over the step-through

- **Date:** 2026-07-02
- **Status:** Design approved (brainstorming), pending implementation plan.
- **Roadmap:** Forward #1 — Cruces / Junctions ([#146]). "In the playground,
  show *which branch executed the input you just edited*, as a computed value,
  never narrated."
- **Arc:** the natural continuation of the playground arc
  (run-a-symbol → step-through → call synthesis). The expensive substrate — the
  bounded tracer, the Stepper, the capture pipeline — is already shipped and
  paid for. This is a pure function plus one additive field plus per-line
  decoration.

[#146]: https://github.com/sssamuelll/copyclip/issues/146

## 1. Goal

When a step-through runs a real call, the trace already records every line the
target function actually executed. Cruces surfaces the **control-flow** reading
of that fact: for each `if`/`elif`/`else` in the function, mark which arm the
run crossed and which it did not — as a **computed structural overlay on the
source pane, with zero prose**. A branch not taken simply has no events; the
overlay reads that off the existing trace.

This honors the product's founding discipline (*exposición, no autoría*): the
overlay states what the run did, never narrates or advises, and — critically —
never claims a branch "did not run" when the evidence is incomplete (§6).

## 2. Scope

**In (v0.1):**
- `if` / `elif` / `else` statements in the target function body, at any nesting
  depth (nesting handled by the natural rule in §7, no special-casing).
- A tri-state `taken` per arm: `true` | `false` | `null` (unknown).
- A static per-run overlay in the Stepper: not-taken arms dimmed, a gutter chip
  on each junction's test line naming the crossed arm.

**Out (deferred to a later "Junctions v0.2 / control-flow C" iteration):**
- Loops (`for` / `while`): ran-vs-skipped, iteration counts.
- `try` / `except` / `finally`: which handler caught.
- Ternary expressions, boolean short-circuit, `match` / `case`, comprehension
  filters.

These are deferred deliberately, to be added from real cases rather than
speculated (ponytail: build the catch for a miss you have counted). v0.1 ships
the most common junction — the `if` ladder — end to end.

## 3. Architecture & data flow

The step-through payload flows today (unchanged by this feature):

```
launch_playground (playground.py:508)
  → run_capture / run_free_text_capture (capture.py:651 / :661)
  → StepThroughResponse{trace, source_lines, func_name, file_line,
                        truncated, truncated_reason}   (capture.py:233)
  → .to_dict() → {kind:'trace', ...}  → SSE frame → <Stepper> (Stepper.tsx:19)
```

Cruces inserts **without touching the capture pipeline**:

1. A new pure module `cuaderno/junctions.py` exposes
   `compute_junctions(source: str, target: TargetIdent, executed_lines: set[int],
   truncated: bool) -> list[dict]`.
2. `launch_playground`, on the cuaderno step-through path, computes `junctions`
   right after a successful capture (both the model and the free-text branches
   converge at the `StepThroughResponse(...)` return, playground.py:625) and
   passes it into the response.
3. `StepThroughResponse` gains a `junctions` field, serialized additively in
   `.to_dict()`.
4. The Stepper decorates its existing source pane from `junctions`.

The overlay is **static per run** — it describes the whole execution, not the
current step — so it is computed once and does not change as the user scrubs.

## 4. The `junctions` contract (backend ↔ frontend)

Backend — new field on `StepThroughResponse.to_dict()` (capture.py:245):

```python
"junctions": [
  {
    "test_line": 42,                          # line of the `if` / `elif` keyword
    "arms": [
      {"kind": "if",   "lines": [42, 45], "taken": True},
      {"kind": "elif", "lines": [46, 48], "taken": False},
      {"kind": "else", "lines": [49, 51], "taken": False}
    ]
  }
]
```

- `kind`: `"if"` | `"elif"` | `"else"`.
- `lines`: `[first, last]` absolute line numbers of the arm's **body**
  (inclusive), aligned with `source_lines[].num` and `Step.line`.
- `taken`: `true` | `false` | `null` (unknown, §6).
- An `else`-less ladder simply has no `"else"` arm.

Frontend — extend `StepThroughResponse` (types/api.ts:678). `source_lines`
stays `{ num, text }[]`; `truncated_reason` stays at :685.

```ts
export type Junction = {
  test_line: number
  arms: { kind: 'if' | 'elif' | 'else'; lines: [number, number]; taken: boolean | null }[]
}
// StepThroughResponse gains:
  junctions?: Junction[]   // optional: absent on older payloads → overlay off
```

`junctions` is optional so an older backend (or the empty-trace / fallback
paths, which never build a Stepper) degrades to today's behavior.

## 5. AST branch extraction

`compute_junctions` is pure and I/O-free; `launch_playground` supplies the
source text and the executed-line set.

- Parse the **whole file** with `ast` (from `os.path.join(project_root,
  resolved.file)`). Parsing the whole module gives absolute `lineno`/`end_lineno`
  for free, so junction lines align with `source_lines[].num` and `Step.line`
  without any offset arithmetic. (Parsing only the function slice would fail on
  the indented body of a method and force fragile dedent+offset math.)
- Locate the target `FunctionDef` / `AsyncFunctionDef` by matching
  `node.lineno == resolved.line_start`. If `line_start` is absent or no node
  matches, fall back to a unique name match; if still ambiguous, return `[]`.
- Walk `ast.If` nodes within the target function body:
  - `test_line = node.lineno` (the `if`/`elif` keyword line).
  - then-arm `lines = (node.body[0].lineno, node.body[-1].end_lineno)`.
  - **`elif` chain:** an `orelse` that is exactly `[ast.If(...)]` is a chained
    `elif` — recurse and emit its arm as `kind:"elif"`, rather than an
    `else { if }`. A non-If `orelse` is a real `else` arm spanning
    `(orelse[0].lineno, orelse[-1].end_lineno)`.
- Only descend into the target function's own body (its nested defs /
  comprehensions have their own code objects and were never traced line-by-line
  — spec parity with the tracer's frame-scoping, `_capture_driver.py:256`).

Degradation: a `SyntaxError`, a missing file, or any unexpected shape returns
`[]` — the feature is invisible rather than wrong. This mirrors how the whole
playground fails open to an honest note rather than a broken widget.

## 6. taken / not-taken / unknown — the honesty rule

```
executed = { s.line for s in trace if s.line }   # raise sentinel line==0 excluded
for each arm with body span (lo, hi):
    hit = any(lo <= L <= hi for L in executed)
    if hit:            taken = True
    elif truncated:    taken = None     # unknown — the trace was cut short
    else:              taken = False
```

`truncated` is the existing `StepThroughResponse.truncated` (steps-cap or
wall-clock overrun, `_capture_driver.py:258-265`). **When the trace was
truncated, an arm with no executed lines is `unknown`, never `not-taken`.**
Claiming "this branch did not run" over a trace that stopped early would be
exactly the overclaim the product forbids. The tri-state is the whole point of
the feature being on-brand, not a nicety.

The `line == 0` raise sentinel (a raise before the body ran,
`_capture_driver.py:294`/`:389`) is excluded from `executed` so it can never
falsely mark an arm taken.

## 7. Nesting policy (no special-casing)

Nesting falls out of §6 for free. If an inner `if` sits inside an arm that was
not taken (or unknown), its own body lines were never executed either, so its
arms compute to `false` / `unknown` correctly. In the render (§8), a junction
whose `test_line` lands inside a dimmed (not-taken/unknown) range does **not**
draw a chip — it is inside dead code for this run. No depth limit, no
special-case branch: one classification rule handles the whole tree.

## 8. Render in the Stepper

A **static** overlay on the source pane the Stepper already renders
(`Stepper.tsx:152-157` via `lineModels`, `trace.ts:30`). Each source line gets a
junction role derived once from `junctions`:

- **Taken arm:** normal styling. The current-step highlight slab
  (`Stepper.tsx:146`) still rides on top independently — no conflict.
- **Not-taken arm (`taken:false`):** dimmed (e.g. reduced opacity / `--ink-4`)
  — dead code *for this run*.
- **Unknown arm (`taken:null`):** dimmed with a distinct tint, so "we can't say"
  never looks like "it didn't run".
- **Chip on `test_line`:** a small gutter marker naming the crossed arm
  (`→ if`, `→ else`). Computed value, no prose. Suppressed when the test line
  is itself inside a dimmed range (§7).

Implementation seam: extend `lineModels` (or add a sibling that consumes
`junctions`) to tag each `LineModel` with `role: 'taken' | 'dim-not-taken' |
'dim-unknown' | undefined`; the render maps role → style. The exact colors and
chip glyph are an implementation-time polish detail, not a contract decision.

Degradation in the UI:
- `junctions` absent or `[]` → Stepper identical to today (feature invisible).
- `staleAnchor` (source moved, line not found, `Stepper.tsx:57`) → suppress the
  overlay entirely, same principle the current highlight already uses.

## 9. Files touched

Backend:
- `src/copyclip/intelligence/cuaderno/junctions.py` — **new**, pure
  `compute_junctions` + AST walk + tri-state classification.
- `src/copyclip/intelligence/capture.py` — add `junctions` to
  `StepThroughResponse` and its `.to_dict()` (:233, :245).
- `src/copyclip/intelligence/playground.py` — call `compute_junctions` on the
  cuaderno step-through path and thread it into the response (:602/:625). Read
  the target source for the AST parse.

Frontend:
- `frontend/src/types/api.ts` — add `Junction` type and optional `junctions` on
  `StepThroughResponse` (:678).
- `frontend/src/components/cuaderno/stepper/trace.ts` — junction-role tagging in
  / alongside `lineModels` (:30).
- `frontend/src/components/cuaderno/stepper/Stepper.tsx` — apply the role styling
  and render the test-line chip (:144-159).

## 10. Testing strategy

- **Core (pure, no LLM, no subprocess) — the risky, deterministic logic:**
  `compute_junctions` over hand-built sources:
  - simple `if` (taken then; else absent);
  - `if` / `else` (each arm taken in separate cases);
  - `if` / `elif` / `else` chain (elif emitted as `kind:"elif"`, not nested else);
  - nested `if` inside a not-taken arm → inner arms `false`, chip suppressed;
  - `truncated=True` with an unexecuted arm → `taken:null` (the honesty rule);
  - function with no `if` → `[]`;
  - unresolvable target / `SyntaxError` → `[]`.
- **Frontend:** one overlay test over a `StepThroughResponse` fixture — taken
  normal, not-taken dimmed, unknown tinted, chip on `test_line`, and overlay
  suppressed under `staleAnchor`.
- **No change** to existing step-through / capture tests: `junctions` is additive
  and optional.

## 11. Non-goals

- No new capture mechanism, subprocess, or tracer change — reads the existing
  trace only.
- No prose, no narration, no advice — a structural overlay only (roadmap #146).
- No loops / try-except / ternary / match in v0.1 (§2, deferred to real cases).
- No cross-file or whole-program branch analysis — the target function only.
