# Wave 3 — Proof Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `graph_view` and `playground` as honest in-frame artifacts (verified topology, tool-evidenced citations, marimo `run` on click with a single slot), plus the Settings paper re-skin.

**Architecture:** Backend first: the ledger learns tool-evidenced paths (gate fix), `get_module_graph` provides citable same-namespace topology from `symbol_edges`, the compositor verifies emitted graphs are subsets of this turn's evidence and validates playground recipes at emit time. Then the runtime: marimo `run` mode + list route; frontend `GraphView` (frame-scale SVG) and `PlaygroundWidget` (4 states, CuadernoPage-level single slot, 5s poll, navigation kills). Finally the global modal + Atlas's live launch path die (declared live-feature removal), and Settings re-skins.

**Tech Stack:** Python (pytest, stdlib server, sqlite), React/TypeScript (`npm --prefix frontend run build`; NO frontend test runner, standing decision), marimo subprocess.

**Spec:** `docs/superpowers/specs/2026-06-04-wave-3-proof-artifacts-design.md` (v2 — read it before any task; §4 and "One-Frame Reality" are load-bearing).

**Verified anchors:**
- `symbol_edges(from_symbol_id, to_symbol_id, edge_type, project_id)` (db.py:95); the working join pattern is `anchor.py:get_callers` (134-153).
- `ReadLedger.record(tool_name, result)` harvests only `result["path"]` into `read_paths` (read_ledger.py:36-41); `_CONTENT_KEYS` at lines 8-11.
- Fabrication check: `quality.py:assess` disjoint test `cited.isdisjoint(read)` (~line 198 post-W2).
- Emit validation chokepoint: `compositor.py:211` `reason = validate_block_dict(inp); emit_status[blk["id"]] = reason` — invalid blocks already ride the `invalid_block` ack + retry latch.
- Recipe validators live in `playground.py` (`FunctionRef.from_dict` 82-124, `PlaygroundLaunchRequest.from_dict` 128-162); `PLAYGROUND_SOURCES` 25-35; runner spawn args `marimo_runner.py:148-166`; cap/instances 135-144; `kill` 207-214.
- Frontend one-frame reality: `Cuaderno.tsx:96` `key={activeQuestion?.position ?? scene}`; `CuadernoPage.tsx` restore 32-47, `onAsk` 61-71, `onSelectFromHistory` 156-158.
- FlowchartCanvas core: `Atlas3DPage.tsx:378-987` (layout `place()` ~473-525, wheel listener ~660-669 — `{passive:false}` + unconditional preventDefault, DO NOT copy that part verbatim).
- `.copyclip-verify.py` is protected/untracked: NEVER stage it; never use bare `git add -A`.

---

### Task 1: Ledger learns tool-evidenced paths; the gate compares against the union

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/read_ledger.py`
- Modify: `src/copyclip/intelligence/cuaderno/quality.py` (the disjoint check)
- Test: `tests/test_cuaderno_evidence_paths.py` (create)

- [ ] **Step 1: Failing tests**

```python
"""Wave-3 gate fix: paths returned by evidence tools count as comparable —
a DB-grounded graph citation must not be condemned as fabricated."""
from copyclip.intelligence.cuaderno.quality import assess, _cited_paths
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.schema import Block, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED


def test_ledger_harvests_file_paths_from_tool_results():
    led = ReadLedger()
    led.record("get_callers", {"callers": [
        {"name": "f", "kind": "function", "file_path": "src/a.py", "line_start": 3},
        {"name": "g", "kind": "function", "file_path": "src/b.py", "line_start": 9},
    ]})
    assert {"src/a.py", "src/b.py"} <= led.evidence_paths
    assert led.read_paths == set()   # read_paths stays read_file/list_dir-only


def test_ledger_harvests_module_graph_paths():
    led = ReadLedger()
    led.record("get_module_graph", {"modules": [
        {"name": "copyclip/intelligence", "file_path": "src/copyclip/intelligence/db.py"},
    ], "edges": [], "truncated": False})
    assert "src/copyclip/intelligence/db.py" in led.evidence_paths


def test_db_grounded_widget_citation_is_not_condemned():
    """read one file + cite 2 tool-evidenced others via a widget -> answer, not ungrounded."""
    led = ReadLedger()
    led.record("read_file", {"path": "src/x.py", "lines": [{"n": 1, "text": "x"}]})
    led.record("get_callers", {"callers": [
        {"name": "f", "kind": "function", "file_path": "src/a.py", "line_start": 3}]})
    w = {"kind": "graph_view",
         "nodes": [{"id": "a", "label": "a", "citation": {"kind": "path", "path": "src/a.py"}}],
         "edges": []}
    v = assess(question="how does a work?",
               blocks=[Block.paragraph("so..."), Block.widget(w)], ledger=led)
    assert v.status == FRAME_STATUS_ANSWER


def test_true_fabrication_still_seals():
    """citing a path NEITHER read NOR tool-evidenced still seals ungrounded."""
    led = ReadLedger()
    led.record("read_file", {"path": "src/x.py", "lines": [{"n": 1, "text": "x"}]})
    b = Block.code_block("y", "python", citation={"kind": "path", "path": "src/never.py"})
    v = assess(question="how does y work?", blocks=[b], ledger=led)
    assert v.status == FRAME_STATUS_UNGROUNDED
