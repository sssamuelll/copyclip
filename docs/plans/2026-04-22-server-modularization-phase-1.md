# Server Modularization Phase 1 Implementation Plan

> For Hermes: use subagent-driven-development to execute this plan task-by-task.

Goal: Turn `src/copyclip/intelligence/server.py` from a feature bucket into a composition layer by extracting shared server context/helpers and the safest low-risk endpoints first, without changing API behavior.

Architecture: Keep `run_server(project_root, port)` as the public entrypoint, but introduce a small `ServerContext` object plus request/response helper modules that the HTTP handler delegates to. Phase 1 should be behavior-preserving: same routes, same payloads, same status codes, same tests. Do not move Ask/Handoff/Decision Advisor/Assemble Context yet.

Tech Stack: Python, `http.server.ThreadingHTTPServer`, SQLite, pytest.

---

## Current state snapshot

Current hotspot
- `src/copyclip/intelligence/server.py` is ~2436 lines.
- `run_server()` owns:
  - runtime state (`events`, `scheduler_state`, `cancel_events`, locks)
  - helper functions (`with_meta`, `_pagination`, `_parse_dt`, `_job_payload`, etc.)
  - analysis job orchestration
  - scheduler/event bus logic
  - `class Handler(BaseHTTPRequestHandler)`
  - all GET/POST/PATCH/DELETE route branching

Safe extraction candidates for Phase 1
- request/response helpers
- server/app context object
- event publishing helpers
- `/api/events`
- `/api/health`
- `/api/config` and `/api/settings` GET/POST

Do NOT move yet
- `/api/ask`
- `/api/assemble-context`
- `/api/agents/chat`
- handoff packet lifecycle
- decision advisor
- alerts scheduler / analysis jobs

Why this order
- lowest contract risk
- creates explicit boundaries for later slices
- leaves the most behavior-dense endpoints untouched until the scaffolding is stable

---

## Target file layout for Phase 1

Create:
- `src/copyclip/intelligence/server_context.py`
- `src/copyclip/intelligence/server_helpers.py`
- `src/copyclip/intelligence/server_events.py`
- `src/copyclip/intelligence/server_routes_core.py`

Modify:
- `src/copyclip/intelligence/server.py`
- `tests/test_intelligence_server_api.py`
- `tests/test_smoke_cli_runtime.py` only if needed for behavior-preserving verification

Initial responsibilities
- `server_context.py`
  - `ServerContext` dataclass
  - shared runtime state container
- `server_helpers.py`
  - JSON response helper(s)
  - metadata helper
  - pagination helper
  - datetime parsing helper
  - project-id lookup helper
- `server_events.py`
  - event publishing helper
  - SSE stream handler for `/api/events`
- `server_routes_core.py`
  - handlers for `/api/health`
  - handlers for `/api/config` and `/api/settings`

`server.py` after Phase 1 should still:
- define `run_server()`
- build the context
- own `ThreadingHTTPServer` startup/shutdown
- define the HTTP `Handler`
- delegate core endpoints to extracted helpers/modules
- keep all other endpoints inline for now

---

## Task 1: Add failing regression tests for the Phase 1 extraction boundary

Objective: Freeze the behavior of the low-risk endpoints before any refactor.

Files:
- Modify: `tests/test_intelligence_server_api.py`

Step 1: Add a focused config/settings round-trip test

Add a new test that:
- starts the server
- POSTs to `/api/settings`
- GETs `/api/settings`
- asserts the value round-trips exactly

Suggested shape:
```python
def test_settings_round_trip_endpoint():
    ...
```

Step 2: Add a focused health endpoint contract test

Assert at minimum:
- `ok == True`
- `service == "copyclip-intelligence"`
- `meta.project` exists
- `meta.generated_at` exists

Step 3: Add an SSE smoke/connected-event test if there is not already one

Keep it minimal:
- request `/api/events?cursor=0`
- assert stream starts with `connected`

Step 4: Run the focused test target and confirm GREEN baseline before refactor

Run:
```bash
python3 -m pytest tests/test_intelligence_server_api.py -q
```

Expected:
- all tests pass before any refactor code lands

Step 5: Commit

```bash
git add tests/test_intelligence_server_api.py
git commit -m "test: pin core server endpoint contracts before modularization"
```

---

## Task 2: Introduce `ServerContext`

Objective: Make runtime/shared server state explicit before moving handlers.

Files:
- Create: `src/copyclip/intelligence/server_context.py`
- Modify: `src/copyclip/intelligence/server.py`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Create the dataclass

Include only fields already present in `run_server()`:
- `root: str`
- `html: str`
- `events: list`
- `events_lock`
- `next_event_id`
- `scheduler_state`
- `analysis_lock`
- `cancel_lock`
- `cancel_events`

Step 2: Construct `ServerContext` in `run_server()`

Keep values identical to today.

Step 3: Replace direct closure capture for the easiest helper(s)

Start with:
- metadata helper
- project basename/root references

Do not move route logic yet.

Step 4: Run the focused tests

Run:
```bash
python3 -m pytest tests/test_intelligence_server_api.py -q
```

Step 5: Commit

```bash
git add src/copyclip/intelligence/server_context.py src/copyclip/intelligence/server.py
git commit -m "refactor: introduce server context for runtime state"
```

---

## Task 3: Extract shared helpers into `server_helpers.py`

Objective: Remove generic utility logic from `run_server()` before moving endpoints.

Files:
- Create: `src/copyclip/intelligence/server_helpers.py`
- Modify: `src/copyclip/intelligence/server.py`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Move pure/shared helpers

