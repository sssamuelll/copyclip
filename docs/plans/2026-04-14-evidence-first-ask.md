# Evidence-first Ask Project Implementation Plan

> For Hermes: use subagent-driven-development to execute this plan task-by-task.

Goal: Turn Ask Project into a grounded investigation workflow that returns structured answers with provenance, confidence, rationale, evidence gaps, and next drill-down actions.

Architecture: Keep the current `/api/ask` endpoint but refactor it behind a dedicated evidence-first answer builder. First define a strict response contract and fallback rules, then improve retrieval/ranking, then upgrade the backend response shape, then wire the frontend to render evidence-first investigation cards instead of generic chat text.

Tech Stack: Python backend (`server.py`, `db.py`, `context_bundle_builder.py`), TypeScript React frontend (`AskPage.tsx`, `api/client.ts`, `types/api.ts`), pytest.

---

## Current state snapshot

Backend today
- `src/copyclip/intelligence/server.py:/api/ask`
- Returns:
  - `answer`
  - `citations`
  - `grounded`
  - `bundle_manifest`
- Retrieval is keyword matching over:
  - decisions
  - risks
  - commits
  - context bundle manifest files
- Ranking is a simple type boost + keyword score.

Frontend today
- `frontend/src/pages/AskPage.tsx`
- Uses `api.agentChat('scout', ...)`, not `api.ask(...)`
- Still behaves like “project consciousness chat”, not an evidence-first investigation UI.

Existing tests
- `tests/test_intelligence_server_api.py::test_ask_endpoint_returns_grounded_answer_with_citations`
- This is too shallow for the target product behavior.

---

## Target response contract

For every Ask Project answer, return:
- `answer_summary: string`
- `confidence: 'low' | 'medium' | 'high'`
- `answer_kind: 'grounded_answer' | 'insufficient_evidence' | 'contradiction_detected'`
- `evidence:`
  - `files: []`
  - `commits: []`
  - `decisions: []`
  - `risks: []`
  - `symbols: []`
- `evidence_selection_rationale: string[]`
- `gaps_or_unknowns: string[]`
- `next_questions: string[]`
- `next_drill_down:`
  - `type: 'file' | 'commit' | 'decision' | 'risk' | 'module' | 'none'`
  - `target: string | number | null`
- `grounded: boolean`
- `bundle_manifest: []`

Compatibility bridge during rollout:
- keep `answer` and `citations` temporarily
- populate them from the new contract until frontend fully migrates

---

## Task 1: Define the response contract in code and docs (#34)

Objective: Make the evidence-first shape explicit before changing retrieval behavior.

Files:
- Modify: `src/copyclip/intelligence/server.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`
- Create or update: `docs/API_CONTRACT_V1.md`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Add new frontend/backend types
- Add `AskEvidenceItem`
- Add `AskEvidenceGroup`
- Expand `AskResponse`

Step 2: Update `/api/ask` docs
- Document required fields
- Document fallback behavior for insufficient evidence and contradictions

Step 3: Add failing contract test
- New test should assert `confidence`, `answer_kind`, `evidence_selection_rationale`, `gaps_or_unknowns`, and `next_questions` exist

Step 4: Minimal backend pass
- Make `/api/ask` return placeholder-complete structured fields with current retrieval logic

Step 5: Verify
- Run: `python3 -m pytest tests/test_intelligence_server_api.py -q`

Step 6: Commit
- `git commit -m "feat: define evidence-first ask response contract"`

---

## Task 2: Extract backend answer builder from `/api/ask` (#34/#36)

Objective: Move ask logic out of the giant server handler into a focused builder module.

Files:
- Create: `src/copyclip/intelligence/ask_project.py`
- Modify: `src/copyclip/intelligence/server.py`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Create `build_ask_response(project_root, question)`
- Inputs:
  - project root
  - question
- Output:
  - full `AskResponse`

Step 2: Move current retrieval and ranking logic into that module

Step 3: Keep server route as a thin transport wrapper

Step 4: Verify
- Run ask endpoint tests again

Step 5: Commit
- `git commit -m "refactor: extract ask project answer builder"`

---

## Task 3: Improve retrieval and ranking with evidence-first signals (#35)

Objective: Replace simple keyword-first ranking with a deterministic score that reflects project trust signals.

Files:
- Modify: `src/copyclip/intelligence/ask_project.py`
- Reuse/inspect: `src/copyclip/intelligence/context_bundle_builder.py`
- Reuse/inspect: `src/copyclip/intelligence/reacquaintance.py`
- Test: `tests/test_ask_project_ranking.py` (new)

Scoring inputs to combine
- lexical overlap with question
- decision linkage
- risk severity/score
- commit recency
- file churn
- symbol/module relevance
- explicit match to current bundle reasons

Step 1: Define scoring helpers
- `_score_decision_evidence(...)`
- `_score_risk_evidence(...)`
- `_score_commit_evidence(...)`
- `_score_file_evidence(...)`
- `_score_symbol_evidence(...)`

Step 2: Add symbol-aware retrieval
- Use indexed module/symbol data where available
- If unavailable, degrade gracefully

Step 3: Add rationale generation
- Example rationale items:
  - `matched_decision_terms`
  - `high_risk_overlap`
  - `recent_commit_overlap`
  - `bundle_manifest_support`

