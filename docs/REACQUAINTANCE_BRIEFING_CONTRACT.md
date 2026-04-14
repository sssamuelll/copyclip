# Reacquaintance Briefing Contract

Status: draft for issue #28
Owner: CopyClip
Related issues: #16, #28, #29, #30, #31, #32, #33

## Purpose

Reacquaintance Mode is the "catch me up" workflow for returning to a project after a context switch.

Its job is not to summarize everything. Its job is to restore continuity quickly and direct attention to the highest-value next reads.

The briefing must answer:
- What changed since my baseline?
- What matters now?
- What should I read first in the next 10 minutes?
- Which decisions, risks, and hotspots are most relevant to re-entry?
- What is still unclear?

## Design principles

- Prioritize attention, do not dump raw telemetry
- Every section must cite evidence
- Prefer deterministic ranking over opaque narrative generation
- Be useful even when evidence is sparse
- Make uncertainty explicit
- Keep the contract stable across UI and CLI delivery paths

## Supported baseline modes

The briefing compares "now" against one baseline.

Allowed baseline modes:
- `last_seen` — last recorded project visit/open by this user
- `last_analysis` — previous completed analysis run
- `window` — explicit rolling window such as `7d`, `14d`, `30d`
- `checkpoint` — future/manual named checkpoint created by user

If `last_seen` is unavailable, fallback order is:
1. `last_analysis`
2. `window=7d`
3. "first run" mode

## Top-level response schema

```json
{
  "meta": {
    "project": "copyclip",
    "generated_at": "2026-04-14T18:00:00Z",
    "briefing_version": "v1",
    "baseline_mode": "last_seen",
    "baseline_label": "since last visit",
    "baseline_started_at": "2026-04-10T09:12:00Z",
    "baseline_available": true,
    "confidence": "medium"
  },
  "project_refresher": {},
  "top_changes": [],
  "read_first": [],
  "relevant_decisions": [],
  "top_risk": null,
  "open_questions": [],
  "evidence_index": [],
  "fallback_notes": []
}
```

## Section contracts

### 1. `project_refresher`

Purpose:
- Re-anchor the user in the project before diving into recent activity

Shape:
```json
{
  "summary": "CopyClip is a local-first project intelligence and AI collaboration control plane.",
  "confidence": "high",
  "why_now": "Recent work concentrated in MCP, tests, and local development flows.",
  "evidence": ["project.story", "snapshot:latest", "readme"]
}
```

Construction:
- Prefer `projects.story`
- Then latest `story_snapshots.summary_json`
- Then README-derived fallback

Evidence requirement:
- must cite at least one of: project story, story snapshot, README

Fallback behavior:
- If no narrative source exists, return a plain factual refresher:
  - project name
  - dominant modules / file count
  - recent activity summary
- confidence must be `low` or `medium`

### 2. `top_changes`

Purpose:
- Show the most important changes since the selected baseline

Shape:
```json
[
  {
    "title": "Packaging and async test support were tightened",
    "importance": 91,
    "summary": "Runtime and dev dependencies were aligned; async MCP tests now run under pytest-asyncio.",
    "change_kind": "engineering_foundation",
    "primary_area": "pyproject.toml",
    "evidence": [
      "commit:<sha>",
      "file:pyproject.toml",
      "file:pytest.ini",
      "file:tests/test_mcp_intent_oracle.py"
    ],
    "why_selected": [
      "recent_change",
      "broad_impact",
      "affects_developer_workflow"
    ]
  }
]
```

Selection rules:
- rank recent changes by `change_importance_score`
- include 3 to 5 items max
- collapse low-signal commit noise into one grouped item when necessary

Evidence requirement:
- every item must cite at least one file or commit
- high-importance items should cite both files and commit(s) when available

### 3. `read_first`

Purpose:
- Give the user a short reading sequence for regaining understanding

Shape:
```json
[
  {
    "rank": 1,
    "target_type": "file",
    "target": "pyproject.toml",
    "score": 94,
    "reason": "Recently changed foundation file tied to packaging and test reliability work.",
    "expected_payoff": "Explains current install/test path quickly.",
    "estimated_minutes": 2,
    "evidence": ["file:pyproject.toml", "commit:<sha>", "risk:packaging"]
  }
]
```

Selection rules:
- include 3 items maximum for default briefing
- items can be file, module, or decision
- rank by `read_first_score`

Evidence requirement:
- every item must cite why it is worth reading first

### 4. `relevant_decisions`

Purpose:
- Surface decisions that matter to current re-entry, not all decisions

Shape:
```json
[
  {
    "id": 12,
    "title": "Use bounded MCP handoff packets",
    "status": "accepted",
    "relevance_score": 82,
    "why_now": "Recent work touched linked files and review workflows.",
    "evidence": ["decision:12", "decision_link:src/copyclip/mcp_server.py"]
  }
]
```

Selection rules:
- accepted/resolved decisions outrank proposed ones
- unresolved/proposed decisions can appear if they are directly linked to changed or risky areas
- include 0 to 3 items max

Evidence requirement:
- decision itself plus at least one linkage to current change/risk/area when available

### 5. `top_risk`

Purpose:
- Make the most important current risk visible immediately

Shape:
```json
{
  "area": "tests/test_mcp_intent_oracle.py",
  "severity": "high",
  "kind": "test_gap",
  "score": 76,
  "summary": "Recent changes in the MCP path previously lacked stable async test support.",
  "recommended_first_action": "Read pyproject.toml and pytest.ini together.",
  "evidence": ["risk:test_gap", "file:pytest.ini", "file:tests/test_mcp_intent_oracle.py"]
}
```

