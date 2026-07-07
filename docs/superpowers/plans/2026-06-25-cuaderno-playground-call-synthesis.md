# Cuaderno Playground — Stage-1 Call Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cuaderno playground auto-fill a runnable call by lifting a real, fully-literal call-site from the codebase (preferring `tests/`), with AST re-verification that the lifted call truly binds to the target symbol — so a developer hits "Step through" with no typing.

**Architecture:** A new pure backend unit `cuaderno/call_synth.py` exposes `synthesize_call(resolved, conn, project_id, project_root) -> SynthesizedCall | None`. It re-finds the target's `symbols.id`, walks `symbol_edges` `'calls'` rows to candidate callers, then — because that edge is name-based and can bind to a same-named symbol in another module — re-parses each caller's source with `ast`, confirms the call binds to THIS symbol via the caller's imports/class context, and lifts the call's args/kwargs (and, for a method, a literal-constructed `ctor`) only when they are `ast.literal_eval`-able literals. The floor (`_construct_playground_floor`) calls it when the bare `name()` floor would otherwise need args; on a hit it folds the literals into the widget's `call`/`call_text` and stamps `arg_source="tests"`; on `None` it keeps today's `needs_args` template and stamps `arg_source="manual"`. The frontend renders a two-value provenance chip.

**Tech Stack:** Python 3.12 stdlib only (`ast`, `json`, `sqlite3`, `dataclasses`, `os`) — no new backend deps. Frontend: React + TypeScript, Vitest + @testing-library/react.

## Global Constraints

- **No new dependencies.** Backend uses only the stdlib already imported in the package; frontend adds no packages.
- **`synthesize_call` is pure and best-effort:** DB reads + `ast` only — no model, no network, no subprocess. It MUST NEVER raise into the floor; any failure (no edge, unparseable caller, unconfirmed binding, no fully-literal call) returns `None`. (Spec §7.)
- **Only real-usage input ships:** lifted values MUST be `ast.literal_eval`-able literals that are JSON-serializable with `allow_nan=False` (matching `capture.CallDescriptor`'s gate). No free names, no fixtures, no fabrication. (Spec §2.3, §6.)
- **`arg_source` has exactly two values in this work: `"tests"` | `"manual"`.** No third value; never silently defaulted to a fabrication. (Spec §4.)
- **`file_path` is POSIX-relative (forward slashes) even on Windows.** Read source via `os.path.join(project_root, resolved.file)`. (analyzer.py:221.)
- **Spanish UI copy uses Venezuelan tuteo** (e.g. `completa la llamada`, never `completá`). Add new i18n keys to BOTH `es` and `en` maps. (User CLAUDE.md.)
- **Frozen dataclasses** for `SynthesizedCall` and internal records (match the codebase convention; `ResolvedFunction`/`CallDescriptor` are frozen).

## Design decisions & documented deviations from the spec

1. **Signature adds `project_id`.** The spec sketches `synthesize_call(resolved, conn, project_root)`, but `ResolvedFunction` carries **no** `symbol_id` (`resolve_function_ref` never SELECTs `symbols.id`) and `symbols`/`symbol_edges` are keyed by `project_id` (int), not `project_root`. The floor (`_construct_playground_floor`) already has `project_id` in scope, so we pass it: `synthesize_call(resolved, conn, project_id, project_root)`. This honors the spec's intent ("DB + ast") and avoids re-deriving the id via an `abspath`-fragile `projects` query.
2. **Methods (ctor) — v1 supports the inline construction form only:** `ClassName(<literals>).method(<literals>)` (a single chained call). This is the canonical "literal-constructed test instance" of acceptance criterion #2. The two-statement form (`obj = ClassName(...); obj.method(...)`) needs dataflow analysis and is **deferred** → such a target falls to `manual`. (Honest: a miss → manual, never a wrong lift.)
3. **Relative-import call-sites (`from . import x`) → `manual`** in v1. Confirming a relative import requires resolving it against the caller's package; rather than risk a wrong binding, an unconfirmed relative import is conservatively skipped. Absolute imports (`from src.pkg.lib import target`, `from copyclip... import x`, `import mod`) are fully supported.
4. **Module-level (non-`def`) call-sites are not discoverable** — the analyzer writes a `'calls'` edge only when the caller is itself a function/method symbol (a top-level call has caller `<module>`, no symbol row, no edge). pytest call-sites live inside `def test_*():`, so they ARE covered; bare module-level calls fall to `manual`. (analyzer.py:783.)
5. **Module-identity ambiguity → `manual` (the false-confirm guard).** `resolved.module` is derived by `playground._module_from_file`, which strips only a leading `src/`. So two DISTINCT files can collapse to the same dotted module (e.g. `src/pkg/lib.py` and `pkg/lib.py` both → `pkg.lib`). Then an import's module string no longer pins a unique file, and a name-based `'calls'` edge + module-string confirmation could lift a call that actually targets the OTHER file — a wrong input wearing a `tests` chip (the §2.2/§8 BLOCKER). Guard: if more than one distinct file holds a symbol named `resolved.name` that maps to `resolved.module`, refuse (→ `None`/`manual`). This makes module-string confirmation sound (module == file for the target's name).
6. **A class-name run-request → `None`.** `synthesize_call` only lifts plain-function and method (inline-ctor) calls; a `kind == "class"` target returns `None` (lifting `ClassName(args)` as a plain call would have no ctor handling). In practice the floor never triggers synthesis for a class (a class name matches no `FunctionDef`, so `_floor_target_arity` is `None` and `needs_args` is False), but the guard is explicit so the function is correct if called directly.

**Synthesis trigger:** synthesis is gated on `needs_args` (a method, or an arity>0 function — `_doomed_floor_reason`), NOT the spec §3 wording "when the model did not already supply a call". This is a correct refinement: the floor (`_construct_playground_floor`) already runs ONLY when the model produced no playground at all (`_has_playground` short-circuits in `_floored_frame`, compositor.py:341), and an arity-0 function needs no synthesis (its bare `name()` floor already runs).

These are all the "no confirmed, fully-literal call-site → `manual`" path the acceptance criteria explicitly allow. **Re-verification framing:** because the analyzer writes only ONE `'calls'` edge per call-site (first-match-wins, analyzer.py:763,778), a same-name collision where the edge bound to the *other* module yields `manual` for the correct target too (no edge to walk) — re-verification reliably PREVENTS a wrong lift; it does not always RECOVER the right one. That is the honest v1 boundary.

## File Structure

- **Create** `src/copyclip/intelligence/cuaderno/call_synth.py` — the synthesizer (one responsibility: lift a verified literal call from real usage). All helpers private (`_`-prefixed) except `SynthesizedCall` + `synthesize_call`.
- **Create** `tests/test_call_synth.py` — unit tests for the synthesizer, including the cross-module same-name re-verification BLOCKER case, using a real analyzer-built DB.
- **Modify** `src/copyclip/intelligence/cuaderno/schema.py` — add an `arg_source` kwarg to `Widget.playground`.
- **Modify** `src/copyclip/intelligence/cuaderno/compositor.py` — wire `synthesize_call` into `_construct_playground_floor`.
- **Modify** `tests/test_cuaderno_playground_floor.py` — add floor-integration tests (synthesized `tests` widget vs `manual` widget).
- **Modify** `frontend/src/types/api.ts` — add `arg_source?: 'tests' | 'manual'` to `PlaygroundWidgetData`.
- **Modify** `frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx` — thread `argSource` into `PreviewCall`.
- **Modify** `frontend/src/components/cuaderno/stepper/PreviewCall.tsx` — render the provenance chip.
- **Modify** `frontend/src/components/cuaderno/strings.ts` — add chip i18n keys (en + es).
- **Modify** `frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx` — chip render tests.

---