Step 4: Add focused ranking tests
- decision-heavy query
- risk-heavy query
- file-specific query
- commit-specific query
- symbol/module query

Step 5: Verify
- Run: `python3 -m pytest tests/test_ask_project_ranking.py -q`

Step 6: Commit
- `git commit -m "feat: improve ask project evidence ranking"`

---

## Task 4: Implement provenance and rationale in backend answers (#36)

Objective: Every answer must explain both what it knows and why it chose that evidence.

Files:
- Modify: `src/copyclip/intelligence/ask_project.py`
- Test: `tests/test_intelligence_server_api.py`

Step 1: Structure evidence into grouped sections
- `files`
- `commits`
- `decisions`
- `risks`
- `symbols`

Step 2: Build `answer_summary` from selected evidence, not generic prose

Step 3: Set confidence deterministically
- High: multiple independent evidence groups align
- Medium: useful but partial evidence
- Low: sparse or noisy evidence

Step 4: Populate `next_drill_down`
- Prefer decision/file/risk target with highest payoff

Step 5: Add tests that verify:
- rationale is non-empty
- confidence changes with evidence richness
- drill-down target is present when answer is grounded

Step 6: Commit
- `git commit -m "feat: add provenance and rationale to ask answers"`

---

## Task 5: Add insufficient-evidence and contradiction handling (#38)

Objective: Make “I don’t know yet” useful and trustworthy.

Files:
- Modify: `src/copyclip/intelligence/ask_project.py`
- Modify: `src/copyclip/intelligence/server.py`
- Test: `tests/test_ask_project_failure_modes.py` (new)

Step 1: Define insufficient-evidence rule
- If selected evidence is below threshold or too narrow:
  - `answer_kind = 'insufficient_evidence'`
  - `grounded = false`
  - `gaps_or_unknowns` must be explicit
  - `next_questions` must guide the user toward sharper retrieval

Step 2: Define contradiction detection rule
- Example triggers:
  - accepted decision conflicts with recent risky change
  - conflicting evidence groups with similar strength
- Return:
  - `answer_kind = 'contradiction_detected'`
  - explain the contradiction
  - give next drill-down

Step 3: Add tests
- empty evidence
- ambiguous evidence
- contradiction between decision and recent change

Step 4: Commit
- `git commit -m "feat: handle insufficient evidence and contradictions in ask"`

---

## Task 6: Replace generic Ask UI with investigation UI (#37)

Objective: Make Ask Project visibly evidence-first in the dashboard.

Files:
- Modify: `frontend/src/pages/AskPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`
- Optional: `frontend/src/styles.css`

Step 1: Stop using `agentChat('scout', ...)` for Ask Project
- Use `api.ask(question)` for the main ask flow

Step 2: Replace generic chat rendering with investigation cards
- Answer summary
- confidence badge
- evidence groups
- rationale list
- gaps/unknowns
- next questions
- drill-down CTA

Step 3: Wire drill-downs
- file -> Changes page archaeology
- commit -> Changes page focused commit
- decision -> Decisions page
- risk -> Risks page

Step 4: Preserve simple chat feel if desired, but the response body must be structured and inspectable

Step 5: Verify
- `npm run build`

Step 6: Commit
- `git commit -m "feat: build evidence-first ask investigation UI"`

---

## Task 7: Add realistic fixtures and evaluation coverage (#39)

Objective: Prove grounded answers over real project-like artifacts.

Files:
- Create: `tests/test_ask_project_ranking.py`
- Create: `tests/test_ask_project_failure_modes.py`
- Modify: `tests/test_intelligence_server_api.py`

Fixture scenarios
1. Decision-backed question
2. Risk-backed question
3. Recent-commit-backed question
4. File/module-specific question
5. Insufficient evidence question
6. Contradiction question

Required assertions
- answer_kind is correct
- confidence is correct enough for scenario
- evidence groups contain the right artifact types
- rationale explains selection
- gaps are explicit when needed
- next drill-down is useful

Verification
- `python3 -m pytest -q`

Commit
- `git commit -m "test: add grounded ask project fixtures and evaluation coverage"`

---

## Post-implementation verification

Run all of these:
- `python3 -m pytest tests/test_intelligence_server_api.py -q`
- `python3 -m pytest tests/test_ask_project_ranking.py -q`
- `python3 -m pytest tests/test_ask_project_failure_modes.py -q`
- `python3 -m pytest -q`
- `cd frontend && npm run build`

Manual smoke checks
1. Ask: `what did we decide about X?`
2. Ask: `where is the highest-risk area related to auth?`
3. Ask: `what changed recently around validation?`
4. Ask an intentionally vague question and confirm insufficient-evidence path
5. Click drill-down from answer into Changes/Decisions/Risks

---

## Recommended execution order mapped to existing issues
- #34 contract + fallback behavior -> Tasks 1-2
- #35 retrieval/ranking -> Task 3
- #36 provenance/rationale -> Task 4
- #38 insufficient-evidence + contradiction handling -> Task 5
- #37 frontend investigation UI -> Task 6
- #39 tests/evaluation fixtures -> Task 7

---

## Definition of done
- Ask Project uses `api.ask(...)` as the primary product flow
- Every answer has visible provenance and confidence
- The system can explicitly say when evidence is insufficient
- Contradictions are surfaced instead of smoothed over
- Drill-down navigation is direct and useful
- Tests cover grounded, sparse, and contradictory scenarios
