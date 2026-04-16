# Safe Agent Handoff Contract

Status: draft for issue #40
Owner: CopyClip
Related issues: #18, #40, #41, #42, #43, #44, #45, #46

## Purpose

Safe Agent Handoff is the bounded delegation workflow for turning a human task into an inspectable packet an external agent can consume without receiving uncontrolled context.

Its job is not to replace human judgment.
Its job is to make delegation explicit, reviewable, and reversible.

The handoff contract must answer:
- What exactly is the objective?
- What is in scope?
- What must not be touched?
- Which decisions and constraints apply?
- Which risks or dark zones make this task dangerous?
- What must the agent clarify before acting?
- How will a human review whether the outcome respected the contract?

## Design principles

- Bound the task before enriching the context
- Separate human-authored instruction from system-derived evidence
- Make do-not-touch boundaries first-class, not implied
- Keep agent-consumable fields compact and explicit
- Preserve provenance for every inferred constraint, decision, and risk
- Support pre-delegation review and post-change review with one stable contract
- Keep the lifecycle explicit enough for backend, UI, and MCP delivery paths

## Contract objects

The workflow uses two primary objects:
1. `handoff_packet` — pre-delegation bounded task packet
2. `handoff_review_summary` — post-change comparison against the declared packet

Optional supporting object:
3. `handoff_execution_record` — metadata about an agent run or proposal linked to a packet

## Lifecycle states

### Packet lifecycle

Allowed `handoff_packet.state` values:
- `draft` — packet is still being composed by the human/system
- `ready_for_review` — enough structure exists to inspect it before delegation
- `approved_for_handoff` — human approved the packet for agent consumption
- `delegated` — packet was delivered to an external agent or tool
- `change_received` — delegated output or proposed diff has been received
- `reviewed` — post-change review completed
- `superseded` — replaced by a newer packet for the same task
- `cancelled` — abandoned before completion

### Execution lifecycle

Allowed `handoff_execution_record.state` values:
- `queued`
- `running`
- `completed`
- `failed`
- `abandoned`

### Review lifecycle

Allowed `handoff_review_summary.review_state` values:
- `not_started`
- `generated`
- `human_reviewed`
- `accepted`
- `changes_requested`

## State transition rules

### Packet transitions

Allowed transitions:
- `draft -> ready_for_review`
- `ready_for_review -> approved_for_handoff`
- `ready_for_review -> draft`
- `approved_for_handoff -> delegated`
- `approved_for_handoff -> cancelled`
- `delegated -> change_received`
- `delegated -> cancelled`
- `change_received -> reviewed`
- `reviewed -> superseded`
- `draft -> superseded`
- `ready_for_review -> superseded`

Disallowed transitions:
- no direct `draft -> delegated`
- no direct `approved_for_handoff -> reviewed`
- no reopening from `cancelled`
- no mutation of agent-consumable fields after `delegated` without creating a replacement/superseding packet

### Human gate expectations

Human approval is required before:
- `ready_for_review -> approved_for_handoff`
- any packet with unresolved `questions_to_clarify` can become `approved_for_handoff` only if explicitly overridden by the human

Human review is required before:
- `generated -> accepted`
- `generated -> changes_requested`

## Top-level handoff packet schema

```json
{
  "meta": {
    "packet_id": "handoff_2026_04_16_001",
    "packet_version": "v1",
    "state": "ready_for_review",
    "created_at": "2026-04-16T12:00:00Z",
    "updated_at": "2026-04-16T12:04:00Z",
    "project": "copyclip",
    "created_by": "human",
    "approved_by": null,
    "delegation_target": null,
    "source_task": {
      "kind": "freeform_prompt",
      "value": "Add safe handoff packet generation for bounded agent delegation"
    }
  },
  "objective": {},
  "scope": {},
  "constraints": [],
  "do_not_touch": [],
  "relevant_decisions": [],
  "risk_dark_zones": [],
  "questions_to_clarify": [],
  "acceptance_criteria": [],
  "agent_consumable_packet": {},
  "review_contract": {},
  "evidence_index": [],
  "notes": []
}
```

## Section contracts

### 1. `objective`

Purpose:
- capture the single bounded job the agent is being asked to do

Shape:
```json
{
  "summary": "Generate a safe handoff packet generator for bounded AI delegation.",
  "task_type": "feature",
  "intent": "Prepare a reviewable delegation artifact, not autonomous execution.",
  "success_definition": "A human can inspect the packet before delegation and see scope, constraints, and review gates clearly."
}
```

Rules:
- must be human-authored or human-confirmed
- must describe one primary task, not a roadmap
- `success_definition` should be phrased as human verification, not agent self-certification

### 2. `scope`

Purpose:
- define what the agent is allowed to touch and what supporting context is intentionally included

Shape:
```json
{
  "declared_files": [
    "src/copyclip/intelligence/handoff.py",
    "src/copyclip/intelligence/server.py",
    "tests/test_handoff_packets.py"
  ],
  "declared_modules": ["copyclip.intelligence"],
  "supporting_files": [
    "src/copyclip/intelligence/ask_project.py",
    "docs/HANDOFF_PACKET_CONTRACT.md"
  ],
  "out_of_scope_modules": ["frontend", "atlas"],
  "scope_rationale": [
    "Packet generation belongs in backend intelligence code.",
    "UI work is intentionally excluded from this packet."
  ]
}
```