### Task 1: `call_synth.py` scaffold — `SynthesizedCall` + DB access (target id + candidate callers)

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/call_synth.py`
- Test: `tests/test_call_synth.py`

**Interfaces:**
- Consumes: `ResolvedFunction` (playground.py:252-261 — `file, name, qualname, kind, module, line_start, parent_class`), a live `sqlite3.Connection`, `project_id: int`.
- Produces:
  - `SynthesizedCall(args: list, kwargs: dict, ctor: dict | None, arg_source: str)` — frozen dataclass.
  - `_resolve_target_symbol_id(conn, project_id, resolved) -> int | None`
  - `_Caller(name: str, kind: str, file_path: str, line_start: int | None, line_end: int | None)` — frozen dataclass.
  - `_candidate_callers(conn, project_id, target_id) -> list[_Caller]`

- [ ] **Step 1: Write the failing test** (`tests/test_call_synth.py`)

Add the verified analyzer-DB fixture builder + the two DB-access tests:

```python
import asyncio
import sqlite3
from pathlib import Path

import pytest

from copyclip.intelligence.analyzer import analyze
from copyclip.intelligence.db import connect
from copyclip.intelligence.playground import ResolvedFunction, resolve_function_ref, FunctionRef
from copyclip.intelligence.cuaderno import call_synth
from copyclip.intelligence.cuaderno.call_synth import (
    SynthesizedCall,
    _resolve_target_symbol_id,
    _candidate_callers,
)


def analyzed_project(tmp_path: Path, files: dict[str, str]):
    """Write source, run the REAL analyzer, return (conn, project_id, root).

    analyze() opens its OWN connection and closes it, so we REOPEN the on-disk
    db with connect(). ':memory:' cannot be used (analyze builds its own conn).
    """
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    asyncio.run(analyze(str(tmp_path)))
    conn = connect(str(tmp_path))
    pid = conn.execute(
        "SELECT id FROM projects WHERE root_path=?", (str(tmp_path),)
    ).fetchone()[0]
    return conn, int(pid), str(tmp_path)


_LIB = "def target(rel):\n    return rel.upper()\n"
_TEST = (
    "from src.pkg.lib import target\n\n"
    "def test_target():\n"
    "    assert target('abc') == 'ABC'\n"
)


