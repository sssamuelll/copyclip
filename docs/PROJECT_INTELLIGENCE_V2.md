# CopyClip Project Intelligence v2 (Current State + Next Specs)

## Status

This document updates v1 with what is already implemented in production code (`main`) and what remains for the next phase.

---

## 1) Product Positioning (Current)

CopyClip is now:

1. **Context Compiler** for AI-assisted development workflows
2. **Human Control Plane** to understand and govern AI-heavy codebases

Core command UX:

```bash
# from any project folder
copyclip start
```

Expected behavior:
- analyze project
- start one local service
- serve frontend + API in one port
- provide URL for browser access

---

## 2) Implemented Commands

## Stable
- `copyclip` (core context compiler features)
- `copyclip analyze [--path .] [--json]`
- `copyclip serve [--path .] [--port 4310]`
- `copyclip start [--path .] [--port 4310]`
- `copyclip decision add|list|resolve`
- `copyclip report`

## Notes
- `start` is the preferred entrypoint for project intelligence.
- `serve` remains available for manual/advanced flow.

---

## 3) Dashboard (Current)

Built-in dashboard served from:
- `src/copyclip/intelligence/ui/index.html`

## Dynamic sections implemented
- Overview KPIs
- Recent changes
- Architecture modules/edges
- Risks table + severity distribution
- Decisions list + detail panel

## Interactions implemented
- Decision status transitions (`accept/resolve/supersede`)
- Decision refs add/read (`file|commit|doc`)
- Global search
- Page-level filters:
  - Changes: author + text
  - Decisions: status + text
  - Risks: kind + severity + text
  - Architecture: text filter
- Filters/search persistence (localStorage)
- Graph zoom/pan
- Empty states + toast feedback

---

## 4) Data Layer (Current)

SQLite DB at:
- `.copyclip/intelligence.db`

## Main tables in use
- `projects`
- `files`
- `commits`
- `file_changes`
- `modules`
- `dependencies`
- `decisions`
- `decision_refs`
- `risks`
- `snapshots`

---

## 5) API Contract (Current)

## GET
- `/api/overview`
- `/api/changes`
- `/api/decisions`
- `/api/decisions/{id}/refs`
- `/api/architecture/graph`
- `/api/risks`

## POST
- `/api/decisions`
- `/api/decisions/{id}/refs`

## PATCH
- `/api/decisions/{id}`

## Contract notes
- Collection/snapshot endpoints include `meta.project`.
- `changes` includes `author`.
- Decision payloads include `source_type`.

---

## 6) Risk Engine (Current v1.1)

Implemented risk kinds:
- `churn`
- `test_gap`
- `complexity`

## Heuristic summary
- Churn from recent git file-change frequency
- Test gap from changed non-test paths lacking test signal
- Complexity proxy from control-flow + function density

---

## 7) Quality Gates (Current)

- Existing suite is green at latest checkpoint.
- Intelligence analyzer tests added (test-path + complexity helpers).

---

## 8) Open Gaps (Next)

## A. API hardening
- Add `meta.generated_at`
- Add pagination (`limit`, `offset`) for changes/risks/decisions
- Introduce error schema consistency across endpoints

## B. Risk v1.2
- Better test matching (import/path-aware)
- Boundary risk from dependency fan-in/fan-out instability
- Confidence score per risk item

## C. Decision system
- Add `decision_refs` management in CLI
- Add ref delete/edit endpoints
- Add status history/audit trail

## D. Ask Project
- New endpoint `POST /api/ask`
- answer + citations (files/commits/decisions)
- strict “no citation, no claim” mode

## E. Performance
- Virtualize large tables in UI
- Cache and incremental analyze runs
- Graph rendering optimization for larger module sets

---

## 9) Acceptance Criteria for Next Milestone

A milestone is done when:
1. `copyclip start` remains one-command stable UX
2. API supports pagination + generated metadata
3. Ask Project returns citation-backed answers
4. Risks include confidence and reduced false positives
5. Dashboard handles large repos without major lag

---

## 10) Recommended Immediate Sequence

1. API contract formalization (meta + pagination)
2. Ask Project MVP with citations
3. Risk v1.2 confidence + boundary signals
4. Table virtualization and graph perf pass
5. Decision audit trail