Selection rules:
- choose the single highest re-entry-relevant risk, not merely the highest raw score
- prefer risks in recently changed or strategically important areas

Evidence requirement:
- must cite risk record plus supporting area/file evidence

Fallback behavior:
- if no risks exist, return `null` and add a note to `fallback_notes`

### 6. `open_questions`

Purpose:
- Show what the user may still need to resolve after reading the briefing

Shape:
```json
[
  {
    "question": "Should MCP-related integration coverage expand beyond current unit tests?",
    "priority": "medium",
    "derived_from": ["risk:test_gap", "changes:mcp"],
    "next_step": "Inspect MCP integration path and decide whether to add a smoke test."
  }
]
```

Selection rules:
- derive from unresolved decisions, risk clusters, evidence gaps, or contradictory signals
- include 1 to 3 questions max

Evidence requirement:
- every question must cite the signal(s) that produced it

### 7. `evidence_index`

Purpose:
- Provide a normalized artifact list used across the briefing

Shape:
```json
[
  {
    "id": "file:pyproject.toml",
    "type": "file",
    "label": "pyproject.toml",
    "ref": "pyproject.toml"
  }
]
```

Use:
- enables UI/CLI to show a readable briefing while keeping references stable

### 8. `fallback_notes`

Purpose:
- Explain degraded behavior when evidence is missing

Examples:
```json
[
  "No last_seen baseline found; fell back to last_analysis.",
  "No risk rows available for this project yet; omitted top_risk."
]
```

## Scoring model

The briefing uses explicit deterministic scores.

### A. Change importance score

Used for `top_changes`.

```text
change_importance_score =
  0.30 * recency_score +
  0.25 * churn_score +
  0.20 * risk_link_score +
  0.15 * decision_link_score +
  0.10 * breadth_score
```

Factors:
- `recency_score` — how close the change is to now / baseline edge
- `churn_score` — commit or file-change frequency in the baseline window
- `risk_link_score` — linked risk count / severity near the changed area
- `decision_link_score` — linked accepted/resolved/unresolved decisions
- `breadth_score` — number of affected modules/files, capped to avoid noise domination

Normalize each factor to 0–100.

### B. Read-first score

Used for `read_first`.

```text
read_first_score =
  0.25 * change_importance_score +
  0.25 * understanding_payoff_score +
  0.20 * risk_score +
  0.15 * decision_relevance_score +
  0.15 * brevity_score
```

Interpretation:
- favor artifacts that quickly improve understanding
- penalize giant/low-payoff areas
- small high-signal files/modules should rise

Factors:
- `understanding_payoff_score` — expected contextual payoff if read now
- `brevity_score` — likely to be digestible in 2–10 minutes

### C. Decision relevance score

Used for `relevant_decisions`.

```text
decision_relevance_score =
  0.40 * direct_link_score +
  0.25 * changed_area_overlap_score +
  0.20 * unresolved_weight +
  0.15 * risk_overlap_score
```

Interpretation:
- a decision matters when it overlaps the current changed/risky surface
- unresolved decisions get an extra boost because they produce uncertainty

### D. Briefing confidence

Top-level `meta.confidence` is derived from evidence quality, not style.

```text
confidence = high   if all core sections have direct evidence and baseline is real
confidence = medium if some sections rely on fallbacks or sparse evidence
confidence = low    if baseline is synthetic/first-run and multiple sections are partial
```

## Section-level evidence rules

Minimum requirements:
- `project_refresher` -> 1 narrative or snapshot source
- `top_changes` -> 1 commit or 1 file per item
- `read_first` -> at least 1 artifact + 1 selection reason per item
- `relevant_decisions` -> decision id + current relevance evidence
- `top_risk` -> risk record + area/file evidence
- `open_questions` -> derived_from references

If a section cannot meet minimum evidence:
- either degrade confidence and keep it
- or omit the section item and explain omission in `fallback_notes`

## Sparse-evidence fallback rules

### First-run project
If there is no baseline and very little project history:
- use current project story / overview
- omit comparative language like "since last visit"
- use "recommended first reads" based on static importance only
- set overall confidence to `low`

### No git history
- `top_changes` becomes file/system-change oriented rather than commit oriented
- cite files and snapshots only

### No decisions
- `relevant_decisions` returns empty list
- add fallback note: "No linked decisions available yet."

### No risks
- `top_risk` returns `null`
- derive open questions from change concentration or missing evidence instead

## Delivery expectations

### API
- return the full structured object
- keep stable keys for frontend and CLI consumers

### UI
- show a short readable briefing first
- preserve drill-down into `evidence_index`
- expose baseline mode and confidence visibly

### CLI
- render a compact human-readable summary
- preserve artifact refs so the user can continue manually

## Implementation notes for follow-up issues

Issue mapping:
- #29 adds persistence for baseline modes (`last_seen`, checkpoints, windows)
- #30 implements the briefing generator and scoring logic
- #31 exposes API and CLI delivery
- #32 renders the briefing in the dashboard
- #33 adds fixtures and tests around ranking and sparse-evidence behavior

## Non-goals for v1

- perfect semantic understanding of all change intent
- personalized user-specific weighting beyond baseline mode
- multi-repo reacquaintance
- LLM-only ranking without deterministic evidence rules