```

- [ ] **Step 2:** Run `python -m pytest tests/test_cuaderno_evidence_paths.py -v` — FAIL (`evidence_paths` missing; third test seals ungrounded).

- [ ] **Step 3: Implement.** In `read_ledger.py`:

```python
def _harvest_file_paths(node: Any, out: set[str]) -> None:
    """Collect file_path fields recursively from a tool result. These are
    tool-EVIDENCED paths: a tool genuinely returned them this turn."""
    if isinstance(node, dict):
        fp = node.get("file_path")
        if isinstance(fp, str) and fp:
            out.add(fp)
        for v in node.values():
            _harvest_file_paths(v, out)
    elif isinstance(node, list):
        for v in node:
            _harvest_file_paths(v, out)
```

In `ReadLedger.__init__` add `self.evidence_paths: set[str] = set()`. In `record`, after the existing body (harvest regardless of content-bearing status, but only for non-answer tools without error — mirror the guard):

```python
        if tool_name not in ANSWER_TOOLS and isinstance(result, dict) and not result.get("error"):
            _harvest_file_paths(result, self.evidence_paths)
```

In `quality.py` `assess`, change the comparable set for the disjoint check:

```python
    read = {_norm_path(p) for p in ledger.read_paths}
    evidenced = {_norm_path(p) for p in getattr(ledger, "evidence_paths", set())}
    comparable = read | evidenced
```

and the check becomes `if codey and cited and comparable and cited.isdisjoint(comparable):` (update the reason string to `"answer cites paths neither read nor tool-evidenced: ..."`). The zero-content-bearing-reads check above it is UNTOUCHED.

- [ ] **Step 4:** `python -m pytest tests/test_cuaderno_evidence_paths.py tests/test_cuaderno_artifact_honesty.py tests/test_cuaderno_quality.py -q` — all PASS (existing fabrication tests must still pass: they construct ledgers without evidence paths).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/read_ledger.py src/copyclip/intelligence/cuaderno/quality.py tests/test_cuaderno_evidence_paths.py
git commit -m "feat(shell): tool-evidenced paths join the grounding comparable set — DB-grounded artifacts stop being condemned"
```

---

### Task 2: `get_module_graph` — citable same-namespace topology, registered everywhere

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/anchor.py` (new function)
- Modify: `src/copyclip/intelligence/cuaderno/tool_catalog.py` (definition in `build_tool_definitions`)
- Modify: the tool DISPATCHER (locate it: `grep -rn "unknown_tool" src/copyclip/intelligence/cuaderno/` — register `get_module_graph` there with the same conn/project_id wiring as `get_callers`)
- Modify: the system prompt (`grep -n "get_callers" src/copyclip/intelligence/cuaderno/prompts.py` — advertise the new tool wherever the existing tools are listed)
- Test: `tests/test_cuaderno_module_graph.py` (create)

- [ ] **Step 1: Failing tests** (seed an in-memory DB copying the seeding pattern from existing anchor tests — `grep -rn "symbol_edges" tests/ | head` to find it):

```python
"""get_module_graph: same-namespace topology from symbol_edges, deterministic caps."""
import sqlite3
import pytest
from copyclip.intelligence.db import init_schema
from copyclip.intelligence.cuaderno.anchor import get_module_graph


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    c.execute("INSERT INTO projects(root_path) VALUES('/p')")
    pid = c.execute("SELECT id FROM projects").fetchone()[0]
    # 3 modules, symbols in each, cross-module call edges
    syms = [
        ("a", "function", "src/pkg/a.py", "pkg/a", 1),
        ("b", "function", "src/pkg/b.py", "pkg/b", 1),
        ("c", "function", "src/pkg/c.py", "pkg/c", 1),
    ]
    for name, kind, fp, mod, line in syms:
        c.execute("INSERT INTO symbols(project_id,name,kind,file_path,module,line_start) VALUES(?,?,?,?,?,?)",
                  (pid, name, kind, fp, mod, line))
    ids = {r[1]: r[0] for r in c.execute("SELECT id,name FROM symbols").fetchall()}
    c.execute("INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
              (pid, ids["a"], ids["b"], "calls"))
    c.execute("INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
              (pid, ids["a"], ids["c"], "calls"))
    return c, pid


def test_edges_join_modules_and_nodes_carry_files(conn):
    c, pid = conn
    g = get_module_graph(c, pid)
    names = {m["name"] for m in g["modules"]}
    assert {"pkg/a", "pkg/b", "pkg/c"} <= names
    assert all(m["file_path"] for m in g["modules"])
    assert {"from": "pkg/a", "to": "pkg/b", "weight": 1} in [
        {k: e[k] for k in ("from", "to", "weight")} for e in g["edges"]]
    # every edge endpoint is a present node — no dangling edges
    for e in g["edges"]:
        assert e["from"] in names and e["to"] in names
    assert g["truncated"] is False


def test_scope_filters_by_substring(conn):
    c, pid = conn
    g = get_module_graph(c, pid, scope="pkg/b")
    assert {m["name"] for m in g["modules"]} == {"pkg/b"}


def test_caps_are_deterministic_and_prune_edges(conn):
    c, pid = conn
    g = get_module_graph(c, pid, max_modules=2, max_edges=80)
    assert len(g["modules"]) == 2
    assert g["truncated"] is True
    names = {m["name"] for m in g["modules"]}
    for e in g["edges"]:
        assert e["from"] in names and e["to"] in names  # pruned, not dangling
