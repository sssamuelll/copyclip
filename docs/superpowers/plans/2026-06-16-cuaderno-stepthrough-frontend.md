# Cuaderno Step-Through (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a pixel-perfect React step-through stepper that consumes a captured execution trace and renders all 8 playground states (Idle, Preview-call, Spawning, Stepping, Truncated, Raised, Fallback, Ended/Evicted/Spawn-error) against the design handoff, light and dark.

**Architecture:** The launch endpoint returns either `StepThroughResponse {kind:"trace"}` (the React stepper, fully client-side replay over a static `Step[]`) or `FallbackResponse {kind:"fallback"}` (the existing Marimo iframe box). The slot store (`playgroundSlot.ts`) gains a third terminal shape that carries the trace; `PlaygroundWidget.tsx` dispatches to the new `<Stepper>` on a trace and to the existing iframe path on a fallback. Stepping logic (`heroStep`/`heroTrack`/`heroNextChange`, `buildRows`, `lineModels`, `mkRow`) is reimplemented in pure TypeScript from the handoff's `Component` class — no design-tool `support.js` ships.

**Three ratified decisions (spec §0/§5/§6/§9/§10) this plan honors:**
- **D1 — capture is a hand-rolled bounded `sys.settrace` callback (backend).** `json-tracer` is dropped. The frontend only consumes the emitted `Step[]`/`Var` schema verbatim; nothing in this plan references json-tracer.
- **D2 — the editable call is FREE-TEXT, exec'd in the module namespace on confirm.** The Preview-call state is a free-text `textarea` (handoff state 02, lines 288–318); the **real** model-proposed call comes from `PlaygroundWidgetData.call` (a `CallDescriptor` emitted by the floor/prompts) and is rendered as the actual invocation — never a fake `name(…)` placeholder. On confirm, the (possibly edited) call text is passed through `launch` to the backend, which now accepts a free-text call override (spec §6/§10).
- **D3 — loop folding is descoped to v1.1.** Change-markers + "next change" stay (both run off the flat `Step[]`). The dead fold UI (loop fixtures, fold-bands, fold chip, hatched-band markup, `foldLabel`) is **not** ported. The flat `Step[]` schema is unchanged.

**Tech Stack:** React 18 + TypeScript + Vite. Test runner: **none exists** (`frontend/package.json` has no test script; the only `*.test.*` files are inside `node_modules`). Task 1 sets up **vitest + @testing-library/react + jsdom** (Vite-native). Every *behavioral* step (stepping, next-change, expand large value, fallback mount, preview edit→re-capture, slot dispatch, call-id recovery) has a real component/behavior test against the detected runner. Pixel-fidelity is the one explicitly-manual checklist task (Task 11), because it cannot be unit-tested.

---

## File Structure

**Created:**
- `frontend/vitest.config.ts` — vitest config (jsdom env, globals, setup file). One responsibility: wire the test runner to the existing Vite/React toolchain.
- `frontend/src/test/setup.ts` — imports `@testing-library/jest-dom` matchers; one responsibility: test bootstrap.
- `frontend/src/components/cuaderno/stepper/trace.ts` — pure trace-replay engine reimplemented from the handoff `Component` (lines 789–839): `mkRow`, `buildRows`, `lineModels`, `clampStep`, `nextChange`, `trackFraction`, change-marker geometry. No React. One responsibility: the stepping math + per-kind row styling.
- `frontend/src/components/cuaderno/stepper/trace.test.ts` — unit tests for `trace.ts` (clamp, next-change wrap, build-rows expand, marker geometry, stale-anchor suppression).
- `frontend/src/components/cuaderno/stepper/Stepper.tsx` — the Stepping/Truncated/Raised view (source column + state panel + scrubber + counter); reads a `StepThroughResponse`. One responsibility: render + drive a captured trace.
- `frontend/src/components/cuaderno/stepper/Stepper.test.tsx` — behavior tests for `<Stepper>` (scrub, next-change, expand large value, raised banner, truncated banner+hatch, stale-anchor highlight suppression).
- `frontend/src/components/cuaderno/stepper/StateRow.tsx` — one state-panel row, dispatching by `Var.kind` (scalar/object/opaque/large) with expand-on-demand children. One responsibility: a single `name → value` row.
- `frontend/src/components/cuaderno/stepper/StateRow.test.tsx` — render/behavior tests for `StateRow` (scalar, opaque, large chip toggle, non-clickable object).
- `frontend/src/components/cuaderno/stepper/PreviewCall.tsx` — the Preview-call state (free-text editable call + Step through / Edit call / Cancel). One responsibility: the consent + correction moment.
- `frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx` — behavior tests for edit toggle + confirm-with-edited-text/cancel callbacks.
- `frontend/src/components/cuaderno/stepper/Spawning.tsx` — the "preparing…" sweep state (no counter, no close button). One responsibility: the capture-in-progress view.
- `frontend/src/components/cuaderno/stepper/IdleInvitation.tsx` — the Idle invitation state (anchored fn + "Step through →"). One responsibility: the invite.
- `frontend/src/components/cuaderno/stepper/EndedCards.tsx` — the Ended/Evicted/Spawn-error trio (the single coherent card the slot is in). One responsibility: terminal-state cards.
- `frontend/src/components/cuaderno/playgroundSlot.test.ts` — slot-store tests (trace vs fallback dispatch, no-poll on trace, stale-token discard, `idFromIframeUrl` recovery format).
- `frontend/src/components/cuaderno/strings.test.ts` — string lookup + en-fallback test.
- `frontend/src/components/cuaderno/widgets/PlaygroundWidget.test.tsx` — integration tests (idle → preview → stepper; fallback mounts iframe; the edited free-text call reaches `launch`).

**Modified:**
- `frontend/src/styles/cuaderno.css` — add `--neg`/`--neg-ink`/`--neg-line` to `:root` (after line 26) and `.theme-dark` (after line 60); add the `.stepper-*` style rules at the end of the playground region (after line 1119). One responsibility: design tokens + stepper styles.
- `frontend/src/types/api.ts` — add `Step`, `Var`, `CallDescriptor`, `StepThroughResponse`, `FallbackResponse`, `PlaygroundLaunchResult`; widen `PlaygroundLaunchRequest` with `call?: CallDescriptor` and `call_text?: string`; widen `PlaygroundWidgetData` with `call?: CallDescriptor` and `call_text?: string`. One responsibility: the capture↔render seam types.
- `frontend/src/api/client.ts` — change `launchPlayground` return type to `PlaygroundLaunchResult` (the union). One responsibility: typed client.
- `frontend/src/components/cuaderno/playgroundSlot.ts` — add a `'trace'` slot kind carrying the `StepThroughResponse`; `launch` dispatches on `res.kind`; only `fallback` polls; recover the playground id from `FallbackResponse.iframe_url` via a tested `idFromIframeUrl`. One responsibility: slot state machine.
- `frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx` — render Idle → PreviewCall → Spawning → (Stepper | iframe box | EndedCards) by slot kind; build the real proposed call from `widget.call` / `widget.call_text`; pass the edited free text through `launch`. One responsibility: state dispatch + chrome.
- `frontend/src/components/cuaderno/strings.ts` — add bilingual step-through copy keys. One responsibility: i18n strings.

---

### Task 1: Set up the frontend test runner (vitest + testing-library)

**Files:**
- `frontend/package.json` (modify — scripts + devDependencies)
- `frontend/vitest.config.ts` (create)
- `frontend/src/test/setup.ts` (create)
- `frontend/src/test/smoke.test.tsx` (create, temporary)

- [ ] **Step 1: Install the test toolchain.** Run:
  ```bash
  cd frontend && npm install -D vitest@^2.1.0 @testing-library/react@^16.0.0 @testing-library/jest-dom@^6.5.0 @testing-library/user-event@^14.5.0 jsdom@^25.0.0
  ```
  Then add a `"test": "vitest run"` and `"test:watch": "vitest"` to `scripts` in `frontend/package.json`.

- [ ] **Step 2: Create the vitest config.** Write `frontend/vitest.config.ts`:
  ```ts
  import { defineConfig } from 'vitest/config'
  import react from '@vitejs/plugin-react'

  export default defineConfig({
    plugins: [react()],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
    },
  })
  ```

- [ ] **Step 3: Create the test setup file.** Write `frontend/src/test/setup.ts`:
  ```ts
  import '@testing-library/jest-dom/vitest'
  ```

- [ ] **Step 4: Write a smoke test (expected to FAIL until deps install, then PASS).** Write `frontend/src/test/smoke.test.tsx`:
  ```tsx
  import { render, screen } from '@testing-library/react'
  import { describe, it, expect } from 'vitest'

  describe('test runner', () => {
    it('renders a React element', () => {
      render(<button>hello</button>)
      expect(screen.getByRole('button', { name: 'hello' })).toBeInTheDocument()
    })
  })
  ```