def test_resolve_target_symbol_id_matches_the_symbols_row(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    sid = _resolve_target_symbol_id(conn, pid, resolved)
    expected = conn.execute(
        "SELECT id FROM symbols WHERE project_id=? AND file_path=? AND name=? AND kind=? AND line_start=?",
        (pid, "src/pkg/lib.py", "target", "function", 1),
    ).fetchone()[0]
    assert sid == expected


def test_candidate_callers_finds_the_test_function(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    sid = _resolve_target_symbol_id(conn, pid, resolved)
    callers = _candidate_callers(conn, pid, sid)
    assert any(c.name == "test_target" and c.file_path == "tests/test_lib.py" for c in callers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_call_synth.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError: cannot import name 'SynthesizedCall' from 'copyclip.intelligence.cuaderno.call_synth'`.

- [ ] **Step 3: Write minimal implementation** (`src/copyclip/intelligence/cuaderno/call_synth.py`)

```python
"""Stage-1 call synthesis (spec 2026-06-18): lift a runnable call to a target
function from a REAL, fully-literal call-site in the codebase, with AST
re-verification that the call-graph 'calls' edge truly binds to THIS symbol.

Pure + best-effort: DB reads + `ast` only, no model/network/subprocess. Any
failure returns None — the floor then emits the `manual` needs_args widget.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SynthesizedCall:
    """A call lifted from a verified, fully-literal real call-site."""
    args: list
    kwargs: dict
    ctor: Optional[dict]   # {"args": [...], "kwargs": {...}} for a method, else None
    arg_source: str        # always "tests" from this function


@dataclass(frozen=True)
class _Caller:
    name: str
    kind: str
    file_path: str
    line_start: Optional[int]
    line_end: Optional[int]


def _resolve_target_symbol_id(
    conn: sqlite3.Connection, project_id: int, resolved
) -> Optional[int]:
    """Re-find the target's symbols.id (ResolvedFunction carries no id). Uses the
    natural key (project_id, file_path, name, kind, line_start)."""
    if resolved.line_start is None:
        return None
    row = conn.execute(
        "SELECT id FROM symbols WHERE project_id=? AND file_path=? AND name=? "
        "AND kind=? AND line_start=?",
        (project_id, resolved.file, resolved.name, resolved.kind, resolved.line_start),
    ).fetchone()
    return int(row[0]) if row else None


def _candidate_callers(
    conn: sqlite3.Connection, project_id: int, target_id: int
) -> list[_Caller]:
    """Candidate call-sites: callers of `target_id` via 'calls' edges. NAME-BASED
    and possibly false positives — each must be re-verified before lifting."""
    rows = conn.execute(
        "SELECT s.name, s.kind, s.file_path, s.line_start, s.line_end "
        "FROM symbol_edges e JOIN symbols s ON e.from_symbol_id = s.id "
        "WHERE e.project_id=? AND e.to_symbol_id=? AND e.edge_type='calls' "
        "ORDER BY s.file_path, s.line_start",
        (project_id, target_id),
    ).fetchall()
    return [
        _Caller(name=r[0], kind=r[1], file_path=r[2], line_start=r[3], line_end=r[4])
        for r in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_call_synth.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/call_synth.py tests/test_call_synth.py
git commit -m "feat(cuaderno): call_synth scaffold — SynthesizedCall + DB access (target id, candidate callers)"
```

---

### Task 2: Import-binding extraction (`_import_bindings`)

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/call_synth.py`
- Test: `tests/test_call_synth.py`

**Interfaces:**
- Produces:
  - `_Binding(module: str, orig_name: str | None)` — frozen dataclass. `module` is the dotted source module; `orig_name` is the imported symbol's original name for `from m import orig [as bound]`, or `None` for `import m [as bound]` (the bound name IS a module).
  - `_import_bindings(tree: ast.Module) -> dict[str, _Binding]` — maps each module-level bound name to its binding. Relative imports (`node.level > 0`) are skipped (v1 limitation).
  - `_dotted_name(node) -> str | None` — reconstruct a dotted name from a `Name`/`Attribute` chain (e.g. `a.b.c`), or `None` for any other node.

- [ ] **Step 1: Write the failing test** (append to `tests/test_call_synth.py`)

```python
import ast
from copyclip.intelligence.cuaderno.call_synth import _import_bindings, _Binding, _dotted_name


def test_import_bindings_from_import_with_and_without_alias():
    tree = ast.parse(
        "from src.pkg.lib import target\n"
        "from src.pkg.lib import target as tgt\n"
        "import os\n"
        "import a.b.c as abc\n"
    )
    b = _import_bindings(tree)
    assert b["target"] == _Binding(module="src.pkg.lib", orig_name="target")
    assert b["tgt"] == _Binding(module="src.pkg.lib", orig_name="target")
    assert b["os"] == _Binding(module="os", orig_name=None)
    assert b["abc"] == _Binding(module="a.b.c", orig_name=None)


def test_import_bindings_plain_module_import_binds_full_dotted():
    tree = ast.parse("import a.b.c\n")
    b = _import_bindings(tree)
    assert b["a.b.c"] == _Binding(module="a.b.c", orig_name=None)


def test_import_bindings_skips_relative_imports():
    tree = ast.parse("from . import sibling\nfrom .pkg import thing\n")
    b = _import_bindings(tree)
    assert "sibling" not in b
    assert "thing" not in b


def test_dotted_name():
    call = ast.parse("a.b.c.func(1)", mode="eval").body
    assert _dotted_name(call.func.value) == "a.b.c"
    assert _dotted_name(ast.parse("bare", mode="eval").body) == "bare"
    assert _dotted_name(ast.parse("x[0]", mode="eval").body) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_call_synth.py -k "import_bindings or dotted_name" -v`
Expected: FAIL — `ImportError: cannot import name '_import_bindings'`.

- [ ] **Step 3: Write minimal implementation** (add to `call_synth.py`; add `import ast` to the top imports)

```python
import ast


@dataclass(frozen=True)
class _Binding:
    module: str               # dotted source module (e.g. "src.pkg.lib")
    orig_name: Optional[str]  # "from m import orig [as bound]" -> orig; "import m" -> None


def _dotted_name(node: ast.AST) -> Optional[str]:
    """Reconstruct a dotted name from a Name/Attribute chain ('a.b.c'), else None."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _import_bindings(tree: ast.Module) -> dict[str, _Binding]:
    """Map module-level bound names to their import binding. Relative imports are
    skipped (v1: unconfirmable without resolving the caller's package)."""
    out: dict[str, _Binding] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import — conservative skip
            mod = node.module or ""
            for alias in node.names:
                bound = alias.asname or alias.name
                out[bound] = _Binding(module=mod, orig_name=alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name
                out[bound] = _Binding(module=alias.name, orig_name=None)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_call_synth.py -k "import_bindings or dotted_name" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/call_synth.py tests/test_call_synth.py
git commit -m "feat(cuaderno): call_synth import-binding extraction (_import_bindings, _dotted_name)"
```

---

### Task 3: Binding confirmation (the BLOCKER engineering) — `_import_module_matches` + `_function_call_confirms`

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/call_synth.py`
- Test: `tests/test_call_synth.py`

**Interfaces:**
- Consumes: `_Binding` map (Task 2), `_dotted_name` (Task 2), a `ResolvedFunction`.
- Produces:
  - `_import_module_matches(import_module: str, resolved_module: str) -> bool` — true when the caller's import module equals `resolved.module`, tolerating a leading `src.`/`lib.` source-root (mirrors `playground._module_from_file`, which strips `src/`/`lib/` from `resolved.module`).
  - `_function_call_confirms(call_node: ast.Call, bindings, caller_file: str, resolved) -> bool` — true when this call binds to THIS function symbol: either a bare `Name(resolved.name)` defined in the same file, or imported from `resolved.module`, or `mod.name` where `mod` imports/aliases `resolved.module`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_call_synth.py`)

This includes the **spec §8 cross-module same-name BLOCKER**: a `calls` edge into the target may actually originate from a call to a same-named function in another module; confirmation must reject it.

```python
from copyclip.intelligence.cuaderno.call_synth import (
    _import_module_matches,
    _function_call_confirms,
)


def _resolved(file, name, module, kind="function", parent=None, line_start=1):
    return ResolvedFunction(
        file=file, name=name,
        qualname=(f"{parent}.{name}" if parent else name),
        kind=kind, module=module, line_start=line_start, parent_class=parent,
    )


def test_import_module_matches_tolerates_src_root():
    assert _import_module_matches("src.pkg.lib", "pkg.lib") is True
    assert _import_module_matches("pkg.lib", "pkg.lib") is True
    assert _import_module_matches("copyclip.intelligence.analyzer", "copyclip.intelligence.analyzer") is True
    assert _import_module_matches("src.pkg.other", "pkg.lib") is False
    assert _import_module_matches("", "pkg.lib") is False


def _one_call(src: str) -> ast.Call:
    """Return the single ast.Call in the last statement of a snippet."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            return node
    raise AssertionError("no call")


def test_function_call_confirms_from_import():
    src = "from src.pkg.lib import target\ndef test_t():\n    target('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True


def test_function_call_confirms_same_file_bare_name():
    src = "def helper():\n    return target(1)\ndef target(x):\n    return x\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "src/pkg/lib.py", resolved) is True


def test_function_call_confirms_module_attribute():
    src = "import src.pkg.lib as lib\ndef test_t():\n    lib.target('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True


def test_function_call_rejects_same_name_other_module():
    # The caller imports `process` from zzz; the resolved target is aaa.process.
    # The 'calls' edge may (wrongly) point here, but the binding must be rejected.
    src = "from src.pkg.zzz import process\ndef test_p():\n    process('x')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved_aaa = _resolved("src/pkg/aaa.py", "process", "pkg.aaa")
    assert _function_call_confirms(call, b, "tests/test_z.py", resolved_aaa) is False
    # ...but it DOES confirm for the correctly-bound target.
    resolved_zzz = _resolved("src/pkg/zzz.py", "process", "pkg.zzz")
    assert _function_call_confirms(call, b, "tests/test_z.py", resolved_zzz) is True


def test_function_call_confirms_aliased_import():
    # `from m import target as tgt; tgt(...)` must confirm via the alias binding —
    # the call name is `tgt`, but its original imported name is the target.
    src = "from src.pkg.lib import target as tgt\ndef test_t():\n    tgt('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True


def test_function_call_same_file_local_def_wins_over_import():
    # The target's own file both imports a same-named symbol AND defines the target.
    # Python binds the module-level def (it shadows the import), and the analyzer's
    # same-file edge points at the local def — so a bare call confirms to THIS symbol.
    src = (
        "from src.pkg.other import target\n"
        "def target(x):\n    return x\n"
        "def helper():\n    return target(1)\n"
    )
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = [n for n in ast.walk(tree) if isinstance(n, ast.Call)][0]
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib", line_start=2)
    assert _function_call_confirms(call, b, "src/pkg/lib.py", resolved) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_call_synth.py -k "module_matches or function_call" -v`
Expected: FAIL — `ImportError: cannot import name '_import_module_matches'`.

- [ ] **Step 3: Write minimal implementation** (add to `call_synth.py`)

```python
# playground._module_from_file (which produces resolved.module) strips ONLY a
# leading "src/", so tolerate exactly that one source root on the import side.
_SRC_ROOTS = ("src",)


def _strip_src_root(module: str) -> str:
    head, _, rest = module.partition(".")
    if head in _SRC_ROOTS and rest:
        return rest
    return module


def _import_module_matches(import_module: str, resolved_module: str) -> bool:
    """True when the caller's import module identifies resolved.module. resolved.module
    is already src-stripped (playground._module_from_file), so tolerate a leading
    `src.` on the import side. NOTE: a module string is not a unique file id — the
    `_target_module_is_unambiguous` guard (Task 5) ensures (name, module) -> one file
    so this string match is sound."""
    if not import_module or not resolved_module:
        return False
    return (
        import_module == resolved_module
        or _strip_src_root(import_module) == resolved_module
    )


def _function_call_confirms(
    call_node: ast.Call, bindings: dict[str, _Binding], caller_file: str, resolved
) -> bool:
    """True when call_node binds to the plain-function target `resolved`."""
    func = call_node.func
    if isinstance(func, ast.Name):
        # A bare name defined in the SAME file as the target is a same-module call.
        # (A module-level def shadows any same-named import for the whole module, so
        # the bare name binds to the local def — which IS the target.)
        if caller_file == resolved.file and func.id == resolved.name:
            return True
        # Imported call — handles both the plain `target()` and the aliased
        # `from m import target as tgt; tgt()` forms (look up the bound name first,
        # then confirm the ORIGINAL imported name is the target and the module matches).
        b = bindings.get(func.id)
        if b is None or b.orig_name != resolved.name:
            return False
        return _import_module_matches(b.module, resolved.module)
    if isinstance(func, ast.Attribute):
        if func.attr != resolved.name:
            return False
        prefix = _dotted_name(func.value)
        if prefix is None:
            return False
        b = bindings.get(prefix)
        if b is None:
            return False
        return _import_module_matches(b.module, resolved.module)
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_call_synth.py -k "module_matches or function_call" -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/call_synth.py tests/test_call_synth.py
git commit -m "feat(cuaderno): call_synth binding re-verification (rejects same-name other-module calls)"
```

---

### Task 4: Literal lifting (`_lift_literal_args`)

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/call_synth.py`
- Test: `tests/test_call_synth.py`

**Interfaces:**
- Produces: `_lift_literal_args(call_node: ast.Call) -> tuple[list, dict] | None` — returns `(args, kwargs)` of `ast.literal_eval`-able, JSON-serializable values, or `None` if any arg is a non-literal (free name / fixture / call), a `*args`/`**kwargs` splat, or not JSON-serializable (`allow_nan=False`).

- [ ] **Step 1: Write the failing test** (append to `tests/test_call_synth.py`)

```python
from copyclip.intelligence.cuaderno.call_synth import _lift_literal_args


def test_lift_literal_args_pure_literals():
    call = _one_call("f(1, 'two', [3, 4], k=True, j=None)")
    out = _lift_literal_args(call)
    assert out == ([1, "two", [3, 4]], {"k": True, "j": None})


def test_lift_literal_args_rejects_free_name():
    assert _lift_literal_args(_one_call("f(conn, 1)")) is None


def test_lift_literal_args_rejects_call_arg():
    assert _lift_literal_args(_one_call("f(Foo(), 1)")) is None


def test_lift_literal_args_rejects_splat():
    assert _lift_literal_args(_one_call("f(*xs)")) is None
    assert _lift_literal_args(_one_call("f(**kw)")) is None


def test_lift_literal_args_rejects_non_json_float():
    assert _lift_literal_args(_one_call("f(float('nan'))")) is None  # not a literal anyway
    # a literal that json rejects:
    assert _lift_literal_args(_one_call("f(1e400)")) is None  # inf literal -> rejected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_call_synth.py -k lift_literal -v`
Expected: FAIL — `ImportError: cannot import name '_lift_literal_args'`.

- [ ] **Step 3: Write minimal implementation** (add to `call_synth.py`; add `import json` to the top imports)

```python
import json


def _is_json_literal(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def _lift_literal_args(call_node: ast.Call) -> Optional[tuple[list, dict]]:
    """Lift (args, kwargs) as literal, JSON-serializable values, or None if any
    argument is non-literal, a splat, or not JSON-serializable."""
    args: list = []
    for a in call_node.args:
        if isinstance(a, ast.Starred):
            return None
        try:
            value = ast.literal_eval(a)
        except (ValueError, SyntaxError, TypeError):
            return None
        if not _is_json_literal(value):
            return None
        args.append(value)
    kwargs: dict = {}
    for kw in call_node.keywords:
        if kw.arg is None:  # **kwargs splat
            return None
        try:
            value = ast.literal_eval(kw.value)
        except (ValueError, SyntaxError, TypeError):
            return None
        if not _is_json_literal(value):
            return None
        kwargs[kw.arg] = value
    return args, kwargs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_call_synth.py -k lift_literal -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/call_synth.py tests/test_call_synth.py
git commit -m "feat(cuaderno): call_synth literal lifting (literal_eval + JSON-serializable guard)"
```

---

### Task 5: `synthesize_call` for plain functions (find → re-parse → confirm → lift → select)

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/call_synth.py`
- Test: `tests/test_call_synth.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4 + `analyzer._is_test_path`.
- Produces: `synthesize_call(resolved, conn, project_id, project_root) -> SynthesizedCall | None` (plain-function path; methods added in Task 6). Internal helpers: `_parse_caller_file`, `_find_def`, `_Candidate`, `_richness`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_call_synth.py`)

```python
def test_synthesize_call_lifts_literal_test_call(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    out = synthesize_call_for_test = call_synth.synthesize_call(resolved, conn, pid, root)
    assert out is not None
    assert out.args == ["abc"]
    assert out.kwargs == {}
    assert out.ctor is None
    assert out.arg_source == "tests"


def test_synthesize_call_returns_none_for_fixture_args(tmp_path):
    files = {
        "src/pkg/lib.py": "def needs_conn(conn, n):\n    return n\n",
        "tests/test_lib.py": (
            "from src.pkg.lib import needs_conn\n\n"
            "def test_it(db):\n"
            "    assert needs_conn(db, 3) == 3\n"   # `db` is a fixture (free name)
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="needs_conn"))
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_returns_none_with_no_call_site(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": "def lonely(x):\n    return x\n"}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="lonely"))
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_does_not_lift_same_name_other_module(tmp_path):
    # The spec §8 re-verification BLOCKER: two same-named `process` functions in
    # DIFFERENT modules; the test imports zzz.process with a literal arg. The
    # analyzer's name-based edge binds test_p -> aaa.process (first-match-wins), so a
    # request for aaa.process must NOT lift zzz's call-site (binding mismatch).
    files = {
        "src/pkg/aaa.py": "def process(rel):\n    return 'AAA'\n",
        "src/pkg/zzz.py": "def process(rel):\n    return 'ZZZ'\n",
        "tests/test_z.py": (
            "from src.pkg.zzz import process\n\n"
            "def test_p():\n"
            "    assert process('x') == 'ZZZ'\n"
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    # aaa: the (wrong) edge points here, but the caller imports zzz -> rejected -> None.
    resolved_aaa = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/aaa.py", name="process"))
    assert call_synth.synthesize_call(resolved_aaa, conn, pid, root) is None
    # zzz: the correctly-bound target has NO inbound edge (the analyzer wrote only the
    # single first-match edge to aaa), so there is nothing to lift -> None. Re-verification
    # PREVENTS the wrong lift; it does not RECOVER the right one (honest v1 boundary).
    resolved_zzz = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/zzz.py", name="process"))
    assert call_synth.synthesize_call(resolved_zzz, conn, pid, root) is None


def test_synthesize_call_refuses_ambiguous_module_collision(tmp_path):
    # False-confirm guard: two DISTINCT files collapse to the same _module_from_file
    # module ('pkg.lib') — src/pkg/lib.py (src-stripped) and pkg/lib.py (already pkg.lib).
    # A module-string match is then not a unique-file match, so synthesis must refuse
    # rather than risk lifting the wrong file's call and stamping it 'tests'.
    files = {
        "src/pkg/lib.py": "def target(rel):\n    return rel.upper()\n",
        "pkg/lib.py": "def target(rel):\n    return rel.lower()\n",
        "tests/test_lib.py": (
            "from pkg.lib import target\n\n"
            "def test_t():\n"
            "    assert target('abc') in ('ABC', 'abc')\n"
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    for f in ("src/pkg/lib.py", "pkg/lib.py"):
        resolved = resolve_function_ref(conn, pid, FunctionRef(file=f, name="target"))
        assert resolved.module == "pkg.lib"  # confirms the collision
        assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_returns_none_for_class_target(tmp_path):
    files = {
        "src/pkg/greet.py": (
            "class Greeter:\n"
            "    def __init__(self, prefix):\n"
            "        self.prefix = prefix\n"
        ),
        "tests/test_greet.py": (
            "from src.pkg.greet import Greeter\n\n"
            "def test_make():\n"
            "    assert Greeter('hi').prefix == 'hi'\n"
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/greet.py", name="Greeter"))
    assert resolved.kind == "class"
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_prefers_tests_and_richest(tmp_path):
    files = {
        "src/pkg/lib.py": "def target(a, b=0):\n    return a\n",
        "src/pkg/use.py": (
            "from src.pkg.lib import target\n\n"
            "def use():\n"
            "    return target(1)\n"            # non-test, fewer args
        ),
        "tests/test_lib.py": (
            "from src.pkg.lib import target\n\n"
            "def test_a():\n"
            "    target(7, b=9)\n"              # test, richer
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    out = call_synth.synthesize_call(resolved, conn, pid, root)
    assert out is not None
    assert out.args == [7] and out.kwargs == {"b": 9}


def test_synthesize_call_returns_none_without_project_root(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    assert call_synth.synthesize_call(resolved, conn, pid, None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_call_synth.py -k synthesize_call -v`
Expected: FAIL — `AttributeError: module 'copyclip.intelligence.cuaderno.call_synth' has no attribute 'synthesize_call'`.

- [ ] **Step 3: Write minimal implementation** (add to `call_synth.py`; add `import os` to the top imports and `from ...analyzer import _is_test_path`)

> Import note: `call_synth.py` is at `src/copyclip/intelligence/cuaderno/`; the analyzer is at `src/copyclip/intelligence/analyzer.py` and the resolver at `src/copyclip/intelligence/playground.py`, so the relative imports are `from ..analyzer import _is_test_path` and `from ..playground import _module_from_file`.

```python
import os

from ..analyzer import _is_test_path
from ..playground import _module_from_file


def _target_module_is_unambiguous(conn: sqlite3.Connection, project_id: int, resolved) -> bool:
    """True when (resolved.name, resolved.module) identifies a SINGLE file.

    `resolved.module` is derived (playground._module_from_file strips a leading
    `src/`), so two DISTINCT files can collapse to the same dotted module
    (`src/pkg/lib.py` and `pkg/lib.py` both → `pkg.lib`). When that happens an
    import's module string no longer pins a unique file, so a name-based `calls`
    edge + module-string confirmation could lift a call that actually targets the
    OTHER file — a wrong input wearing a `tests` chip. Refuse (→ manual) instead."""
    rows = conn.execute(
        "SELECT DISTINCT file_path FROM symbols WHERE project_id=? AND name=?",
        (project_id, resolved.name),
    ).fetchall()
    same_module_files = {r[0] for r in rows if _module_from_file(r[0]) == resolved.module}
    return len(same_module_files) <= 1


@dataclass(frozen=True)
class _Candidate:
    is_test: bool
    richness: int
    file_path: str
    line: int
    args: list
    kwargs: dict
    ctor: Optional[dict]


def _parse_caller_file(project_root: str, file_path: str) -> Optional[ast.Module]:
    path = os.path.join(project_root, file_path)
    try:
        with open(path, encoding="utf-8") as fh:
            return ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None


def _find_def(
    tree: ast.Module, name: str, line_start: Optional[int]
) -> Optional[ast.AST]:
    """Find the FunctionDef/AsyncFunctionDef named `name`, preferring the one whose
    lineno matches line_start (mirrors compositor._floor_target_arity)."""
    best = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != name:
            continue
        if best is None or node.lineno == line_start:
            best = node
            if node.lineno == line_start:
                break
    return best


def _richness(args: list, kwargs: dict, ctor: Optional[dict]) -> int:
    """Count of non-degenerate literal values, where 'non-degenerate' = not None.
    A present ``''`` / ``0`` / ``False`` / ``[]`` is a real value and DOES count;
    only ``None`` (and absent args) score 0, so an empty/None-only call ranks lowest
    (spec §2.4 'avoid an empty/None-only call that teaches nothing')."""
    n = sum(1 for v in args if v is not None)
    n += sum(1 for v in kwargs.values() if v is not None)
    if ctor is not None:
        n += sum(1 for v in (ctor.get("args") or []) if v is not None)
        n += sum(1 for v in (ctor.get("kwargs") or {}).values() if v is not None)
    return n


def _iter_calls(def_node: ast.AST):
    for node in ast.walk(def_node):
        if isinstance(node, ast.Call):
            yield node


def synthesize_call(
    resolved, conn: sqlite3.Connection, project_id: int, project_root: Optional[str]
) -> Optional[SynthesizedCall]:
    """Lift a runnable call to `resolved` from a verified, fully-literal real
    call-site. None when none exists (the floor then emits the `manual` widget).
    Best-effort: any failure returns None and never raises into the floor."""
    try:
        if conn is None or project_id is None or not project_root:
            return None
        if resolved.line_start is None:
            return None
        if resolved.kind == "class":
            # A class-name run-request: lifting ClassName(args) has no ctor handling.
            return None
        if not _target_module_is_unambiguous(conn, project_id, resolved):
            # Module string is not a unique file id -> refuse (false-confirm guard).
            return None
        is_method = resolved.kind == "method" or bool(resolved.parent_class)
        if is_method:
            # Methods are handled in a later task; for now, plain functions only.
            return None
        target_id = _resolve_target_symbol_id(conn, project_id, resolved)
        if target_id is None:
            return None
        candidates: list[_Candidate] = []
        for caller in _candidate_callers(conn, project_id, target_id):
            tree = _parse_caller_file(project_root, caller.file_path)
            if tree is None:
                continue
            bindings = _import_bindings(tree)
            def_node = _find_def(tree, caller.name, caller.line_start)
            if def_node is None:
                continue
            is_test = _is_test_path(caller.file_path)
            for call_node in _iter_calls(def_node):
                if not _function_call_confirms(call_node, bindings, caller.file_path, resolved):
                    continue
                lifted = _lift_literal_args(call_node)
                if lifted is None:
                    continue
                a, k = lifted
                candidates.append(_Candidate(
                    is_test=is_test, richness=_richness(a, k, None),
                    file_path=caller.file_path, line=call_node.lineno,
                    args=a, kwargs=k, ctor=None,
                ))
        if not candidates:
            return None
        best = sorted(
            candidates,
            key=lambda c: (not c.is_test, -c.richness, c.file_path, c.line),
        )[0]
        return SynthesizedCall(args=best.args, kwargs=best.kwargs, ctor=best.ctor,
                               arg_source="tests")
    except Exception:  # noqa: BLE001 — best-effort; never raise into the floor
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_call_synth.py -k synthesize_call -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the whole file to catch regressions**

Run: `python -m pytest tests/test_call_synth.py -q`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/call_synth.py tests/test_call_synth.py
git commit -m "feat(cuaderno): synthesize_call for plain functions (re-verified lift + tests/richest selection)"
```

---

### Task 6: `synthesize_call` for methods — inline `ClassName(lit).method(lit)`

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/call_synth.py`
- Test: `tests/test_call_synth.py`

**Interfaces:**
- Produces: `_method_call_confirms_and_lifts(call_node, bindings, caller_file, resolved) -> tuple[list, dict, dict] | None` returning `(method_args, method_kwargs, ctor)` where `ctor = {"args": [...], "kwargs": {...}}`; and the method branch wired into `synthesize_call`.
- Scope: inline construction `ClassName(<literals>).method(<literals>)` only (v1). Two-statement assignment → `None`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_call_synth.py`)

```python
_CLS = (
    "class Greeter:\n"
    "    def __init__(self, prefix):\n"
    "        self.prefix = prefix\n"
    "    def greet(self, name):\n"
    "        return self.prefix + name\n"
)
_CLS_TEST = (
    "from src.pkg.greet import Greeter\n\n"
    "def test_greet():\n"
    "    assert Greeter('hi ').greet('sam') == 'hi sam'\n"
)


def test_synthesize_call_method_inline_lifts_ctor_and_args(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/greet.py": _CLS, "tests/test_greet.py": _CLS_TEST}
    )
    resolved = resolve_function_ref(
        conn, pid, FunctionRef(file="src/pkg/greet.py", name="greet", qualname="Greeter.greet")
    )
    out = call_synth.synthesize_call(resolved, conn, pid, root)
    assert out is not None
    assert out.args == ["sam"]
    assert out.ctor == {"args": ["hi "], "kwargs": {}}
    assert out.arg_source == "tests"


def test_synthesize_call_method_two_statement_form_returns_none(tmp_path):
    two_stmt = (
        "from src.pkg.greet import Greeter\n\n"
        "def test_greet():\n"
        "    g = Greeter('hi ')\n"
        "    assert g.greet('sam') == 'hi sam'\n"
    )
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/greet.py": _CLS, "tests/test_greet.py": two_stmt}
    )
    resolved = resolve_function_ref(
        conn, pid, FunctionRef(file="src/pkg/greet.py", name="greet", qualname="Greeter.greet")
    )
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_method_non_literal_ctor_returns_none(tmp_path):
    nonlit = (
        "from src.pkg.greet import Greeter\n\n"
        "def test_greet(cfg):\n"
        "    assert Greeter(cfg).greet('sam') == 'x'\n"   # ctor arg is a fixture
    )
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/greet.py": _CLS, "tests/test_greet.py": nonlit}
    )
    resolved = resolve_function_ref(
        conn, pid, FunctionRef(file="src/pkg/greet.py", name="greet", qualname="Greeter.greet")
    )
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_call_synth.py -k method -v`
Expected: FAIL — `test_synthesize_call_method_inline_lifts_ctor_and_args` fails (currently methods short-circuit to `None`).

- [ ] **Step 3: Write minimal implementation** (add the helper to `call_synth.py`, then replace the early method short-circuit in `synthesize_call`)

Add the helper:

```python
def _class_binds(class_node: ast.AST, bindings: dict[str, _Binding],
                 caller_file: str, resolved) -> bool:
    """True when the constructor reference binds to resolved's class in resolved.module."""
    simple = _dotted_name(class_node)
    if simple is None:
        return False
    simple_name = simple.split(".")[-1]
    if simple_name != resolved.parent_class:
        return False
    if isinstance(class_node, ast.Name):
        if caller_file == resolved.file:
            return True
        b = bindings.get(class_node.id)
        return (
            b is not None
            and b.orig_name == simple_name
            and _import_module_matches(b.module, resolved.module)
        )
    # Attribute chain: mod.ClassName(...)
    prefix = _dotted_name(class_node.value) if isinstance(class_node, ast.Attribute) else None
    if prefix is None:
        return False
    b = bindings.get(prefix)
    return b is not None and _import_module_matches(b.module, resolved.module)


def _method_call_confirms_and_lifts(
    call_node: ast.Call, bindings: dict[str, _Binding], caller_file: str, resolved
) -> Optional[tuple[list, dict, dict]]:
    """Confirm + lift an inline ``ClassName(<lit>).method(<lit>)`` call. Returns
    (method_args, method_kwargs, ctor) or None."""
    func = call_node.func
    if not isinstance(func, ast.Attribute) or func.attr != resolved.name:
        return None
    inner = func.value
    if not isinstance(inner, ast.Call):  # not inline construction (e.g. obj.method())
        return None
    if not _class_binds(inner.func, bindings, caller_file, resolved):
        return None
    method_lits = _lift_literal_args(call_node)
    ctor_lits = _lift_literal_args(inner)
    if method_lits is None or ctor_lits is None:
        return None
    m_args, m_kwargs = method_lits
    c_args, c_kwargs = ctor_lits
    return m_args, m_kwargs, {"args": c_args, "kwargs": c_kwargs}
```

Now replace the method short-circuit in `synthesize_call`. Change:

```python
        is_method = resolved.kind == "method" or bool(resolved.parent_class)
        if is_method:
            # Methods are handled in a later task; for now, plain functions only.
            return None
        target_id = _resolve_target_symbol_id(conn, project_id, resolved)
```

to:

```python
        is_method = resolved.kind == "method" or bool(resolved.parent_class)
        # Nested-class methods are out of v1 scope (fold only renders 2-segment
        # qualnames); a method with no parent_class cannot be constructed.
        if is_method and not resolved.parent_class:
            return None
        target_id = _resolve_target_symbol_id(conn, project_id, resolved)
```

and in the per-call loop, branch on `is_method`. Replace:

```python
            for call_node in _iter_calls(def_node):
                if not _function_call_confirms(call_node, bindings, caller.file_path, resolved):
                    continue
                lifted = _lift_literal_args(call_node)
                if lifted is None:
                    continue
                a, k = lifted
                candidates.append(_Candidate(
                    is_test=is_test, richness=_richness(a, k, None),
                    file_path=caller.file_path, line=call_node.lineno,
                    args=a, kwargs=k, ctor=None,
                ))
```

with:

```python
            for call_node in _iter_calls(def_node):
                if is_method:
                    lifted = _method_call_confirms_and_lifts(
                        call_node, bindings, caller.file_path, resolved)
                    if lifted is None:
                        continue
                    m_args, m_kwargs, ctor = lifted
                    candidates.append(_Candidate(
                        is_test=is_test, richness=_richness(m_args, m_kwargs, ctor),
                        file_path=caller.file_path, line=call_node.lineno,
                        args=m_args, kwargs=m_kwargs, ctor=ctor,
                    ))
                else:
                    if not _function_call_confirms(call_node, bindings, caller.file_path, resolved):
                        continue
                    lifted = _lift_literal_args(call_node)
                    if lifted is None:
                        continue
                    a, k = lifted
                    candidates.append(_Candidate(
                        is_test=is_test, richness=_richness(a, k, None),
                        file_path=caller.file_path, line=call_node.lineno,
                        args=a, kwargs=k, ctor=None,
                    ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_call_synth.py -k method -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the whole file**

Run: `python -m pytest tests/test_call_synth.py -q`
Expected: PASS (all green — plain-function tests still pass).

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/call_synth.py tests/test_call_synth.py
git commit -m "feat(cuaderno): synthesize_call method support — inline ClassName(lit).method(lit) lift"
```

---

### Task 7: `Widget.playground` gains `arg_source`; wire `synthesize_call` into the floor

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/schema.py:61-77`
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py:257-296`
- Test: `tests/test_cuaderno_playground_floor.py`

**Interfaces:**
- Consumes: `synthesize_call(resolved, conn, project_id, project_root)` (Tasks 5-6).
- Produces: floor widgets carry `arg_source="tests"` with a populated `call` (no `needs_args`) when a literal call-site exists, else `arg_source="manual"` with the existing `needs_args=True` template.

- [ ] **Step 1: Write the failing test** (append to `tests/test_cuaderno_playground_floor.py`)

Mirror the existing `_seed_arity_n_function` helper pattern (test_cuaderno_playground_floor.py:334), but with a real literal test call-site on disk so synthesis succeeds:

```python
def test_floor_synthesizes_tests_call_for_arity_n_function(tmp_path):
    root = str(tmp_path)
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0])
    # Real source: an arity-1 function and a test that calls it with a literal.
    src = tmp_path / "src" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def needs_arg(rel):\n    return rel.upper()\n", encoding="utf-8")
    tst = tmp_path / "tests" / "test_mod.py"
    tst.parent.mkdir(parents=True, exist_ok=True)
    tst.write_text(
        "from src.pkg.mod import needs_arg\n\n"
        "def test_it():\n"
        "    assert needs_arg('abc') == 'ABC'\n",
        encoding="utf-8",
    )
    # Seed the symbols + the 'calls' edge that synthesize_call walks.
    fn_id = int(conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, "needs_arg", "function", "src/pkg/mod.py", 1, 2, None, "pkg"),
    ).lastrowid)
    test_id = int(conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, "test_it", "function", "tests/test_mod.py", 3, 4, None, "tests"),
    ).lastrowid)
    conn.execute(
        "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,'calls')",
        (pid, test_id, fn_id),
    )
    conn.commit()

    block, reason = _construct_playground_floor(
        "run needs_arg", conn, pid, ledger=None, emitted=[], project_root=root)
    assert reason is None
    w = block.to_dict()["widget"]
    assert w.get("needs_args") is None, "a synthesized tests call must NOT flag needs_args"
    assert w.get("arg_source") == "tests"
    assert w["call"]["args"] == ["abc"]
    assert w["call_text"] == "needs_arg('abc')"