Extract only helpers that are safe and generic:
- `_project_id(...)`
- `with_meta(...)`
- `_pagination(...)`
- `_parse_dt(...)`
- `_job_payload(...)` only if it can be moved without dragging too much analysis-job state; otherwise defer it to Phase 2

Step 2: Add a tiny request JSON helper if useful

Examples:
- `read_json_body(handler)`
- `json_response(handler, payload, code=200)`

Do not change payload shape.

Step 3: Update `Handler` to call helper functions instead of nested closures where possible

Step 4: Verify no behavior change

Run:
```bash
python3 -m pytest tests/test_intelligence_server_api.py -q
python3 -m pytest tests/test_smoke_cli_runtime.py -q
```

Step 5: Commit

```bash
git add src/copyclip/intelligence/server_helpers.py src/copyclip/intelligence/server.py
git commit -m "refactor: extract shared server helpers"
```

---

## Task 4: Extract event bus + SSE route

Objective: Pull the event queue logic and `/api/events` implementation out of the giant GET method.

Files:
- Create: `src/copyclip/intelligence/server_events.py`
- Modify: `src/copyclip/intelligence/server.py`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Move event publishing helper

Extract a helper like:
- `publish_event(ctx, kind, data)`

Step 2: Move SSE response logic

Extract a function like:
- `handle_events_get(handler, ctx, parsed)`

Keep:
- `connected` initial event
- backlog replay behavior
- 30-second streaming window

Step 3: Replace inline `/api/events` block in `do_GET`

Delegate to the extracted function.

Step 4: Verify focused behavior

Run:
```bash
python3 -m pytest tests/test_intelligence_server_api.py -q
```

Step 5: Commit

```bash
git add src/copyclip/intelligence/server_events.py src/copyclip/intelligence/server.py
git commit -m "refactor: extract server event bus and SSE handler"
```

---

## Task 5: Extract the safest core routes

Objective: Move the lowest-risk GET/POST settings endpoints out of `server.py`.

Files:
- Create: `src/copyclip/intelligence/server_routes_core.py`
- Modify: `src/copyclip/intelligence/server.py`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Move `/api/health`

Create a handler function that returns the exact same payload.

Step 2: Move `/api/config` and `/api/settings` GET

Keep both aliases exactly as-is.

Step 3: Move `/api/config` and `/api/settings` POST

Preserve:
- insert/update semantics
- response shape `{ "status": "ok" }`

Step 4: Delegate from `Handler`

`do_GET` / `do_POST` should branch early to the extracted core route functions.

Step 5: Verify

Run:
```bash
python3 -m pytest tests/test_intelligence_server_api.py -q
python3 -m pytest tests/test_smoke_cli_runtime.py -q
```

Step 6: Commit

```bash
git add src/copyclip/intelligence/server_routes_core.py src/copyclip/intelligence/server.py tests/test_intelligence_server_api.py
git commit -m "refactor: extract core health and settings routes"
```

---

## Task 6: Phase 1 cleanup and equivalence verification

Objective: Confirm Phase 1 actually reduced `server.py` without drifting behavior.

Files:
- Modify: `src/copyclip/intelligence/server.py`
- Optional update: `docs/plans/2026-04-22-server-modularization-phase-1.md`

Step 1: Remove dead nested helper code from `server.py`

Only after all delegates are wired.

Step 2: Re-check file size and responsibility shift

Run:
```bash
wc -l src/copyclip/intelligence/server.py
wc -l src/copyclip/intelligence/server_context.py src/copyclip/intelligence/server_helpers.py src/copyclip/intelligence/server_events.py src/copyclip/intelligence/server_routes_core.py
```

Step 3: Run the full relevant verification set

Run:
```bash
python3 -m pytest tests/test_intelligence_server_api.py -q
python3 -m pytest tests/test_smoke_cli_runtime.py -q
python3 -m pytest -q
npm --prefix frontend run build
./scripts/dev-smoke.sh
```

Step 4: Sanity-check route coverage

Specifically verify:
- `/api/events`
- `/api/health`
- `/api/settings`
- startup smoke still passes

Step 5: Commit

```bash
git add src/copyclip/intelligence/server.py src/copyclip/intelligence/server_context.py src/copyclip/intelligence/server_helpers.py src/copyclip/intelligence/server_events.py src/copyclip/intelligence/server_routes_core.py tests/test_intelligence_server_api.py docs/plans/2026-04-22-server-modularization-phase-1.md
git commit -m "refactor: complete server modularization phase 1 scaffolding"
```

---

## Definition of done for Phase 1

Phase 1 is done when:
- `run_server()` still exists as the public entrypoint
- runtime/shared state is represented explicitly via `ServerContext`
- generic helpers are no longer nested inside `run_server()`
- `/api/events` is extracted from the giant `do_GET`
- `/api/health` and `/api/config`/`/api/settings` GET/POST are extracted
- `server.py` is smaller and more obviously a composition layer
- all current tests and smoke checks still pass unchanged

## Not included in Phase 1

Do not treat these as in-scope yet:
- analysis job extraction
- alerts/scheduler extraction
- handoff route extraction
- ask route extraction
- decision advisor extraction
- assemble-context extraction
- any API contract changes

Those belong to later phases.

---

## Recommended Phase 2 after this

Once Phase 1 is green, the next slice should be:
1. analysis job orchestration + `/api/analyze/*`
2. alerts/scheduler + `/api/alerts*`

That is where the deepest remaining server/runtime coupling still lives.