- [ ] **Step 5: Run the smoke test (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/test/smoke.test.tsx
  ```
  Expect: `1 passed`. If it fails on JSX/TSX, confirm `tsconfig.app.json` has `"jsx": "react-jsx"` (it does — Vite default).

- [ ] **Step 6: Delete the smoke test and commit.** Remove `frontend/src/test/smoke.test.tsx`, then:
  ```bash
  cd frontend && git add package.json package-lock.json vitest.config.ts src/test/setup.ts && git commit -m "$(cat <<'EOF'
  test(cuaderno): set up vitest + testing-library for frontend

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 2: Add the `--neg`/`--neg-ink`/`--neg-line` design tokens

**Files:**
- `frontend/src/styles/cuaderno.css` (modify — `:root` after line 26; `.theme-dark` after line 60)

- [ ] **Step 1: Add the negative-band tokens to `:root`.** In `frontend/src/styles/cuaderno.css`, immediately after the `--accent-2` line in `:root` (line 26), insert:
  ```css

  /* negative band — exception state only (hue 30, the rare "it threw" ink) */
  --neg:      oklch(0.56 0.13 30 / 0.12);
  --neg-ink:  oklch(0.46 0.12 30);
  --neg-line: oklch(0.56 0.13 30 / 0.34);
  ```

- [ ] **Step 2: Add the negative-band tokens to `.theme-dark`.** In the `.theme-dark` block, immediately after the `--accent-2` line (line 60), insert:
  ```css

  --neg:      oklch(0.60 0.13 30 / 0.20);
  --neg-ink:  oklch(0.74 0.12 30);
  --neg-line: oklch(0.60 0.13 30 / 0.34);
  ```
  (These match the handoff light figure at lines 96 / 402 and dark figure at line 177 exactly.)

- [ ] **Step 3: Verify the build still compiles.** Run:
  ```bash
  cd frontend && npx vite build
  ```
  Expect: build succeeds (CSS is not type-checked; this just confirms no syntax error). No unit test — these are CSS variables; their use is verified by the manual pixel checklist in Task 11.

- [ ] **Step 4: Commit.**
  ```bash
  cd frontend && git add src/styles/cuaderno.css && git commit -m "$(cat <<'EOF'
  feat(cuaderno): add --neg/--neg-ink/--neg-line tokens for the exception band

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3: Add the trace seam types + widen the launch + widget contracts

**Files:**
- `frontend/src/types/api.ts` (modify — add after `PlaygroundLaunchResponse` at line 646; widen `PlaygroundLaunchRequest` at line 635; widen `PlaygroundWidgetData`)
- `frontend/src/api/client.ts` (modify — `launchPlayground` at line 180–181; import at line 1)

The wire types (`Step`/`Var`/`StepThroughResponse`/`FallbackResponse`/`CallDescriptor`) match the backend emitter **exactly** (spec §4, §8, §9). Do not reshape them. `FallbackResponse` is `{kind, reason, iframe_url}` per spec §8 — it carries **no** `playground_id`; Task 4 recovers the id from `iframe_url`.

- [ ] **Step 1: Add the trace schema + response union types.** In `frontend/src/types/api.ts`, after the `PlaygroundLaunchResponse` block (line 646), insert:
  ```ts

  // --- Cuaderno step-through (capture↔render seam, design spec §9) ---------

  export type Var = {
    name: string
    kind: 'scalar' | 'object' | 'opaque' | 'large'
    text?: string                       // scalar/object: capped repr
    label?: string                      // opaque: type name only (never repr'd)
    summary?: string                    // large: "dict" | "DataFrame" | "list" | ...
    meta?: string                       // large: "3 keys" | "1000×12" | "5,000 items"
    children?: { name: string; text: string }[]  // large: first-N expand entries
  }

  export type Step = {
    line: number
    event: 'call' | 'line' | 'return' | 'raise'
    changed: string[]                   // var names that moved this step
    scope: Var[]                        // ALL in-scope vars, stable insertion order
    raised?: { type: string; message: string }  // only on the final step if it threw
  }

  // The model's proposed invocation (spec §4). The backend emits this through
  // the floor/prompts so the widget can render the REAL call, not a placeholder.
  export type CallDescriptor = {
    function_ref: FunctionRef
    args?: unknown[]
    kwargs?: Record<string, unknown>
    ctor?: { args?: unknown[]; kwargs?: Record<string, unknown> }
  }

  export type StepThroughResponse = {
    kind: 'trace'
    trace: Step[]
    source_lines: { num: number; text: string }[]
    func_name: string
    file_line: string                   // e.g. "intelligence/symbols.py:255"
    truncated: boolean
  }

  export type FallbackResponse = {
    kind: 'fallback'
    reason: string
    iframe_url: string                  // spec §8: no playground_id; id recovered from this
  }

  export type PlaygroundLaunchResult = StepThroughResponse | FallbackResponse
  ```

- [ ] **Step 2: Widen the launch request with the call descriptor + edited free text.** In `frontend/src/types/api.ts`, edit `PlaygroundLaunchRequest` (line 635) to add `call?` and `call_text?` after `breadcrumb`:
  ```ts
  export type PlaygroundLaunchRequest = {
    source: PlaygroundSource
    function_ref: FunctionRef
    deps_hint?: string[]
    suggested_inputs?: unknown[]
    breadcrumb: string
    call?: CallDescriptor              // the model's structured proposal (spec §4)
    call_text?: string                 // the user's edited free-text call (spec §6/§10, D2)
  }
  ```
  Both fields are optional and additive. `call` is the model's repr-literal-guarded descriptor; `call_text` is the user's free text exec'd in the module namespace on confirm — the backend now accepts it (D2). `CallDescriptor` is defined in Step 1, so this compiles.

- [ ] **Step 3: Widen `PlaygroundWidgetData` so the real proposed call reaches the widget.** Find `PlaygroundWidgetData` in `frontend/src/types/api.ts` and add the call carriers (the floor/prompts emit these — spec §6, D2):
  ```ts
    call?: CallDescriptor      // the model's structured proposed invocation
    call_text?: string         // the model's proposed invocation pre-rendered as source text
  ```
  Add them alongside the existing `function_ref`/`breadcrumb`/`citation`/`suggested_inputs` fields. Both optional, so existing widget payloads still type-check.

- [ ] **Step 4: Re-type `launchPlayground` to the union.** In `frontend/src/api/client.ts`, add `PlaygroundLaunchResult` to the type import on line 1, then change lines 180–181 to:
  ```ts
    launchPlayground: (req: PlaygroundLaunchRequest) =>
      postJSON<PlaygroundLaunchResult>('/api/playground/launch', req),
  ```
  (The legacy `PlaygroundLaunchResponse {playground_id, iframe_url}` type is now unused by this call but stays in `api.ts` for back-compat with the slot store's poll path; Task 4 reconciles the slot store.)

- [ ] **Step 5: Type-check (expected PASS).** Run:
  ```bash
  cd frontend && npx tsc -b
  ```
  Expect: no errors. No runtime test — these are type-only additions; their use is covered in Task 4+.

- [ ] **Step 6: Commit.**
  ```bash
  cd frontend && git add src/types/api.ts src/api/client.ts && git commit -m "$(cat <<'EOF'
  feat(cuaderno): trace seam types + free-text call on launch + widget call carriers

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4: Reshape the slot store for trace vs fallback (with tested id recovery)

**Files:**
- `frontend/src/components/cuaderno/playgroundSlot.ts` (modify — `SlotState` at line 4–8; `launch` at line 47–61; imports at line 1–2)
- `frontend/src/components/cuaderno/playgroundSlot.test.ts` (create)

The `FallbackResponse` carries `{kind, reason, iframe_url}` and **no** `playground_id` (spec §8). To close/reconcile the fallback Marimo box we must recover the id from `iframe_url`. The existing Marimo iframe URL format is `/playground/<id>` (the legacy `PlaygroundLaunchResponse.iframe_url` followed the same shape next to its `playground_id`). We pin that contract here: `idFromIframeUrl` takes the **last non-empty path segment**, stripping any query/hash. This is tested below, so there is no unresolved assumption — if the backend ever changes the URL shape, the `idFromIframeUrl` test fails loudly and pins the new format.

- [ ] **Step 1: Write failing tests for the new slot shape + id recovery.** Write `frontend/src/components/cuaderno/playgroundSlot.test.ts`:
  ```ts
  import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
  import type { StepThroughResponse, FallbackResponse } from '../../types/api'

  // Mock the api client BEFORE importing the module under test.
  const launchPlayground = vi.fn()
  const closePlayground = vi.fn(() => Promise.resolve({ ok: true }))
  const playgroundStatus = vi.fn()
  const playgroundList = vi.fn(() => Promise.resolve({ items: [] }))
  vi.mock('../../api/client', () => ({
    api: { launchPlayground, closePlayground, playgroundStatus, playgroundList },
  }))

  import { launch, getState, close, idFromIframeUrl } from './playgroundSlot'

  const TRACE: StepThroughResponse = {
    kind: 'trace',
    trace: [{ line: 255, event: 'call', changed: ['x'], scope: [{ name: 'x', kind: 'scalar', text: '1' }] }],
    source_lines: [{ num: 255, text: 'def f(x):' }],
    func_name: 'f',
    file_line: 'a.py:255',
    truncated: false,
  }
  const FALLBACK: FallbackResponse = { kind: 'fallback', reason: 'generator', iframe_url: '/playground/pg-42' }
  const req = { source: 'cuaderno' as const, function_ref: { file: 'a.py', name: 'f' }, breadcrumb: 'Step through f' }

  beforeEach(() => {
    launchPlayground.mockReset(); closePlayground.mockClear()
    playgroundStatus.mockReset(); close()
  })
  afterEach(() => vi.useRealTimers())

  describe('idFromIframeUrl', () => {
    it('recovers the playground id from the last path segment', () => {
      expect(idFromIframeUrl('/playground/pg-42')).toBe('pg-42')
      expect(idFromIframeUrl('http://127.0.0.1:8000/playground/abc?token=x#frag')).toBe('abc')
      expect(idFromIframeUrl('/playground/abc/')).toBe('abc')
    })
  })

  describe('playgroundSlot', () => {
    it('lands in the trace slot on a kind:"trace" response and does not poll', async () => {
      launchPlayground.mockResolvedValue(TRACE)
      await launch('a.py:f:', req)
      const s = getState()
      expect(s.kind).toBe('trace')
      if (s.kind === 'trace') {
        expect(s.response.func_name).toBe('f')
        expect(s.widgetKey).toBe('a.py:f:')
      }
      expect(closePlayground).not.toHaveBeenCalled()
    })

    it('lands in the live slot on a kind:"fallback" response', async () => {
      launchPlayground.mockResolvedValue(FALLBACK)
      await launch('a.py:f:', req)
      const s = getState()
      expect(s.kind).toBe('live')
      if (s.kind === 'live') {
        expect(s.iframeUrl).toBe('/playground/pg-42')
        expect(s.playgroundId).toBe('pg-42')   // recovered via idFromIframeUrl
      }
    })

    it('a stale launch (superseded token) discards a late trace response', async () => {
      let resolveFirst!: (v: StepThroughResponse) => void
      launchPlayground.mockReturnValueOnce(new Promise((r) => { resolveFirst = r }))
      launchPlayground.mockResolvedValueOnce(TRACE)
      const p1 = launch('a.py:f:', req)   // token 1, pending
      const p2 = launch('a.py:f:', req)   // token 2, resolves immediately
      await p2
      resolveFirst(TRACE)                  // token 1 resolves late
      await p1
      expect(getState().kind).toBe('trace') // token-2 result, not clobbered
    })

    it('a stale fallback closes the orphaned playground via the recovered id', async () => {
      let resolveFirst!: (v: FallbackResponse) => void
      launchPlayground.mockReturnValueOnce(new Promise((r) => { resolveFirst = r }))
      launchPlayground.mockResolvedValueOnce(TRACE)
      const p1 = launch('a.py:f:', req)
      const p2 = launch('a.py:f:', req)
      await p2
      resolveFirst(FALLBACK)               // late fallback for a dead token
      await p1
      expect(closePlayground).toHaveBeenCalledWith('pg-42')
    })
  })
  ```

- [ ] **Step 2: Run the tests (expected FAIL).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/playgroundSlot.test.ts
  ```
  Expect: FAIL — `idFromIframeUrl` is not exported, `kind 'trace'` is not in `SlotState`, and `launch` always sets `live` from `res.playground_id`.

- [ ] **Step 3: Implement the trace slot + dispatch + id recovery.** Edit `frontend/src/components/cuaderno/playgroundSlot.ts`:
  - Update imports (line 1–2):
    ```ts
    import { api } from '../../api/client'
    import type { PlaygroundLaunchRequest, StepThroughResponse } from '../../types/api'
    ```
  - Add the `'trace'` variant to `SlotState` (line 4–8):
    ```ts
    export type SlotState =
      | { kind: 'empty' }
      | { kind: 'spawning'; widgetKey: string; token: number }
      | { kind: 'live'; widgetKey: string; playgroundId: string; iframeUrl: string; token: number }
      | { kind: 'trace'; widgetKey: string; response: StepThroughResponse; token: number }
      | { kind: 'ended'; widgetKey: string; reason: 'closed' | 'evicted' | 'exited' | 'error'; message?: string }
    ```
  - Add the exported `idFromIframeUrl` helper near the top (after `getState`, ~line 17). The fallback `FallbackResponse` carries only `iframe_url` (spec §8); the Marimo box URL is `/playground/<id>`, so the id is the last non-empty path segment (query/hash stripped). Exported so the test pins the format:
    ```ts
    /** Recover the playground id from a fallback iframe_url ("/playground/<id>"). */
    export function idFromIframeUrl(url: string): string {
      const parts = url.split(/[/?#]/).filter(Boolean)
      return parts[parts.length - 1] ?? url
    }
    ```
  - Rewrite the body of `launch` (line 52–60, the `try` block) to dispatch on `res.kind`:
    ```ts
      try {
        const res = await api.launchPlayground(req)
        if (token !== myToken) {
          // late result for a superseded launch: a fallback spawned a real
          // playground we must reap; a trace has no subprocess.
          if (res.kind === 'fallback') api.closePlayground(idFromIframeUrl(res.iframe_url)).catch(() => {})
          return
        }
        if (res.kind === 'trace') {
          // capture-only: no subprocess to poll, the trace is immutable per launch
          set({ kind: 'trace', widgetKey, response: res, token: myToken })
        } else {
          const playgroundId = idFromIframeUrl(res.iframe_url)
          set({ kind: 'live', widgetKey, playgroundId, iframeUrl: res.iframe_url, token: myToken })
          startPoll(playgroundId, widgetKey, myToken)
        }
      } catch (e) {
        if (token !== myToken) return
        set({ kind: 'ended', widgetKey, reason: 'error', message: e instanceof Error ? e.message : String(e) })
      }
    ```

- [ ] **Step 4: Run the tests (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/playgroundSlot.test.ts
  ```
  Expect: `5 passed`.

- [ ] **Step 5: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/playgroundSlot.ts src/components/cuaderno/playgroundSlot.test.ts && git commit -m "$(cat <<'EOF'
  feat(cuaderno): slot store dispatches trace vs fallback; id recovered from iframe_url

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 5: The trace-replay engine (`trace.ts`) — pure TS port of the handoff `Component`

**Files:**
- `frontend/src/components/cuaderno/stepper/trace.ts` (create)
- `frontend/src/components/cuaderno/stepper/trace.test.ts` (create)

This is a 1:1 port of the handoff logic (handoff lines 789–839, 855–864). It is React-free and exhaustively unit-tested. Geometry constants are load-bearing: **row/line height = 26px**, hero handle `(step-1)/(total-1)*100%`, marker `i/(total-1)*100%`, slab top `curIdx*26`. **No loop-fold geometry is ported** (D3 — the flat `Step[]` carries no iteration identity; `foldBands`/`foldLabel`/`loopStops` are dead and omitted).

- [ ] **Step 1: Write failing tests for the engine.** Write `frontend/src/components/cuaderno/stepper/trace.test.ts`:
  ```ts
  import { describe, it, expect } from 'vitest'
  import type { Step, Var } from '../../../types/api'
  import { clampStep, nextChange, trackFraction, lineModels, buildRows, markerLefts } from './trace'

  const v = (name: string, kind: Var['kind'], extra: Partial<Var> = {}): Var => ({ name, kind, ...extra })

  // resolveTrace happy path (handoff 742–750): 9 steps, line 263 skipped.
  const TRACE: Step[] = [
    { line: 255, event: 'call', changed: ['conn', 'module_id', 'ref'], scope: [v('conn', 'opaque', { label: 'Connection' }), v('module_id', 'scalar', { text: '42' }), v('ref', 'large', { summary: 'FunctionRef', meta: '5 fields', children: [{ name: 'qualname', text: "'Foo.method'" }, { name: 'file', text: "'symbols.py'" }] })] },
    { line: 256, event: 'line', changed: ['qualname'], scope: [v('qualname', 'scalar', { text: "'Foo.method'" })] },
    { line: 257, event: 'line', changed: ['parent'], scope: [v('parent', 'scalar', { text: 'None' })] },
    { line: 258, event: 'line', changed: [], scope: [v('qualname', 'scalar', { text: "'Foo.method'" })] },
    { line: 259, event: 'line', changed: ['head', 'tail'], scope: [v('head', 'scalar', { text: "'Foo'" }), v('tail', 'scalar', { text: "'method'" })] },
    { line: 260, event: 'line', changed: ['parent'], scope: [v('parent', 'object', { text: "Symbol('Foo')" })] },
    { line: 261, event: 'line', changed: ['row'], scope: [v('row', 'large', { summary: 'dict', meta: '5 keys', children: [{ name: 'id', text: '91' }] })] },
    { line: 262, event: 'line', changed: [], scope: [v('row', 'large', { summary: 'dict', meta: '5 keys' })] },
    { line: 264, event: 'return', changed: ['return'], scope: [v('return', 'object', { text: "Symbol('Foo.method')" })] },
  ]
  const SRC = [255, 256, 257, 258, 259, 260, 261, 262, 263, 264].map((num) => ({ num, text: `line ${num}` }))

  describe('clampStep', () => {
    it('is 1-based and clamps to [1, len]', () => {
      expect(clampStep(0, 9)).toBe(1)
      expect(clampStep(5, 9)).toBe(5)
      expect(clampStep(99, 9)).toBe(9)
    })
  })

  describe('nextChange', () => {
    it('wraps modulo length, never lands on the current step', () => {
      // step 9 (return) -> next change wraps to step 1 (call)
      expect(nextChange(9, TRACE)).toBe(1)
    })
    it('skips no-change steps (258 has changed=[])', () => {
      // step 3 (line 257) -> step 5 (line 259), skipping step 4 (258, no change)
      expect(nextChange(3, TRACE)).toBe(5)
    })
  })

  describe('trackFraction', () => {
    it('maps a click fraction to a 1-based clamped step', () => {
      expect(trackFraction(0, 9)).toBe(1)
      expect(trackFraction(1, 9)).toBe(9)
      expect(trackFraction(0.5, 9)).toBe(5) // round(0.5*8)+1 = 5
    })
  })

  describe('lineModels', () => {
    it('marks the current source index with accent-ink + weight 700', () => {
      const models = lineModels(SRC, 0)
      expect(models[0].numStyle).toContain('var(--accent-ink)')
      expect(models[0].numStyle).toContain('font-weight:700')
      expect(models[1].numStyle).toContain('var(--ink-4)')
      expect(models[1].codeStyle).toContain('var(--ink-2)')
    })
    it('marks NO line when curIdx < 0 (stale anchor, spec §7)', () => {
      const models = lineModels(SRC, -1)
      models.forEach((m) => {
        expect(m.numStyle).toContain('var(--ink-4)')
        expect(m.numStyle).not.toContain('var(--accent-ink)')
      })
    })
  })

  describe('buildRows', () => {
    it('renders every scope var; only changed names get accent + visible diamond', () => {
      const rows = buildRows(TRACE[0], {})
      expect(rows.map((r) => r.name)).toEqual(['conn', 'module_id', 'ref'])
      expect(rows[1].dotStyle).toContain('opacity:1')      // module_id changed
      expect(rows[1].scalarStyle).toContain('var(--accent-ink)')
    })
    it('an unchanged var keeps the diamond in the DOM at opacity 0 (no reflow)', () => {
      const rows = buildRows(TRACE[3], {})  // changed=[]
      expect(rows[0].dotStyle).toContain('opacity:0')
    })
    it('expands a large var into non-changed scalar children at indent 1', () => {
      const rows = buildRows(TRACE[0], { ref: true })
      const names = rows.map((r) => r.name)
      expect(names).toEqual(['conn', 'module_id', 'ref', 'qualname', 'file'])
      const child = rows.find((r) => r.name === 'qualname')!
      expect(child.isScalar).toBe(true)
      expect(child.scalarStyle).toContain('var(--ink-3)') // forced changed:false
      expect(child.rowStyle).toContain('3.5px 0 3.5px 20px') // indent 1
    })
    it('opaque vars never reflect changed and render a label', () => {
      const rows = buildRows(TRACE[0], {})
      expect(rows[0].isOpaque).toBe(true)
      expect(rows[0].label).toBe('Connection')
    })
  })

  describe('markerLefts (hero geometry)', () => {
    it('emits a tick percent per change step at i/(total-1)*100', () => {
      const lefts = markerLefts(TRACE)
      expect(lefts[0]).toBeCloseTo(0)            // step 0 changed
      expect(lefts).not.toContain(3 / 8 * 100)   // step 3 (idx 3) has no change
      expect(lefts[lefts.length - 1]).toBeCloseTo(8 / 8 * 100) // step 8 changed
    })
  })
  ```

- [ ] **Step 2: Run the tests (expected FAIL).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/trace.test.ts
  ```
  Expect: FAIL — `./trace` does not exist.

- [ ] **Step 3: Implement the engine.** Write `frontend/src/components/cuaderno/stepper/trace.ts`:
  ```ts
  import type { Step, Var } from '../../../types/api'

  export const ROW_H = 26 // px — load-bearing: slab top = curIdx*ROW_H, line-height

  const clamp = (n: number, lo: number, hi: number) => Math.min(Math.max(n, lo), hi)

  // hero step is 1-based, clamped to [1, len]
  export function clampStep(step: number, len: number): number {
    return clamp(step, 1, Math.max(len, 1))
  }

  // wraps modulo len, starts at k=1 so it never lands on the current step (handoff 837–839)
  export function nextChange(cur: number, trace: Step[]): number {
    const len = trace.length
    for (let k = 1; k <= len; k++) {
      const i = (cur - 1 + k) % len
      if (trace[i].changed.length > 0) return i + 1
    }
    return cur
  }

  // click fraction (0..1) -> 1-based step (handoff 831–836)
  export function trackFraction(f: number, len: number): number {
    return clamp(Math.round(f * (len - 1)) + 1, 1, len)
  }

  export type LineModel = { num: number; code: string; numStyle: string; codeStyle: string }

  // curIdx < 0 (stale anchor, spec §7) marks NO line — the slab is suppressed by the caller.
  export function lineModels(
    src: { num: number; text: string }[],
    curIdx: number,
  ): LineModel[] {
    return src.map((l, i) => {
      const on = i === curIdx // never true when curIdx < 0
      return {
        num: l.num,
        code: l.text,
        numStyle: `flex:none;width:30px;text-align:right;padding-right:14px;font-variant-numeric:tabular-nums;color:${on ? 'var(--accent-ink)' : 'var(--ink-4)'};font-weight:${on ? '700' : '400'};`,
        codeStyle: `white-space:pre;color:${on ? 'var(--ink)' : 'var(--ink-2)'};transition:color .3s ease;`,
      }
    })
  }

  export type RowModel = {
    name: string
    isScalar: boolean; isOpaque: boolean; isLarge: boolean; isObject: boolean
    text: string; label: string; summary: string; meta: string
    caret: string
    expandable: boolean
    rowStyle: string; dotStyle: string; nameStyle: string; valWrap: string
    scalarStyle: string; objStyle: string; chipStyle: string
    metaStyle: string; caretStyle: string; opaqueStyle: string
  }

  // 1:1 with the handoff mkRow (789–810). `expanded` is the name->bool map.
  export function mkRow(
    name: string,
    def: Pick<Var, 'kind' | 'text' | 'label' | 'summary' | 'meta'>,
    changed: boolean,
    indent: number,
    expanded: Record<string, boolean>,
  ): RowModel {
    const exp = !!expanded[name]
    return {
      name,
      isScalar: def.kind === 'scalar', isOpaque: def.kind === 'opaque',
      isLarge: def.kind === 'large', isObject: def.kind === 'object',
      text: def.text || '', label: def.label || '', summary: def.summary || '', meta: def.meta || '',
      caret: exp ? '▾' : '▸',
      expandable: def.kind === 'large',
      rowStyle: `display:flex;align-items:baseline;gap:8px;padding:3.5px 0 3.5px ${indent ? 20 : 0}px;`,
      dotStyle: `flex:none;width:7px;text-align:center;color:var(--accent);opacity:${changed ? 1 : 0};font-size:8px;line-height:18px;`,
      nameStyle: `flex:none;color:${changed ? 'var(--ink-2)' : 'var(--ink-4)'};${indent ? 'opacity:.85;' : ''}`,
      valWrap: `flex:1;min-width:0;display:flex;justify-content:flex-end;align-items:baseline;`,
      scalarStyle: `color:${changed ? 'var(--accent-ink)' : 'var(--ink-3)'};font-weight:${changed ? '600' : '400'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:color .3s ease;`,
      objStyle: `color:${changed ? 'var(--accent-ink)' : 'var(--ink-3)'};font-weight:${changed ? '600' : '400'};font-style:normal;transition:color .3s ease;`,
      chipStyle: `display:inline-flex;align-items:center;gap:6px;border:1px solid ${changed ? 'var(--accent-line)' : 'var(--hairline)'};background:var(--surface-2);border-radius:6px;padding:1px 8px;cursor:pointer;color:${changed ? 'var(--accent-ink)' : 'var(--ink-3)'};transition:color .3s ease,border-color .3s ease;`,
      metaStyle: `color:var(--ink-4);font-size:11px;`,
      caretStyle: `color:var(--ink-4);font-size:10px;`,
      opaqueStyle: `display:inline-flex;align-items:center;border:1px dashed var(--hairline);border-radius:6px;padding:1px 9px;color:var(--ink-4);`,
    }
  }

  // cumulative scope -> rows; large vars expand to non-changed scalar children at indent 1 (handoff 811–820)
  export function buildRows(step: Step, expanded: Record<string, boolean>): RowModel[] {
    const out: RowModel[] = []
    step.scope.forEach((v) => {
      const changed = step.changed.includes(v.name)
      out.push(mkRow(v.name, v, changed, 0, expanded))
      if (v.kind === 'large' && expanded[v.name] && v.children) {
        v.children.forEach((c) => out.push(mkRow(c.name, { kind: 'scalar', text: c.text }, false, 1, expanded)))
      }
    })
    return out
  }

  // hero change-marker percents: i/(total-1)*100 for steps where changed.length>0 (handoff 862–864)
  export function markerLefts(trace: Step[]): number[] {
    const total = trace.length
    return trace
      .map((t, i) => ({ on: t.changed.length > 0, left: (i / (total - 1)) * 100 }))
      .filter((m) => m.on)
      .map((m) => m.left)
  }
  ```

- [ ] **Step 4: Run the tests (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/trace.test.ts
  ```
  Expect: all passing.

- [ ] **Step 5: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/stepper/trace.ts src/components/cuaderno/stepper/trace.test.ts && git commit -m "$(cat <<'EOF'
  feat(cuaderno): pure-TS trace-replay engine (mkRow/buildRows/lineModels/nextChange/markers)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 6: Add the bilingual step-through copy strings

**Files:**
- `frontend/src/components/cuaderno/strings.ts` (modify — `en` block after line 39; `es` block after line 74)
- `frontend/src/components/cuaderno/strings.test.ts` (create)

All strings are verbatim from the handoff (§8 copy) and the UI/UX brief §7. The breadcrumb verb changes to "Step through" / "Recorrer".

- [ ] **Step 1: Add the `en` keys.** In `frontend/src/components/cuaderno/strings.ts`, after `playground_evicted` in the `en` block (line 39), insert:
  ```ts
      playground_step_through: 'Step through',
      playground_step_arrow: 'Step through →',
      playground_anchored: 'Anchored function',
      playground_run_note: 'Runs your real code once, side effects included.',
      playground_python_limit: 'Steps through your Python; library calls appear as one step.',
      playground_preview_lead: "I'll step through this call:",
      playground_edit_call: 'Edit call',
      playground_cancel: 'Cancel',
      playground_preparing_capturing: 'running once · capturing trace',
      playground_state: 'State',
      playground_next_change: 'next change ◆',
      playground_truncated: 'Stopped at step {n} — trace truncated.',
      playground_raised_final: 'Raised — this is the final step.',
      playground_raised_label: 'raised',
      playground_fallback_note: "This function can't be stepped through yet — {reason}. Here's its input and output.",
      playground_input: 'Input',
      playground_output: 'Output',
      playground_source: '▸ source',
      playground_runtime_closed: 'Runtime closed',
      playground_runtime_closed_body: 'The sandbox shut down after idle. The captured trace is gone.',
      playground_reopen: 'Reopen',
      playground_evicted_title: 'Evicted',
      playground_evicted_body: 'Another example took this slot. Only one playground runs at a time.',
      playground_bring_back: 'Bring it back',
      playground_spawn_error: 'Spawn error',
      playground_spawn_error_body: "The playground didn't start. Nothing ran — your code wasn't touched.",
      playground_try_again: 'Try again',
  ```

- [ ] **Step 2: Add the `es` keys.** In the `es` block, after `playground_evicted` (line 74), insert:
  ```ts
      playground_step_through: 'Recorrer',
      playground_step_arrow: 'Recorrer →',
      playground_anchored: 'Función anclada',
      playground_run_note: 'Corre tu código real una vez, con sus efectos.',
      playground_python_limit: 'Recorre tu Python; las llamadas a librerías son un paso.',
      playground_preview_lead: 'Voy a recorrer esta llamada:',
      playground_edit_call: 'Editar llamada',
      playground_cancel: 'Cancelar',
      playground_preparing_capturing: 'corriendo una vez · capturando la traza',
      playground_state: 'Estado',
      playground_next_change: 'siguiente cambio ◆',
      playground_truncated: 'Detenido en el paso {n} — traza truncada.',
      playground_raised_final: 'Lanzó — este es el paso final.',
      playground_raised_label: 'lanzó',
      playground_fallback_note: 'Esta función no se puede recorrer paso a paso todavía — {reason}. Aquí está su entrada y salida.',
      playground_input: 'Entrada',
      playground_output: 'Salida',
      playground_source: '▸ fuente',
      playground_runtime_closed: 'Runtime cerrado',
      playground_runtime_closed_body: 'El sandbox se apagó tras estar inactivo. La traza capturada se perdió.',
      playground_reopen: 'Reabrir',
      playground_evicted_title: 'Desalojado',
      playground_evicted_body: 'Otro ejemplo tomó este espacio. Solo corre un playground a la vez.',
      playground_bring_back: 'Traerlo de vuelta',
      playground_spawn_error: 'Error al iniciar',
      playground_spawn_error_body: 'El playground no arrancó. Nada corrió — tu código no se tocó.',
      playground_try_again: 'Reintentar',
  ```

- [ ] **Step 3: Add a lookup + fallback test.** Write `frontend/src/components/cuaderno/strings.test.ts`:
  ```ts
  import { describe, it, expect } from 'vitest'
  import { t } from './strings'

  describe('step-through strings', () => {
    it('returns the breadcrumb verb per language', () => {
      expect(t('playground_step_through', 'en')).toBe('Step through')
      expect(t('playground_step_through', 'es')).toBe('Recorrer')
    })
    it('falls back to en for an unknown lang', () => {
      expect(t('playground_truncated', null)).toBe('Stopped at step {n} — trace truncated.')
    })
  })
  ```
  > **Note:** `t()` does NOT interpolate `{n}`/`{reason}` — the consuming components do `.replace('{n}', String(n))`. This test only checks lookup + fallback; the components handle substitution (covered in Tasks 8/10).

- [ ] **Step 4: Run the test (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/strings.test.ts
  ```
  Expect: passing.

- [ ] **Step 5: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/strings.ts src/components/cuaderno/strings.test.ts && git commit -m "$(cat <<'EOF'
  feat(cuaderno): bilingual step-through copy strings (breadcrumb verb -> step through)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 7: The state-panel row component (`StateRow.tsx`)

**Files:**
- `frontend/src/components/cuaderno/stepper/StateRow.tsx` (create)
- `frontend/src/components/cuaderno/stepper/StateRow.test.tsx` (create)

Renders one `RowModel` (from `trace.ts`) into the exact handoff markup (handoff lines 138–147): a diamond span (opacity-toggled, always in DOM), a name span, and a value span dispatching by kind. Large chips call `onToggle`. Inline styles come straight from the `RowModel` style strings (so the component is a thin renderer; the math is tested in Task 5).

- [ ] **Step 1: Write failing tests.** Write `frontend/src/components/cuaderno/stepper/StateRow.test.tsx`:
  ```tsx
  import { render, screen } from '@testing-library/react'
  import userEvent from '@testing-library/user-event'
  import { describe, it, expect, vi } from 'vitest'
  import { mkRow } from './trace'
  import { StateRow } from './StateRow'

  describe('StateRow', () => {
    it('renders a scalar value as text', () => {
      const row = mkRow('module_id', { kind: 'scalar', text: '42' }, true, 0, {})
      render(<StateRow row={row} onToggle={() => {}} />)
      expect(screen.getByText('42')).toBeInTheDocument()
      expect(screen.getByText('module_id')).toBeInTheDocument()
    })
    it('wraps an opaque label in angle quotes', () => {
      const row = mkRow('conn', { kind: 'opaque', label: 'Connection' }, false, 0, {})
      render(<StateRow row={row} onToggle={() => {}} />)
      expect(screen.getByText('‹Connection›')).toBeInTheDocument()
    })
    it('renders a large chip with summary + meta + caret and fires onToggle', async () => {
      const row = mkRow('ref', { kind: 'large', summary: 'FunctionRef', meta: '5 fields' }, true, 0, {})
      const onToggle = vi.fn()
      render(<StateRow row={row} onToggle={onToggle} />)
      expect(screen.getByText('FunctionRef')).toBeInTheDocument()
      expect(screen.getByText('5 fields')).toBeInTheDocument()
      await userEvent.click(screen.getByText('FunctionRef'))
      expect(onToggle).toHaveBeenCalledWith('ref')
    })
    it('does not make non-large rows clickable', async () => {
      const row = mkRow('x', { kind: 'object', text: "Symbol('Foo')" }, false, 0, {})
      const onToggle = vi.fn()
      render(<StateRow row={row} onToggle={onToggle} />)
      await userEvent.click(screen.getByText("Symbol('Foo')"))
      expect(onToggle).not.toHaveBeenCalled()
    })
  })
  ```

- [ ] **Step 2: Run the tests (expected FAIL).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/StateRow.test.tsx
  ```
  Expect: FAIL — `./StateRow` does not exist.

- [ ] **Step 3: Implement `StateRow`.** Write `frontend/src/components/cuaderno/stepper/StateRow.tsx`. The `style` prop strings are parsed by a tiny `s()` helper into a React style object (jsdom + React want an object, not a raw string). The large chip shows the expand caret and is clickable only when `row.expandable`.
  ```tsx
  import type { CSSProperties } from 'react'
  import type { RowModel } from './trace'

  // parse a "a:b;c:d;" inline-style string into a React style object
  export function s(css: string): CSSProperties {
    const out: Record<string, string> = {}
    css.split(';').forEach((decl) => {
      const i = decl.indexOf(':')
      if (i < 0) return
      const prop = decl.slice(0, i).trim()
      const val = decl.slice(i + 1).trim()
      if (!prop) return
      const camel = prop.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase())
      out[camel] = val
    })
    return out as CSSProperties
  }

  type Props = {
    row: RowModel
    onToggle: (name: string) => void
  }

  export function StateRow({ row, onToggle }: Props) {
    return (
      <div style={s(row.rowStyle)}>
        <span style={s(row.dotStyle)}>◆</span>
        <span style={s(row.nameStyle)}>{row.name}</span>
        <span style={s(row.valWrap)}>
          {row.isScalar && <span style={s(row.scalarStyle)}>{row.text}</span>}
          {row.isObject && <span style={s(row.objStyle)}>{row.text}</span>}
          {row.isOpaque && <span style={s(row.opaqueStyle)}>‹{row.label}›</span>}
          {row.isLarge && (
            <span
              style={s(row.chipStyle)}
              onClick={row.expandable ? () => onToggle(row.name) : undefined}
            >
              {row.summary} <span style={s(row.metaStyle)}>{row.meta}</span>
              <span style={s(row.caretStyle)}> {row.caret}</span>
            </span>
          )}
        </span>
      </div>
    )
  }
  ```

- [ ] **Step 4: Run the tests (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/StateRow.test.tsx
  ```
  Expect: passing.

- [ ] **Step 5: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/stepper/StateRow.tsx src/components/cuaderno/stepper/StateRow.test.tsx && git commit -m "$(cat <<'EOF'
  feat(cuaderno): StateRow — per-kind state-panel row (scalar/object/opaque/large)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 8: The `<Stepper>` — Stepping + Truncated + Raised

**Files:**
- `frontend/src/components/cuaderno/stepper/Stepper.tsx` (create)
- `frontend/src/components/cuaderno/stepper/Stepper.test.tsx` (create)

`<Stepper>` takes a `StepThroughResponse` + `lang` + `onClose`. It owns `step` (1-based, default 1) and `expanded` (name→bool). It renders the head strip (counter `step N / M`), the optional banner (Truncated `--accent` tick / Raised `--neg` band — derived from `truncated` and the final step's `event === 'raise'`/`raised`), the source column (slab at `curIdx*ROW_H`, lines via `lineModels`), the state panel (rows via `buildRows` + `<StateRow>`, plus the raised card when the current step has `raised`), and the scrubber (prev/next, clickable track via `trackFraction`, hero change-markers via `markerLefts`, `next change` button via `nextChange`). Body height: **480px** normally, **404px** when a banner is shown (handoff 423/482).

**Stale-anchor (spec §7):** when `source_lines.findIndex` misses (`curIdx < 0`), the highlight slab is **suppressed** (not rendered) — never defaulted to line 0. Stale-anchor highlight drift is a known §7 limitation deferred from this work.

- [ ] **Step 1: Write failing behavior tests.** Write `frontend/src/components/cuaderno/stepper/Stepper.test.tsx`:
  ```tsx
  import { render, screen } from '@testing-library/react'
  import userEvent from '@testing-library/user-event'
  import { describe, it, expect, vi } from 'vitest'
  import type { StepThroughResponse, Step, Var } from '../../../types/api'
  import { Stepper } from './Stepper'

  const v = (name: string, kind: Var['kind'], extra: Partial<Var> = {}): Var => ({ name, kind, ...extra })
  const trace: Step[] = [
    { line: 255, event: 'call', changed: ['ref'], scope: [v('ref', 'large', { summary: 'FunctionRef', meta: '5 fields', children: [{ name: 'qualname', text: "'Foo.method'" }] })] },
    { line: 256, event: 'line', changed: ['qualname'], scope: [v('ref', 'large', { summary: 'FunctionRef', meta: '5 fields', children: [{ name: 'qualname', text: "'Foo.method'" }] }), v('qualname', 'scalar', { text: "'Foo.method'" })] },
    { line: 257, event: 'line', changed: [], scope: [v('qualname', 'scalar', { text: "'Foo.method'" })] },
    { line: 258, event: 'line', changed: ['parent'], scope: [v('parent', 'scalar', { text: 'None' })] },
  ]
  const resp: StepThroughResponse = {
    kind: 'trace', trace,
    source_lines: [255, 256, 257, 258].map((num) => ({ num, text: `line ${num}` })),
    func_name: 'resolve_function_ref', file_line: 'intelligence/symbols.py:255', truncated: false,
  }

  describe('Stepper', () => {
    it('opens on step 1 of N and shows the counter', () => {
      render(<Stepper response={resp} onClose={() => {}} />)
      expect(screen.getByText('step 1 / 4')).toBeInTheDocument()
    })
    it('advances with the next button', async () => {
      render(<Stepper response={resp} onClose={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: '▶' }))
      expect(screen.getByText('step 2 / 4')).toBeInTheDocument()
    })
    it('clamps at the last step', async () => {
      render(<Stepper response={resp} onClose={() => {}} />)
      const next = screen.getByRole('button', { name: '▶' })
      for (let i = 0; i < 10; i++) await userEvent.click(next)
      expect(screen.getByText('step 4 / 4')).toBeInTheDocument()
    })
    it('jumps to the next change, skipping no-change steps', async () => {
      render(<Stepper response={resp} onClose={() => {}} />)
      // step 1 -> next change is step 2 (qualname). From 2, next change skips 3 (none) to 4 (parent).
      await userEvent.click(screen.getByRole('button', { name: /next change/ }))
      expect(screen.getByText('step 2 / 4')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /next change/ }))
      expect(screen.getByText('step 4 / 4')).toBeInTheDocument()
    })
    it('expands a large chip into its children', async () => {
      render(<Stepper response={resp} onClose={() => {}} />)
      expect(screen.queryByText("'Foo.method'")).not.toBeInTheDocument()
      await userEvent.click(screen.getByText('FunctionRef'))
      expect(screen.getByText("'Foo.method'")).toBeInTheDocument()
    })
    it('shows the truncated banner when truncated=true', () => {
      render(<Stepper response={{ ...resp, truncated: true }} onClose={() => {}} lang="en" />)
      expect(screen.getByText('Stopped at step 4 — trace truncated.')).toBeInTheDocument()
    })
    it('renders the raised card + banner on a raise terminal step', async () => {
      const raisedTrace: Step[] = [
        ...trace,
        { line: 263, event: 'raise', changed: [], scope: [v('qualname', 'scalar', { text: "'ghost'" })], raised: { type: 'KeyError', message: "'ghost'" } },
      ]
      render(<Stepper response={{ ...resp, trace: raisedTrace }} onClose={() => {}} lang="en" />)
      const next = screen.getByRole('button', { name: '▶' })
      for (let i = 0; i < 10; i++) await userEvent.click(next)
      expect(screen.getByText('Raised — this is the final step.')).toBeInTheDocument()
      expect(screen.getByText("KeyError: 'ghost'")).toBeInTheDocument()
    })
    it('suppresses the highlight slab on a stale anchor (line not in source_lines)', () => {
      // a trace whose first step line (999) is absent from source_lines → curIdx < 0
      const stale: StepThroughResponse = {
        ...resp,
        trace: [{ line: 999, event: 'call', changed: ['x'], scope: [v('x', 'scalar', { text: '1' })] }],
      }
      const { container } = render(<Stepper response={stale} onClose={() => {}} />)
      // the slab carries the accent left border; on a stale anchor it must not render
      const slab = container.querySelector('[data-testid="hl-slab"]')
      expect(slab).toBeNull()
    })
    it('fires onClose from the × button', async () => {
      const onClose = vi.fn()
      render(<Stepper response={resp} onClose={onClose} />)
      await userEvent.click(screen.getByRole('button', { name: '×' }))
      expect(onClose).toHaveBeenCalled()
    })
  })
  ```

- [ ] **Step 2: Run the tests (expected FAIL).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/Stepper.test.tsx
  ```
  Expect: FAIL — `./Stepper` does not exist.

- [ ] **Step 3: Implement `<Stepper>`.** Write `frontend/src/components/cuaderno/stepper/Stepper.tsx`. Use the handoff hero markup (lines 98–169) translated to inline-style objects via the `s()` helper from `StateRow.tsx`; geometry comes from `trace.ts`. Banner logic: `truncated` → accent tick banner + 404px body; the final step's `event === 'raise'` (or `raised` present) → `--neg` banner + 404px body; otherwise 480px. The raised card renders in the state panel when `currentStep.raised` is set (handoff 509–512). The track click uses `getBoundingClientRect` + `trackFraction`. **Stale anchor:** when `curIdx < 0`, the slab is not rendered at all (no `top:0` default).
  ```tsx
  import { useState } from 'react'
  import type { StepThroughResponse } from '../../../types/api'
  import { t } from '../strings'
  import {
    ROW_H, clampStep, nextChange, trackFraction, lineModels, buildRows, markerLefts,
  } from './trace'
  import { StateRow, s } from './StateRow'

  type Props = {
    response: StepThroughResponse
    onClose: () => void
    lang?: string | null
  }

  export function Stepper({ response, onClose, lang }: Props) {
    const { trace, source_lines, func_name, file_line, truncated } = response
    const total = trace.length
    const [step, setStep] = useState(1)
    const [expanded, setExpanded] = useState<Record<string, boolean>>({})

    const cur = clampStep(step, total)
    const tr = trace[cur - 1]
    const curIdx = source_lines.findIndex((l) => l.num === tr.line)
    const staleAnchor = curIdx < 0   // spec §7: source moved, line not found
    const lines = lineModels(source_lines, curIdx)
    const rows = buildRows(tr, expanded)
    const hlTop = curIdx * ROW_H     // only used when !staleAnchor
    const handleLeft = total > 1 ? `${((cur - 1) / (total - 1)) * 100}%` : '0%'
    const markers = markerLefts(trace)

    const raised = tr.event === 'raise' || !!tr.raised
    const slabBg = raised ? 'var(--neg)' : 'var(--accent-soft)'
    const slabBorder = raised ? 'var(--neg-ink)' : 'var(--accent)'
    const banner = truncated
      ? { tick: 'var(--accent)', bg: 'var(--surface-2)', ink: 'var(--ink-2)', text: t('playground_truncated', lang).replace('{n}', String(total)) }
      : raised
        ? { tick: 'var(--neg-ink)', bg: 'var(--neg)', ink: 'var(--neg-ink)', text: t('playground_raised_final', lang) }
        : null
    const bodyHeight = banner ? 404 : 480

    const toggle = (name: string) =>
      setExpanded((e) => ({ ...e, [name]: !e[name] }))
    const move = (d: number) => setStep(clampStep(cur + d, total))
    const onTrack = (e: React.MouseEvent<HTMLDivElement>) => {
      const r = e.currentTarget.getBoundingClientRect()
      const f = (e.clientX - r.left) / r.width
      setStep(trackFraction(f, total))
    }
    const onNextChange = () => setStep(nextChange(cur, trace))
    const atEnd = cur >= total

    const btn = 'width:28px;height:28px;flex:none;border-radius:7px;border:1px solid var(--hairline);background:var(--paper);color:var(--ink-2);cursor:pointer;font-size:9px;display:flex;align-items:center;justify-content:center;'

    return (
      <div className="widget stepper-widget">
        {/* head strip */}
        <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
          <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
          <span style={s('color:var(--ink-4);')}>·</span>
          <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{func_name}</span>
          <span style={s('flex:1;')} />
          <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums;')}>step {cur} / {total}</span>
          <button onClick={onClose} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;padding:0 2px;')}>×</button>
        </div>
        {/* breadcrumb */}
        <div style={s('padding:11px 16px 12px;border-bottom:1px solid var(--hairline-soft);')}>
          <div style={s('font-family:var(--font-body);font-size:15px;color:var(--ink);')}>
            {t('playground_step_through', lang)} <span style={s('font-family:var(--font-mono);font-size:13px;color:var(--accent-ink);')}>{func_name}</span>
          </div>
          <div style={s('font-family:var(--font-mono);font-size:11px;color:var(--ink-4);margin-top:3px;')}>{file_line}</div>
        </div>
        {/* banner */}
        {banner && (
          <div style={s(`display:flex;align-items:center;gap:9px;padding:9px 16px;background:${banner.bg};border-bottom:1px solid var(--hairline-soft);`)}>
            <span style={s(`display:inline-block;width:3px;height:13px;border-radius:1px;background:${banner.tick};flex:none;`)} />
            <span style={s(`font-size:12px;color:${banner.ink};font-family:var(--font-ui);`)}>{banner.text}</span>
          </div>
        )}
        {/* body */}
        <div style={{ ...s('display:flex;flex-direction:column;padding:16px 16px 13px;'), height: bodyHeight }}>
          <div style={s('flex:1;display:flex;min-height:0;')}>
            {/* source */}
            <div style={s('flex:1.55;position:relative;overflow:hidden;font-family:var(--font-mono);font-size:13px;line-height:26px;')}>
              {!staleAnchor && (
                <div data-testid="hl-slab" style={{ ...s(`position:absolute;left:-16px;right:6px;height:26px;background:${slabBg};border-left:2px solid ${slabBorder};transition:top .22s cubic-bezier(.4,0,.2,1);`), top: hlTop }} />
              )}
              <div style={s('position:relative;')}>
                {lines.map((ln) => (
                  <div key={ln.num} style={s('display:flex;height:26px;')}>
                    <span style={s(ln.numStyle)}>{ln.num}</span>
                    <span style={s(ln.codeStyle)}>{ln.code}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* divider */}
            <div style={s('width:1px;background:var(--hairline-soft);margin:0 16px;flex:none;')} />
            {/* state */}
            <div style={s('flex:1;min-width:0;display:flex;flex-direction:column;')}>
              <div style={s('display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;')}>
                <span style={s('font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>{t('playground_state', lang)}</span>
                <span style={s('font-family:var(--font-mono);font-size:11px;color:var(--ink-4);font-variant-numeric:tabular-nums;')}>step {cur}</span>
              </div>
              <div style={s('flex:1;overflow:auto;font-family:var(--font-mono);font-size:12.5px;')}>
                {rows.map((row, i) => (<StateRow key={`${row.name}-${i}`} row={row} onToggle={toggle} />))}
                {tr.raised && (
                  <div style={s('margin-top:10px;padding:9px 11px;background:var(--neg);border:1px solid var(--neg-line);border-radius:8px;')}>
                    <div style={s('font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--neg-ink);font-family:var(--font-ui);font-weight:600;margin-bottom:4px;')}>{t('playground_raised_label', lang)}</div>
                    <div style={s('color:var(--neg-ink);font-weight:600;')}>{tr.raised.type}: {tr.raised.message}</div>
                  </div>
                )}
              </div>
            </div>
          </div>
          {/* scrubber */}
          <div style={s('display:flex;align-items:center;gap:11px;padding-top:13px;margin-top:11px;border-top:1px solid var(--hairline-soft);')}>
            <button onClick={() => move(-1)} aria-label="◀" className="stepper-btn" style={s(btn)}>◀</button>
            <div onClick={onTrack} style={s('position:relative;flex:1;height:26px;display:flex;align-items:center;cursor:pointer;')}>
              <div style={s('position:absolute;left:0;right:0;height:3px;border-radius:2px;background:var(--hairline);')} />
              <div style={{ ...s('position:absolute;left:0;height:3px;border-radius:2px;background:var(--accent-line);transition:width .22s cubic-bezier(.4,0,.2,1);'), width: handleLeft }} />
              {markers.map((left, i) => (
                <div key={i} style={{ ...s('position:absolute;top:50%;transform:translate(-50%,-50%);width:2px;height:11px;border-radius:1px;background:var(--accent-line);'), left: `${left}%` }} />
              ))}
              <div style={{ ...s('position:absolute;width:13px;height:13px;border-radius:50%;background:var(--accent);border:2px solid var(--surface);transform:translateX(-50%);transition:left .22s cubic-bezier(.4,0,.2,1);box-shadow:0 1px 3px rgba(0,0,0,.3);'), left: handleLeft }} />
            </div>
            <button onClick={() => move(1)} aria-label="▶" className="stepper-btn" style={{ ...s(btn), ...(atEnd ? s('color:var(--ink-4);') : {}) }}>▶</button>
            <button onClick={onNextChange} className="stepper-btn" style={s('flex:none;height:28px;border-radius:7px;border:1px solid var(--hairline);background:var(--paper);color:var(--ink-3);cursor:pointer;font-size:11px;padding:0 11px;white-space:nowrap;')}>{t('playground_next_change', lang)}</button>
          </div>
          {/* honesty note */}
          <div style={s('display:flex;align-items:center;gap:8px;margin-top:11px;')}>
            <span style={s('width:5px;height:5px;border-radius:50%;background:var(--accent);opacity:.55;flex:none;')} />
            <span style={s('font-size:11.5px;color:var(--ink-3);')}>{t('playground_python_limit', lang)}</span>
          </div>
        </div>
      </div>
    )
  }
  ```
  > **Note (background, hover, theme):** prev/next button background is `--paper` (light figure); the dark figure uses `--surface-2`, but since both themes share one CSS-variable scope and `--paper` is theme-defined, this single value is correct for both. Hover states (`border-color:var(--accent-line)`) are added as `.stepper-btn:hover` CSS in Task 9 rather than inline (inline can't express `:hover`).

- [ ] **Step 4: Run the tests (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/Stepper.test.tsx
  ```
  Expect: all passing.

- [ ] **Step 5: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/stepper/Stepper.tsx src/components/cuaderno/stepper/Stepper.test.tsx && git commit -m "$(cat <<'EOF'
  feat(cuaderno): Stepper view — stepping/truncated/raised; stale-anchor slab suppressed

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 9: Idle, PreviewCall (free-text), Spawning, EndedCards + the stepper CSS hover/scroll rules

**Files:**
- `frontend/src/components/cuaderno/stepper/IdleInvitation.tsx` (create)
- `frontend/src/components/cuaderno/stepper/PreviewCall.tsx` (create)
- `frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx` (create)
- `frontend/src/components/cuaderno/stepper/Spawning.tsx` (create)
- `frontend/src/components/cuaderno/stepper/EndedCards.tsx` (create)
- `frontend/src/styles/cuaderno.css` (modify — append after line 1119)

`PreviewCall` is faithful to handoff state 02 (lines 288–318): the proposed call shows read-only with a ✎ pencil; clicking ✎ (or "Edit call") reveals a **free-text `textarea`** seeded with the proposed call; **on confirm, the current (possibly edited) free text is returned via `onConfirm(callText)`** so the widget can pass it to the backend (D2). This wires `callText`/`previewEditing`/`toggleEdit` for real — no `void callText` stub.

- [ ] **Step 1: Write failing tests for PreviewCall.** Write `frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx`:
  ```tsx
  import { render, screen } from '@testing-library/react'
  import userEvent from '@testing-library/user-event'
  import { describe, it, expect, vi } from 'vitest'
  import { PreviewCall } from './PreviewCall'

  describe('PreviewCall', () => {
    it('shows the proposed call read-only with a pencil button', () => {
      render(<PreviewCall funcName="resolve_function_ref" initialCall="resolve_function_ref(conn, 42, ref)" onConfirm={() => {}} onCancel={() => {}} />)
      expect(screen.getByText('resolve_function_ref(conn, 42, ref)')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '✎' })).toBeInTheDocument()
    })
    it('confirms the UNEDITED proposed call when not edited', async () => {
      const onConfirm = vi.fn()
      render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
      expect(onConfirm).toHaveBeenCalledWith('f(1)')
    })
    it('reveals a textarea when editing and confirms the edited free-text call', async () => {
      const onConfirm = vi.fn()
      render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: '✎' }))
      const ta = screen.getByRole('textbox')
      await userEvent.clear(ta)
      await userEvent.type(ta, 'f(2)')
      await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
      expect(onConfirm).toHaveBeenCalledWith('f(2)')
    })
    it('fires onCancel', async () => {
      const onCancel = vi.fn()
      render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={() => {}} onCancel={onCancel} />)
      await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
      expect(onCancel).toHaveBeenCalled()
    })
  })
  ```

- [ ] **Step 2: Run the test (expected FAIL).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/stepper/PreviewCall.test.tsx
  ```
  Expect: FAIL — `./PreviewCall` does not exist.