```

Adjust the INSERT column lists to the REAL schemas (read `db.py`'s `CREATE TABLE symbols` and `symbol_edges` first; if `symbols` requires more NOT NULL columns, supply them).

- [ ] **Step 2:** Run — FAIL (ImportError).

- [ ] **Step 3: Implement** in `anchor.py` (signature includes test-only cap overrides with the spec defaults):

```python
def get_module_graph(conn: sqlite3.Connection, project_id: int, scope: str = "",
                     max_modules: int = 50, max_edges: int = 80) -> dict[str, Any]:
    """Module-level topology aggregated from symbol_edges — both endpoints live
    in the symbols.module namespace, so every node maps to a real file (citation)
    and stdlib/external import targets never appear. Deterministic caps: modules
    ranked by edge degree DESC then name ASC; edges pruned to surviving nodes,
    then capped by weight DESC."""
    rows = conn.execute(
        """
        SELECT s1.module, s2.module, COUNT(*) AS weight
        FROM symbol_edges e
        JOIN symbols s1 ON e.from_symbol_id = s1.id
        JOIN symbols s2 ON e.to_symbol_id = s2.id
        WHERE e.project_id=? AND s1.module IS NOT NULL AND s2.module IS NOT NULL
              AND s1.module != s2.module
        GROUP BY s1.module, s2.module
        """, (project_id,)).fetchall()
    files = dict(conn.execute(
        "SELECT module, MIN(file_path) FROM symbols WHERE project_id=? AND module IS NOT NULL GROUP BY module",
        (project_id,)).fetchall())
    mods = set(files)
    if scope:
        mods = {m for m in mods if scope in m}
    edges = [(f, t, w) for (f, t, w) in rows if f in mods and t in mods]
    degree: dict[str, int] = {}
    for f, t, w in edges:
        degree[f] = degree.get(f, 0) + 1
        degree[t] = degree.get(t, 0) + 1
    ranked = sorted(mods, key=lambda m: (-degree.get(m, 0), m))
    truncated = len(ranked) > max_modules
    keep = set(ranked[:max_modules])
    pruned = [(f, t, w) for (f, t, w) in edges if f in keep and t in keep]
    pruned.sort(key=lambda e: (-e[2], e[0], e[1]))
    if len(pruned) > max_edges:
        truncated = True
        pruned = pruned[:max_edges]
    return {
        "modules": [{"name": m, "file_path": files[m]} for m in sorted(keep)],
        "edges": [{"from": f, "to": t, "weight": w} for (f, t, w) in pruned],
        "truncated": truncated,
    }