def test_floor_falls_to_manual_when_no_literal_call_site(tmp_path):
    root = str(tmp_path)
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_arity_n_function(conn, root, tmp_path)  # existing helper: arity-1 fn, NO call-site
    block, reason = _construct_playground_floor(
        "run needs_arg", conn, pid, ledger=None, emitted=[], project_root=root)
    assert reason is None
    w = block.to_dict()["widget"]
    assert w.get("needs_args") is True
    assert w.get("arg_source") == "manual"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_playground_floor.py -k "synthesizes_tests_call or falls_to_manual" -v`
Expected: FAIL — `arg_source` not present (KeyError/`None`), and the synthesized call's args are empty.

- [ ] **Step 3: Add `arg_source` to `Widget.playground`** (`schema.py:61-77`)

Change the signature and body:

```python
    @staticmethod
    def playground(function_ref: dict, breadcrumb: str,
                   suggested_inputs: Optional[list] = None,
                   call: Optional[dict] = None,
                   needs_args: Optional[bool] = None,
                   arg_source: Optional[str] = None) -> "Widget":
        citation: dict[str, Any] = {"kind": "path", "path": function_ref.get("file")}
        if function_ref.get("line") is not None:
            citation["line_start"] = function_ref["line"]
        d: dict[str, Any] = {"function_ref": function_ref, "breadcrumb": breadcrumb,
                             "citation": citation}
        if suggested_inputs is not None:
            d["suggested_inputs"] = suggested_inputs
        if call is not None:
            d["call"] = call
        if needs_args:
            d["needs_args"] = True
        if arg_source is not None:
            d["arg_source"] = arg_source
        return Widget(kind="playground", data=d)