- [ ] **Step 3: Implement `PreviewCall`.** Write `frontend/src/components/cuaderno/stepper/PreviewCall.tsx` from the handoff state 02 (lines 298–318). It owns `editing` + `callText`; `onConfirm(callText)` passes the **current free text** (edited or not), `onCancel()` aborts. Head strip is the simple chrome (no counter):
  ```tsx
  import { useState } from 'react'
  import { t } from '../strings'
  import { s } from './StateRow'

  type Props = {
    funcName: string
    initialCall: string             // the REAL model-proposed invocation (from widget.call_text)
    onConfirm: (callText: string) => void
    onCancel: () => void
    lang?: string | null
  }

  export function PreviewCall({ funcName, initialCall, onConfirm, onCancel, lang }: Props) {
    const [editing, setEditing] = useState(false)
    const [callText, setCallText] = useState(initialCall)
    return (
      <div className="widget stepper-widget">
        <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
          <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
          <span style={s('color:var(--ink-4);')}>·</span>
          <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
          <span style={s('flex:1;')} />
          <button onClick={onCancel} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;')}>×</button>
        </div>
        <div style={{ ...s('display:flex;flex-direction:column;padding:18px 16px 13px;'), height: 430 }}>
          <div style={s('flex:1;display:flex;flex-direction:column;justify-content:center;')}>
            <div style={s('font-family:var(--font-body);font-size:15px;color:var(--ink-2);margin-bottom:13px;')}>{t('playground_preview_lead', lang)}</div>
            {editing ? (
              <textarea
                value={callText}
                onChange={(e) => setCallText(e.target.value)}
                spellCheck={false}
                style={s('font-family:var(--font-mono);font-size:14px;color:var(--ink);background:var(--surface-2);border:1px solid var(--accent-line);border-radius:9px;padding:13px 14px;width:100%;resize:none;height:62px;line-height:1.5;outline:none;')}
              />
            ) : (
              <div style={s('position:relative;font-family:var(--font-mono);font-size:14px;color:var(--ink);background:var(--surface-2);border:1px solid var(--hairline);border-radius:9px;padding:13px 46px 13px 14px;line-height:1.5;')}>
                {callText}
                <button onClick={() => setEditing(true)} aria-label="✎" className="stepper-pencil" style={s('position:absolute;right:9px;top:9px;border:1px solid var(--hairline);background:var(--paper);color:var(--ink-3);border-radius:6px;width:28px;height:28px;cursor:pointer;font-size:12px;')}>✎</button>
              </div>
            )}
            <div style={s('display:flex;align-items:center;gap:8px;margin-top:13px;')}>
              <span style={s('width:5px;height:5px;border-radius:50%;background:var(--accent);opacity:.55;flex:none;')} />
              <span style={s('font-size:12.5px;color:var(--ink-3);')}>{t('playground_run_note', lang)}</span>
            </div>
          </div>
          <div style={s('display:flex;align-items:center;gap:10px;padding-top:13px;border-top:1px solid var(--hairline-soft);')}>
            <button onClick={() => onConfirm(callText)} className="stepper-primary" style={s('border:1px solid var(--accent-line);background:var(--accent-soft);color:var(--accent-ink);border-radius:8px;padding:9px 18px;font-size:13.5px;font-weight:500;font-family:var(--font-ui);cursor:pointer;')}>{t('playground_step_through', lang)}</button>
            <button onClick={() => setEditing((val) => !val)} style={s('border:1px solid var(--hairline);background:var(--paper);color:var(--ink-3);border-radius:8px;padding:9px 16px;font-size:13.5px;font-family:var(--font-ui);cursor:pointer;')}>{t('playground_edit_call', lang)}</button>
            <span style={s('flex:1;')} />
            <button onClick={onCancel} style={s('border:none;background:none;color:var(--ink-4);font-size:13px;cursor:pointer;font-family:var(--font-ui);')}>{t('playground_cancel', lang)}</button>
          </div>
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 4: Implement `IdleInvitation`.** Write `frontend/src/components/cuaderno/stepper/IdleInvitation.tsx` from the handoff state 01 (lines 260–282). Props: `funcName`, `fileLine`, `onStepThrough`, `onClose`, `lang`. Single primary "Step through →" button → `onStepThrough()`. No standalone unit test (its single click handler is covered by the Task 10 integration test); keep it markup-only:
  ```tsx
  import { t } from '../strings'
  import { s } from './StateRow'

  type Props = { funcName: string; fileLine: string; onStepThrough: () => void; onClose: () => void; lang?: string | null }

  export function IdleInvitation({ funcName, fileLine, onStepThrough, onClose, lang }: Props) {
    return (
      <div className="widget stepper-widget">
        <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
          <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
          <span style={s('color:var(--ink-4);')}>·</span>
          <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
          <span style={s('flex:1;')} />
          <button onClick={onClose} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;')}>×</button>
        </div>
        <div style={{ ...s('display:flex;flex-direction:column;'), height: 430 }}>
          <div style={s('flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:24px;')}>
            <div style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-4);font-weight:600;margin-bottom:14px;')}>{t('playground_anchored', lang)}</div>
            <div style={s('font-family:var(--font-mono);font-size:19px;color:var(--ink);margin-bottom:6px;')}>{funcName}</div>
            <div style={s('font-family:var(--font-mono);font-size:11px;color:var(--ink-4);margin-bottom:26px;')}>{fileLine}</div>
            <button onClick={onStepThrough} className="stepper-primary" style={s('border:1px solid var(--accent-line);background:var(--accent-soft);color:var(--accent-ink);border-radius:9px;padding:10px 22px;font-size:14px;font-family:var(--font-ui);font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:9px;')}>{t('playground_step_through', lang)} <span style={s('font-size:12px;')}>→</span></button>
            <div style={s('font-size:12px;color:var(--ink-3);margin-top:16px;')}>{t('playground_run_note', lang)}</div>
          </div>
          <div style={s('display:flex;align-items:center;gap:8px;padding:0 16px 13px;')}>
            <span style={s('width:5px;height:5px;border-radius:50%;background:var(--accent);opacity:.55;flex:none;')} />
            <span style={s('font-size:11.5px;color:var(--ink-3);')}>{t('playground_python_limit', lang)}</span>
          </div>
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 5: Implement `Spawning`.** Write `frontend/src/components/cuaderno/stepper/Spawning.tsx` from the handoff state 03 (lines 326–340) — head strip with **no counter, no close button**; the sweep bar uses the `stepperSweep` keyframe (added in Step 7 CSS) and `stepperPulse` for the pulsing span. The `callText` is the real proposed call passed down from the widget:
  ```tsx
  import { t } from '../strings'
  import { s } from './StateRow'

  type Props = { funcName: string; callText: string; lang?: string | null }

  export function Spawning({ funcName, callText, lang }: Props) {
    return (
      <div className="widget stepper-widget">
        <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
          <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
          <span style={s('color:var(--ink-4);')}>·</span>
          <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
        </div>
        <div style={{ ...s('display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;'), height: 430 }}>
          <div style={s('font-family:var(--font-mono);font-size:13px;color:var(--ink-3);margin-bottom:20px;')}>{callText}</div>
          <div style={s('position:relative;width:220px;height:4px;border-radius:2px;background:var(--surface-2);overflow:hidden;margin-bottom:20px;')}>
            <div className="stepper-sweep" style={s('position:absolute;top:0;left:0;height:100%;width:34%;border-radius:2px;background:var(--accent-line);')} />
          </div>
          <div style={s('font-size:14px;color:var(--ink-2);font-family:var(--font-ui);display:flex;align-items:center;gap:7px;')}>
            {t('playground_preparing', lang)} <span className="stepper-pulse" style={s('color:var(--ink-3);')}>{t('playground_preparing_capturing', lang)}</span>
          </div>
        </div>
      </div>
    )
  }
  ```
  > **Note:** `playground_preparing` ("preparing…" / "preparando…") already exists in `strings.ts` (en line 37, es line 72) from the prior playground work; reuse it — do not redefine it.

- [ ] **Step 6: Implement `EndedCards`.** Write `frontend/src/components/cuaderno/stepper/EndedCards.tsx` from the handoff state 08 (lines 380–393). The slot holds ONE ended reason at a time, so render the SINGLE card matching `reason` (`'closed'`/`'exited'` → Runtime closed, `'evicted'` → Evicted, `'error'` → Spawn error), each with its relaunch button calling `onRetry`:
  ```tsx
  import { t } from '../strings'
  import { s } from './StateRow'

  type Reason = 'closed' | 'evicted' | 'exited' | 'error'
  type Props = { funcName: string; reason: Reason; message?: string; onRetry: () => void; onClose: () => void; lang?: string | null }

  export function EndedCards({ funcName, reason, message, onRetry, onClose, lang }: Props) {
    const spec = reason === 'evicted'
      ? { tick: 'var(--ink-4)', tickOpacity: '', title: t('playground_evicted_title', lang), body: t('playground_evicted_body', lang), btn: t('playground_bring_back', lang) }
      : reason === 'error'
        ? { tick: 'var(--neg-ink)', tickOpacity: '.7', title: t('playground_spawn_error', lang), body: message ?? t('playground_spawn_error_body', lang), btn: t('playground_try_again', lang) }
        : { tick: 'var(--ink-4)', tickOpacity: '', title: t('playground_runtime_closed', lang), body: t('playground_runtime_closed_body', lang), btn: t('playground_reopen', lang) }
    return (
      <div className="widget stepper-widget">
        <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
          <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
          <span style={s('color:var(--ink-4);')}>·</span>
          <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
          <span style={s('flex:1;')} />
          <button onClick={onClose} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;')}>×</button>
        </div>
        <div style={s('padding:18px;display:flex;flex-direction:column;gap:12px;')}>
          <div style={s('display:flex;align-items:center;gap:9px;')}>
            <span style={s(`width:8px;height:8px;border-radius:2px;background:${spec.tick};${spec.tickOpacity ? `opacity:${spec.tickOpacity};` : ''}`)} />
            <span style={s('font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>{spec.title}</span>
          </div>
          <div style={s('font-size:13px;line-height:1.5;color:var(--ink-2);')}>{spec.body}</div>
          <button onClick={onRetry} className="stepper-ghost" style={s('align-self:flex-start;border:1px solid var(--hairline);background:var(--paper);color:var(--accent-ink);border-radius:7px;padding:7px 14px;font-size:12.5px;font-family:var(--font-ui);cursor:pointer;')}>{spec.btn}</button>
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 7: Add the stepper CSS (hover states, scrollbar, animations).** Append to `frontend/src/styles/cuaderno.css` after line 1119. These express the `:hover` overlays the inline styles can't, plus the two keyframes the handoff defines (`cuaSweep`, `cuaPulse`) namespaced as `stepper-*`:
  ```css

  /* ---------- step-through stepper ---------- */
  .stepper-widget { overflow: hidden; }
  .stepper-primary:hover { background: var(--accent); color: var(--paper); }
  .stepper-ghost:hover { border-color: var(--accent-line); }
  .stepper-btn:hover { border-color: var(--accent-line); color: var(--accent-ink); }
  .stepper-pencil:hover { color: var(--accent-ink); border-color: var(--accent-line); }
  @keyframes stepperSweep { 0% { transform: translateX(-120%); } 100% { transform: translateX(420%); } }
  @keyframes stepperPulse { 0%, 100% { opacity: .4; } 50% { opacity: .95; } }
  .stepper-sweep { animation: stepperSweep 1.25s cubic-bezier(.4, 0, .2, 1) infinite; }
  .stepper-pulse { animation: stepperPulse 1.5s ease-in-out infinite; }
  ```

- [ ] **Step 8: Run the PreviewCall test (expected PASS) + full suite.** Run:
  ```bash
  cd frontend && npm test
  ```
  Expect: all suites passing.

- [ ] **Step 9: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/stepper src/styles/cuaderno.css && git commit -m "$(cat <<'EOF'
  feat(cuaderno): Idle/PreviewCall(free-text)/Spawning/EndedCards states + stepper CSS

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 10: Wire `PlaygroundWidget` to the new states (dispatch + real call + free-text override)

**Files:**
- `frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx` (modify — full rewrite of the render dispatch, lines 13–107)
- `frontend/src/components/cuaderno/widgets/PlaygroundWidget.test.tsx` (create)

The widget drives the full state machine: `IdleInvitation` when the slot is empty/not-mine, the `PreviewCall` when the user clicks "Step through" (a local `previewing` flag), `Spawning` while the slot is spawning, `<Stepper>` when the slot is `trace`, the existing iframe box (kept inline) when the slot is `live` (fallback), and `EndedCards` when the slot is `ended`.

**Real proposed call (D2):** the widget renders the **real** model-proposed invocation. It prefers `widget.call_text` (the pre-rendered invocation source), else derives it from `widget.call` (the structured `CallDescriptor`), via a small `callTextOf(...)` builder. There is **no** fake `name(…)` placeholder. On confirm, the edited free text flows through `launch` as `call_text`, alongside the structured `call` descriptor — the backend now accepts the free-text override (D2).

- [ ] **Step 1: Write failing integration tests.** Write `frontend/src/components/cuaderno/widgets/PlaygroundWidget.test.tsx`:
  ```tsx
  import { render, screen, act } from '@testing-library/react'
  import userEvent from '@testing-library/user-event'
  import { describe, it, expect, beforeEach, vi } from 'vitest'
  import type { StepThroughResponse, FallbackResponse, PlaygroundWidgetData } from '../../../types/api'

  const launchPlayground = vi.fn()
  const closePlayground = vi.fn(() => Promise.resolve({ ok: true }))
  const playgroundStatus = vi.fn(() => Promise.resolve({ status: 'running', id: '1' }))
  const playgroundList = vi.fn(() => Promise.resolve({ items: [] }))
  vi.mock('../../../api/client', () => ({
    api: { launchPlayground, closePlayground, playgroundStatus, playgroundList },
  }))

  import { PlaygroundWidget } from './PlaygroundWidget'
  import { close } from '../playgroundSlot'

  const fn = { file: 'intelligence/symbols.py', name: 'resolve_function_ref', line: 255 }
  const widget: PlaygroundWidgetData = {
    kind: 'playground',
    function_ref: fn,
    breadcrumb: 'Step through resolve_function_ref',
    call: { function_ref: fn, args: ['conn', 42, 'ref'] },
    call_text: 'resolve_function_ref(conn, 42, ref)',
  }
  const trace: StepThroughResponse = {
    kind: 'trace',
    trace: [{ line: 255, event: 'call', changed: ['x'], scope: [{ name: 'x', kind: 'scalar', text: '1' }] }],
    source_lines: [{ num: 255, text: 'def f(x):' }],
    func_name: 'resolve_function_ref', file_line: 'intelligence/symbols.py:255', truncated: false,
  }
  const fallback: FallbackResponse = { kind: 'fallback', reason: 'generator', iframe_url: '/playground/abc' }

  beforeEach(() => { launchPlayground.mockReset(); closePlayground.mockClear(); close() })

  describe('PlaygroundWidget', () => {
    it('renders the idle invitation by default', () => {
      render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
      expect(screen.getByText('intelligence/symbols.py:255')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /step through/i })).toBeInTheDocument()
    })
    it('shows the REAL proposed call (not a placeholder) in preview', async () => {
      render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: /step through/i }))
      expect(screen.getByText('resolve_function_ref(conn, 42, ref)')).toBeInTheDocument()
      expect(screen.queryByText('resolve_function_ref(…)')).not.toBeInTheDocument()
    })
    it('idle -> preview -> stepper on confirm (mounts the React stepper for kind:trace)', async () => {
      launchPlayground.mockResolvedValue(trace)
      render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: /step through/i }))
      expect(screen.getByText(/step through this call/i)).toBeInTheDocument()
      await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
      expect(await screen.findByText('step 1 / 1')).toBeInTheDocument()
    })
    it('passes the edited free-text call through launch as call_text', async () => {
      launchPlayground.mockResolvedValue(trace)
      render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: /step through/i }))
      await userEvent.click(screen.getByRole('button', { name: '✎' }))
      const ta = screen.getByRole('textbox')
      await userEvent.clear(ta)
      await userEvent.type(ta, 'resolve_function_ref(conn, 99, ref)')
      await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
      expect(launchPlayground).toHaveBeenCalledWith(
        expect.objectContaining({ call_text: 'resolve_function_ref(conn, 99, ref)' }),
      )
    })
    it('mounts the iframe box for kind:fallback', async () => {
      launchPlayground.mockResolvedValue(fallback)
      const { container } = render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
      await userEvent.click(screen.getByRole('button', { name: /step through/i }))
      await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
      const iframe = container.querySelector('iframe')
      expect(iframe).toBeTruthy()
      expect(iframe!.getAttribute('src')).toBe('/playground/abc')
    })
  })
  ```

- [ ] **Step 2: Run the tests (expected FAIL).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/widgets/PlaygroundWidget.test.tsx
  ```
  Expect: FAIL — the current widget renders the legacy `playground-run` button, no preview, no stepper.

