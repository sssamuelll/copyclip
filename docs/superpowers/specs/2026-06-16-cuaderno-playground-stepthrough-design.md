# Anchored Playground → Guided Step-Through — Design Spec

**Date**: 2026-06-16
**Status**: Approved for spec (brainstorm complete; UI/UX delegated to the design team — see the companion `2026-06-16-cuaderno-playground-stepthrough-uiux-brief.md`)
**Relationship**: Deepens the Anchored Playground (`2026-05-22-anchored-playground-design.md`). For **non-cuaderno** sources (atlas, debt_navigator, etc.) the engine (Marimo), the embedding (iframe), and the spawn-on-demand model are **unchanged**. For the **cuaderno step-through**, this spec adds a *captured execution trace* and renders it in the React frontend (see the update note below). It extends the launch contract from a bare `function_ref` to a *call descriptor*.

## 0. Update 2026-06-16 — design handoff + render-location decision

The design team delivered a pixel-perfect, interactive prototype (`2026-06-16-cuaderno-playground-stepthrough-handoff/Cuaderno Step-Through.dc.html` — the **source of truth** for the frontend). Two consequences supersede the original §8 plan:

1. **The step-through renders in our React frontend, not inside Marimo.** The prototype is already React-shaped (inline styles, state, event handlers) using the exact `cuaderno.css` tokens, and its interactivity is **pure client-side replay over a static trace** (no re-execution while stepping). Rendering it pixel-perfect with Marimo-native primitives is impossible, and re-implementing it as an `anywidget` inside Marimo's page chrome is strictly harder than rendering React-in-React. So Approach B's "render inside the Marimo notebook" and the v1.5 "Approach C anywidget" are **both dropped** in favor of a third shape: **a capture-only subprocess + a native React renderer.**
2. **For the cuaderno step-through, the subprocess captures and the launch endpoint returns the trace JSON — not an `iframe_url`.** The subprocess's only job becomes running our bounded `sys.settrace` capture driver under the caps and emitting the trace. No iframe is mounted for the stepping view. The **fallback** (input→output box) and **all other playground sources** keep the existing Marimo-iframe path unchanged.

Everything else (record-then-replay, the call descriptor, preview-then-confirm, the caps, license hygiene, the honest degradations) stands. §8 and §9 below are rewritten to match; §4 gains the new response shape.

### Three implementation decisions (ratified 2026-06-16, after a roster panel)

A drafted plan was cross-checked; three decisions surfaced and were ratified. The roster's standing rule — *ship less, own what you ship, record the reversals* — is honored by amending the affected sections on the record here:

