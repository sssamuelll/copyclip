# Wave 1 — Ratified Cuts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the six surfaces Samuel ratified for removal (dead/inverted product identities), preserving the two routes live pages still depend on (`/api/issues`, `/api/analyze/*`).

**Architecture:** Pure deletion in dependency order — each cut is proven unreferenced (grep), deleted, then proven still-green (typecheck + tests). AtlasPage must die before the `/api/identity/drift` route (it is the route's sole consumer). OpsPage's alerts/scheduler/weekly routes die, but the analyze routes it shares with the live DebtNavigatorPage survive.

**Tech Stack:** Python (aiohttp-style stdlib server, pytest), React/TypeScript (vite, `tsc -b` via `npm --prefix frontend run build`), bash scripts.

**Spec:** `docs/superpowers/specs/2026-06-04-cuaderno-shell-consensus-design.md` (§5–§7).

**Quarantined — must survive this wave untouched:**
- `/api/issues` (server.py ~1375), `api.issues` (client.ts ~139), `IssueItem` type — live consumer: `ContextBuilderPage.tsx:29`.
- `/api/analyze/*` routes, `api.analyzeStatus`, `api.startAnalyzeJob`, their types — live consumer: `DebtNavigatorPage.tsx:109,128`.

---

### Task 1: Delete `cache.py` (broken + unreferenced)

**Files:**
- Delete: `src/copyclip/cache.py`

- [ ] **Step 1: Prove it is unreferenced**

```bash
grep -rn "from .cache\|from copyclip.cache\|import cache" src/ tests/
```
Expected: no matches. (`flow_diagram.py:132` defines its own unrelated in-class `self.cache: Dict` — verified; do NOT touch flow_diagram.py.)

- [ ] **Step 2: Delete the file**

```bash
git rm src/copyclip/cache.py
```

- [ ] **Step 3: Verify green**

```bash
python -c "import copyclip.flow_diagram, copyclip.minimizer, copyclip.scanner" && python -m pytest tests/ -q -x
```
Expected: imports succeed; test suite passes.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(wave1): delete cache.py — unreferenced SemanticCache with latent NameError (uses sys/time without importing them)"
```

---

### Task 2: Delete `IssuesPage.tsx` (orphaned page; the route survives)

**Files:**
- Delete: `frontend/src/pages/IssuesPage.tsx`

- [ ] **Step 1: Prove the page is orphaned and the route is consumed elsewhere**

```bash
grep -rn "IssuesPage" frontend/src/ ; grep -rn "api.issues(" frontend/src/
```
Expected: `IssuesPage` matches only inside `IssuesPage.tsx` itself; `api.issues(` matches `ContextBuilderPage.tsx:29` (the route's live consumer — KEEP `/api/issues`, `api.issues`, `IssueItem`).

- [ ] **Step 2: Delete the file**

```bash
git rm frontend/src/pages/IssuesPage.tsx
```

- [ ] **Step 3: Verify green**

```bash
npm --prefix frontend run build
```
Expected: tsc -b + vite build succeed with no missing-module errors.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(wave1): delete orphaned IssuesPage — /api/issues survives (ContextBuilderPage is its live consumer)"
```

---

### Task 3: Delete the autonomous agent framework

**Files:**
- Delete: `src/copyclip/intelligence/agents.py`
- Delete: `frontend/src/components/AgentTerminal.tsx`
- Delete: `tests/test_agents_system.py`
- Modify: `src/copyclip/intelligence/server.py` (route block at ~2153–2173: `if parsed.path == "/api/agents/chat":` including `from .agents import get_agent`)
- Modify: `frontend/src/api/client.ts` (line ~155 `agentChat:` method + `AgentResponse` in the import list at line 1)
- Modify: `frontend/src/types/api.ts` (the `export type AgentResponse = {...}` block at ~86)

- [ ] **Step 1: Prove the blast radius is exactly these files**

```bash
grep -rn "AgentTerminal\|agentChat\|agents/chat\|from .agents\|AgentResponse" src/ frontend/src/ tests/ scripts/
```
Expected: matches ONLY in the six files listed above (AgentTerminal self-references; client.ts:155; server.py:2153/2155/2167; api.ts:86; agents.py; test_agents_system.py).

- [ ] **Step 2: Delete the standalone files**

```bash
git rm src/copyclip/intelligence/agents.py frontend/src/components/AgentTerminal.tsx tests/test_agents_system.py
```

- [ ] **Step 3: Remove the server route block**

In `src/copyclip/intelligence/server.py`, delete the whole `if parsed.path == "/api/agents/chat":` block (starts ~2153, contains `from .agents import get_agent` and `agent = get_agent(agent_type, root)`, ends where the next `if parsed.path ==` begins). Verify after:

```bash
grep -n "agents" src/copyclip/intelligence/server.py
```
Expected: no `/api/agents/chat` or `get_agent` matches remain.

- [ ] **Step 4: Remove the client binding and the type**

In `frontend/src/api/client.ts`: delete the `agentChat:` line and remove `AgentResponse` from the type-import list on line 1. In `frontend/src/types/api.ts`: delete the `export type AgentResponse = {...}` block.

- [ ] **Step 5: Verify green**

```bash
npm --prefix frontend run build && python -m pytest tests/ -q
```
Expected: both pass; no dangling references.

- [ ] **Step 6: Commit**

```bash
git commit -am "chore(wave1): delete autonomous agent framework — agents.py, AgentTerminal, /api/agents/chat, api.agentChat (clause-2 inversion; superseded by evidence-first ask per docs/plans/2026-04-14)"
```

---

### Task 4: Delete `AtlasPage.tsx` (legacy 2D atlas — MUST precede Task 5)

**Files:**
- Delete: `frontend/src/pages/AtlasPage.tsx`

- [ ] **Step 1: Prove orphanhood and that it is the SOLE identityDrift consumer**

```bash
grep -rn "AtlasPage" frontend/src/ ; grep -rn "identityDrift" frontend/src/
```
Expected: `AtlasPage` matches only itself (the live page is `Atlas3DPage`, a different file); `identityDrift` matches only `AtlasPage.tsx:20` and the `client.ts` definition. This is what frees Task 5's route.

- [ ] **Step 2: Delete the file**

```bash
git rm frontend/src/pages/AtlasPage.tsx
```

- [ ] **Step 3: Verify green**

```bash
npm --prefix frontend run build
```
Expected: build passes (shared types overview/changes/decisions/risks/timeline are consumed by live pages and remain).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(wave1): delete orphaned legacy AtlasPage (superseded by Atlas3DPage) — frees /api/identity/drift for removal"
```

---

### Task 5: Delete `NarrativePage.tsx` + the `/api/identity/drift` route

**Files:**
- Delete: `frontend/src/pages/NarrativePage.tsx`
- Modify: `src/copyclip/intelligence/server.py` (the `/api/identity/drift` handler at ~562)
- Modify: `frontend/src/api/client.ts` (line ~153 `identityDrift:` + any type imports it leaves orphaned)
- Modify: `frontend/src/types/api.ts` (`IdentityDriftItem` ~391 and `IdentityDriftResponse` ~401 blocks)

- [ ] **Step 1: Prove zero remaining consumers (Task 4 must already be merged into the branch)**

```bash
grep -rn "NarrativePage" frontend/src/ ; grep -rn "identityDrift\|identity/drift\|IdentityDrift" frontend/src/ src/ tests/ scripts/
```
Expected: `NarrativePage` matches only itself; `identityDrift`/`identity/drift` matches only `client.ts:153`, the server handler (~562), and the api.ts types — no page consumer remains.

- [ ] **Step 2: Delete page + route + binding + types**

```bash
git rm frontend/src/pages/NarrativePage.tsx
```
Then: in `server.py` delete the `/api/identity/drift` handler block (~562, the block that queries `identity_drift_snapshots`); in `client.ts` delete the `identityDrift:` line and remove `IdentityDriftResponse` from the import list; in `api.ts` delete the `IdentityDriftItem` and `IdentityDriftResponse` type blocks.

- [ ] **Step 3: Verify green**

```bash
grep -rn "IdentityDrift\|identity/drift" frontend/src/ src/ && echo "LEFTOVERS" || echo "CLEAN"
npm --prefix frontend run build && python -m pytest tests/ -q
```
Expected: `CLEAN`; both builds pass.

- [ ] **Step 4: Commit**

```bash
git commit -am "chore(wave1): delete orphaned NarrativePage and /api/identity/drift — route had zero reachable consumers after AtlasPage removal"
```

---

### Task 6: Delete `OpsPage.tsx` + alerts/scheduler/weekly-export routes (PRESERVE analyze)

**Files:**
- Delete: `frontend/src/pages/OpsPage.tsx`
- Modify: `src/copyclip/intelligence/server.py` (alerts/scheduler/weekly route blocks at ~1462, 1485, 1510, 1518, 1768, 1912, 2108, 2122 + `scheduler_state` wiring in `run_server`)
- Modify: `frontend/src/api/client.ts` (lines ~126–138: `alerts`, `alertRules`, `schedulerState`, `setSchedulerState`, `upsertAlertRule`, `updateAlertRule`, `deleteAlertRule`, `weeklyExport` — KEEP `analyzeStatus`/`startAnalyzeJob`)
- Modify: `frontend/src/types/api.ts` (`AlertRule` ~138, `AlertsResponse` ~157, `WeeklyExport` ~165, `SchedulerState` ~170)
- Modify: `scripts/qa_gate.sh` (lines 26, 27, 29 — alerts/weekly curls), `scripts/smoke_e2e.sh` (lines 17, 18)
- Modify: `tests/test_intelligence_server_api.py` (alerts/scheduler/weekly test sites)

- [ ] **Step 1: Map the exact blast radius and the analyze quarantine**

```bash
grep -rn "OpsPage" frontend/src/
grep -n "api/alerts\|api/export/weekly\|scheduler" src/copyclip/intelligence/server.py
grep -n "alerts\|scheduler\|weekly" tests/test_intelligence_server_api.py scripts/qa_gate.sh scripts/smoke_e2e.sh
grep -rn "analyzeStatus\|startAnalyzeJob" frontend/src/
```
Expected: `OpsPage` matches only itself; analyze consumers include `DebtNavigatorPage.tsx:109,128` (KEEP all analyze plumbing — `SettingsPage` shares none, verified).

- [ ] **Step 2: Delete the page**

```bash
git rm frontend/src/pages/OpsPage.tsx
```

- [ ] **Step 3: Remove the alerts/scheduler/weekly server routes**

In `server.py`: delete every route block matched by Step 1's grep for `api/alerts`, `api/export/weekly`, and the scheduler blocks (including the `scheduler_state` setup in `run_server` and any background scheduler thread/loop it starts). Do NOT touch routes matching `api/analyze`.

```bash
grep -n "api/alerts\|api/export/weekly\|scheduler" src/copyclip/intelligence/server.py
```
Expected after: no matches. Then confirm analyze survived:

```bash
grep -cn "api/analyze" src/copyclip/intelligence/server.py
```
Expected: count unchanged from Step 1.

- [ ] **Step 4: Remove client methods + types + script curls + test sites**

`client.ts`: delete the 8 methods listed above and remove `AlertRule`, `AlertsResponse`, `WeeklyExport`, `SchedulerState` from the import list. `api.ts`: delete those 4 type blocks. `qa_gate.sh`/`smoke_e2e.sh`: delete the 5 alerts/weekly curl lines. `test_intelligence_server_api.py`: delete the test functions that hit `/api/alerts*` or `/api/export/weekly` (grep from Step 1 lists them).

- [ ] **Step 5: Verify green**

```bash
grep -rn "AlertRule\|AlertsResponse\|WeeklyExport\|SchedulerState\|api/alerts\|export/weekly" frontend/src/ src/ tests/ scripts/ && echo "LEFTOVERS" || echo "CLEAN"
npm --prefix frontend run build && python -m pytest tests/ -q
```
Expected: `CLEAN`; both pass (especially `test_intelligence_server_api.py` with alerts sites removed).

- [ ] **Step 6: Commit**

```bash
git commit -am "chore(wave1): delete OpsPage and SRE routes (alerts/scheduler/weekly-export) — team-observability ontology out of scope; /api/analyze/* preserved for DebtNavigatorPage"
```

---

### Task 7: Wave gate — full verification

- [ ] **Step 1: Zero references to any deleted symbol**

```bash
grep -rn "SemanticCache\|IssuesPage\|AgentTerminal\|agentChat\|get_agent\|AtlasPage\|NarrativePage\|identityDrift\|OpsPage\|AlertRule\|SchedulerState\|weeklyExport" src/ frontend/src/ tests/ scripts/ && echo "LEFTOVERS" || echo "CLEAN"
```
Expected: `CLEAN` (note: `Atlas3DPage` is a different, live file and must still exist).

- [ ] **Step 2: Full suites**

```bash
python -m pytest tests/ -q && npm --prefix frontend run build
```
Expected: all green.

- [ ] **Step 3: Smoke the survivors**

```bash
bash scripts/dev-smoke.sh
```
Expected: passes; `/api/issues` and `/api/analyze/*` respond (quarantine intact); every page still routed in `App.tsx` loads.

- [ ] **Step 4: Wave-1 summary commit message check**

Branch is ready for PR: `feat/cuaderno-shell-wave-1` → squash subject `feat(shell): wave 1 — delete the six ratified dead surfaces (#NN)`.