```

- [ ] **Step 4: Wire `synthesize_call` into `_construct_playground_floor`** (`compositor.py`)

Add the import at the top of `compositor.py` (near the other `from .` imports):

```python
from .call_synth import synthesize_call
```

Then, immediately after the line `needs_args = doomed_reason is not None` (compositor.py:261), insert:

```python
    # Stage-1 call synthesis (spec 2026-06-18): when the bare floor would need
    # args, try to lift a real, fully-literal call-site from the codebase. On a
    # hit the widget ships a runnable `tests` call (no needs_args); on a miss it
    # keeps the `manual` needs_args template.
    synth = synthesize_call(resolved, conn, project_id, project_root) if needs_args else None
    arg_source = None
    if needs_args:
        if synth is not None:
            needs_args = False
            arg_source = "tests"
        else:
            arg_source = "manual"
```

Next, fold the synthesized literals into `extra_widget_data`. Replace the existing method/ctor block (compositor.py:275-288):

```python
    extra_widget_data: dict[str, Any] = {}
    if resolved.kind == "method" or resolved.parent_class:
        if resolved.qualname and "." in resolved.qualname:
            class_name = resolved.qualname.split(".")[0]
        elif resolved.parent_class:
            class_name = resolved.parent_class
        else:
            class_name = "Object"
        fr = {**fr, "qualname": f"{class_name}.{resolved.name}"}
        extra_widget_data["ctor"] = {"args": [], "kwargs": {}}
