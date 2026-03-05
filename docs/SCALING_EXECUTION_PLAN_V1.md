# CopyClip Scaling Execution Plan v1

Goal: make CopyClip handle very large repositories (10k+ files) without reducing scope, using deterministic pipelines and progressive UX.

---

## Success Criteria

1. Full-project analysis remains possible (no hard cap).
2. Re-runs are significantly faster via real incremental processing.
3. UI shows truthful progress (phase + processed + throughput + ETA).
4. Large lists remain responsive via strict pagination + virtualization.
5. Non-deterministic (LLM) usage is compacted through deterministic preselection.

---

## Workstreams

## WS1 — Phased Analysis Pipeline (deterministic)

### Scope
- Formalize phases as first-class pipeline stages:
  1) discovery
  2) metadata/hash
  3) parse/import graph
  4) risk signals
  5) snapshots/alerts

### Deliverables
- Stable phase model in code (`phase` enum-like constants).
- Job state persistence per phase.
- Phase transitions emitted via SSE.

### Acceptance
- Every analyze job has clear, monotonic phase transitions.
- Restarting server does not lose persisted phase status.

---

## WS2 — Real Incremental by hash/mtime

### Scope
- Add incremental file state and delta logic:
  - unchanged file => skip expensive stages
  - changed file => recalc minimal dependent artifacts

### Deliverables
- New table: `analysis_file_state` (path, hash, mtime, last_processed_at, stage_mask).
- Delta detector pass.
- Recompute only impacted modules/risks where possible.

### Acceptance
- Second run after no changes is much faster.
- Small file edit reprocesses only affected subset.

---

## WS3 — Deterministic Queue + Workers + Checkpoints

### Scope
- Introduce deterministic work queue:
  - stable ordering
  - worker pool for IO/parse
  - batch checkpointing every N items (e.g., 500)

### Deliverables
- Queue engine with configurable workers.
- Checkpoint records in job state.
- Resume support from last checkpoint.

### Acceptance
- Interrupt + resume continues from checkpoint.
- Output remains deterministic across runs.

---

## WS4 — Compaction for non-deterministic stages

### Scope
- Never send full repo to LLM.
- Build deterministic compact bundles by:
  - impacted modules
  - hot files + graph neighbors
  - active risks + open decisions

### Deliverables
- Bundle builder module (`context_bundle_builder`).
- Explainable bundle manifest (why each file selected).
- Integration with ask/contextual calls.

### Acceptance
- Ask/context prompts include citations + compact manifests.
- Token footprint drops while preserving answer quality.

---

## WS5 — Progress UX (real, actionable)

### Scope
- Show truthful progress in UI:
  - phase
  - processed/total
  - throughput (files/s)
  - ETA
  - cancel / resume controls

### Deliverables
- Analyze panel with live SSE updates.
- Cancel endpoint.
- Resume endpoint.

### Acceptance
- User can start/cancel/resume reliably from UI.
- No fake spinner-only behavior.

---

## WS6 — Strict pagination + large-list UX

### Scope
- Keep backend paginated and add frontend virtualization.
- Add page size controls + server-side filters where needed.

### Deliverables
- Virtualized tables for heavy pages (changes/risks/issues/pulls/files).
- Unified list query params: `limit`, `offset`, filters.

### Acceptance
- Smooth UI with large datasets.
- No expensive full-list rendering.

---

## Step-by-step Implementation Sequence

Status snapshot (updated):
- ✅ Step 1 complete (phase constants, monotonic transitions, SSE progress events).
- ✅ Step 2 complete:
  - ✅ `analysis_file_state` implemented.
  - ✅ Delta detector using mtime+size with hash reuse for unchanged files.
  - ✅ Incremental parse/import reuse via `analysis_file_insights` cache.
  - ✅ Dependency-aware invalidation (module/import impacted files re-parse).
- ✅ Step 3 complete:
  - ✅ checkpoint cursor persisted on analyze jobs.
  - ✅ resume endpoint (`/api/analyze/resume`) starts from last checkpoint.
  - ✅ deterministic worker queue for metadata/hash scan (`ThreadPoolExecutor`) with stable ordering.
  - ✅ hardened resume semantics: downstream derived tables rebuild deterministically to avoid duplicates.
- ✅ Step 4 complete:
  - ✅ deterministic compact bundle builder (`context_bundle_builder`) with explainable manifest.
  - ✅ `/api/context-bundle` endpoint for inspecting selected files + reasons.
  - ✅ ask/context assembly paths now surface `bundle_manifest`.
  - ✅ compact bundle integrated into LLM generation flow for intelligence agents (manifest + snippets in prompt).
- 🟡 Step 5 next:
  - UI cancel/resume controls + richer progress card.

## Step 1 (Start now)
- Freeze pipeline phase constants + job schema extensions.
- Add explicit phase transition helper.
- Emit phase events through SSE.

## Step 2
- Implement `analysis_file_state` and delta detector.
- Wire incremental skip in metadata/hash and parse stages.

## Step 3
- Worker queue + batch checkpoints + resume cursor.

## Step 4
- LLM compaction bundle builder + manifest.

## Step 5
- UI cancel/resume controls + richer progress card.

## Step 6
- Virtualized lists + server-side filter/pagination polish.

---

## Metrics to Track

- Analyze wall-time (cold run vs warm run).
- Files processed vs skipped per run.
- Throughput avg/peak (files/s).
- ETA accuracy.
- UI frame smoothness on large lists.
- LLM token input size before/after compaction.

---

## Risks and Guardrails

- Determinism drift due to concurrency.
  - Guardrail: stable queue ordering + deterministic reducers.
- Incomplete invalidation logic.
  - Guardrail: conservative fallback (recompute broader scope when uncertain).
- Over-complex UX controls.
  - Guardrail: progressive disclosure (basic start visible, advanced controls collapsible).

---

## Definition of Done (Scaling v1)

- Incremental runs are meaningfully faster on unchanged repos.
- Cancel/resume works reliably.
- UI remains responsive on very large projects.
- LLM pathways use deterministic compact bundles.
- End-to-end tests cover scaling-critical paths.
