# CopyClip Project Intelligence v1 (Human Control Plane)

> Historical design document: parts of this spec describe the original v1 vision and no longer match the current CLI exactly. For the current shipped flow, use `copyclip start`, `copyclip analyze --path ...`, `copyclip decision ...`, `copyclip mcp`, and the setup documented in `README.md` / `docs/LOCAL_DEVELOPMENT.md`.

## Vision

CopyClip evolves from a context packer into a **human-facing project intelligence system** for AI-heavy software development.

Core promise:
- AI can build fast.
- Humans still need to understand, govern, and decide.
- CopyClip provides the dashboard and evidence layer for that.

---

## Product Outcome (v1)

Run in any repo (current shipped flow):

```bash
copyclip analyze --path .
copyclip start --path .
```

Open browser and get a pro dashboard with:
1. What the project is
2. What changed and why
3. What decisions exist and which are unresolved
4. Where risk is accumulating
5. What humans should decide next

---

## Scope

### In Scope (v1)
- Local-first analysis (single repo)
- Git + source code + markdown docs ingestion
- Architecture map (module + dependency view)
- Change intelligence (7/30 day windows)
- Decision extraction (ADR/commit/PR-style text heuristics)
- Risk scoring (heuristic)
- Local web dashboard (FastAPI + React)

### Out of Scope (v1)
- Multi-repo org graphs
- Real-time IDE plugin streaming
- SaaS auth/multi-user permissions
- Heavy ML training pipeline

---

## User Personas

1. **Lead developer / tech lead**
   - Needs fast situational awareness before making architecture decisions.

2. **Founder / PM with technical literacy**
   - Needs confidence in what AI agents are shipping.

3. **Senior IC joining a codebase**
   - Needs accelerated understanding of domain and system structure.

---

## Functional Requirements

## 1) Analyze Command

```bash
copyclip analyze [--since 30d] [--full] [--json]
```

Build/refresh local intelligence index.

Inputs:
- code files
- git history
- markdown docs (README, ADRs, notes)

Outputs:
- sqlite database
- graph artifacts (dependencies/modules)
- summary cache for dashboard

## 2) Start Command

```bash
copyclip start [--path .] [--port 4310] [--no-open]
```

Starts the local dashboard and API.

## 3) Decision Commands

```bash
copyclip decision add --title "..." --context "..." --impact high --refs src/a.py,docs/adr-12.md
copyclip decision list
copyclip decision resolve <id>
```

Manual control for explicit human decisions.

## 4) Reports (planned / not yet a stable shipped CLI surface)

```bash
# historical v1 idea
copyclip report --type daily
copyclip report --type weekly
```

Human-readable narrative reports remain part of the product direction, but the current shipped CLI is centered on `start`, `analyze`, `decision`, and `mcp`.

---

## Dashboard Information Architecture

## A. Home (Executive)
- Project summary
- Active risks
- Unresolved decisions
- Last 7-day change pulse
- Suggested next actions

## B. Architecture
- Module graph
- Dependency clusters
- Hotspot files
- Core boundary violations

## C. Changes
- Timeline of recent commits grouped by feature area
- “High impact / low test evidence” flags
- AI-heavy churn indicators

## D. Decisions
- Extracted + manual decisions
- status: proposed / accepted / superseded / unresolved
- linked files and commits

## E. Risks
- Risk scorecards by area
- test gap warnings
- complexity drift
- ownership ambiguity

## F. Ask Project
- Q&A over indexed project facts
- answers must cite source artifacts (file/commit/decision)

---

## Data Model (SQLite v1)

## tables

### projects
- id
- root_path
- name
- created_at
- updated_at

### files
- id
- project_id
- path
- language
- size_bytes
- last_modified_at
- hash

### commits
- id
- project_id
- sha
- author
- date
- message

### file_changes
- id
- commit_sha
- file_path
- additions
- deletions

### modules
- id
- project_id
- name
- path_prefix

### dependencies
- id
- project_id
- from_module
- to_module
- edge_type

### decisions
- id
- project_id
- title
- summary
- status
- confidence
- source_type   -- extracted|manual
- created_at
- resolved_at

### decision_refs
- id
- decision_id
- ref_type      -- file|commit|doc
- ref_value

### risks
- id
- project_id
- area
- severity      -- low|med|high
- kind          -- test_gap|churn|complexity|boundary|unknown
- rationale
- score
- created_at

### snapshots
- id
- project_id
- generated_at
- summary_json

---

## API (FastAPI v1)

- `GET /api/overview`
- `GET /api/architecture/graph`
- `GET /api/changes?window=7d|30d`
- `GET /api/decisions`
- `POST /api/decisions`
- `PATCH /api/decisions/{id}`
- `GET /api/risks`
- `GET /api/file/{path}`
- `POST /api/ask`

All `/ask` responses should include citations:
- file path(s)
- commit sha(s)
- decision id(s)

---

## Scoring Heuristics (v1)

## Risk score (0-100)
Weighted sum:
- churn_intensity (last 14d)
- complexity_proxy (LOC + branching)
- test_gap_proxy (changes without nearby test changes)
- dependency_instability (frequent edge churn)
- unresolved_decisions_count

## Confidence score for extracted decisions
- phrase quality match ("decide", "we should", "chosen", "tradeoff")
- source reliability (ADR > PR > commit message)
- reference count (files/commits linked)

---

## UX Requirements (Pro-grade)

- Fast initial load (<2s on medium repo snapshot)
- Clear visual hierarchy (executive first, deep dive second)
- Explainability by default (why this risk/decision is shown)
- No gimmicks: serious operational interface

---

## Implementation Plan (2 weeks)

## Week 1
1. CLI scaffolding for `analyze`, `start`, `decision`, `mcp` (with `report` retained as a future/planned surface)
2. SQLite schema + migration setup
3. Analyzer pipeline (files + git + docs)
4. Basic API endpoints (`overview`, `changes`, `decisions`, `risks`)

## Week 2
1. React dashboard pages (Home, Changes, Decisions, Risks)
2. Architecture graph (first-pass module dependency visualization)
3. Ask Project endpoint with source citations
4. Polish + smoke tests + demo script

---

## Success Metrics

- Time-to-understanding for new repo (target: <20 min to useful mental model)
- % of high-risk changes surfaced before merge
- % decisions explicitly tracked vs implicit in chat/commits
- User-reported decision confidence improvement

---

## Backward Compatibility

Existing CopyClip strengths remain untouched:
- deterministic context packaging
- minimization modes
- clipboard/file output

New intelligence layer is additive.

---

## Immediate Next Tasks

1. Create command skeletons in CLI (`analyze`, `start`, `decision`, `mcp`; `report` remains a planned surface)
2. Add `copyclip/intelligence/` package structure
3. Implement SQLite bootstrap + first migration
4. Add analyzer pass: git + files + markdown extraction
5. Add minimal dashboard shell with Overview page
