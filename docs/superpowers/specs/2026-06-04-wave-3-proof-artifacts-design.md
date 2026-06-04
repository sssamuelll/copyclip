# Wave 3 — Proof Artifacts: `graph_view` + `playground` in the Frame

**Date:** 2026-06-04 (v2 — revised after full roster review: Serrano, Halberg, Vale, Tane, Richter; 49 findings)
**Status:** Approved (Samuel; v2 decisions ratified 2026-06-04)
**Parent:** `2026-06-04-cuaderno-shell-consensus-design.md` (Wave 3 of 5)
**Depends on:** Wave 2's artifact-aware honesty backbone (merged, #133)

## Goal

Ship the two ratified proof artifacts on top of the widened gate: an Atlas-grade explanatory graph the tutor emits inside frames, and marimo as a didactic, click-to-run example bound to the conversation. Re-skin Settings as the one legitimate side surface.

## Ratified decisions (v1 + v2)

| Decision | Ruling |
|---|---|
| Graph data contract | Inline bounded subset + new tool. Data-ref hydration only if a full graph in a frame is ever wanted. |
| Graph topology source | **`symbol_edges` aggregated to module level** (v2 — supersedes `dependencies`). Serrano/Halberg proved `dependencies.to_module` stores import-target bases (`'os'`, `'copyclip'`) while `modules.name`/`symbols.module` use relpath format (`'copyclip/intelligence'`): the namespaces do not join, edges would dangle uncited. `symbol_edges JOIN symbols` has both endpoints in the same namespace WITH file paths — and naturally excludes stdlib/external pseudo-modules, which also fixes Halberg's routine-false-confession finding. |
| Playground concurrency | Single active slot, owned at CuadernoPage level (v2: it must survive frame remounts — see One-Frame Reality). |
| Subprocess trust | Spawn-on-CLICK only. The compositor never spawns. |
| Marimo mode for the cuaderno | **`marimo run` (app view)** (v2). `edit` is a full IDE that neither fits the ~596px usable column (Tane) nor respects the ratified exposition-not-authorship ceiling. The runner gains a parametrized mode; source `"cuaderno"` launches `run`. |
| Atlas modal deletion | **Delete, declared as live-feature removal** (v2). Richter exposed the "#104 dead connector" as a two-consensus-round myth: `launchableSelection` enables for Python symbol nodes after module expand and `playground.launch({source:'atlas'})` is reachable. We delete it anyway — Atlas3DPage dies whole on 2026-06-19 and the in-frame playground is its replacement — but the record says we removed a live feature, not dead code. |
| Renderer strategy | Purpose-built `GraphView` with **frame-scale constants** (v2 — Atlas constants overflow the column; see 1c). Atlas3DPage is not refactored. ArchitecturePage (Wave 4) mounts this same widget. |
| Gate interaction | **The Wave-2 gate IS extended this wave** (v2 — supersedes v1's "no gate changes", which three critics proved false): tool-evidenced paths join the comparable set, and graph topology is verified by construction (§4). |

## One-Frame Reality (Halberg's blocker — the constraint that shapes §2)

The cuaderno renders ONLY the active question; `Cuaderno.tsx` keys the frame div by position, forcing a FULL REMOUNT on every history switch and every new question (`onAsk` clears the active frame into midstream scene). There is no scrollable multi-frame conversation. Consequences encoded below: the slot manager lives above the frame; navigating away from a frame with a live playground kills it; nothing assumes two frames coexist.

## 1. `graph_view` — the explanatory graph artifact

### 1a. Tool: `get_module_graph` (v2 design)

`anchor.py` implementation + **explicit registration in BOTH `build_tool_definitions()` and `dispatch_tool()`** + system-prompt advertisement (Serrano's blocker: an unregistered tool is invisible and uncallable; all three registration points are deliverables).

- Topology: `SELECT s1.module AS from_m, s2.module AS to_m, COUNT(*) AS weight FROM symbol_edges e JOIN symbols s1 ON e.<from_col>=s1.id JOIN symbols s2 ON e.<to_col>=s2.id WHERE s1.module != s2.module AND project_id=? GROUP BY s1.module, s2.module` (adapt column names to the real `symbol_edges` schema — read it first; `get_callers` in anchor.py shows the working join).
- Node citations: `SELECT module, MIN(file_path) FROM symbols WHERE project_id=? GROUP BY module` — same namespace, always resolvable for any module that appears as an edge endpoint (guaranteed: endpoints come from `symbols`).
- `scope` filters modules by substring (empty = whole project, still capped).
- **Cap semantics (v2, deterministic):** rank modules by edge degree DESC then name ASC; keep top 50; THEN prune edges to surviving endpoints; THEN cap edges at 80 by weight DESC. No dangling edges, ever. `truncated: true` when either cap bites.
- Returns `{modules: [{name, file_path}], edges: [{from, to, weight}], truncated: bool}`.
- The tool result records every returned `file_path` into the ledger's tool-evidenced set (§4).

### 1b. Widget kind `graph_view`

- `Widget.graph_view(nodes, edges, focus=None, truncated=False)` → data `{nodes: [{id, label, citation?}], edges: [{from, to, weight?}], focus?: str, truncated: bool}`.
- The tutor assembles it from `get_module_graph` (module-level) or `get_callers`/`get_callees` (symbol-level); every node carries a `citation`.
- **Truncation confesses to the HUMAN** (Vale): when `truncated`, the widget renders a quiet note ('graph truncated to the strongest connections' / 'grafo truncado a las conexiones más fuertes').
- `_artifact_summary` gains a `graph_view` per-kind summarizer.
- Topology is verified by construction at emit time (§4).

### 1c. Frontend `GraphView.tsx` (v2 frame-scale)

- Core techniques from FlowchartCanvas (deterministic recursive layout, Bezier cross-links, focus/dim) with **frame-derived constants**, not Atlas constants (Tane: LEVEL_GAP 280 / NODE_W 200 spans ~1040px in a ~596px usable column, forcing illegible 0.4 zoom): LEVEL_GAP ≈ 150, NODE_W ≈ 140, NODE_H ≈ 32, 11px labels; auto-fit with a **min-zoom floor of 0.75** — below the floor, the graph pans instead of shrinking into illegibility.
- **Wheel contract (Halberg):** plain wheel scrolls the page — NO unconditional `preventDefault`. Zoom only on ctrl/cmd+wheel (preventDefault only then); pan by drag inside the container.
- Container: 100% width of the widget body, fixed height ~420px, paper palette (one sienna for the focused node, ink/gray tones from cuaderno.css variables otherwise), `.widget` chrome.
- Node click with citation → `onOpenCitation`. FrameDynamic gains `case 'graph_view'`; types/api.ts gains `GraphViewWidget`.

## 2. `playground` — the didactic runnable artifact

### 2a. Widget kind `playground`

- Data = the recipe: `{function_ref: {file, name, line?, qualname?}, suggested_inputs?: [...], breadcrumb: str, citation}`.
- **Emit-time validation (v2 — Serrano):** the compositor validates the recipe with the SAME rules `playground.py` enforces at launch (identifier name, ≤2-segment qualname, relative no-`..` path, importable module segments — import/reuse the validators, never duplicate them). An invalid recipe → `invalid_block` + the existing retry latch. An unrunnable recipe is never offered to the human; click-time 400 stops being the discovery point.
- `_artifact_summary` summarizer: `playground: run {name} from {file} — {breadcrumb}`.
- Stale-recipe honesty (Vale, accepted + surfaced): a restored recipe may point at moved/deleted code; launch-time `function_not_found` renders in the widget's error register. Accepted for this wave; re-resolution against the live symbol table is a future refinement.

### 2b. Backend

- `PLAYGROUND_SOURCES` gains `"cuaderno"` (+ TS mirror).
- **Runner mode parameter (v2):** `launch(notebook_path, mode="edit")`; `"run"` spawns `python -m marimo run …` (same host/port/headless/no-token flags). The launch route passes `mode="run"` when `source == "cuaderno"`; existing sources keep `edit` until they die.
- **New list route (v2 — reload reconciliation):** `GET /api/playground` → `{items: [{id, status}]}` from a new `runner.list()`. On cuaderno mount, the slot manager fetches the list and DELETEs every instance — after this wave the cuaderno is the only launcher, so anything alive at mount is an orphan from a previous page load (Halberg: browser reload leaks a slot otherwise; kill_all only fires on server shutdown).
- Notebook template: unchanged (already imports the real symbol).

### 2c. Frontend in-frame runtime

New `PlaygroundWidget.tsx` + a **single-slot manager at CuadernoPage level** (survives frame remounts; the slot keys on `playgroundId` + question position):

1. **idle** — still preview (function name, file:line citation chip, breadcrumb) + one sienna "run example" affordance. Restored frames always land here (the recipe persists; never a URL/port).
2. **spawning** — paper-toned skeleton during POST (`{source:"cuaderno", mode-resolved server-side}`). **Launch serialization (v2 — Halberg):** a monotonic launch token (port the deleted `launchTokenRef` pattern); the eviction DELETE is AWAITED before the new POST; a double-click is absorbed by the token guard.
3. **live** — iframe `sandbox="allow-scripts allow-same-origin allow-forms"` inside a **dedicated sized container** (v2 — Tane: `.widget-body` has no height; an iframe collapses to 0): new CSS class, width 100%, height ~480px, iframe fills absolutely. `marimo run` app view fits this; `edit` would not.
4. **runtime ended** — sealed still + quiet provenance line; never a broken iframe, never `null`. Entered on: explicit close, eviction, **status poll** result `exited`/`missing`, navigation away, or launch error (`marimo_not_installed` keeps its install hint).

**Status poll (v2 — specified, it did not exist anywhere):** owned by the slot manager; every 5s while a playground is `live`; GET `/{id}/status`; `running` → stay; `exited`/`missing` → runtime ended + best-effort DELETE; poll teardown on slot clear/unmount.

**Navigation = death (v2 — One-Frame Reality):** history switch and new-question both unmount the active frame; the slot manager (living above the frame) detects the active-frame change and issues DELETE + transitions the slot to empty. The persisted widget stays a recipe → next visit renders idle. The example runs while you look at it.

**The global modal dies — as a live-feature removal:** `PlaygroundPanel.tsx`, `usePlayground.tsx`, the `PlaygroundProvider` mounts, AND Atlas3D's working launch path (`LAUNCHABLE_NODE_TYPES`, `launchableSelection`, the launch button, the `usePlayground` import) are deleted. Atlas3DPage keeps rendering its graph; its playground capability is replaced by the cuaderno's in-frame artifact 15 days before the page itself dies.

### 2d. Strings (es/en, quiet register, banlist-clean)

`strings.ts`: `playground_run` ('run example' / 'correr ejemplo'), `playground_preparing` ('preparing…' / 'preparando…'), `playground_ended` ('runtime ended — run again to relaunch' / 'el runtime terminó: corre de nuevo para relanzarlo'), `playground_evicted` ('paused — another example is running' / 'en pausa: hay otro ejemplo corriendo'), `graph_truncated` ('graph truncated to the strongest connections' / 'grafo truncado a las conexiones más fuertes'). Final microcopy pass at implementation; no Tier-1 banlist words; es uses colon, not em dash.

## 3. Settings as paper side surface

Unchanged from v1: "Configuration Nexus" → "Settings", plain description, paper chrome via cuaderno.css variables, zero plumbing changes.

## 4. Honesty regime — what this wave EXTENDS (supersedes v1 §4)

### 4a. Tool-evidenced paths (fixes the fabricated-grounding collision)

Three critics proved v1's "no gate changes" false: DB-derived widget citations are disjoint from `read_paths`, so one incidental `read_file` + a 50-node graph seals the whole frame `ungrounded` (quality.py disjoint check). Fix: `ReadLedger` gains a **tool-evidenced path set** — evidence tools that return real `file_path`s (`get_module_graph`, `grep_symbols`, `get_callers`, `get_callees`, `find_tests`) record them. The fabrication check compares `cited` against `read ∪ tool_evidenced`. Honest semantics preserved: a citation must point at something a tool actually returned this turn. (Also fixes Vale's "inert check" finding: graph turns now have a comparable set instead of an empty one.)

### 4b. Verified-by-construction topology (fixes Vale's blocker)

Nothing in Wave 2 checks EDGES — a graph with invented dependencies would seal `answer` with `artifacts_cited=True`. Fix at the emit chokepoint: the compositor caches this turn's graph-evidence results (`get_module_graph`, `get_callers`, `get_callees`); `emit_block` validation for a `graph_view` verifies nodes and edges are a **subset of cached evidence** (module edges against the tool's edge list; symbol edges against caller/callee pairs). Non-subset → `invalid_block` + existing retry latch. The graph becomes what Voronov demanded: a projection of evidence the ledger already holds — enforced, not hoped.

