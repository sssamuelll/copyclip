# Cruces / Junctions v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the cuaderno step-through, mark which `if`/`elif`/`else` arm the run crossed — as a computed structural overlay on the source pane, never narrated.

**Architecture:** A new pure module `compute_junctions` reads the target function's AST plus the executed-line set the tracer already records, and returns a per-arm `taken` tri-state (`true`/`false`/`null`). An additive `junctions` field rides on the existing `StepThroughResponse`; the Stepper dims not-taken arms and draws a gutter chip on the crossed arm. No capture-pipeline change — it reads a completed trace.

**Tech Stack:** Python (`ast`, `dataclasses`) + pytest backend; React/TypeScript + vitest frontend.

**Spec:** `docs/superpowers/specs/2026-07-02-cuaderno-cruces-junctions-design.md`

## Global Constraints

- **v0.1 scope:** `if` / `elif` / `else` only. No loops, `try`/`except`, ternary, `match`, boolean short-circuit.
- **Tri-state `taken`:** `true` | `false` | `null`. When the trace was `truncated`, an arm with no executed lines is `null` (unknown) — **never** `false`. Claiming "did not run" over a cut-short trace is forbidden (*exposición, no autoría*).
- **Scope exclusion:** never emit junctions for `if`s inside nested `def`/`async def`/`class` bodies — those have their own code object and are not traced, so we cannot say which arm ran.
- **Additive & optional:** `junctions` defaults to `[]` on the backend and is `junctions?:` on the frontend; absent/empty → the Stepper behaves exactly as today.
- **Structural only:** the overlay is dim + a `→ kind` chip. No prose, no narration, no advice.
- **`compute_junctions` is pure and I/O-free:** it takes source text, never reads the filesystem. The file read lives in the playground caller.
- **Line alignment:** junction line numbers are absolute (whole-file `ast.parse`), matching `source_lines[].num` and `Step.line`.

---