```

Register: (a) in `tool_catalog.py:build_tool_definitions()` add the definition (description: "Module-level dependency topology (who calls whom across modules), with the file backing each module. Use it to build a graph_view widget; emit only nodes/edges this tool returned."; input_schema: `{scope: {type: string, description: 'substring filter, empty = whole project'}}`); (b) in the dispatcher (found via `unknown_tool` grep) wire `get_module_graph(conn, project_id, args.get("scope", ""))` exactly like `get_callers` is wired; (c) in the system prompt's tool list add one line mirroring the neighbors. Also add `"modules"` to `_CONTENT_KEYS` in `read_ledger.py:8-11` so a graph-only turn counts as content-bearing (Vale's inert-check finding).

- [ ] **Step 4:** Run the new tests + `python -m pytest tests/ -q -k "anchor or catalog or module_graph"` — PASS. Write one more test that calls the tool THROUGH the dispatcher (copy how existing dispatcher tests invoke `get_callers`; assert no `unknown_tool`).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anchor.py src/copyclip/intelligence/cuaderno/tool_catalog.py src/copyclip/intelligence/cuaderno/prompts.py src/copyclip/intelligence/cuaderno/read_ledger.py tests/test_cuaderno_module_graph.py
git commit -m "feat(shell): get_module_graph — citable symbol_edges topology, registered in definitions+dispatch+prompt"
```
(add the dispatcher's file if it is not one of the above)

---

### Task 3: Widget factories + judge summarizers for both kinds

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/schema.py` (two factories)
- Modify: `src/copyclip/intelligence/cuaderno/quality.py` (`_artifact_summary` two per-kind branches)
- Modify: the system prompt Block-schema documentation (where the existing 3 widget kinds are described — match the pattern)
- Test: append to `tests/test_cuaderno_artifact_honesty.py`

- [ ] **Step 1: Failing tests**

```python
def test_widget_factories_new_kinds():
    from copyclip.intelligence.cuaderno.schema import Widget
    g = Widget.graph_view(nodes=[{"id": "a", "label": "A"}], edges=[], truncated=True)
    assert g.kind == "graph_view" and g.data["truncated"] is True
    p = Widget.playground(function_ref={"file": "src/a.py", "name": "f", "line": 3},
                          breadcrumb="parses x")
    assert p.kind == "playground"
    assert p.data["citation"] == {"kind": "path", "path": "src/a.py", "line_start": 3}


def test_artifact_summary_graph_view_and_playground():
    from copyclip.intelligence.cuaderno.quality import _artifact_summary
    g = {"kind": "graph_view",
         "nodes": [{"id": "a", "label": "Parser"}], "edges": [{"from": "a", "to": "b"}],
         "truncated": False}
    p = {"kind": "playground",
         "function_ref": {"file": "src/a.py", "name": "parse"}, "breadcrumb": "tokenizes input"}
    s = _artifact_summary([Block.widget(g), Block.widget(p)])
    assert "Parser" in s and "a -> b" in s
    assert "parse" in s and "src/a.py" in s and "tokenizes input" in s
```

- [ ] **Step 2:** Run — FAIL.

- [ ] **Step 3: Implement.** schema.py after `callers_tree`:

```python
    @staticmethod
    def graph_view(nodes: list[dict], edges: list[dict],
                   focus: Optional[str] = None, truncated: bool = False) -> "Widget":
        d: dict[str, Any] = {"nodes": nodes, "edges": edges, "truncated": truncated}
        if focus is not None:
            d["focus"] = focus
        return Widget(kind="graph_view", data=d)

    @staticmethod
    def playground(function_ref: dict, breadcrumb: str,
                   suggested_inputs: Optional[list] = None) -> "Widget":
        citation: dict[str, Any] = {"kind": "path", "path": function_ref.get("file")}
        if function_ref.get("line") is not None:
            citation["line_start"] = function_ref["line"]
        d: dict[str, Any] = {"function_ref": function_ref, "breadcrumb": breadcrumb,
                             "citation": citation}
        if suggested_inputs is not None:
            d["suggested_inputs"] = suggested_inputs
        return Widget(kind="playground", data=d)
```

quality.py `_artifact_summary`: add before the generic fallback:

```python
        elif kind == "graph_view":
            nodes = [n for n in (w.get("nodes") or []) if isinstance(n, dict)]
            edges = [e for e in (w.get("edges") or []) if isinstance(e, dict)]
            labels = [str(n.get("label") or n.get("id") or "?") for n in nodes]
            arrows = [f"{e.get('from') or '?'} -> {e.get('to') or '?'}" for e in edges]
            parts.append(f"graph: nodes [{', '.join(labels)}]; edges [{'; '.join(arrows)}]"
                         + ("; truncated" if w.get("truncated") else ""))
        elif kind == "playground":
            fr = w.get("function_ref") or {}
            parts.append(f"playground: run {fr.get('name') or '?'} from {fr.get('file') or '?'}"
                         + (f" — {w.get('breadcrumb')}" if w.get("breadcrumb") else ""))
```

System prompt: document both kinds next to the existing widget docs (graph_view: "nodes/edges MUST come from this turn's get_module_graph or get_callers/get_callees results; every node carries a citation"; playground: "a runnable example descriptor; function_ref must name a real symbol you located this turn; never invent paths").

- [ ] **Step 4:** Run new + existing artifact-honesty tests — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/schema.py src/copyclip/intelligence/cuaderno/quality.py src/copyclip/intelligence/cuaderno/prompts.py tests/test_cuaderno_artifact_honesty.py
git commit -m "feat(shell): graph_view + playground widget factories, judge summarizers, prompt contract"
```

---

### Task 4: Emit-time verification — subset topology + recipe validation

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py` (evidence cache + deep validation at the line-211 chokepoint)
- Modify: `src/copyclip/intelligence/cuaderno/schema.py` OR a new `widget_checks.py` (the two validators — prefer `src/copyclip/intelligence/cuaderno/widget_checks.py`, new focused file)
- Test: `tests/test_cuaderno_widget_checks.py` (create)

- [ ] **Step 1: Failing tests**

```python
"""Emit-time verification: graphs must be subsets of this turn's evidence;
playground recipes must pass launch-grade validation at emit."""
from copyclip.intelligence.cuaderno.widget_checks import (
    validate_widget_payload, GraphEvidence)


def _ev():
    ev = GraphEvidence()
    ev.add_module_graph({"modules": [{"name": "pkg/a", "file_path": "src/pkg/a.py"},
                                     {"name": "pkg/b", "file_path": "src/pkg/b.py"}],
                         "edges": [{"from": "pkg/a", "to": "pkg/b", "weight": 1}],
                         "truncated": False})
    return ev


def test_graph_subset_passes():
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a", "citation": {"kind": "path", "path": "src/pkg/a.py"}},
                   {"id": "pkg/b", "label": "b", "citation": {"kind": "path", "path": "src/pkg/b.py"}}],
         "edges": [{"from": "pkg/a", "to": "pkg/b"}]}
    assert validate_widget_payload({"kind": "widget", "widget": w}, _ev()) is None


def test_invented_edge_rejected():
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a"}, {"id": "pkg/b", "label": "b"}],
         "edges": [{"from": "pkg/b", "to": "pkg/a"}]}   # reversed: not in evidence
    reason = validate_widget_payload({"kind": "widget", "widget": w}, _ev())
    assert reason and "edge" in reason


def test_invented_node_rejected():
    w = {"kind": "graph_view", "nodes": [{"id": "pkg/zz", "label": "zz"}], "edges": []}
    reason = validate_widget_payload({"kind": "widget", "widget": w}, _ev())
    assert reason and "node" in reason


def test_callers_evidence_admits_symbol_edges():
    ev = GraphEvidence()
    ev.add_callers("parse", {"callers": [
        {"name": "main", "kind": "function", "file_path": "src/m.py", "line_start": 2}]})
    w = {"kind": "graph_view",
         "nodes": [{"id": "main", "label": "main"}, {"id": "parse", "label": "parse"}],
         "edges": [{"from": "main", "to": "parse"}]}
    assert validate_widget_payload({"kind": "widget", "widget": w}, ev) is None


def test_bad_recipe_rejected_at_emit():
    w = {"kind": "playground",
         "function_ref": {"file": "../etc/x.py", "name": "f"}, "breadcrumb": "b"}
    reason = validate_widget_payload({"kind": "widget", "widget": w}, GraphEvidence())
    assert reason and "function_ref" in reason