1. **Capture mechanism = a hand-rolled bounded `sys.settrace` callback; `json-tracer` is dropped (reverses §5).** Because the caps must live *inside* our own frame callback regardless, and because we emit our own `Step`/`Var` schema (not Python Tutor's heap-graph shape), `json-tracer` would be an imported-but-never-called dependency. The license rule (never copy Online Python Tutor source) is satisfied by not copying it. §5 is rewritten accordingly. *(Roster: Halberg, Stride, Vex for; Serrano preferred keeping it but required the reversal be recorded deliberately — done here.)*
2. **The editable call is free-text, executed in the module namespace on confirm (amends §10).** Faithful to the handoff's textarea. This introduces a second, deliberately-authorized consent path distinct from the model-proposed descriptor; §10 is amended to declare it (the alternative would be a silent §10 contradiction — a blocker). *(Roster split: Stride + Tane for free-text; Halberg preferred structured-args; Vex preferred no-edit. Owner chose free-text.)*
3. **Loop folding is descoped to v1.1; change-markers + "next change" stay (corrects §9).** The flat `Step[]` carries no iteration identity, so the fold-bands have no data producer — they would be UI tested only against a fake fixture. Markers + next-change run end-to-end off the real schema and keep a 600-step trace navigable. *(Roster: unanimous 5/5.)*

---

## 1. Why

The Anchored Playground's stated wedge (2026-05-22, line 16) is *"going from reading a function to understanding what it actually does."* Today, on a cuaderno run-request, the generated Marimo notebook is a **reactive input→output box plus a collapsed source accordion** (`src/copyclip/intelligence/playground.py:339-392`). It renders `name(value) → result` — the **externally observable** behavior at the function boundary. It never shows the **internally observable** behavior: the state trajectory *inside* the function. That inner behavior is the actual subject of the "hardest cognitive jump," and it is the half of the wedge that was never built. The product owner's report that the widget "still isn't clear" is the architecture reporting it shipped the easy half of its own thesis.

This spec adds a **guided step-through**: capture one real execution of the anchored function, then let the developer walk it step by step with the live state visible at each step.

## 2. The governing decision: record-then-replay, not a live debugger

A **step-through visualizer** is a *reader over a recording*: the trace is captured once, then scrubbed (forward and back, instantly). A **debugger** is a *controller over a live process*: stateful, socket-backed, it owns the program counter and negotiates step/continue/breakpoint as a dialogue.

These are ontologically distinct artifacts. Only the second collides with the locked non-goal *"NOT a general-purpose debugger"* (2026-05-22, line 22), because only the second asserts control authority over a running process and lets the user step *out* of the anchored function into arbitrary library frames — dissolving the anchor. A replay of a pre-scoped trace stays anchored by construction.

**Decision: record-then-replay.** It is the only model that respects every locked constraint at once — one spawn-and-kill Marimo subprocess, no DAP socket, no kernel pool, no event loop, instant back/forward, all behind the iframe.

**Non-goal carve-out (record this against the 2026-05-22 spec).** A recorded step-through is a *reader* and is in-scope; the non-goal renounces becoming a tool the user *drives* (a live debugger), not showing the user what their code *did*. Reviewers must not read this as scope-creep toward a debugger.

**Reopened locked decision (record this deliberately).** The 2026-05-22 spec, line 299, set *"v1: pass-through whatever the connector provides. Don't generate."* This spec **reopens that decision on purpose**: the cuaderno already runs an LLM that located the symbol this turn, so it now also proposes the example call. This is not a new model — it is one more field in the descriptor the cuaderno already emits.

## 3. Scope

**In scope (v1):**
- A line-level captured trace of one anchored function, captured by a subprocess and rendered pixel-perfect as a step-through in the React frontend (per the 2026-06-16 design handoff).
- The cuaderno's model proposes a **complete call** (positional args + kwargs, and constructor args for methods).
- A **preview-then-confirm** run model: the proposed call is shown (editable) before any real code runs.
- Hard capture bounds (steps, value size/time) and graceful fallback.

**Out of scope (named, not promised):**
- **Dropped — Approach C (`anywidget` inside Marimo):** the §0 decision renders in React directly, so there is no `anywidget`/Marimo renderer path anymore. The trace-JSON seam now sits between the capture subprocess and the React frontend.
- **Deferred — Approach D:** expression-level capture (birdseye-style AST instrumentation) for per-sub-expression / per-loop-iteration values and true on-source hover. Build only if line-level proves insufficient. Carries the risk that AST rewriting subtly alters recursion/generator/async behavior. (The design's value `kind` model already leaves room for this — it is additive on the same `Var` shape.)
- **v3 drawer — Approach E:** live stepping (debugpy/DAP). Requires a process-model redesign of `marimo_runner.py` and drifts into the non-goal.
- Free-form notebook editing, multi-language, saved snippets, kernel pooling — all remain out per 2026-05-22.

## 4. The contract extension: `function_ref` → call descriptor

Today the launch request carries a `function_ref` and the generator always emits a single-positional `fn(value)` (`playground.py:372,458`); methods emit `Foo(...).method(value)` with a literal `Ellipsis` instance (`playground.py:449-452`), which a tracer would execute into a constructor crash. To trace real methods and multi-arg functions, the cuaderno emits a **call descriptor**.

### Wire shape (additive; the existing `function_ref` stays for back-compat)

```typescript
type CallDescriptor = {
  function_ref: FunctionRef;          // unchanged: file, name, line?, qualname?
  // The model's proposed invocation. All values are JSON-serializable literals.
  args?: unknown[];                   // positional args
  kwargs?: Record<string, unknown>;   // keyword args
  ctor?: { args?: unknown[]; kwargs?: Record<string, unknown> }; // for methods: how to build the instance
};
```

- The generator builds the full invocation from the descriptor:
  - plain function → `fn(*args, **kwargs)`
  - method → `Foo(*ctor.args, **ctor.kwargs).method(*args, **kwargs)`
- **Validation:** every value remains injection-guarded. Args/kwargs are injected as `repr()` literals (never raw source), the same discipline `FunctionRef.from_dict` already applies to identifiers and paths (`playground.py:86-127`). Reject non-JSON-serializable proposals at the bridge with a `400 invalid_call_descriptor`.
- **Eligibility gate (server-side):** if the descriptor cannot form a runnable call (missing required args the model didn't supply, a constructor that needs un-proposable arguments), the bridge declines the step-through and the frontend falls back to today's reactive box (§7).

## 5. Capture (hand-rolled bounded tracer — §0 decision 1)

- **Tracer:** a **hand-rolled bounded `sys.settrace` callback** in a dedicated capture driver, emitting our `Step`/`Var` schema (§9) directly. The four dispatch events map straight through: `call` → the call step, `line` → a line step, `return` → the return step, `exception` → the `raise` terminal step. **Frame-scoping:** the callback only records frames whose `f_code` belongs to the target function (and, for a method, its class) — it does **not** descend into stdlib / third-party / C-extension frames, which is exactly the "library calls appear as one step" honesty of §7.
- **License hygiene (hard rule, unchanged):** the trace *shape* is our own; **never** copy `pg_logger.py` / `ExecutionVisualizer` / any Online Python Tutor source (the umbrella `pgbovine` repo is GPLv3, original deleted 2020). We do not depend on `json-tracer` — it was dropped (§0 decision 1) because we emit our own schema and caps live inside our callback regardless.
- **Where capture runs:** a dedicated capture subprocess (`python -m <capture_driver>` in the user's real env) imports the user's module, builds the invocation from the call descriptor (or the user's edited free-text call, §6), runs it once under the bounded callback, and emits the trace. The endpoint blocks on it, bounded by `MAX_STEPS` + the wall-clock guard (no Marimo healthcheck to fight on this path).

### Bounds (acceptance criteria, NOT follow-ups)

The capture runs the user's real, possibly-unbounded-loop code with no sandbox. Without bounds it hangs or OOMs — strictly worse than today's instant box. Therefore, enforced **inside the frame callback**:

1. **`MAX_STEPS`** (default ~1000, where Online Python Tutor breaks). On hit, capture aborts and emits a **truncated** trace flagged `truncated: true`. The abort must complete well under the launch healthcheck window.
2. **Per-value `repr` size cap** (`cheap_repr`-style): large objects are recorded as a summary (`list[5000]`, `DataFrame[1000×12]`) with the full value available lazily, never fully serialized inline.
3. **Per-value `repr` time cap / `try-except`:** a `__repr__` that blocks or raises must not hang or crash the serializer (verified failure mode). Wrap every `repr` in `try/except` + a time budget.
4. **Skip-list for dangerous-to-repr types:** file handles, sockets, DB sessions, lazy ORM proxies that hit the network on attribute access — rendered as an opaque type tag, never `repr`'d.
5. **Wall-clock guard** on the whole capture.

### Immutability

The captured trace is **immutable per launch**. Replaying (stepping forward/back) never re-runs code. Re-capturing (because the user edited the proposed call) is an explicit new run.

## 6. Run model: preview-then-confirm

The example call is **model-generated** and executes **real code with possible side effects** (writes, network, DB — same trust boundary as `pytest`, no sandbox, per 2026-05-22 line 260). Therefore the call is **shown before it runs**:

1. The widget renders the **real** model-proposed invocation, e.g. `resolve_function_ref(conn, 42, ref)`, in a **free-text, editable** field (the handoff's textarea — §0 decision 2).
2. A single explicit affordance (`[Recorrer]` / `[Step through]`) triggers capture.
3. Editing the call and re-confirming triggers a fresh capture (the only gesture that re-runs real code). The **edited free text is executed in the module namespace** (REPL-like) — see §10 for why this is an authorized second consent path, not a §10 violation.

This resolves two risks at once: the user sees what real code will run before it touches disk/network, and can correct an unrepresentative model-proposed input. The model's proposal must reach the widget as a real call descriptor (the floor/prompts emit it; §4), so step 1 shows the actual invocation, never a placeholder.

## 7. Eligibility and honest degradations

The step-through must not pretend to do what it cannot:

- **Methods / multi-arg functions:** now eligible, because the model proposes constructor args + call args (§4). If the proposal can't form a runnable call, **decline → fall back** to the existing reactive box with a note.
- **Async / generator functions:** **declined in v1 → fall back** to the reactive box. A linear step scrubber cannot honestly represent coroutine suspend/resume/await interleaving, and capturing an async function inside Marimo's own event loop is fragile.
- **C-extension frames are invisible to `sys.settrace`.** numpy / pandas / pydantic-core / torch internals appear as a **single step**. The walkthrough is honest only for pure-Python logic. The UI copy must say so: *"steps through your Python; library calls appear as one step."* Approach D (AST) shares this blind spot — it does not remove the limitation.
- **Capture raised:** if the function raises with the chosen input, that is a **rendered terminal step** ("here it threw: `KeyError: 'x'`"), not a launch failure — the trace up to the exception is still valuable.
- **Stale anchor:** if source changed since analysis, line highlights can land on the wrong lines (a pre-existing open question, 2026-05-22 line 298). Out of scope to fully solve here; flag for the plan.

## 8. Rendering (v1, React frontend, pixel-perfect from the handoff)

The step-through renders in the **React frontend**, pixel-perfect against `2026-06-16-cuaderno-playground-stepthrough-handoff/Cuaderno Step-Through.dc.html` (the source of truth). The capture subprocess returns the trace JSON (§9); React renders and scrubs it **fully client-side** (no re-execution, no server round-trip per step — the prototype's interaction model). New frontend surface, in `frontend/src/components/cuaderno/`:

- **Stepper** — source column (current line highlighted via the existing `.hl` / `--accent-soft` convention) beside the state panel, sharing one step index.
- **State panel** — every in-scope variable at the current step; *changed-this-step* gets `--accent` ink + a ◆ marker, *unchanged* dims to `--ink-4` (exact treatment in the handoff's `mkRow`).
- **Large-value chips** — type+shape (`dict · 3 keys`, `DataFrame · 1000×12`), expand-on-demand; **opaque** types render as a dashed `‹Type›` tag, never expanded.
- **Scrubber** — track with change-markers, prev/next, **"next change"** (jump to the next step where `changed` is non-empty), and folded loop-iteration bands for long traces.
- **Step counter** — "step N / M" (tabular-nums) in the widget head.
- **All states** from the handoff: Idle, Preview-call (editable), Spawning, Stepping, Truncated, Raised, Fallback, Ended/Evicted/Spawn-error.

Translate the handoff's inline styles to the existing token system; **add the two new tokens** `--neg` / `--neg-ink` (hue 30, the exception band) to `:root` and `.theme-dark` in `cuaderno.css`. The client-side step logic (`heroStep` / `heroTrack` / `heroNextChange`, `buildRows`, `lineModels`) is reimplemented in TypeScript from the handoff's `Component` class. Do **not** ship the handoff's `support.js` runtime — it is the design tool's, not ours.

### Launch response (cuaderno step-through)

For `source: "cuaderno"` with an eligible call descriptor, the endpoint returns the **trace** instead of an `iframe_url`:

```typescript
type StepThroughResponse = {
  kind: "trace";
  trace: Step[];          // §9
  source_lines: { num: number; text: string }[];  // the function's source, for the source column
  func_name: string;
  file_line: string;      // e.g. "intelligence/symbols.py:255"
  truncated: boolean;
};
type FallbackResponse = { kind: "fallback"; reason: string; iframe_url: string };  // the existing Marimo box
```

The frontend mounts the React stepper on `kind: "trace"`, or the existing iframe box on `kind: "fallback"`.

## 9. Trace schema — the seam (refined by the handoff's data model)

The capture↔render seam is the trace JSON. The design's `Component` class fixed its exact shape — capture (our bounded `sys.settrace` driver + the `repr`/summary layer) must emit this, and the React renderer consumes it verbatim:

```typescript
type Step = {
  line: number;
  event: "call" | "line" | "return" | "raise";
  changed: string[];            // var names that moved this step → sienna + ◆
  scope: Var[];                 // ALL in-scope vars at this step, in stable insertion order
  raised?: { type: string; message: string };  // present only on the final step if it threw
};

type Var = {
  name: string;
  kind: "scalar" | "object" | "opaque" | "large";
  text?: string;                // scalar / object: the (capped) repr
  label?: string;               // opaque: the type name only (skip-repr — never repr'd)
  summary?: string;             // large: "dict" | "DataFrame" | "list" | …
  meta?: string;                // large: "3 keys" | "1000×12" | "5,000 items"
  children?: { name: string; text: string }[];  // large: first-N expand-on-demand entries (capped at capture)
};
```

`changed` is **derived in normalization**, not emitted by the bare callback: the driver records `line`/`event`/`scope`, and the normalizer diffs each step's scope against the previous to fill `changed` (first-bind counts as changed; `opaque` values never flag). A test must assert this derivation matches the handoff's hand-authored `changed` for the canonical resolve-trace, so the two never silently diverge.

Notes that bind capture to the caps (§5): `kind:"large"` is how the per-value size cap surfaces (summary + capped `children`, never the full object); `kind:"opaque"` is how the dangerous-type skip-list surfaces (a `label`, no `repr`); a `raise` event with a `raised` payload is the terminal step when the function throws (§7).

The trace is a **flat `Step[]`**. The renderer derives **change-markers** (`changed.length > 0`) and **"next change"** entirely client-side from this flat shape — those are the long-trace navigation aids that ship. **Loop folding is NOT derivable from a flat stream** (it needs per-step loop-iteration identity the schema does not carry) — it is descoped to v1.1 (§0 decision 3). *(Handoff note: the handoff's loop fixture keys variable rows as `n`; the real schema key is `name`. Recorded so v1.1 does not rediscover it.)* The plan should decide whether capture writes a `trace.json` into the temp dir or streams it back inline in the response.

## 10. Security

Unchanged from 2026-05-22 §Security: real code, real env, **no sandbox**, loopback-only iframe, identifier/path injection guards. New surface:

- **Two authorized consent paths (§0 decision 2):**
  1. **Model-proposed descriptor:** the `args`/`kwargs`/`ctor` the *model* proposes are injected as `repr()` literals, **never raw source**. This guards against a malformed/garbled model proposal injecting code, and backs the `400 invalid_call_descriptor` rejection + serialization caps (§4).
  2. **User-edited free-text call:** when the *user* edits the call (§6) and confirms, that free text **is executed in the module namespace** (REPL-like). This is the user running **their own code** under the same `pytest`-equivalent trust boundary, gated by an explicit confirm. It is a deliberately distinct path from (1) — the repr-literal guard protects against the *model*, not against the *user editing their own call*. The free-text path must still respect all capture caps (§5) and is never auto-run (only on explicit confirm).
- The capture runs real code **once per confirmed call** — the preview-then-confirm gate (§6) is the user's informed consent, and the launch copy carries the `pytest`-equivalent trust statement.
- `MAX_STEPS` abort can leave a side effect half-applied; the trust statement must say the run is real and one-shot.
- **Process-group kill:** a hung capture must die cleanly on close. Adopt `CREATE_NEW_PROCESS_GROUP` (Windows) / `start_new_session` (POSIX) so the whole process tree is reclaimed; today `_best_effort_kill` (`marimo_runner.py:318`) does not group-kill.

## 11. Open implementation questions (for the plan, not the design)

1. **Capture host:** a dedicated capture subprocess (`python -m <capture_driver>` in the user's env, returning the trace on stdout / via a temp `trace.json`) vs reusing `marimo_runner`'s spawn machinery as a one-shot. The endpoint blocks on capture; `MAX_STEPS` + wall-clock must bound it (no 10s healthcheck to fight now, but the request still shouldn't hang).
2. **Trace transport:** stream the trace inline in the JSON response vs write `trace.json` in a temp dir and return a path. Inline is simpler and avoids a file lifecycle; a file is reusable by future tooling. Either way the size cap (§5) must hold before it crosses to the browser.
3. **Frame-scoping edge cases:** the bounded callback records only frames owned by the target function's `f_code` (and its class for a method). Confirm this handles closures / nested `def`s / comprehensions sensibly (comprehensions get their own code object on some Python versions) and that the `call`→`return`/`exception` pairing stays balanced when the target calls into untraced library frames.
4. **Eligibility detection:** how the bridge decides a descriptor can't form a runnable call before spawning.
5. **Test coupling:** ~29 assertions in `tests/test_playground.py` are pinned to the exact template string. Reshaping the template rewrites most of them and adds capture/cap/truncation tests — this dominates the diff (Plumb's "M not S").

## 12. Acceptance criteria

- [ ] On a cuaderno run-request for an eligible function, the playground shows the model's proposed call (editable); on confirm the endpoint returns a trace and the **React stepper** scrubs it — current source line highlights, the state panel shows in-scope vars, changed values get sienna + ◆, large values are type+shape chips, opaque values are dashed tags.
- [ ] Methods and multi-arg functions trace when the model supplies constructor/keyword args; ineligible targets (async, generators, un-constructable) return `kind:"fallback"` and the frontend mounts the existing input→output box with a note — never a crash, never a constructor-crash trace.
- [ ] `MAX_STEPS`, per-value size+time caps, the dangerous-type skip-list, and the wall-clock guard are enforced **at capture**; a runaway-loop function produces a visibly truncated trace, not a hang. Tests prove the cap fires.
- [ ] The breadcrumb reads as a walkthrough, not "see the output" (§ UI/UX brief), and the launch point carries the one-shot real-code trust statement.
- [ ] No `pg_logger.py` / OPT source in the tree; the trace is produced by our own bounded `sys.settrace` driver (no `json-tracer` dependency). The handoff's `support.js` is not shipped.
- [ ] The trace JSON (§9) matches the shape the React renderer consumes; capture and render share that schema verbatim.
- [ ] The React stepper matches the design handoff pixel-perfect across all 8 states, light **and** dark; only the owned palette ships (the two new `--neg` tokens added to `cuaderno.css`).
- [ ] The cuaderno still emits a valid playground widget descriptor through the floor (`compositor.py` widget checks); the fallback path and other playground sources are unchanged; `pytest -q` passes.

## 13. References

- `2026-05-22-anchored-playground-design.md` — the parent contract (engine, embedding, bridge, security, non-goals).
- `2026-06-10-cuaderno-interaction-trace-design.md` — the developer debug-log trace (a *different* artifact: it logs the cuaderno pipeline, not the user's code execution). Do not conflate.
- **Design handoff (pixel-perfect source of truth):** `2026-06-16-cuaderno-playground-stepthrough-handoff/Cuaderno Step-Through.dc.html` — all 8 states, the interactive stepping prototype, and the `Component` class that fixed the trace schema (§9) and the value-kind treatment (§8). `support.js` is the design tool's runtime (reference only — not shipped).
- Current code: `playground.py` (template `:339`, method ellipsis `:449-452`, input element `:461-492`, resolver `:255`, run mode `:536`), `intelligence/cuaderno/compositor.py` (floor + breadcrumb `:156-164`), `marimo_runner.py` (kill `:318`, healthcheck), `PlaygroundWidget.tsx` (chrome + live-context band), `frontend/src/styles/cuaderno.css` (tokens — add `--neg`/`--neg-ink`), `tests/test_playground.py` (template-pinned assertions).
- OSS: **none adopted as a runtime dependency** — capture is our own bounded `sys.settrace` callback (§0 decision 1; `json-tracer` was dropped). Reference-only: Online Python Tutor (the trace-shape *idea*, contested-GPL — never lift), nbtutor (BSD, prior art), Thonny (MIT, UX bar), `json-tracer` (MIT, confirmed our schema/caps approach but we don't import it). Deferred: `birdseye` (MIT, Approach D), `debugpy` (MIT, v3 live stepping). (`anywidget` / `@observablehq/inspector` are not on the path — we render in React; see §0.)