- [ ] **Step 3: Rewrite `PlaygroundWidget`.** Replace the body of `frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx`:
  ```tsx
  import { useState, useSyncExternalStore } from 'react'
  import type { PlaygroundWidgetData, Citation, CallDescriptor } from '../../../types/api'
  import { CitationChip } from '../CitationChip'
  import { subscribe, getState, launch, close } from '../playgroundSlot'
  import { IdleInvitation } from '../stepper/IdleInvitation'
  import { PreviewCall } from '../stepper/PreviewCall'
  import { Spawning } from '../stepper/Spawning'
  import { Stepper } from '../stepper/Stepper'
  import { EndedCards } from '../stepper/EndedCards'

  type Props = {
    widget: PlaygroundWidgetData
    onOpenCitation: (c: Citation) => void
    lang?: string | null
  }

  // Build a faithful invocation string from the model's structured descriptor.
  // Prefer the pre-rendered call_text; this is the fallback when only `call` is present.
  function callTextOf(name: string, call?: CallDescriptor): string {
    if (!call) return `${name}()`
    const lit = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v))
    const pos = (call.args ?? []).map(lit)
    const kw = Object.entries(call.kwargs ?? {}).map(([k, v]) => `${k}=${lit(v)}`)
    return `${name}(${[...pos, ...kw].join(', ')})`
  }

  export function PlaygroundWidget({ widget, onOpenCitation, lang }: Props) {
    const slot = useSyncExternalStore(subscribe, getState)
    const [previewing, setPreviewing] = useState(false)

    const fn = widget.function_ref
    const myKey = `${fn.file}:${fn.name}:${fn.line ?? ''}`
    const isMine = slot.kind !== 'empty' && slot.widgetKey === myKey
    const fileLine = `${fn.file}${fn.line ? `:${fn.line}` : ''}`
    // The REAL model-proposed invocation (D2): the pre-rendered text if the floor
    // emitted it, else built from the structured descriptor. Never a fake "name(…)".
    const proposedCall = widget.call_text ?? callTextOf(fn.name, widget.call)

    // On confirm the (possibly edited) free text flows through as call_text (D2);
    // the structured descriptor rides along for the backend's repr-literal guard.
    const doLaunch = (callText: string) => {
      setPreviewing(false)
      void launch(myKey, {
        source: 'cuaderno',
        function_ref: fn,
        suggested_inputs: widget.suggested_inputs,
        breadcrumb: widget.breadcrumb,
        call: widget.call,
        call_text: callText,
      })
    }

    // trace: the React stepper
    if (isMine && slot.kind === 'trace') {
      return <Stepper response={slot.response} onClose={close} lang={lang} />
    }

    // live: fallback Marimo iframe box (unchanged path) + surviving context band
    if (isMine && slot.kind === 'live') {
      return (
        <div className="widget">
          <div className="widget-head">
            <span>
              <span className="kind">playground</span> ·{' '}
              <span className="widget-head-name">{fn.name}</span>
            </span>
            <button className="playground-close" onClick={close} title="close">×</button>
          </div>
          {widget.breadcrumb || widget.citation ? (
            <div className="playground-live-context">
              {widget.breadcrumb ? (<span className="playground-breadcrumb">{widget.breadcrumb}</span>) : null}
              {widget.citation ? (<CitationChip citation={widget.citation} onClick={onOpenCitation} />) : null}
            </div>
          ) : null}
          <div className="playground-live">
            <iframe
              src={slot.iframeUrl}
              sandbox="allow-scripts allow-same-origin allow-forms"
              title={fn.name}
            />
          </div>
        </div>
      )
    }

    // spawning: capture in progress
    if (isMine && slot.kind === 'spawning') {
      return <Spawning funcName={fn.name} callText={proposedCall} lang={lang} />
    }

    // ended/evicted/error: single relaunchable card
    if (isMine && slot.kind === 'ended') {
      return (
        <EndedCards
          funcName={fn.name}
          reason={slot.reason}
          message={slot.reason === 'error' ? slot.message : undefined}
          onRetry={() => setPreviewing(true)}
          onClose={close}
          lang={lang}
        />
      )
    }

    // preview-call: shown before any real code runs
    if (previewing) {
      return (
        <PreviewCall
          funcName={fn.name}
          initialCall={proposedCall}
          onConfirm={doLaunch}
          onCancel={() => setPreviewing(false)}
          lang={lang}
        />
      )
    }

    // idle invitation (default)
    return (
      <IdleInvitation
        funcName={fn.name}
        fileLine={fileLine}
        onStepThrough={() => setPreviewing(true)}
        onClose={close}
        lang={lang}
      />
    )
  }
  ```