Rules:
- `declared_files` and `declared_modules` define allowed working scope
- `supporting_files` may be read for context but do not imply write permission
- `out_of_scope_modules` should be explicit when blast radius could be tempting
- scope may be partially human-authored and partially system-expanded, but the final visible set must be inspectable before approval

### 3. `constraints`

Purpose:
- capture rules the agent must follow inside the declared scope

Shape:
```json
[
  {
    "constraint_id": "constraint:decision:12",
    "type": "architectural_decision",
    "summary": "Use bounded MCP handoff packets rather than ad hoc prompt dumps.",
    "source": ["decision:12"],
    "severity": "high",
    "origin": "system_derived"
  },
  {
    "constraint_id": "constraint:workflow:review_gate",
    "type": "workflow",
    "summary": "Do not skip human review before delegation.",
    "source": ["handoff_contract:lifecycle"],
    "severity": "high",
    "origin": "human_authored"
  }
]
```

Rules:
- every constraint must have provenance in `source`
- `origin` must be one of:
  - `human_authored`
  - `human_confirmed`
  - `system_derived`
- high-severity constraints should be mirrored in the agent-consumable packet

### 4. `do_not_touch`

Purpose:
- make boundaries explicit rather than inferred from omission

Shape:
```json
[
  {
    "target": "frontend/src/pages/AskPage.tsx",
    "reason": "UI is intentionally excluded from backend packet generation work.",
    "severity": "hard_boundary",
    "source": ["human_boundary:ui_excluded"]
  }
]
```

Rules:
- hard boundaries mean touching the file/module should trigger a review warning
- should be human-authored or human-confirmed
- may reference files, modules, folders, or behaviors (e.g. `do not change DB schema in this packet`)

### 5. `relevant_decisions`

Purpose:
- list only the decisions that matter for this delegation

Shape:
```json
[
  {
    "id": 12,
    "title": "Use bounded MCP handoff packets",
    "status": "accepted",
    "why_relevant": "The task is defining the bounded delegation artifact itself.",
    "linked_targets": ["src/copyclip/mcp_server.py"],
    "evidence": ["decision:12", "decision_link:src/copyclip/mcp_server.py"]
  }
]
```

Rules:
- accepted/resolved decisions outrank proposed ones
- proposed decisions can appear only as cautionary context, not binding constraints
- must not dump the entire decision database

### 6. `risk_dark_zones`

Purpose:
- surface risky or cognitively dark areas relevant to delegation

Shape:
```json
[
  {
    "risk_id": 7,
    "area": "src/copyclip/mcp_server.py",
    "kind": "intent_drift",
    "severity": "high",
    "score": 91,
    "why_it_matters": "Unbounded MCP delivery could bypass the contract and hand the agent too much context.",
    "recommended_guardrail": "Keep agent-consumable fields explicit and minimal.",
    "evidence": ["risk:7", "file:src/copyclip/mcp_server.py"]
  }
]
```

Rules:
- include both conventional risks and dark-zone/cognitive-debt areas when available
- every risk must have a recommended guardrail or mitigation note
- must be system-derived but visible for human review

### 7. `questions_to_clarify`

Purpose:
- identify missing information the agent should not invent

Shape:
```json
[
  {
    "question": "Should the first handoff contract support only backend delivery, or also define UI-visible labels now?",
    "priority": "high",
    "blocking": true,
    "derived_from": ["scope_gap:ui_vs_backend"],
    "resolution": null
  }
]
```

Rules:
- blocking questions should prevent automatic `approved_for_handoff` unless explicitly overridden by a human
- resolved questions should preserve the answer in future packet versions or notes

### 8. `acceptance_criteria`

Purpose:
- define what a reviewer will check after delegated work returns

Shape:
```json
[
  {
    "id": "ac1",
    "summary": "The packet contract separates human-authored instruction, derived evidence, and review data.",
    "check_type": "contract_integrity"
  },
  {
    "id": "ac2",
    "summary": "Lifecycle states are explicit enough for backend, UI, and MCP implementation.",
    "check_type": "review_readiness"
  }
]
```

Rules:
- should be human-authored or human-confirmed
- should be testable or reviewable without interpreting vague intent

### 9. `agent_consumable_packet`

Purpose:
- define the minimal structured payload an external agent actually receives

Shape:
```json
{
  "objective": "Generate a backend handoff packet builder.",
  "allowed_write_scope": [
    "src/copyclip/intelligence/handoff.py",
    "src/copyclip/intelligence/server.py",
    "tests/test_handoff_packets.py"
  ],
  "read_scope": [
    "src/copyclip/mcp_server.py",
    "docs/HANDOFF_PACKET_CONTRACT.md"
  ],
  "constraints": [
    "Do not bypass explicit scope boundaries.",
    "Keep the packet inspectable and deterministic."
  ],
  "do_not_touch": ["frontend", "atlas"],
  "questions_to_clarify": [
    "Should UI fields be included now or deferred to a later issue?"
  ],
  "acceptance_criteria": [
    "Packet separates instruction, evidence, and review fields."
  ]
}
```