```

with:

```python
    extra_widget_data: dict[str, Any] = {}
    if resolved.kind == "method" or resolved.parent_class:
        if resolved.qualname and "." in resolved.qualname:
            class_name = resolved.qualname.split(".")[0]
        elif resolved.parent_class:
            class_name = resolved.parent_class
        else:
            class_name = "Object"
        fr = {**fr, "qualname": f"{class_name}.{resolved.name}"}
        # A synthesized method call supplies a real ctor; otherwise the empty
        # ctor that gives call_text a "Class().method()" template to edit.
        if synth is not None and synth.ctor is not None:
            extra_widget_data["ctor"] = synth.ctor
        else:
            extra_widget_data["ctor"] = {"args": [], "kwargs": {}}
    # Synthesized positional/keyword literals (plain function or method args).
    if synth is not None:
        extra_widget_data["args"] = synth.args
        extra_widget_data["kwargs"] = synth.kwargs
```

Finally, pass `arg_source` into the widget factory. Change the `Widget.playground(...)` call (compositor.py:289-292):

```python
    raw_widget: Widget = Widget.playground(
        function_ref=fr, breadcrumb=breadcrumb,
        needs_args=needs_args if needs_args else None,
    )
```

to:

```python
    raw_widget: Widget = Widget.playground(
        function_ref=fr, breadcrumb=breadcrumb,
        needs_args=needs_args if needs_args else None,
        arg_source=arg_source,
    )