- [ ] **Step 4: Run the tests (expected PASS).** Run:
  ```bash
  cd frontend && npm test -- src/components/cuaderno/widgets/PlaygroundWidget.test.tsx
  ```
  Expect: passing.

- [ ] **Step 5: Run the full suite + type-check + build.** Run:
  ```bash
  cd frontend && npm test && npx tsc -b && npx vite build
  ```
  Expect: all tests pass, no type errors, build succeeds.

- [ ] **Step 6: Commit.**
  ```bash
  cd frontend && git add src/components/cuaderno/widgets/PlaygroundWidget.tsx src/components/cuaderno/widgets/PlaygroundWidget.test.tsx && git commit -m "$(cat <<'EOF'
  feat(cuaderno): PlaygroundWidget drives idle/preview/spawning/stepper/fallback/ended; real call + free-text override

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 11: Manual pixel-fidelity checklist (light + dark, all 8 states)

**Files:** none (verification task — no code). Pixel-fidelity cannot be unit-tested; this is the explicit manual checklist against the handoff `docs/superpowers/specs/2026-06-16-cuaderno-playground-stepthrough-handoff/Cuaderno Step-Through.dc.html`. (Every *behavioral* requirement already has a real test in Tasks 4–10; this task covers only the visual fidelity those tests can't assert.)

- [ ] **Step 1: Build + serve for visual inspection.** Run:
  ```bash
  cd frontend && npm run dev
  ```
  Open the cuaderno, trigger a playground widget (or mount the stepper against a fixture trace), and toggle `.theme-dark` on the root.

- [ ] **Step 2: Walk the checklist — verify EACH against the handoff, in light AND dark.** Tick only after eyeballing both themes:
  - [ ] **Tokens:** `--neg`/`--neg-ink`/`--neg-line` render the raised band sienna-red (hue 30), distinct from the sienna accent (hue 45); no cyan/amber/pure-red anywhere.
  - [ ] **01 Idle:** body 430px; eyebrow "Anchored function"; mono fn name 19px; location 11px ink-4; primary "Step through →" with accent-soft bg → accent on hover; run-note + honesty footer.
  - [ ] **02 Preview-call:** lead "I'll step through this call:"; read-only box showing the REAL proposed call with ✎ top-right (28×28, right padding 46px); ✎ → free-text textarea (mono 14px, surface-2, accent-line border, 62px); footer primary "Step through" + "Edit call" + ghost "Cancel"; body 430px.
  - [ ] **03 Spawning:** head has NO counter and NO close button; 220×4 sweep track with 34% accent-line bar animating; "Preparing… running once · capturing trace" with the pulse on the second span; body 430px.
  - [ ] **04 Stepping (hero):** body 480px; source flex 1.55, divider 1px hairline-soft margin 0 16px, state flex 1; line/row height 26px; slab `accent-soft` + 2px accent left border at `curIdx*26`, slides .22s; counter `step N / M` tabular-nums in head; changed values accent-ink + visible ◆, unchanged ink-4 + ◆ opacity 0 (no reflow); large chip `summary meta ▸` expands to indented children; scrubber track 3px, fill accent-line, 13×13 handle (2px surface border), change ticks 2px×11px; `next change ◆` plain bordered button; honesty note.
  - [ ] **05 Truncated:** banner between head and body (surface-2 bg, 3px×13px accent tick) "Stopped at step N — trace truncated."; body 404px; track fill `left:0 right:14%`, hatched fold band at `right:0 width:14%`, handle at 86%; ▶ dimmed (ink-4). (The hatched band here is the truncation marker, not a loop-fold — kept.)
  - [ ] **06 Fallback:** callout (surface-2, dot) with the can't-step reason; Input box; centered ↓; Output **dashed** box ink-3; `▸ source` footer; iframe mounts in the live path (this state is the existing Marimo box, not the React stepper).
  - [ ] **07 Raised:** banner `--neg` bg + `--neg-ink` tick "Raised — this is the final step."; slab uses `--neg`/`--neg-ink` at the raise line; body 404px; raised card (`--neg` bg, `--neg-line` border) with "raised" eyebrow + `KeyError: 'ghost'`; track fully filled, handle at 100% colored `--neg-ink`; ▶ dimmed.
  - [ ] **08 Ended/Evicted/Spawn-error:** the matching single card — chip square 8×8 (ink-4 for closed/evicted, neg-ink @ .7 for spawn error), uppercase title, body copy, ghost relaunch button ("Reopen"/"Bring it back"/"Try again").
  - [ ] **Large-value study:** dict expands to keys; DataFrame expands to "schema · 4 of 12 columns" + "1000 rows not serialized — schema only."; list expands to `[0]…[4]` + "+N more · capped at capture."; opaque shows dashed `‹Connection›`. (Driven by `buildRows` expand-on-demand; the loop-specific fixture from the handoff is NOT ported.)
  - [ ] **Long-trace navigation:** change markers on the track (`markerLefts`); `next change ◆` jumps to the next non-empty `changed` step and skips no-change steps. **NOTE (D3):** loop-fold bands, the fold chip, and the `iter {iter}` header are descoped to v1.1 and must NOT appear in the shipped stepper.
  - [ ] **Motion split:** position (slab top, track width, handle left) eases `.22s cubic-bezier(.4,0,.2,1)`; color (values, code lines, chip border) eases `.3s ease`.
  - [ ] **Stale-anchor (spec §7):** when a trace line is absent from `source_lines`, NO highlight slab renders (the source still lists; no line is bolded). This is the deferred §7 limitation — highlight drift is not solved here, only suppressed.

- [ ] **Step 3: Fix any drift, re-run tests, commit.** For each mismatch, correct the inline style/CSS to match the handoff exactly, then:
  ```bash
  cd frontend && npm test && npx tsc -b
  ```
  Expect: green. Commit any fixes:
  ```bash
  cd frontend && git add -A && git commit -m "$(cat <<'EOF'
  fix(cuaderno): pixel-fidelity corrections from the handoff checklist

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```
  (Skip the commit if the checklist found no drift.)

---

### Task 12: Self-review checklist (writing-plans gate)

**Files:** none (review task).

- [ ] **Step 1: Verify every referenced type/function is defined in some task.** Confirm: `Step`/`Var`/`CallDescriptor`/`StepThroughResponse`/`FallbackResponse`/`PlaygroundLaunchResult` + the widened `PlaygroundLaunchRequest`/`PlaygroundWidgetData` (Task 3); slot `'trace'` kind + `idFromIframeUrl` (Task 4); `clampStep`/`nextChange`/`trackFraction`/`lineModels`/`mkRow`/`buildRows`/`markerLefts`/`ROW_H`/`RowModel`/`LineModel` (Task 5); strings keys (Task 6); `s()`/`StateRow` (Task 7); `Stepper` (Task 8); `IdleInvitation`/`PreviewCall`/`Spawning`/`EndedCards` + stepper CSS (Task 9); widget dispatch + `callTextOf` (Task 10). No reference to any deleted loop-fold symbol (`loopStops`/`loopSource`/`loopBands`/`foldLabel`/`loopMarkers`/`loopIdx`/`loopMove`) remains anywhere in the plan or code.

- [ ] **Step 2: Verify the three ratified decisions hold.** Confirm: **D1** — no `json-tracer` reference; the frontend only consumes the emitted schema. **D2** — the Preview-call is a free-text textarea; `proposedCall` is the REAL invocation (`widget.call_text` / `callTextOf(widget.call)`), never `name(…)`; `onConfirm(callText)` flows the edited text into `launch` as `call_text` (tested in Task 9 + Task 10). **D3** — no fold-band UI, no fold chip, no `iter` header, no loop fixture; `markerLefts` + `nextChange` are the only long-trace aids and run off the flat `Step[]`.

- [ ] **Step 3: Verify TDD discipline.** Confirm each behavioral task has: failing test → run (FAIL) → minimal impl → run (PASS) → commit. (Tasks 2/3 are token/type-only — they verify via build/tsc, not a unit test, which is correct since there is no runtime behavior to assert. Task 11 is the explicitly-manual pixel checklist.)

- [ ] **Step 4: Verify DRY/YAGNI + no support.js.** Confirm: the `s()` style-string parser lives in one place (`StateRow.tsx`) and is reused; `trace.ts` is the single source of stepping math (no duplicated geometry in components); the legacy iframe path is reused verbatim for fallback (not reimplemented); the handoff's `support.js` is NOT shipped (we re-implemented the `Component` logic in TS); no speculative features (no hover tooltips, no heap diagram, no loop fold — all out of scope).

- [ ] **Step 5: Verify the full suite + build one final time.** Run:
  ```bash
  cd frontend && npm test && npx tsc -b && npx vite build
  ```
  Expect: all green. This is the final gate before the branch is finishable.

---

## Remaining gaps (carry into review, not blockers for this plan)

- **`PlaygroundWidgetData.call` / `call_text` are emitted by the backend floor/prompts.** This frontend plan assumes the widget payload carries the real proposed call (D2, spec §6). The backend plan owns producing `call`/`call_text`; if a widget arrives without them, `callTextOf` degrades to `name(args…)` from the structured descriptor, or `name()` if neither is present — the preview is still editable, so the user can always type the real call. (Honest degradation, not a crash.)
- **`call_text` execution semantics are the backend's.** The frontend passes the free text verbatim; the backend exec's it in the module namespace under the caps (spec §10, D2). No frontend-side validation beyond surfacing it for consent.
- **Stale-anchor highlight drift (spec §7) is deferred.** This plan only *suppresses* the slab on a miss (`curIdx < 0`); it does not re-anchor a moved line. Solving drift (re-mapping captured line numbers to current source) is out of scope for v1.