Rules:
- must be a projection of the full packet, not a separate source of truth
- must exclude internal-only notes and non-essential metadata
- must preserve hard boundaries and blocking questions

### 10. `review_contract`

Purpose:
- define how the eventual output will be reviewed against the packet

Shape:
```json
{
  "expected_review_type": "post_change_summary",
  "compare_scope_against_touched_files": true,
  "check_decision_conflicts": true,
  "check_dark_zone_entry": true,
  "check_blast_radius": true,
  "required_human_questions": [
    "Did the change stay within declared write scope?",
    "Did it violate any accepted decisions?"
  ]
}
```

Rules:
- this section is the bridge between packet creation and post-change review
- should not include execution results yet

### 11. `evidence_index`

Purpose:
- provide normalized references reused across packet and review objects

Shape:
```json
[
  {
    "id": "decision:12",
    "type": "decision",
    "label": "Use bounded MCP handoff packets",
    "ref": 12
  },
  {
    "id": "file:src/copyclip/mcp_server.py",
    "type": "file",
    "label": "src/copyclip/mcp_server.py",
    "ref": "src/copyclip/mcp_server.py"
  }
]
```

Rules:
- every referenced decision/risk/file/module should have one canonical evidence item where possible
- packet sections should refer to these IDs in `source`, `evidence`, or `derived_from`

## Post-change review summary contract

### Top-level schema

```json
{
  "meta": {
    "review_id": "review_2026_04_16_001",
    "packet_id": "handoff_2026_04_16_001",
    "review_state": "generated",
    "generated_at": "2026-04-16T14:20:00Z"
  },
  "result": {
    "summary": "Change mostly stayed in scope but entered one dark zone.",
    "verdict": "changes_requested",
    "confidence": "medium"
  },
  "scope_check": {},
  "decision_conflicts": [],
  "blast_radius": {},
  "dark_zone_entry": [],
  "unresolved_questions": [],
  "review_evidence": []
}
```

### `scope_check`

```json
{
  "declared_scope": [
    "src/copyclip/intelligence/handoff.py",
    "src/copyclip/intelligence/server.py"
  ],
  "touched_files": [
    "src/copyclip/intelligence/handoff.py",
    "src/copyclip/mcp_server.py"
  ],
  "out_of_scope_touches": ["src/copyclip/mcp_server.py"],
  "summary": "One touched file was outside the approved write scope."
}
```

### `decision_conflicts`

```json
[
  {
    "decision_id": 12,
    "severity": "high",
    "summary": "The change bypasses the bounded packet contract by expanding uncontrolled context delivery.",
    "evidence": ["decision:12", "file:src/copyclip/mcp_server.py"]
  }
]
```

### `blast_radius`

```json
{
  "impacted_modules": ["copyclip.intelligence", "copyclip.mcp"],
  "impact_summary": "Delegation output now affects packet generation and MCP delivery paths.",
  "estimated_size": "medium"
}
```

### `dark_zone_entry`

```json
[
  {
    "area": "src/copyclip/mcp_server.py",
    "reason": "High intent_drift risk area was touched despite not being in declared write scope.",
    "evidence": ["risk:7", "file:src/copyclip/mcp_server.py"]
  }
]
```

### `unresolved_questions`

```json
[
  {
    "question": "Was MCP integration intentionally expanded, or was it accidental scope drift?",
    "priority": "high"
  }
]
```

## Human-only vs agent-consumable sections

### Human-only / human-review sections
- `meta.approved_by`
- `notes`
- full `evidence_index`
- review-generation internals
- any local-only reviewer annotations
- post-change verdict metadata before human review

### Agent-consumable sections
- `objective`
- approved write/read scope projection
- explicit constraints
- do-not-touch boundaries
- unresolved questions the agent must respect
- acceptance criteria relevant to the delegated task

### Mixed sections requiring projection
- `relevant_decisions`
- `risk_dark_zones`
- `review_contract`

The full object may contain richer evidence, but the delivered agent packet should only include compact summaries plus stable references.

## Persistence expectations for later issues

This issue defines the contract only. Later issues may persist it across:
- `handoff_packets`
- `handoff_packet_scope_items`
- `handoff_review_summaries`
- `handoff_execution_records`

The contract should stay stable even if storage is normalized later.

## Non-goals for #40

This issue does not require:
- packet generation logic
- packet persistence tables
- dashboard UI
- MCP delivery implementation
- automated post-change comparison logic

Those belong to #41, #42, #43, #44, #45, and #46.

## Ready-for-implementation checklist

#40 should be considered complete when:
- [ ] there is a stable contract for handoff packets and review summaries
- [ ] lifecycle states and transitions are explicit
- [ ] human-authored vs system-derived vs agent-consumable sections are clearly separated
- [ ] backend/UI/MCP work can implement against this contract without guessing field intent