```

> Note: `args`/`kwargs`/`ctor` placed in `extra_widget_data` are top-level widget keys that `fold_playground_widget` reads and folds into `call`/`call_text`; `arg_source` is a top-level key the fold preserves (it drops only `args`/`kwargs`/`ctor`), and `validate_widget_payload` does not allowlist keys, so it passes through unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_playground_floor.py -k "synthesizes_tests_call or falls_to_manual" -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full floor + synth + emit_fold suites for regressions**

Run: `python -m pytest tests/test_cuaderno_playground_floor.py tests/test_call_synth.py tests/test_emit_fold.py -q`
Expected: PASS (all green — existing floor tests unaffected: the no-call-site path still yields `needs_args=True`, now additionally tagged `arg_source="manual"`).

> If any pre-existing floor test asserts on the EXACT widget dict and now sees an extra `arg_source` key, update that assertion to expect `arg_source` (it is an additive field; the failure would be a test that did an equality check on the whole widget dict — adjust to subset/key checks).

- [ ] **Step 7: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/schema.py src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_playground_floor.py
git commit -m "feat(cuaderno): floor wires synthesize_call — tests-provenance call or manual template"
```

---

### Task 8: Frontend — `arg_source` type + provenance chip + i18n

**Files:**
- Modify: `frontend/src/types/api.ts:754-763`
- Modify: `frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx:82-93`
- Modify: `frontend/src/components/cuaderno/stepper/PreviewCall.tsx`
- Modify: `frontend/src/components/cuaderno/strings.ts` (en ~line 65, es ~line 126)
- Test: `frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx`

**Interfaces:**
- Consumes: `widget.arg_source` from the backend (Task 7).
- Produces: a non-clickable provenance chip (`data-testid="arg-source-chip"`) with exactly two labels: `tests` and `manual`. The `tests` case is fully runnable (Step-through enabled from the start; `needs_args` is falsy).

- [ ] **Step 1: Write the failing test** (append to `frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx`)

```typescript
  it('renders the tests-provenance chip (en) when argSource="tests"', () => {
    render(
      <PreviewCall
        funcName="target"
        initialCall="target('abc')"
        onConfirm={() => {}}
        onCancel={() => {}}
        argSource="tests"
        lang="en"
      />
    )
    const chip = screen.getByTestId('arg-source-chip')
    expect(chip).toHaveTextContent('from a test')
  })

  it('renders the tests-provenance chip (es, Venezuelan tuteo)', () => {
    render(
      <PreviewCall
        funcName="target"
        initialCall="target('abc')"
        onConfirm={() => {}}
        onCancel={() => {}}
        argSource="tests"
        lang="es"
      />
    )
    expect(screen.getByTestId('arg-source-chip')).toHaveTextContent('args de un test')
  })

  it('renders the manual chip when argSource="manual"', () => {
    render(
      <PreviewCall
        funcName="needs_arg"
        initialCall="needs_arg()"
        onConfirm={() => {}}
        onCancel={() => {}}
        needsArgs={true}
        argSource="manual"
        lang="es"
      />
    )
    expect(screen.getByTestId('arg-source-chip')).toHaveTextContent('completa la llamada')
  })

  it('renders no chip when argSource is absent', () => {
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={() => {}} onCancel={() => {}} />)
    expect(screen.queryByTestId('arg-source-chip')).toBeNull()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/components/cuaderno/stepper/PreviewCall.test.tsx`
Expected: FAIL — `argSource` is not a prop; no `arg-source-chip` testid found.

- [ ] **Step 3: Add the type field** (`frontend/src/types/api.ts:754-763`)

Add `arg_source` after `needs_args`:

```typescript
export type PlaygroundWidgetData = {
  kind: 'playground'
  function_ref: FunctionRef
  breadcrumb: string
  suggested_inputs?: unknown[]
  citation?: Citation
  call?: CallDescriptor      // the model's structured proposed invocation
  call_text?: string         // the model's proposed invocation pre-rendered as source text
  needs_args?: boolean       // floor widget: call_text is an incomplete template; user must complete before confirming
  arg_source?: 'tests' | 'manual'  // provenance: lifted from a real test call-site, or a manual completion template
}
```