### 4c. Accepted limitations (named, not hidden)

- `artifacts_cited` stays per-frame all-or-nothing (Vale): a 49/50-cited graph reads as cited. 4b removes the sharp edge (invented topology); per-widget confession is a future wave.
- Stale recipes/citations on restore are surfaced at launch (`function_not_found`), not re-resolved at render.
- "Runtime ended" after a failed best-effort DELETE may briefly understate a dying process; the status poll converges it.

## 5. Testing

- TDD backend: `get_module_graph` (namespace correctness: edges join modules; scope; deterministic cap + pruning — no dangling edges; truncated flag; citations always resolvable; ledger records tool-evidenced paths), tool REGISTRATION (definitions + dispatch — a test that calls the tool through dispatch_tool), recipe emit-time validation (valid passes; `..` path / 3-segment qualname / non-identifier name → invalid_block), subset verification (graph_view ⊆ evidence passes; invented edge → invalid_block), gate: cited-vs-(read ∪ tool_evidenced) (graph turn with zero read_file no longer condemnable; true fabrication still seals), `_artifact_summary` both kinds, runner mode parameter (`run` in spawn args for cuaderno source), `runner.list()` + GET /api/playground.
- Frontend: build only (standing decision); FrameDynamic renders both kinds.
- Live gate: real `copyclip start` — module graph renders flat/paper with working citations and page-scroll over the graph; marimo example spawns on click in `run` view, second example evicts the first honestly, history switch kills the subprocess (verify via `GET /api/playground`), browser reload reconciles orphans on mount, restored frame lands idle.

## Out of scope (later waves)

ArchitecturePage folding into `graph_view` (Wave 4); marimo UI elements/sliders; data-ref hydration; per-widget citation confession; recipe re-resolution on restore; sidebar label renames beyond Settings (Wave 4); Atlas3DPage deletion (Wave 5).