def test_good_recipe_passes():
    w = {"kind": "playground",
         "function_ref": {"file": "src/pkg/a.py", "name": "f", "line": 3},
         "breadcrumb": "b",
         "citation": {"kind": "path", "path": "src/pkg/a.py", "line_start": 3}}
    assert validate_widget_payload({"kind": "widget", "widget": w}, GraphEvidence()) is None


def test_non_graph_widgets_unaffected():
    w = {"kind": "sequence_diagram", "actors": [], "steps": []}
    assert validate_widget_payload({"kind": "widget", "widget": w}, GraphEvidence()) is None
```

- [ ] **Step 2:** Run — FAIL (module missing).

- [ ] **Step 3: Implement** `src/copyclip/intelligence/cuaderno/widget_checks.py`:

```python
"""Emit-time verification for evidence-bearing widgets (Wave 3, spec §4b).
A graph_view must be a SUBSET of this turn's graph evidence; a playground
recipe must pass launch-grade validation at emit, not at click."""
from __future__ import annotations

from typing import Any, Optional

from ..playground import FunctionRef, InvalidFunctionRefError, InvalidRequestError


class GraphEvidence:
    """What graph tools returned this turn: admissible nodes and edges."""

    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.edges: set[tuple[str, str]] = set()

    def add_module_graph(self, result: dict) -> None:
        for m in result.get("modules") or []:
            if isinstance(m, dict) and m.get("name"):
                self.nodes.add(str(m["name"]))
        for e in result.get("edges") or []:
            if isinstance(e, dict) and e.get("from") and e.get("to"):
                self.edges.add((str(e["from"]), str(e["to"])))

    def add_callers(self, symbol: str, result: dict) -> None:
        self.nodes.add(symbol)
        for c in result.get("callers") or []:
            if isinstance(c, dict) and c.get("name"):
                self.nodes.add(str(c["name"]))
                self.edges.add((str(c["name"]), symbol))

    def add_callees(self, symbol: str, result: dict) -> None:
        self.nodes.add(symbol)
        for c in result.get("callees") or []:
            if isinstance(c, dict) and c.get("name"):
                self.nodes.add(str(c["name"]))
                self.edges.add((symbol, str(c["name"])))


def _check_graph_view(w: dict, ev: GraphEvidence) -> Optional[str]:
    for n in w.get("nodes") or []:
        nid = n.get("id") if isinstance(n, dict) else None
        if nid is None or str(nid) not in ev.nodes:
            return f"graph_view node {nid!r} is not in this turn's graph evidence"
    for e in w.get("edges") or []:
        pair = (str(e.get("from")), str(e.get("to"))) if isinstance(e, dict) else ("?", "?")
        if pair not in ev.edges:
            return f"graph_view edge {pair[0]} -> {pair[1]} is not in this turn's graph evidence"
    return None


def _check_playground(w: dict) -> Optional[str]:
    fr = w.get("function_ref")
    if not isinstance(fr, dict):
        return "playground widget missing function_ref"
    try:
        FunctionRef.from_dict(fr)
    except (InvalidFunctionRefError, InvalidRequestError, KeyError, TypeError) as exc:
        return f"playground function_ref invalid: {exc}"
    if not isinstance(w.get("breadcrumb"), str) or not w["breadcrumb"].strip():
        return "playground widget missing breadcrumb"
    return None


def validate_widget_payload(block: Any, evidence: GraphEvidence) -> Optional[str]:
    """None = ok; else a reason string (rides the existing invalid_block ack)."""
    if not isinstance(block, dict) or block.get("kind") != "widget":
        return None
    w = block.get("widget")
    if not isinstance(w, dict):
        return None
    if w.get("kind") == "graph_view":
        return _check_graph_view(w, evidence)
    if w.get("kind") == "playground":
        return _check_playground(w)
    return None
```

(Check the exact exception names exported by `playground.py` first — adjust the import to what exists; `FunctionRef.from_dict` may raise only the two playground error classes.)

In `compositor.py`: create `evidence = GraphEvidence()` next to `emit_status` (line ~197). Where tool RESULTS are produced (the dispatcher call site — find where `get_callers` results come back; same place ledger.record happens), feed the cache:

```python
                if tool_name == "get_module_graph":
                    evidence.add_module_graph(result)
                elif tool_name == "get_callers":
                    evidence.add_callers(args.get("symbol", ""), result)
                elif tool_name == "get_callees":
                    evidence.add_callees(args.get("symbol", ""), result)
```

At the line-211 validation site, extend:

```python
                        reason = validate_block_dict(inp)
                        if reason is None:
                            reason = validate_widget_payload(inp, evidence)
                        emit_status[blk["id"]] = reason
```

Import `from .widget_checks import GraphEvidence, validate_widget_payload`.

- [ ] **Step 4:** Run the new tests + a compositor-level test: extend an existing StubStream compositor test pattern (find one in `tests/test_cuaderno_compositor*.py`) with a stream that calls `get_module_graph` then emits a graph_view with an invented edge — assert the turn retries/acks `invalid_block` (copy the existing invalid-block test shape). Then `python -m pytest tests/ -q -k "cuaderno"` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/widget_checks.py src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_widget_checks.py tests/
git commit -m "feat(shell): emit-time verification — graph subsets of turn evidence, launch-grade recipe validation"
```

---

### Task 5: Runner `run` mode + `"cuaderno"` source + list route

**Files:**
- Modify: `src/copyclip/intelligence/marimo_runner.py` (`launch(notebook_path, mode="edit")`, `list()`)
- Modify: `src/copyclip/intelligence/playground.py` (`PLAYGROUND_SOURCES` + pass mode for cuaderno source)
- Modify: `src/copyclip/intelligence/server.py` (GET `/api/playground` list route)
- Test: append to `tests/test_marimo_runner.py` + `tests/test_playground.py`