- [ ] **Step 4: Add the i18n keys** (`frontend/src/components/cuaderno/strings.ts`)

In the `en` map, after `playground_complete_call:` (~line 65) add:

```typescript
    playground_chip_tests: 'from a test',
    playground_chip_manual: 'complete the call',
```

In the `es` map, after `playground_complete_call:` (~line 126) add (Venezuelan tuteo):

```typescript
    playground_chip_tests: 'args de un test',
    playground_chip_manual: 'completa la llamada',
```

- [ ] **Step 5: Add the `argSource` prop + chip to `PreviewCall`** (`PreviewCall.tsx`)

Add to `Props` (after `needsArgs?: boolean`):

```typescript
  argSource?: 'tests' | 'manual'  // provenance chip: trustworthy test-lifted args vs manual template
```

Add `argSource` to the destructured params:

```typescript
export function PreviewCall({ funcName, initialCall, onConfirm, onCancel, needsArgs, argSource, lang }: Props) {
```

Render the chip inside the preview body. Replace the existing `needsArgs ? (...) : null` block (PreviewCall.tsx:38-45) — keep the needs-args hint and add the chip ABOVE it:

```tsx
          {argSource ? (
            <div
              data-testid="arg-source-chip"
              style={s('display:inline-flex;align-self:flex-start;align-items:baseline;gap:6px;font-family:var(--font-mono);font-size:12.5px;color:var(--accent-ink);background:var(--accent-soft);border:1px solid var(--accent-line);padding:2px 8px 3px;border-radius:999px;letter-spacing:-0.01em;margin-bottom:10px;')}
            >
              {t(argSource === 'tests' ? 'playground_chip_tests' : 'playground_chip_manual', lang)}
            </div>
          ) : null}
          {needsArgs ? (
            <div
              data-testid="needs-args-hint"
              style={s('font-size:12.5px;color:var(--accent-ink);margin-bottom:10px;')}
            >
              {t('playground_complete_call', lang)}
            </div>
          ) : null}
```

> The chip mirrors the `.cite` pill (cuaderno.css:334-352) via the `s()` inline-style helper the file already uses, minus `cursor:pointer`/hover (it is informational, not clickable).

- [ ] **Step 6: Thread `argSource` from `PlaygroundWidget`** (`PlaygroundWidget.tsx:82-93`)

Add the prop to the `<PreviewCall>` mount:

```tsx
      <PreviewCall
        funcName={fn.name}
        initialCall={proposedCall}
        onConfirm={doLaunch}
        onCancel={() => { setPreviewing(false); setPreviewToken(-1) }}
        needsArgs={widget.needs_args}
        argSource={widget.arg_source}
        lang={lang}
      />
```

- [ ] **Step 7: Run the test to verify it passes**

Run (from `frontend/`): `npx vitest run src/components/cuaderno/stepper/PreviewCall.test.tsx`
Expected: PASS (existing PreviewCall tests + 4 new chip tests green).

- [ ] **Step 8: Type-check + full frontend suite**

Run (from `frontend/`): `npx tsc -b && npx vitest run`
Expected: tsc clean; all vitest green (PlaygroundWidget tests unaffected — `arg_source` is optional).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/components/cuaderno/strings.ts frontend/src/components/cuaderno/stepper/PreviewCall.tsx frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx frontend/src/components/cuaderno/stepper/PreviewCall.test.tsx
git commit -m "feat(cuaderno): two-value provenance chip (tests | manual) in the call preview"
```

---

### Task 9: Acceptance verification + spec/memory sync

**Files:**
- Run-only (no code) + optional `docs/superpowers/specs/2026-06-18-cuaderno-playground-call-synthesis-design.md` status line.

- [ ] **Step 1: Full backend suite**

Run: `python -m pytest -q`
Expected: PASS (the prior baseline 989 + the new `test_call_synth.py` + floor tests; 0 failures).

- [ ] **Step 2: Full frontend suite + build**

Run (from `frontend/`): `npx vitest run && npx tsc -b && npm run build`
Expected: all green; build OK.

- [ ] **Step 3: Walk the acceptance criteria (spec §10)** — confirm each is covered by a test:
  - Literal-arg function → pre-filled `tests` widget, binding confirmed → `test_floor_synthesizes_tests_call_for_arity_n_function` + `test_synthesize_call_does_not_lift_same_name_other_module`.
  - Method with literal-constructed instance → `ctor` + method args → `test_synthesize_call_method_inline_lifts_ctor_and_args`.
  - No confirmed literal call-site → `manual`, never fabricated → `test_floor_falls_to_manual_when_no_literal_call_site` + `test_synthesize_call_returns_none_with_no_call_site`.
  - Lifted `tests` call is self-contained (literals only) → `test_synthesize_call_returns_none_for_fixture_args`.
  - Exactly two chip values; cross-module re-verification unit-tested → `test_function_call_rejects_same_name_other_module` + the 4 chip tests.

- [ ] **Step 4: Update the spec status + memory**

Edit the spec's status line to note "implemented (Core Stage 1) on branch `feat/cuaderno-call-synthesis`" and update the memory file `playground-stepthrough-redesign.md` NEXT-FEATURE section to "built". Commit.

```bash
git add docs/superpowers/specs/2026-06-18-cuaderno-playground-call-synthesis-design.md
git commit -m "docs(cuaderno): mark Stage-1 call synthesis implemented"
```

---

## Self-Review

**1. Spec coverage:** §2 synthesizer (`call_synth.py`) → Tasks 1-6. §2.1 candidate call-sites → Task 1. §2.2 binding re-verification (BLOCKER) → Task 3 (`_function_call_confirms` incl. the cross-module reject + alias) **and the module-identity false-confirm guard `_target_module_is_unambiguous` in Task 5** (`test_..._refuses_ambiguous_module_collision`). §2.3 literal-only lift → Task 4 + `test_..._fixture_args`. §2.4 selection (tests/, richest, tie-break) → Task 5 `test_..._prefers_tests_and_richest`. §3 floor wiring → Task 7 (gated on `needs_args` — see Synthesis trigger note). §4 widget contract (`arg_source`) → Tasks 7-8. §5 preview chip → Task 8. §6 consent (only literals ship) → Task 4 JSON guard. §7 best-effort never-raise → Task 5 `try/except`. §8 testing → all task tests. §9 scope (no fabrication; class target excluded) → no LLM/type-hint code anywhere. §10 acceptance → Task 9.

**Adversarial review pass (2026-06-25, 3 lenses):** spec-coverage (Serrano), AST false-confirm hunt, TDD test realism. Two BLOCKERs found and fixed in this plan: (1) module-string identity is not file identity → added `_target_module_is_unambiguous` (Design decision #5, Task 5); (2) the analyzer writes only one `'calls'` edge per call-site, so the cross-module test's positive-lift assertion was unreachable → the test now asserts the honest v1 reality (both same-name targets → `None`). One HIGH: the `_function_call_confirms` Name branch short-circuited before consulting alias bindings → rewritten to look up the binding first (alias call-sites now lift). Minors folded in: `_SRC_ROOTS` reduced to `("src",)`, explicit class-target guard, clarified `_richness` definition, documented the `needs_args` gating.

**2. Placeholder scan:** every code step contains complete, runnable code; no TBD/"add error handling"/"similar to". The `try/except Exception` in `synthesize_call` is the spec-mandated best-effort boundary, not a placeholder.

**3. Type consistency:** `synthesize_call(resolved, conn, project_id, project_root)` is used identically in Tasks 5, 6, 7 (and tests). `SynthesizedCall(args, kwargs, ctor, arg_source)` fields match between definition (Task 1) and consumption (Tasks 5-7). `_Binding(module, orig_name)` consistent across Tasks 2-3, 6. `arg_source` values `"tests"|"manual"` consistent across backend (Task 7) and frontend type/i18n (Task 8). The widget top-level keys `args`/`kwargs`/`ctor`/`arg_source` match `fold_playground_widget`'s read/preserve contract.
