# Anchored Playground — Design Spec

**Date**: 2026-05-22
**Status**: Approved for implementation
**Tracking**: Epic issue (TBD on creation)

## Why

CopyClip's wedge is *"stay attached to your codebase while AI writes most of it"*. Today the dashboard tells the developer:

- **What** changed → git log, Changes page
- **Why** it changed → Decision History, MemPalace recap (PR #83)
- **Where** it lives → Codebase Map (Atlas)
- **What might bite you** → Debt Navigator, Risks

What it does NOT show is **observable behavior**. The hardest cognitive jump — going from *reading* a function to *understanding* what it actually does — is left entirely to the developer's head. When AI wrote the function, that jump is the **single biggest source of cognitive load** in the workflow CopyClip targets.

This spec introduces an **Anchored Playground**: a runnable sandbox that opens **pre-loaded** from anywhere in the dashboard with the relevant code, dependencies, and example inputs already in place. Never an empty buffer. Always anchored to a specific function, decision, debt entry, or risk.

## Non-goals

This is **not** a general-purpose Jupyter alternative. We do not compete with VS Code Jupyter, Cursor's notebook, Replit, or any "scratch buffer" surface. The differentiator is **the bridge** that brings codebase context into the playground — never the playground itself.

Out of scope for v1:

- Free-form notebook editing without an anchor
- Multi-language execution (only Python in v1)
- Saved snippets / state persistence between sessions
- Kernel pooling / pre-warmed subprocesses
- Inline AI assistance inside the playground
- Editing the user's source files from the playground

## Architecture

Three layers, with the bridge contract as the single most important interface.

```
┌────────────────────────────────────────────────────────────────┐
│ Surfaces (frontend, multiple)                                  │
│  Atlas3D · Reacquaintance · Debt Navigator · Decision History  │
│  Risks · Timeline · Context Builder                            │
│  each emits a PlaygroundLaunchRequest on user gesture          │
└─────────────────────────┬──────────────────────────────────────┘
                          │
                  POST /api/playground/launch
                          │
              ┌───────────▼────────────┐
              │ Bridge (Python)         │
              │ src/copyclip/intelligence/playground.py
              │                         │
              │  ┌──────────────────┐   │
              │  │ resolver         │   │   resolves function_ref
              │  │ (uses analyzer)  │   │   to (file, name, imports)
              │  └──────────────────┘   │
              │  ┌──────────────────┐   │
              │  │ marimo file gen  │   │   writes .py template
              │  │                  │   │   with cells: imports,
              │  └──────────────────┘   │   target call, free cell
              └───────────┬─────────────┘
                          │
              ┌───────────▼────────────┐
              │ Subprocess manager      │
              │ marimo_runner.py        │
              │   spawn on free port    │
              │   healthcheck           │
              │   kill on close         │
              └───────────┬─────────────┘
                          │
                  http://localhost:{port}
                          │
              ┌───────────▼────────────┐
              │ Frontend (React)        │
              │ PlaygroundPanel.tsx     │
              │   iframe shell          │
              │   cyan-only chrome      │
              │   breadcrumb header     │
              │   close → DELETE        │
              └─────────────────────────┘
```

### Stack lock-in (do NOT re-discuss in PRs)

These are decided. Sub-issue PRs do not re-open them.

| Decision | Choice | Why |
|---|---|---|
| Notebook engine | **Marimo** (Apache-2.0) | Reactive model = "change input, see dependent cells re-run" matches the "understand behavior" wedge directly. Pure-Python file format = git-friendly. Less code to write than a Jupyter UI. |
| Embedding | **iframe** | Fastest path to working UI. Custom UI on top of Marimo's backend is v2 if estheticxz conflicts. |
| Language | **Python only** in v1 | JS/TS support deferred. Multi-language would require a kernel abstraction we don't need yet. |
| Process model | **Spawn-on-demand**, one subprocess per launch | No kernel pool. Killed when panel closes. Optimize only if it hurts. |
| Persistence | **None** in v1 | Each launch is fresh. Saved snippets is a v2 feature. |
| Web framework | **Existing stdlib HTTP** (`BaseHTTPRequestHandler` in `server.py`) | No new framework. New routes go in the existing `do_POST` dispatch. |
| Temp file location | `tempfile.mkdtemp(prefix="copyclip-playground-")` | Standard, OS-managed cleanup. |

Rejected alternatives (briefly): JupyterLite/Pyodide cannot import the user's real Python env (no native deps, no filesystem). Jupyter Server is heavier; revisited in v3 only if multi-language matters. Building our own notebook UI is reinventing the wheel.

## The Bridge Contract

**Single most important artifact in this spec.** Every connector emits the same shape. The bridge does not know which surface called it.

### Wire shape (TypeScript)

```typescript
type PlaygroundLaunchRequest = {
  source:
    | "atlas"
    | "reacquaintance"
    | "debt_navigator"
    | "decisions"
    | "risks"
    | "timeline"
    | "context_builder";
  function_ref: {
    file: string;          // absolute or project-relative path
    name: string;          // function or method name
    line?: number;         // optional, for disambiguation
    qualname?: string;     // optional, e.g. "ClassName.method_name"
  };
  deps_hint?: string[];    // optional: imports detected statically (passed if known)
  suggested_inputs?: unknown[]; // optional: example inputs, JSON-serializable
  breadcrumb: string;      // human-readable trail, e.g. "Atlas → src/foo.py → bar()"
};

type PlaygroundLaunchResponse = {
  playground_id: string;   // uuid, used to DELETE on close
  iframe_url: string;      // http://localhost:{port}/
  expires_at: string;      // ISO timestamp, soft TTL hint
};
```

### Wire shape (Python, matching)

```python
@dataclass
class FunctionRef:
    file: str
    name: str
    line: int | None = None
    qualname: str | None = None

@dataclass
class PlaygroundLaunchRequest:
    source: str
    function_ref: FunctionRef
    deps_hint: list[str] | None = None
    suggested_inputs: list[object] | None = None
    breadcrumb: str = ""
```

### Endpoints

- `POST /api/playground/launch` — body is `PlaygroundLaunchRequest`, returns `PlaygroundLaunchResponse`. Resolves function, generates Marimo file, spawns subprocess, returns iframe URL.
- `DELETE /api/playground/{playground_id}` — kills subprocess, cleans temp dir.
- `GET /api/playground/{playground_id}/status` — optional, for frontend reconnect. Returns `running|exited|missing`.

### Generated Marimo file template

```python
import marimo

app = marimo.App(width="medium")

@app.cell
def __():
    # ── Auto-loaded by CopyClip ────────────────────────────────
    # Source: {source}
    # Breadcrumb: {breadcrumb}
    import sys
    sys.path.insert(0, {project_root!r})
    {imports_block}
    return ({exported_symbols},)

@app.cell
def __({exported_symbols}):
    # ── Suggested input ───────────────────────────────────────
    sample = {suggested_input_repr}
    result = {call_expr}
    result
    return result, sample,

@app.cell
def __():
    # ── Free cell: experiment freely ──────────────────────────
    return,

if __name__ == "__main__":
    app.run()
```

If `suggested_inputs` is empty, the second cell uses `# TODO: supply input` and does not call the function. Generation must always produce a valid runnable file.

## Phases

### v1 — Day 1 ("minimum lovable")

Goal: one connector working end-to-end, the bridge contract usable by future connectors without modification.

| Sub-issue | Component | Est. LOC | Parallelizable |
|---|---|---|---|
| Backend foundation | `playground.py` (contract types, resolver, file generator), new `POST /api/playground/launch` and `DELETE /api/playground/{id}` routes in `server.py` | ~400 | ✓ |
| Subprocess manager | `marimo_runner.py` (spawn, port alloc, healthcheck, cleanup) | ~250 | ✓ |
| Frontend panel | `PlaygroundPanel.tsx` (iframe shell, cyan chrome, breadcrumb header, close lifecycle) + `usePlayground` hook | ~300 | ✓ |
| Atlas connector | wire node-click in `Atlas3DPage.tsx` to dispatch a `PlaygroundLaunchRequest` (function/method/class nodes only) | ~150 | sequenced after backend + panel |

**Total day 1 budget: ~1100 LOC across 4 issues**, three parallelizable. With dev agents per [[feedback-kickoff-format]] this is one focused day.

### v2 — Follow-up connectors (one issue each)

Once the contract is set, each new connector is a small surface change (~150 LOC + tests). Open in parallel as PRs once v1 is merged.

1. **Reacquaintance briefing** → playground for functions that changed since last visit
2. **Debt Navigator** → playground for functions flagged as cognitive debt
3. **Decision History** → playground for functions mentioned in a decision
4. **Risks** → playground for risky functions
5. **Timeline** → playground for functions at a specific commit
6. **Context Builder** → playground as preview before bundling for an agent

### v3 — Stretch (NOT scheduled, NOT promised)

- Saved snippets per project
- AI-suggested inputs derived from test fixtures
- Multi-language via Jupyter kernels
- Kernel pool / pre-warm

## Error handling

| Scenario | Behavior |
|---|---|
| Marimo not installed | `POST /launch` returns `503 {"error": "marimo_not_installed", "install_hint": "pip install marimo"}`. Frontend shows an onboarding empty state per [[feedback-ux-errors]] — never a raw error. |
| Function not found | `404 {"error": "function_not_found", "file": ..., "name": ...}`. Frontend shows "this function was renamed or deleted since the Atlas was last analyzed — run analyze again". |
| Subprocess fails to start | `500 {"error": "marimo_spawn_failed", "stderr_tail": "..."}`. Frontend shows the stderr tail in a copy-able block. |
| Port exhausted | `503 {"error": "no_free_port"}`. Suggests closing other playgrounds. |
| Subprocess dies mid-session | Frontend polls `GET /status`, shows "playground exited" state with reopen button. |

All errors are JSON. No HTML error pages.

## Security

The playground executes code from the user's project, in the user's Python env, on the user's machine. This is the same trust boundary as `pytest` or any other tool that imports the project. **We do not sandbox.** The user is running their own code with their own dependencies.

Explicit constraints:
- Subprocess binds to `127.0.0.1` only (never `0.0.0.0`).
- Subprocess inherits the project venv (`sys.executable` of the CopyClip process by default).
- Iframe `src` is verified to be `localhost`-only on the frontend.
- No remote upload of generated notebook content (everything is local).

## Acceptance criteria (epic level)

- [ ] From a function/method/class node in Atlas3D, a single click opens the playground panel with that function imported, dependencies resolved, and one runnable cell pre-populated.
- [ ] Closing the panel kills the Marimo subprocess (verified via `ps`) within 2 seconds.
- [ ] Adding the second connector (Reacquaintance) requires no changes to `playground.py`, `marimo_runner.py`, or `PlaygroundPanel.tsx`. The diff is < 200 LOC + tests.
- [ ] The contract document (this spec) accurately describes the wire shape that ships.
- [ ] All errors are JSON with onboarding-friendly frontend states per [[feedback-ux-errors]].
- [ ] `marimo` is added as a `dependencies` entry in `pyproject.toml`.
- [ ] `pytest -q` passes. `scripts/dev-smoke.sh` passes.

## References

- [[feedback-kickoff-format]] — issue structure for dev agents
- [[feedback-implementation-style]] — start small, iterate, cyan-only
- [[feedback-ux-errors]] — onboarding empty states, never crash on missing config
- [[feedback-cyan-only-contextual]] — neutral data is cyan, alerts can be amber/red
- [[project-venv-setup]] — `.venv` setup for CopyClip dev work
- [[feedback-codemirror]] — code rendering convention (used only if we ever surface source-code preview inside the panel chrome)
- PR #81 — Atlas focus/dim pattern; node-click in Atlas3D already has a selection lifecycle we plug into
- Issue #15 — Epic format reference
- Issue #84 — Architecture issue format reference

## Open questions (resolve before v2 starts)

- **Reanalysis trigger**: if the user edits source code between Atlas analysis and clicking a node, the function ref may be stale. Should the bridge detect and prompt re-analyze? — *Provisional: yes, but only if file mtime > analysis timestamp. Implement in v1.*
- **Input inference**: how aggressively do we try to generate `suggested_inputs`? Pulling from tests is doable; LLM-suggesting is feature creep. — *v1: pass-through whatever the connector provides. Don't generate. Pull-from-tests is v3.*
- **Project venv detection**: do we use `sys.executable` of the CopyClip process, or detect a project-local `.venv`? — *v1: `sys.executable`. Project venv detection in v2 if Samuel hits a real case.*