- [ ] **Step 1: Failing tests** (copy the `_FakeProcess`/monkeypatch harness already in test_marimo_runner.py):

```python
def test_launch_run_mode_spawn_args(monkeypatch_fake_popen_fixture_style):
    # using the file's existing fake-popen pattern: capture argv
    runner.launch(nb_path, mode="run")
    assert captured_argv[2:4] == ["marimo", "run"]


def test_launch_default_mode_is_edit(...):
    runner.launch(nb_path)
    assert captured_argv[2:4] == ["marimo", "edit"]


def test_list_returns_instances(...):
    pid_a, _ = runner.launch(nb_path)
    items = runner.list()
    assert any(i["id"] == pid_a and i["status"] in ("running", "exited") for i in items)
```

And in test_playground.py (existing live-server harness with Mock runner):

```python
def test_cuaderno_source_accepted_and_launch_passes_run_mode(...):
    # POST /api/playground/launch with source="cuaderno" -> 200; Mock runner
    # asserts it was called with mode="run"
def test_get_playground_list_route(...):
    # GET /api/playground -> {"items": [...]} from runner.list()
```

- [ ] **Step 2:** Run — FAIL.

- [ ] **Step 3: Implement.**
- `marimo_runner.py`: `def launch(self, notebook_path: str, mode: str = "edit")`; the spawn argv uses `mode` in place of the literal `"edit"`. **First verify flag compatibility:** run `python -m marimo run --help` — keep `--host/--port/--headless`; include `--no-token` ONLY if listed for `run` (if absent, build the flag list per mode). Add:

```python
    def list(self) -> list[dict[str, str]]:
        with self._lock:
            ids = list(self._instances)
        return [{"id": i, "status": self.status(i)} for i in ids]
```