### Task 1: The pure `compute_junctions` module

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/junctions.py`
- Test: `tests/test_junctions.py`

**Interfaces:**
- Consumes: nothing (pure; stdlib `ast` only).
- Produces: `compute_junctions(source: str, func_line: int | None, func_name: str, executed_lines: set[int], truncated: bool) -> list[dict]`. Each element is `{"test_line": int, "arms": [{"kind": "if"|"elif"|"else", "lines": [int, int], "taken": bool | None}, ...]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_junctions.py
from copyclip.intelligence.cuaderno.junctions import compute_junctions

SRC_IF_ELSE = (
    "\n"
    "def f(x):\n"          # line 2
    "    if x > 0:\n"      # line 3
    "        a = 1\n"      # line 4
    "        b = 2\n"      # line 5
    "    else:\n"          # line 6
    "        a = -1\n"     # line 7
    "    return a\n"       # line 8
)

SRC_LADDER = (
    "\n"
    "def g(x):\n"          # 2
    "    if x == 1:\n"     # 3
    "        r = 'a'\n"    # 4
    "    elif x == 2:\n"   # 5
    "        r = 'b'\n"    # 6
    "    else:\n"          # 7
    "        r = 'c'\n"    # 8
    "    return r\n"       # 9
)

SRC_BARE_IF = (
    "\n"
    "def h(x):\n"          # 2
    "    y = 0\n"          # 3
    "    if x:\n"          # 4
    "        y = 1\n"      # 5
    "    return y\n"       # 6
)

SRC_NESTED = (
    "\n"
    "def n(x):\n"          # 2
    "    if x > 0:\n"      # 3
    "        if x > 10:\n" # 4
    "            a = 2\n"  # 5
    "        else:\n"      # 6
    "            a = 1\n"  # 7
    "    else:\n"          # 8
    "        a = 0\n"      # 9
    "    return a\n"       # 10
)

SRC_NESTED_DEF = (
    "\n"
    "def outer(x):\n"          # 2
    "    def inner(y):\n"      # 3
    "        if y:\n"          # 4
    "            return 1\n"   # 5
    "        return 0\n"       # 6
    "    if x:\n"              # 7
    "        return inner(x)\n"# 8
    "    return -1\n"          # 9
)


def test_if_else_took_if():
    j = compute_junctions(SRC_IF_ELSE, 2, "f", {3, 4, 5, 8}, False)
    assert j == [{"test_line": 3, "arms": [
        {"kind": "if", "lines": [4, 5], "taken": True},
        {"kind": "else", "lines": [7, 7], "taken": False},
    ]}]


def test_if_else_took_else():
    j = compute_junctions(SRC_IF_ELSE, 2, "f", {3, 7, 8}, False)
    arms = j[0]["arms"]
    assert arms[0]["taken"] is False
    assert arms[1]["taken"] is True


def test_ladder_took_elif():
    j = compute_junctions(SRC_LADDER, 2, "g", {3, 5, 6, 9}, False)
    assert j == [{"test_line": 3, "arms": [
        {"kind": "if", "lines": [4, 4], "taken": False},
        {"kind": "elif", "lines": [6, 6], "taken": True},
        {"kind": "else", "lines": [8, 8], "taken": False},
    ]}]


def test_bare_if_no_else():
    j = compute_junctions(SRC_BARE_IF, 2, "h", {3, 4, 6}, False)
    assert j == [{"test_line": 4, "arms": [
        {"kind": "if", "lines": [5, 5], "taken": False},
    ]}]


def test_truncated_yields_unknown_not_false():
    # only the test line was reached before the cap
    j = compute_junctions(SRC_IF_ELSE, 2, "f", {3}, True)
    arms = j[0]["arms"]
    assert arms[0]["taken"] is None
    assert arms[1]["taken"] is None


def test_nested_if_inside_taken_arm():
    # outer took the if-arm; inner took its else-arm
    j = compute_junctions(SRC_NESTED, 2, "n", {3, 4, 7, 10}, False)
    outer = next(x for x in j if x["test_line"] == 3)
    inner = next(x for x in j if x["test_line"] == 4)
    assert outer["arms"][0]["taken"] is True     # if-arm (lines 4..7)
    assert outer["arms"][1]["taken"] is False    # else-arm (line 9)
    assert inner["arms"][0]["taken"] is False    # inner if (line 5)
    assert inner["arms"][1]["taken"] is True     # inner else (line 7)


def test_if_in_nested_def_excluded():
    # inner()'s `if y:` must NOT appear — nested defs are not traced
    j = compute_junctions(SRC_NESTED_DEF, 2, "outer", {7, 8}, False)
    assert all(x["test_line"] != 4 for x in j)
    assert [x["test_line"] for x in j] == [7]


def test_no_if_returns_empty():
    src = "\ndef p(x):\n    return x + 1\n"
    assert compute_junctions(src, 2, "p", {3}, False) == []


def test_syntax_error_returns_empty():
    assert compute_junctions("def broken(:\n", 1, "broken", set(), False) == []


def test_target_not_found_returns_empty():
    assert compute_junctions(SRC_IF_ELSE, 999, "missing", {3}, False) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_junctions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'copyclip.intelligence.cuaderno.junctions'`

- [ ] **Step 3: Write the module**

```python
# src/copyclip/intelligence/cuaderno/junctions.py
"""Cruces / Junctions v0.1 — executed-arm overlay over the step-through.

Pure, I/O-free control-flow reading of a completed trace: for each
if/elif/else in the target function, mark which arm the run crossed (taken),
which it did not (not-taken), and — when the trace was truncated — which we
cannot say (unknown). A branch not taken simply produced no trace events.

See docs/superpowers/specs/2026-07-02-cuaderno-cruces-junctions-design.md.
"""
from __future__ import annotations

import ast


def compute_junctions(
    source: str,
    func_line: int | None,
    func_name: str,
    executed_lines: set[int],
    truncated: bool,
) -> list[dict]:
    """Return the if/elif/else junctions of the target function, each arm tagged
    taken=True|False|None. Fails open to [] on any parse/lookup problem so the
    feature is invisible rather than wrong."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    target = _find_func(tree, func_line, func_name)
    if target is None:
        return []
    out: list[dict] = []
    _junctions_in_scope(target.body, executed_lines, truncated, out)
    return out


def _find_func(tree: ast.AST, func_line: int | None, func_name: str):
    funcs = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if func_line is not None:
        for n in funcs:
            if n.lineno == func_line:
                return n
    named = [n for n in funcs if n.name == func_name]
    return named[0] if len(named) == 1 else None


def _arm(kind: str, body: list, executed: set[int], truncated: bool) -> dict:
    lo = body[0].lineno
    hi = body[-1].end_lineno
    hit = any(lo <= line <= hi for line in executed)
    if hit:
        taken: bool | None = True
    elif truncated:
        taken = None      # unknown — the trace stopped early; do not claim "did not run"
    else:
        taken = False
    return {"kind": kind, "lines": [lo, hi], "taken": taken}


def _build_ladder(node: ast.If, executed: set[int], truncated: bool) -> dict:
    arms = [_arm("if", node.body, executed, truncated)]
    orelse = node.orelse
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_node = orelse[0]
        arms.append(_arm("elif", elif_node.body, executed, truncated))
        orelse = elif_node.orelse
    if orelse:
        arms.append(_arm("else", orelse, executed, truncated))
    return {"test_line": node.lineno, "arms": arms}


def _ladder_bodies(node: ast.If) -> list[list]:
    """The arm bodies of the ladder, for recursing into nested ifs WITHOUT
    re-treating the elif If-nodes as their own top-level junctions."""
    bodies = [node.body]
    orelse = node.orelse
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_node = orelse[0]
        bodies.append(elif_node.body)
        orelse = elif_node.orelse
    if orelse:
        bodies.append(orelse)
    return bodies


def _generic_child_bodies(node: ast.AST) -> list[list]:
    """Statement-list bodies to descend for nested ifs in the SAME scope
    (For/While/With/Try). Non-If compound statements only — If is handled by
    _build_ladder + _ladder_bodies."""
    out: list[list] = []
    for field in ("body", "orelse", "finalbody"):
        val = getattr(node, field, None)
        if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
            out.append(val)
    for handler in getattr(node, "handlers", []) or []:
        if handler.body:
            out.append(handler.body)
    return out


def _junctions_in_scope(stmts: list, executed: set[int], truncated: bool, out: list[dict]) -> None:
    for node in stmts:
        # Nested defs/classes have their OWN code object and are not traced
        # (frame-scoping, _capture_driver.py) — we cannot say which of their
        # branches ran, so we never emit junctions for them.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.If):
            out.append(_build_ladder(node, executed, truncated))
            for body in _ladder_bodies(node):
                _junctions_in_scope(body, executed, truncated, out)
        else:
            for body in _generic_child_bodies(node):
                _junctions_in_scope(body, executed, truncated, out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_junctions.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/junctions.py tests/test_junctions.py
git commit -m "feat(cuaderno): compute_junctions — if/elif/else executed-arm reading (Cruces v0.1)"
```

---

### Task 2: Wire `junctions` onto the step-through response

**Files:**
- Modify: `src/copyclip/intelligence/capture.py` (imports; `StepThroughResponse` at :233; `to_dict` at :245)
- Modify: `src/copyclip/intelligence/playground.py` (add helper; thread into the `StepThroughResponse(...)` return at :625)
- Test: `tests/test_junctions_wiring.py`

**Interfaces:**
- Consumes: `compute_junctions(...)` from Task 1; `StepThroughResponse`, `Step`, `ResolvedFunction` (existing).
- Produces: `StepThroughResponse.junctions: list[dict]` (default `[]`), serialized as `"junctions"` in `to_dict()`. Helper `_junctions_for(resolved, project_root, executed_lines, truncated) -> list[dict]` in `playground.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_junctions_wiring.py
import os
import textwrap

from copyclip.intelligence.capture import StepThroughResponse, Step
from copyclip.intelligence import playground as pg
from copyclip.intelligence.playground import ResolvedFunction


def test_to_dict_includes_junctions():
    resp = StepThroughResponse(
        trace=[Step(line=3, event="line", changed=[], scope=[])],
        source_lines=[{"num": 3, "text": "if x:"}],
        func_name="f", file_line="a.py:2", truncated=False, truncated_reason=None,
        junctions=[{"test_line": 3, "arms": [{"kind": "if", "lines": [4, 4], "taken": True}]}],
    )
    d = resp.to_dict()
    assert d["junctions"] == [{"test_line": 3, "arms": [{"kind": "if", "lines": [4, 4], "taken": True}]}]


def test_to_dict_junctions_defaults_empty():
    resp = StepThroughResponse(
        trace=[], source_lines=[], func_name="f", file_line="a.py:1",
        truncated=False, truncated_reason=None,
    )
    assert resp.to_dict()["junctions"] == []


def test_junctions_for_reads_file_and_computes(tmp_path):
    src = textwrap.dedent(
        """\
        def f(x):
            if x > 0:
                a = 1
            else:
                a = -1
            return a
        """
    )
    (tmp_path / "m.py").write_text(src, encoding="utf-8")
    resolved = ResolvedFunction(
        file="m.py", name="f", qualname="f", kind="function",
        module="m", line_start=1, parent_class=None,
    )
    j = pg._junctions_for(resolved, str(tmp_path), {2, 3, 6}, False)
    assert j == [{"test_line": 2, "arms": [
        {"kind": "if", "lines": [3, 3], "taken": True},
        {"kind": "else", "lines": [5, 5], "taken": False},
    ]}]


def test_junctions_for_missing_file_returns_empty():
    resolved = ResolvedFunction(
        file="nope.py", name="f", qualname="f", kind="function",
        module="m", line_start=1, parent_class=None,
    )
    assert pg._junctions_for(resolved, os.getcwd(), {1}, False) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_junctions_wiring.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'junctions'` and `AttributeError: module ... has no attribute '_junctions_for'`

- [ ] **Step 3a: Add the field + serialization in `capture.py`**

At the top of `capture.py`, ensure `field` is imported (the dataclasses import currently reads `from dataclasses import dataclass`):

```python
from dataclasses import dataclass, field
```

Replace the `StepThroughResponse` dataclass (capture.py:232-254) with:

```python
@dataclass(frozen=True)
class StepThroughResponse:
    trace: list[Step]
    source_lines: list[dict[str, Any]]
    func_name: str
    file_line: str
    truncated: bool
    # PR #177 fix 5: split the bare `truncated` bool into a REASON so the frontend
    # shows the right message — 'steps' (MAX_STEPS overflow) vs 'time' (wall-clock
    # overrun) — and never conflates truncation with a terminal raise. None when
    # the trace completed cleanly.
    truncated_reason: str | None = None
    # Cruces v0.1: if/elif/else arms with taken=True|False|None, computed from
    # the target AST + the executed-line set. Additive; [] means no junctions.
    junctions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "trace",
            "trace": [s.to_dict() for s in self.trace],
            "source_lines": self.source_lines,
            "func_name": self.func_name,
            "file_line": self.file_line,
            "truncated": self.truncated,
            "truncated_reason": self.truncated_reason,
            "junctions": list(self.junctions),
        }
```

- [ ] **Step 3b: Add the helper + thread it in `playground.py`**

Add this helper near the other module-level helpers in `playground.py` (e.g. after `_module_from_file`):

```python
def _junctions_for(
    resolved: ResolvedFunction,
    project_root: str,
    executed_lines: set[int],
    truncated: bool,
) -> list[dict]:
    """Read the target's source and compute its if/elif/else junctions. Pure
    logic lives in cuaderno.junctions; this only supplies the source text and
    fails open to [] so a read/parse problem never breaks the step-through."""
    from .cuaderno.junctions import compute_junctions
    try:
        with open(os.path.join(project_root, resolved.file), encoding="utf-8") as fh:
            source = fh.read()
    except OSError:
        return []
    return compute_junctions(
        source, resolved.line_start, resolved.name, executed_lines, truncated
    )
```

Replace the `StepThroughResponse(...)` return (playground.py:625-627) with:

```python
        executed_lines = {s.line for s in steps if s.line}
        junctions = _junctions_for(resolved, project_root, executed_lines, truncated)
        return StepThroughResponse(
            trace=steps, source_lines=source_lines, func_name=func_name,
            file_line=file_line, truncated=truncated, truncated_reason=truncated_reason,
            junctions=junctions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_junctions_wiring.py tests/test_cuaderno_playground_floor.py -v`
Expected: PASS (new wiring tests pass; existing floor tests still green — `junctions` is additive)

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/capture.py src/copyclip/intelligence/playground.py tests/test_junctions_wiring.py
git commit -m "feat(cuaderno): thread junctions onto StepThroughResponse from the trace"
```

---

### Task 3: Frontend type — `Junction` on `StepThroughResponse`

**Files:**
- Modify: `frontend/src/types/api.ts` (`StepThroughResponse` at :678-686)

**Interfaces:**
- Produces: TS `Junction` type and optional `junctions?: Junction[]` on `StepThroughResponse`. Consumed by Task 4.

- [ ] **Step 1: Add the type**

Immediately above the `export type StepThroughResponse = {` block (api.ts:678), add:

```ts
export type Junction = {
  test_line: number
  arms: { kind: 'if' | 'elif' | 'else'; lines: [number, number]; taken: boolean | null }[]
}
```

Then add one line inside the `StepThroughResponse` object type, after `truncated_reason?: 'steps' | 'time' | null` (api.ts:685):

```ts
  junctions?: Junction[]
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no type errors; the field is optional so no call site breaks)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno): Junction type on StepThroughResponse (frontend contract)"
```

---

### Task 4: Stepper overlay — dim not-taken arms + the crossed-arm chip

**Files:**
- Modify: `frontend/src/components/cuaderno/stepper/trace.ts` (add `junctionOverlay`)
- Modify: `frontend/src/components/cuaderno/stepper/Stepper.tsx` (apply the overlay in the source-line map, :144-159)
- Test: `frontend/src/components/cuaderno/stepper/trace.test.ts`

**Interfaces:**
- Consumes: `Junction` (Task 3).
- Produces: `junctionOverlay(junctions?: Junction[]): { role: Record<number, 'not-taken' | 'unknown'>; chips: Record<number, string> }`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/components/cuaderno/stepper/trace.test.ts
import { describe, it, expect } from 'vitest'
import { junctionOverlay } from './trace'
import type { Junction } from '../../../types/api'

describe('junctionOverlay', () => {
  it('dims not-taken arm bodies and chips the crossed arm', () => {
    const j: Junction[] = [{
      test_line: 3,
      arms: [
        { kind: 'if', lines: [4, 5], taken: true },
        { kind: 'else', lines: [7, 7], taken: false },
      ],
    }]
    const { role, chips } = junctionOverlay(j)
    expect(role[4]).toBeUndefined()   // taken arm: normal
    expect(role[5]).toBeUndefined()
    expect(role[7]).toBe('not-taken') // else body dimmed
    expect(chips[3]).toBe('→ if')
  })

  it('marks unknown arms distinctly under truncation', () => {
    const j: Junction[] = [{
      test_line: 3,
      arms: [
        { kind: 'if', lines: [4, 4], taken: null },
        { kind: 'else', lines: [6, 6], taken: null },
      ],
    }]
    const { role, chips } = junctionOverlay(j)
    expect(role[4]).toBe('unknown')
    expect(role[6]).toBe('unknown')
    expect(chips[3]).toBeUndefined()  // nothing crossed → no chip
  })

  it('suppresses the chip for a junction inside a dimmed (dead) range', () => {
    // outer took the else-arm (lines 8..9); the inner if at line 8 is dead code
    const j: Junction[] = [
      { test_line: 3, arms: [
        { kind: 'if', lines: [4, 5], taken: false },
        { kind: 'else', lines: [8, 9], taken: true },
      ] },
      { test_line: 4, arms: [   // nested inside the not-taken if-arm (4..5)
        { kind: 'if', lines: [5, 5], taken: false },
      ] },
    ]
    const { chips } = junctionOverlay(j)
    expect(chips[4]).toBeUndefined() // line 4 is inside the dimmed 4..5 range
  })

  it('returns empty maps for undefined junctions', () => {
    expect(junctionOverlay(undefined)).toEqual({ role: {}, chips: {} })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/cuaderno/stepper/trace.test.ts`
Expected: FAIL — `junctionOverlay is not a function`

- [ ] **Step 3: Implement `junctionOverlay` in `trace.ts`**

Add to the top imports of `trace.ts` (it already imports `Step`):

```ts
import type { Step, Junction } from '../../../types/api'
```

(If `trace.ts` currently imports only `Step`, extend that import to include `Junction`; otherwise add the line above.)

Append to `trace.ts`:

```ts
export type LineRole = 'not-taken' | 'unknown'
export type JunctionOverlay = { role: Record<number, LineRole>; chips: Record<number, string> }

// Static per-run overlay: dim the body lines of arms the run did not take
// (or could not observe, under truncation), and chip the crossed arm on its
// junction's test line. A junction whose test line is itself inside a dimmed
// range is dead code for this run, so it gets no chip.
export function junctionOverlay(junctions?: Junction[]): JunctionOverlay {
  const role: Record<number, LineRole> = {}
  const chips: Record<number, string> = {}
  if (!junctions) return { role, chips }
  for (const j of junctions) {
    for (const arm of j.arms) {
      if (arm.taken === true) continue
      const r: LineRole = arm.taken === null ? 'unknown' : 'not-taken'
      for (let n = arm.lines[0]; n <= arm.lines[1]; n++) {
        if (!(n in role)) role[n] = r   // outer (processed first) wins over nested
      }
    }
  }
  for (const j of junctions) {
    if (j.test_line in role) continue   // junction sits inside dead code this run
    const taken = j.arms.find((a) => a.taken === true)
    if (taken) chips[j.test_line] = `→ ${taken.kind}`
  }
  return { role, chips }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/cuaderno/stepper/trace.test.ts`
Expected: PASS (4 passed)

- [ ] **Step 5: Apply the overlay in `Stepper.tsx`**

Add `junctionOverlay` to the existing `./trace` import (Stepper.tsx:4-6) and `useMemo` (already imported at :1). After `const markers = markerLefts(trace)` (:62), add:

```tsx
  // Cruces v0.1: static per-run branch overlay. Suppressed when the source
  // anchor is stale (same guard the current-step highlight uses).
  const overlay = useMemo(
    () => (staleAnchor ? { role: {}, chips: {} } : junctionOverlay(response.junctions)),
    [response.junctions, staleAnchor],
  )
```

Replace the source-line map (Stepper.tsx:152-157) with:

```tsx
              {lines.map((ln) => {
                const dim = overlay.role[ln.num]
                const chip = overlay.chips[ln.num]
                return (
                  <div key={ln.num} style={s('display:flex;height:26px;position:relative;')}>
                    <span style={s(ln.numStyle)}>{ln.num}</span>
                    <span style={{ ...s(ln.codeStyle), ...(dim ? { opacity: dim === 'unknown' ? 0.5 : 0.34 } : {}) }}>{ln.code}</span>
                    {chip && (
                      <span style={s('position:absolute;right:6px;top:0;font-family:var(--font-ui);font-size:10px;letter-spacing:.04em;color:var(--accent-ink);opacity:.85;')}>{chip}</span>
                    )}
                  </div>
                )
              })}
```

- [ ] **Step 6: Typecheck + run the full stepper suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/components/cuaderno/stepper/`
Expected: PASS (typecheck clean; trace tests pass; existing stepper tests unaffected)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/cuaderno/stepper/trace.ts frontend/src/components/cuaderno/stepper/trace.test.ts frontend/src/components/cuaderno/stepper/Stepper.tsx
git commit -m "feat(cuaderno): Stepper renders the Cruces overlay — dim not-taken arms + crossed-arm chip"
```

---

## Self-Review

**1. Spec coverage:**
- §2 scope (if/elif/else, tri-state, static overlay) → Task 1 (logic) + Task 4 (render). ✓
- §4 contract (`{test_line, arms:[{kind, lines, taken}]}`, optional frontend field) → Task 1 shape + Task 2 serialization + Task 3 type. ✓
- §5 AST extraction (whole-file parse, absolute lines, elif chain, find by line_start) → Task 1 `_find_func` / `_build_ladder`; file read in Task 2 `_junctions_for`. ✓
- §6 taken/not-taken/unknown + `line==0` exclusion → Task 1 `_arm`; Task 2 `{s.line for s in steps if s.line}`. ✓
- §7 nesting + scope exclusion → Task 1 `_junctions_in_scope` (skip nested defs) + Task 1 `test_if_in_nested_def_excluded`; chip suppression in Task 4. ✓
- §8 render (dim + chip, staleAnchor suppression, absent→today) → Task 4. ✓
- §9 files touched → matches Tasks 1-4. ✓
- §10 testing (pure core cases + frontend overlay + no existing-test change) → Task 1 suite, Task 4 vitest, Task 2 re-runs floor tests. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; test bodies are concrete. ✓

**3. Type consistency:** `compute_junctions` signature identical in Task 1 (def), Task 2 (call in `_junctions_for`), and the spec. `junctions` field name identical across capture.py, playground.py, api.ts. `junctionOverlay` return shape identical between Task 4 def, its test, and the Stepper `useMemo`. `taken` is `bool | None` (Py) / `boolean | null` (TS) consistently. ✓

## Execution Handoff

Two execution options — chosen after you review the plan.
