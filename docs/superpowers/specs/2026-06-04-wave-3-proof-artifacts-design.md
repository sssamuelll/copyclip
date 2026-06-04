# Wave 3 — Proof Artifacts: `graph_view` + `playground` in the Frame

**Date:** 2026-06-04
**Status:** Approved (Samuel, 2026-06-04)
**Parent:** `2026-06-04-cuaderno-shell-consensus-design.md` (Wave 3 of 5)
**Depends on:** Wave 2's artifact-aware honesty backbone (merged, #133)

## Goal

Ship the two ratified proof artifacts on top of the widened gate: an Atlas-grade explanatory graph the tutor emits inside frames, and marimo as a didactic, click-to-run example bound to the conversation. Re-skin Settings as the one legitimate side surface.

## Ratified decisions

| Decision | Ruling |
|---|---|
| Graph data contract | **Inline bounded subset + new tool** (supersedes the consensus plan's data-ref note, which targeted the full 800-edge graph). `get_module_graph` returns cited topology; the tutor emits a ≤50-node subset inline. Data-ref hydration arrives only if a full graph in a frame is ever wanted. |
| Playground concurrency | **Single active slot.** Launching a playground from a frame kills the previous one (DELETE); its widget transitions to "runtime ended". |
| Subprocess trust | Spawn-on-CLICK only (Wave-2 ratification stands). The compositor never spawns — it emits a recipe. |
| Renderer strategy | **Purpose-built `GraphView` widget renderer** copying FlowchartCanvas's proven core (~200 lines: deterministic recursive layout, Bezier cross-links, focus/dim) and dropping page-isms. Atlas3DPage is NOT refactored — it dies whole in Wave 5 (2026-06-19). "No second renderer" holds where it matters: ArchitecturePage (Wave 4) mounts this same widget. |
| Marimo template | Unchanged this wave. It already imports the REAL resolved symbol (`from {mod} import {name}`) — Vale's fabricated-pedagogy risk is covered by construction. marimo UI elements (sliders) are a future wave. |

## Verified facts this design relies on

- **Atlas3D is SVG, not Three.js.** `FlowchartCanvas` (Atlas3DPage.tsx:378-987) is a props-driven `forwardRef` SVG renderer (`data: FlowData {nodes:{id,name,type,path}, links:{source,target,type}}`, `nodeColors`/`edgeColors` as props, deterministic `place()` layout: LEVEL_GAP 280 / NODE_GAP 16 / NODE_H 40 / NODE_W 200; focus/dim via `connectedIds`, non-focused at opacity 0.15).
- `/api/architecture/graph` (server.py ~1190): nodes are `{name}` only; edges `{from,to,type}` LIMIT 800; module→file mapping exists via `symbols.module + symbols.file_path`.
- No cuaderno tool returns module topology today; `get_callers`/`get_callees` return flat symbol lists.
- Playground stack is real and complete: `PLAYGROUND_SOURCES` (7 values, others rejected 400), `PlaygroundLaunchRequest {source, function_ref{file,name,line?,qualname?}, deps_hint?, suggested_inputs?, breadcrumb}`, runner cap 5 (`NoFreePortError`), spawn `python -m marimo edit --headless --no-token`, healthcheck 10s, `kill()` removes tempdir, `kill_all()` on shutdown, orphan sweep on startup, DELETE `/api/playground/{id}` + GET `/{id}/status` routes, `usePlayground.close()` really kills.
- Widget pipeline is generic: SSE/persistence round-trip any widget dict; `validate_block_dict` only checks block kind; new widget kind crosses exactly: schema.py factory, types/api.ts union, FrameDynamic switch (unknown kind falls to `return null` — must not be reachable for the new kinds).
- Wave-2 backbone: `_walk_citations` collects citations recursively from any widget data (new kinds covered for free); `artifacts_cited` injected at `_seal`; `_artifact_summary` has a generic fallback (per-kind summarizers preferred for readability).
- Dead connector: `LAUNCHABLE_NODE_TYPES` + the permanently-disabled launch button (Atlas3DPage.tsx ~21-42, 1186-1253, the #104 path) — ratified for deletion THIS wave.
- `PlaygroundProvider` wraps both App branches; `PlaygroundPanel` is a global modal (App.tsx:157). Atlas3DPage's only usePlayground consumer is the dead #104 path.

## 1. `graph_view` — the explanatory graph artifact

### 1a. Tool: `get_module_graph`

`anchor.py` + `tool_catalog.py`. Signature: `get_module_graph(scope: str = "")`.
- Query `modules` + `dependencies` for the project; map each module to its file via `SELECT module, MIN(file_path) FROM symbols GROUP BY module` (deterministic representative file).
- `scope` filters modules by substring (empty = whole graph, still capped).
- **Cap: 50 modules / 80 edges** (tool-side; the result names the truncation when it bites — no silent caps).
- Returns `{modules: [{name, file_path}], edges: [{from, to, type}], truncated: bool}`.

### 1b. Widget kind `graph_view`

- Schema factory: `Widget.graph_view(nodes, edges, focus=None)` with data `{nodes: [{id, label, citation?}], edges: [{from, to, type?}], focus?: str}`.
- The tutor assembles it from `get_module_graph` (module-level) or `get_callers`/`get_callees` (symbol-level); **every node that asserts something about the code carries a `citation`** (Wave-2 contract; the collector picks them up with zero gate work).
- `_artifact_summary` gains a `graph_view` per-kind summarizer (same shape as graph_subset's: labels + `A -> B` arrows).
- System-prompt/Block-schema documentation of the new kind (wherever the existing 3 widget kinds are documented to the model — match that pattern).

### 1c. Frontend `GraphView.tsx`

- Copies FlowchartCanvas's core: deterministic recursive layout (`place()`), straight CONTAINS lines + Bezier cross-links, focus/dim on click (non-connected at low opacity), pan/zoom within the container.
- Drops page-isms: module expand, orphans toggle, drag, minimap, launch button.
- **Paper palette (Tane's rule):** one sienna for the focused node, grays/ink tones otherwise; no 26-color rainbow; fits the 760px reading column, fixed height (~420px), `.widget` chrome.
- Node click with a citation → `onOpenCitation` (same affordance as CallersTree).
- FrameDynamic switch gains `case 'graph_view'`; types/api.ts gains `GraphViewWidget` in the union.

## 2. `playground` — the didactic runnable artifact

### 2a. Widget kind `playground`

- Data = **the recipe, never a live handle**: `{function_ref: {file, name, line?, qualname?}, suggested_inputs?: [...], breadcrumb: str, citation: {kind:'path', path: file, line_start: line}}`.
- Schema factory `Widget.playground(function_ref, breadcrumb, suggested_inputs=None)` derives the citation from the function_ref.
- The compositor has NO spawn capability (unchanged — verified it takes no runner). The tutor emits the descriptor with `suggested_inputs`/`breadcrumb` harvested from its read evidence.
- `_artifact_summary` per-kind summarizer: `playground: run {name} from {file} — {breadcrumb}`.

### 2b. Backend

- `PLAYGROUND_SOURCES` gains `"cuaderno"` (playground.py:25-35) + the TS `PlaygroundSource` union mirror.
- Notebook template, runner, routes: **unchanged**.

### 2c. Frontend in-frame runtime (the four states)

New `PlaygroundWidget.tsx` rendered by FrameDynamic's `case 'playground'`:
1. **idle** — still preview (function name, file:line citation chip, breadcrumb) + one sienna "run example" affordance. Restored frames ALWAYS land here (the recipe is what persists; never a URL/port).
2. **spawning** — paper-toned skeleton (no cyan spinner) while POST `/api/playground/launch` runs ({source:"cuaderno", ...recipe}).
3. **live** — `<iframe sandbox="allow-scripts allow-same-origin allow-forms">` in fixed-aspect `.widget-body`.
4. **runtime ended** — sealed still + quiet provenance line; never a broken iframe, never `null`. Entered on: explicit close, eviction by the single slot, status poll says exited, or launch error (error detail shown in the same register; `marimo_not_installed` keeps its install hint).

**Single active slot:** cuaderno-level state (one `{playgroundId, frameKey}` at a time). Launching from any frame: if a previous playground is live → `DELETE` it and transition its widget to runtime-ended, then launch the new one. Closing the conversation view does best-effort DELETE (the runner's shutdown kill_all + orphan sweep are the backstop).

**The global modal dies:** `PlaygroundPanel.tsx`, `usePlayground.tsx`, and the `PlaygroundProvider` mounts in App.tsx are DELETED — their only consumers are the modal itself and the dead #104 path. The new `PlaygroundWidget` owns its state through a small cuaderno-local single-slot manager (module-level state or a context scoped to CuadernoPage — implementer's call, but it lives under `frontend/src/components/cuaderno/`). **The Atlas3D #104 dead connector is deleted** (LAUNCHABLE_NODE_TYPES, the launchableSelection gate, the disabled button block, its usePlayground import) — Atlas3DPage keeps rendering its graph with zero playground references.

### 2d. Strings (es/en, quiet register, banlist-clean)

`strings.ts`: `playground_run` ('run example' / 'correr ejemplo'), `playground_preparing` ('preparing…' / 'preparando…'), `playground_ended` ('runtime ended — run again to relaunch' / 'el runtime terminó: corre de nuevo para relanzarlo'), `playground_evicted` ('paused — another example is running' / 'en pausa: hay otro ejemplo corriendo'), plus error-state reuse of existing patterns. (Final microcopy pass at implementation; no Tier-1 banlist words, no em dash in es.)

## 3. Settings as paper side surface

`SettingsPage.tsx`: "Configuration Nexus" → "Settings"; "Configure how Project Memory sees, interprets, and speaks" + "Interpretive Providers" → plain descriptions (configure the LLM provider and API keys); re-skin to paper chrome reusing cuaderno.css variables. No plumbing changes (verified: owns zero analyze routes).

## 4. Honesty & bench

- Both kinds enter the Wave-2 regime with no gate changes: citations collected recursively; `artifacts_cited` confesses uncited graphs; the judge sees both via per-kind summarizers.
- Bench `has_artifact` already supports `kind: "graph_view"` / `"playground"` (kind is an open string). No corpus change → corpus_sha unchanged.

## 5. Testing

- TDD backend: `get_module_graph` (scope filter, cap + truncated flag, citations present, empty DB), widget factories + the citation derivation, `_artifact_summary` summarizers for both kinds.
- TDD frontend-adjacent (Python): `"cuaderno"` accepted by PLAYGROUND_SOURCES; launch request from a recipe validates.
- Single-slot contract: with a Mock runner — launching a 2nd playground issues DELETE for the 1st (test at the API-client call level or via the state module if extracted; otherwise covered by build + live check).
- Frontend: `npm --prefix frontend run build` only (no test runner, standing decision); FrameDynamic renders both kinds (no `return null` path reachable for them).
- Live gate: a real `copyclip start` session — ask for a module graph (renders flat/paper, citations clickable), run a marimo example (spawn on click, ESC/close kills, second example evicts the first honestly), restore the session (recipe → idle, no dead iframe).

## Out of scope (later waves)

ArchitecturePage folding into `graph_view` (Wave 4); marimo UI elements/sliders; data-ref hydration for full graphs; sidebar label renames beyond Settings (Wave 4 chrome reconciliation); Atlas3DPage deletion (Wave 5).