- `playground.py`: add `"cuaderno"` to `PLAYGROUND_SOURCES`; in `launch_playground`, call `runner.launch(notebook_path, mode="run" if req.source == "cuaderno" else "edit")` (keep backward compat: StubMarimoRunner/mocks without the kwarg — call with try/except TypeError fallback to positional-only, OR update StubMarimoRunner's signature too; prefer updating the stub).
- `server.py`: GET `/api/playground` (exact match, BEFORE the `/status` prefix matcher) → `{"items": runner.list()}` (guard `getattr(runner, "list", None)` → `[]`).
- TS mirror: `PlaygroundSource` union gains `'cuaderno'`; client `playgroundList: () => getJSON<{items: {id: string; status: PlaygroundStatus}[]}>('/api/playground')`.

- [ ] **Step 4:** `python -m pytest tests/test_marimo_runner.py tests/test_playground.py -q` — PASS (integration tests skip without marimo; fine).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/marimo_runner.py src/copyclip/intelligence/playground.py src/copyclip/intelligence/server.py frontend/src/types/api.ts frontend/src/api/client.ts tests/test_marimo_runner.py tests/test_playground.py
git commit -m "feat(shell): marimo run mode for the cuaderno source + runner.list + GET /api/playground"
```

---

### Task 6: `GraphView.tsx` — frame-scale explanatory graph

**Files:**
- Create: `frontend/src/components/cuaderno/widgets/GraphView.tsx`
- Modify: `frontend/src/types/api.ts` (GraphViewWidget + union), `frontend/src/components/cuaderno/frames/FrameDynamic.tsx` (case), `frontend/src/components/cuaderno/strings.ts` (`graph_truncated`), `frontend/src/styles/cuaderno.css` (container class)

- [ ] **Step 1: Type + case.** api.ts:

```ts
export type GraphViewWidget = {
  kind: 'graph_view'
  nodes: Array<{ id: string; label: string; citation?: AskLikeCitation }>
  edges: Array<{ from: string; to: string; weight?: number }>
  focus?: string
  truncated?: boolean
}
```
(check what citation type name the cuaderno types use — `grep -n "citation" frontend/src/types/api.ts | head` — reuse the existing cuaderno Citation type, NOT a new one). Add to the `Widget` union. FrameDynamic: `case 'graph_view': return <GraphView widget={block.widget} onOpenCitation={onOpenCitation} lang={lang} />`.

- [ ] **Step 2: Component.** Open `Atlas3DPage.tsx:473-525` (layout) and `:660-700` (wheel/pan) as the reference. Build `GraphView.tsx`:
- Props `{ widget: GraphViewWidget; onOpenCitation: (c: Citation) => void; lang?: string | null }`.
- Internal `FlowNode`-like shape derived from widget nodes; tree-ish layout: roots = nodes with no incoming edge; `place(id, x, yCenter)` recursion copied from FlowchartCanvas with constants `LEVEL_GAP = 150, NODE_W = 140, NODE_H = 32, FONT = 11`; cycle guard (visited set — module graphs CAN cycle, FlowchartCanvas's tree assumption must not infinite-loop: skip already-placed nodes, route their edges as cross-links).
- Edges: straight lines for tree links, Bezier for cross-links (copy the path math).
- Focus/dim: click sets focus; connected set at full opacity, rest at 0.15; initial focus from `widget.focus`.
- **Wheel contract:** ctrl/cmd+wheel → zoom (preventDefault ONLY then); plain wheel untouched. Pan via pointer drag. Auto-fit zoom with floor 0.75.
- Palette: focused node fill `var(--accent)` (sienna — check cuaderno.css variable name), others `var(--ink-3)`/`var(--ink-4)` strokes on paper background. NO Atlas color tables.
- Node click with citation → `onOpenCitation(citation)`.
- `truncated` → quiet note under the SVG: `t('graph_truncated', lang)`.
- Container: `div.graph-view` (new CSS: `width:100%; height:420px; overflow:hidden; position:relative`).
- strings.ts both locales: `graph_truncated: 'graph truncated to the strongest connections'` / `'grafo truncado a las conexiones más fuertes'`.

- [ ] **Step 3:** `npm --prefix frontend run build` — green.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/cuaderno/widgets/GraphView.tsx frontend/src/types/api.ts frontend/src/components/cuaderno/frames/FrameDynamic.tsx frontend/src/components/cuaderno/strings.ts frontend/src/styles/cuaderno.css
git commit -m "feat(shell): GraphView widget — frame-scale SVG graph, ctrl+wheel zoom, paper palette, truncation note"
```

---

### Task 7: `PlaygroundWidget.tsx` + single-slot manager

**Files:**
- Create: `frontend/src/components/cuaderno/playgroundSlot.ts` (framework-free store)
- Create: `frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx`
- Modify: `frontend/src/types/api.ts` (PlaygroundWidget type + union), `FrameDynamic.tsx` (case), `strings.ts` (4 state strings), `cuaderno.css` (sized container), `frontend/src/pages/CuadernoPage.tsx` (slot hooks)

- [ ] **Step 1: The slot store** (`playgroundSlot.ts`) — single module-level store, `useSyncExternalStore`-compatible:

```ts
import { api } from '../../api/client'
import type { PlaygroundLaunchRequest } from '../../types/api'

export type SlotState =
  | { kind: 'empty' }
  | { kind: 'spawning'; widgetKey: string; token: number }
  | { kind: 'live'; widgetKey: string; playgroundId: string; iframeUrl: string; token: number }
  | { kind: 'ended'; widgetKey: string; reason: 'closed' | 'evicted' | 'exited' | 'error'; message?: string }

let state: SlotState = { kind: 'empty' }
let token = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
const listeners = new Set<() => void>()

function set(next: SlotState) { state = next; listeners.forEach((l) => l()) }
export function subscribe(l: () => void) { listeners.add(l); return () => listeners.delete(l) }
export function getState(): SlotState { return state }

function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

function startPoll(id: string, widgetKey: string, myToken: number) {
  stopPoll()
  pollTimer = setInterval(async () => {
    try {
      const s = await api.playgroundStatus(id)
      if (token !== myToken) return
      if (s.status !== 'running') {
        stopPoll()
        api.closePlayground(id).catch(() => {})
        set({ kind: 'ended', widgetKey, reason: 'exited' })
      }
    } catch { /* network blip: keep polling */ }
  }, 5000)
}

async function killCurrent(reason: 'closed' | 'evicted'): Promise<void> {
  stopPoll()
  if (state.kind === 'live') {
    const { playgroundId, widgetKey } = state
    set({ kind: 'ended', widgetKey, reason })
    try { await api.closePlayground(playgroundId) } catch { /* reaped on next reconcile */ }
  } else if (state.kind === 'spawning') {
    set({ kind: 'ended', widgetKey: state.widgetKey, reason })
  }
}

export async function launch(widgetKey: string, req: PlaygroundLaunchRequest): Promise<void> {
  const myToken = ++token              // absorbs double-clicks: stale awaits no-op
  await killCurrent('evicted')          // awaited DELETE BEFORE the new POST
  if (token !== myToken) return
  set({ kind: 'spawning', widgetKey, token: myToken })
  try {
    const res = await api.launchPlayground(req)
    if (token !== myToken) { api.closePlayground(res.playground_id).catch(() => {}); return }
    set({ kind: 'live', widgetKey, playgroundId: res.playground_id, iframeUrl: res.iframe_url, token: myToken })
    startPoll(res.playground_id, widgetKey, myToken)
  } catch (e) {
    if (token !== myToken) return
    set({ kind: 'ended', widgetKey, reason: 'error', message: e instanceof Error ? e.message : String(e) })
  }
}

export function close(): void { token++; void killCurrent('closed') }

/** Navigation = death (one-frame reality): any active-frame change kills the runtime. */
export function onActiveFrameChange(): void { token++; void killCurrent('evicted') }

/** Mount reconciliation: anything alive at mount is an orphan from a previous load. */
export async function reconcileOnMount(): Promise<void> {
  try {
    const res = await api.playgroundList()
    await Promise.all(res.items.map((i) => api.closePlayground(i.id).catch(() => {})))
  } catch { /* list route unavailable: nothing to do */ }
}
```

- [ ] **Step 2: The widget** (`PlaygroundWidget.tsx`): `useSyncExternalStore(subscribe, getState)`; the widget's own key = stable identity from its recipe (`${function_ref.file}:${function_ref.name}:${line}`); renders by matching slot state to its key:
- slot not mine OR `empty` → **idle**: function name + file:line CitationChip + breadcrumb + sienna button `t('playground_run', lang)` → `launch(myKey, {source: 'cuaderno', function_ref, suggested_inputs, breadcrumb})`.
- mine + `spawning` → paper skeleton + `t('playground_preparing', lang)`.
- mine + `live` → iframe `src={iframeUrl}` `sandbox="allow-scripts allow-same-origin allow-forms"` in `div.playground-live` (CSS: `position:relative; width:100%; height:480px;` iframe `position:absolute; inset:0; width:100%; height:100%; border:0`), plus a quiet close affordance → `close()`.
- mine + `ended` → still + `t(reason === 'evicted' ? 'playground_evicted' : 'playground_ended', lang)`; `error` shows `message` in the same register (keep `marimo_not_installed`'s message intact — it carries the install hint); the run button renders again (re-launchable).
PlaygroundWidget type in api.ts: `{ kind: 'playground'; function_ref: FunctionRef; breadcrumb: string; suggested_inputs?: unknown[]; citation?: ... }`; union + FrameDynamic case.
strings.ts both locales: `playground_run` ('run example'/'correr ejemplo'), `playground_preparing` ('preparing…'/'preparando…'), `playground_ended` ('runtime ended — run again to relaunch'/'el runtime terminó: corre de nuevo para relanzarlo'), `playground_evicted` ('paused — another example is running'/'en pausa: hay otro ejemplo corriendo').

- [ ] **Step 3: CuadernoPage hooks.** In `CuadernoPage.tsx`: `useEffect(() => { void reconcileOnMount() }, [])`; call `onActiveFrameChange()` inside BOTH the new-question submit handler (~onAsk, line 61-71) and the history-switch handler (~156-158) — read the file and place the calls where the active frame actually changes.

- [ ] **Step 4:** `npm --prefix frontend run build` — green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cuaderno/playgroundSlot.ts frontend/src/components/cuaderno/widgets/PlaygroundWidget.tsx frontend/src/types/api.ts frontend/src/components/cuaderno/frames/FrameDynamic.tsx frontend/src/components/cuaderno/strings.ts frontend/src/styles/cuaderno.css frontend/src/pages/CuadernoPage.tsx
git commit -m "feat(shell): PlaygroundWidget — recipe-to-runtime with single slot, 5s poll, navigation kills, mount reconciliation"
```

---

### Task 8: Delete the global modal + Atlas's live launch path (declared live-feature removal)

**Files:**
- Delete: `frontend/src/components/PlaygroundPanel.tsx`, `frontend/src/hooks/usePlayground.tsx`
- Modify: `frontend/src/App.tsx` (PlaygroundProvider mounts + PlaygroundPanel render, ~105/114/157)
- Modify: `frontend/src/pages/Atlas3DPage.tsx` (LAUNCHABLE_NODE_TYPES ~21-42, launchableSelection ~1197-1214, the launch button block ~1238-1263, the usePlayground import)

- [ ] **Step 1: Prove the post-W3 consumer count**

```bash
grep -rn "usePlayground\|PlaygroundPanel\|PlaygroundProvider" frontend/src/
```
Expected consumers: PlaygroundPanel itself, the hook file, App.tsx mounts, Atlas3DPage. The NEW widget (Task 7) must NOT import any of them. If anything else matches, STOP, report BLOCKED.

- [ ] **Step 2: Delete + edit.** `git rm` the two files; remove App.tsx Provider wrappers + Panel render; in Atlas3DPage remove the import, the LAUNCHABLE_NODE_TYPES block, launchableSelection, isPythonSymbolPath if launch-only (grep its other uses first), and the launch-button JSX. The page must still render its graph.

- [ ] **Step 3: Verify**

```bash
grep -rn "usePlayground\|PlaygroundPanel\|PlaygroundProvider\|LAUNCHABLE_NODE_TYPES\|launchableSelection" frontend/src/ && echo LEFTOVERS || echo CLEAN
npm --prefix frontend run build
```
Expected: CLEAN; build green.

- [ ] **Step 4: Commit** (message declares the truth — this removes a LIVE feature):

```bash
git commit -am "feat(shell): remove the global playground modal and Atlas3D's live launch path — replaced by the in-frame cuaderno playground (page dies whole on 2026-06-19)"
```

---

### Task 9: Settings paper re-skin

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1:** Read the page. Replace the heading "Configuration Nexus" with "Settings"; replace "Configure how Project Memory sees, interprets, and speaks" and "Interpretive Providers" with plain text ("Configure the LLM provider and API keys." / section title "Providers"). Re-skin: swap dark-panel classes for paper equivalents (reuse cuaderno.css variables — if the page's classes come from styles.css dark theme, scope a minimal paper container: background `var(--paper, #faf6f0)`-style tokens already defined in cuaderno.css — read both CSS files and reuse, do not invent new tokens). Zero plumbing changes.

- [ ] **Step 2:** `npm --prefix frontend run build` — green. Commit:

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat(shell): Settings drops the Nexus costume — plain name, paper chrome, zero plumbing changes"
```

---

### Task 10: Wave gate

- [ ] **Step 1:** `python -m pytest tests/ -q` (rotating Windows-flaky families re-run individually if they fail) + `npm --prefix frontend run build` + `bash scripts/dev-smoke.sh`.
- [ ] **Step 2:** Regenerate served bundle: `cp frontend/dist/index.html src/copyclip/intelligence/ui/index.html`; verify it contains `graph_view`/`playground_run` strings and zero `PlaygroundPanel` references; commit `chore(shell): regenerate served UI bundle for wave 3`.
- [ ] **Step 3:** Live checklist (the human's): module graph renders flat/paper with working citations and page-scroll over the graph; marimo example spawns on click in run view; second example evicts the first honestly; history switch kills the subprocess (verify `GET /api/playground` empty); browser reload reconciles on mount; restored frame lands idle.
- [ ] **Step 4:** Branch ready: squash subject `feat(shell): wave 3 — graph_view + playground proof artifacts (#NN)`.
