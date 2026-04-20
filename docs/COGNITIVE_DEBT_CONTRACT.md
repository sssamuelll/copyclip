# Cognitive Debt Contract

Status: draft for issue #47
Owner: CopyClip
Related issues: #19, #47, #48, #49, #50, #51, #52

## Purpose

Cognitive debt measures how far a piece of code has drifted away from human understanding. A high score is not just "messy code"; it means the human has lost traction — reviews are stale, recent change was not human-authored, the area has no anchoring decisions, or ownership is ambiguous.

Its job is not to produce a prettier metric. Its job is to explain itself: every score must be backed by a factor breakdown with signal sources and evidence, so the user can see why an area is dark and what the smallest next step is to reduce uncertainty.

The contract must answer:
- Why is this area cognitively dark?
- Which factors contributed, with which weight?
- Is this low / medium / high / critical, and is the classification stable?
- Can I compare this area to another one practically?
- What level of confidence should I place on the score?

## Design principles

- Every score is explainable by a factor breakdown
- Factors are independent, composable, and individually measurable
- Severity thresholds are stable across UI, prioritization, MCP, and briefing surfaces
- Prefer deterministic scoring over opaque narrative generation
- Expose evidence per factor so remediation (#49) can ground its suggestions
- Aggregate scope-aware: file → module → project, never flatten silently
- Make uncertainty explicit (missing signals reduce confidence, not score)
- Keep the contract stable even if factor weights change between versions

## Contract objects

Cognitive debt is described by four objects that travel together:

1. `debt_score` — scalar in `[0, 100]` with a severity label
2. `debt_factor_breakdown` — ordered list of per-factor contributions
3. `debt_severity` — semantic bucket derived from the score
4. `debt_scope` — file, module, or project aggregation envelope

All four are projections of the same underlying computation. The raw signals live in the project database; the contract objects live in the API response, the MCP projection, and the UI render layer.

## Severity thresholds

Thresholds are fixed so that UI, prioritization, and MCP can render the same bucket without re-deriving labels.

| Bucket      | Range     | Meaning                                          |
|-------------|-----------|--------------------------------------------------|
| `low`       | `0-24`    | Area is well understood                          |
| `medium`    | `25-49`   | Some drift, acknowledge but do not prioritize    |
| `high`      | `50-74`   | Dark zone; re-acquaint before non-trivial change |
| `critical`  | `75-100`  | Avoid delegation; human must re-read first       |

Labels are stable. Tuning factor weights does not change bucket semantics.

## Top-level schema

```json
{
  "meta": {
    "project": "copyclip",
    "generated_at": "2026-04-20T10:00:00Z",
    "contract_version": "v1",
    "scope_kind": "file",
    "scope_id": "src/copyclip/mcp_server.py"
  },
  "score": {
    "value": 72.4,
    "severity": "high",
    "confidence": "medium",
    "signal_coverage": 0.83
  },
  "factor_breakdown": [],
  "evidence_index": [],
  "notes": []
}
```

## Factor model

Factors are measured independently, normalized to `[0, 100]`, weighted, and summed.

### Canonical factors

| `factor_id`              | Signal source                                                    | Normalization                                                   | Weight |
|--------------------------|------------------------------------------------------------------|-----------------------------------------------------------------|--------|
| `churn_pressure`         | `file_changes` rows over the lookback window                     | `min(100, churn_count * churn_unit)`                            | 0.18   |
| `agent_authored_ratio`   | `git blame` agent-authored lines / total lines                   | `ratio * 100`                                                   | 0.22   |
| `review_staleness`       | days since last human-authored line                              | `min(100, days_since_human / 60 * 100)`                         | 0.15   |
| `test_evidence_gap`      | linked test files / (files × 1) over the module or file's module | `(1 - coverage_hint) * 100`                                     | 0.12   |
| `decision_gap`           | decisions linked to the area vs touched decisions across churn   | `(1 - decision_link_ratio) * 100`                               | 0.13   |
| `ownership_ambiguity`    | distinct authors + tenure dispersion in blame                    | `min(100, distinct_authors * tenure_weight)`                    | 0.08   |
| `blast_radius`           | module fan-out and import-graph depth                            | `min(100, (fan_out_normalized + import_depth_normalized) * 50)` | 0.07   |
| `novelty_recency`        | `commits` whose SHA first introduced the file, within window     | `age_recency_bump()`                                            | 0.05   |

Weights sum to `1.00`. The default weights above are the v1 baseline; different weight profiles may exist later (e.g. delegation-mode vs review-mode) but the contract version must be bumped when profiles change.

### Factor breakdown item shape

```json
{
  "factor_id": "agent_authored_ratio",
  "label": "Agent-authored ratio",
  "weight": 0.22,
  "raw_signal": { "agent_lines": 140, "total_lines": 220 },
  "normalized_contribution": 63.6,
  "weighted_contribution": 14.0,
  "signal_available": true,
  "rationale": "63.6% of current lines were authored by external agents.",
  "evidence": ["file:src/copyclip/mcp_server.py", "blame:agent"]
}
```

Rules:
- `weight` is the declared factor weight, independent of the raw signal
- `normalized_contribution` is the `[0, 100]` projection of the raw signal
- `weighted_contribution = weight * normalized_contribution`
- `signal_available: false` means the factor was skipped (see `signal_coverage` below)
- `evidence` uses the same normalized ids as the rest of the intelligence surface (`file:*`, `decision:*`, `risk:*`, `commit:*`, `module:*`)

## Score composition rule

```
debt_score = clamp( Σ factor.weighted_contribution / Σ factor.weight_if_available , 0, 100 )
```

If a factor's signal is unavailable, its weight is removed from the denominator instead of being treated as zero. This preserves the `[0, 100]` shape regardless of signal coverage.

`signal_coverage = Σ weight_if_available / 1.0` and feeds into `confidence`:

| `signal_coverage` | `confidence` |
|-------------------|--------------|
| `>= 0.85`         | `high`       |
| `0.6 - 0.85`      | `medium`     |
| `< 0.6`           | `low`        |

Low confidence does not suppress the score; it flags it as less trustworthy for prioritization.

## Scope-level aggregation

The same factor model applies at three scope kinds:

### File scope
- signals are measured against the single file
- `evidence_index` is compact
- default unit for dashboard drilldown

### Module scope
- files in the module are aggregated weighted by LOC
- `churn_pressure` is the module's total churn normalized against module LOC
- severity is the max(file severity, module aggregated severity) — highest-severity file can lift the module bucket
- `evidence_index` references both `module:<id>` and up to 5 top-contributing files

### Project scope
- `score.value` is the weighted mean of module scores
- `severity` is the project bucket from the mean; the top modules surface separately in UI
- project scope does not drive remediation recommendations directly; it sets context for #49

## Comparison rules

- **Within a project**: direct score comparison is valid. Use severity bucket first, raw value second.
- **Across projects**: do not compare raw scores directly. Use percentile rank within each project or factor-by-factor comparison.
- **Across versions**: include `meta.contract_version` and the weight profile used so historical comparisons are grounded.
- Every comparison must include the factor breakdown, otherwise two identical scores can have completely different remediation needs.

## Remediation hooks

#49 will consume this contract to produce recommendations. The contract reserves these read-only fields that #49 is expected to populate without mutating the breakdown:

- `remediation_candidates`: ranked actions, each referencing the factor(s) they would reduce
- `read_first`: ordered list of files/decisions/tests that most efficiently reduce the top factor
- `expected_impact`: projected score delta for each candidate (must be presented as an estimate, never a promise)

These fields are out of scope for #47 itself but must be compatible with the breakdown shape defined here.

## Integration hooks

#51 will consume this contract from two surfaces:

- **Ask Project**: debt score and top factor breakdown should enrich evidence answers when the question targets a file, module, or area
- **Reacquaintance Mode**: debt score should boost `read_first` priority in briefings when severity is `high` or `critical`

Integration must not mutate the debt contract — it consumes projections.

## Evidence index

Same normalized id scheme used across CopyClip:
- `file:<path>`
- `module:<name>`
- `decision:<id>`
- `decision_link:<target>`
- `risk:<id>`
- `commit:<sha>`
- `blame:agent` / `blame:human` (aggregate markers)

Any factor that contributed a non-zero weighted value must add at least one evidence id.

## Confidence and signal availability

Confidence is not a hedge on the score; it is a hedge on the comparison. Downstream:
- `high` confidence: safe to prioritize by this score alone
- `medium` confidence: show factor breakdown alongside the score
- `low` confidence: force factor breakdown, warn against cross-comparison

A file with `signal_available = false` for `review_staleness` is common in greenfield repos; the contract must not pretend this is "zero staleness".

## Stability and versioning

- `meta.contract_version` starts at `v1`
- changing weight profiles requires a minor bump (`v1.1`)
- adding or removing a factor requires a major bump (`v2`)
- severity thresholds are treated as part of the public API and do not change within a major version

## Non-goals for #47

This issue does not require:
- backend implementation of factor breakdowns
- remediation recommendation logic
- UI for dark-zone inspection
- integration into Reacquaintance / Ask
- automated tests and fixtures

Those belong to #48, #49, #50, #51, and #52.

## Ready-for-implementation checklist

#47 should be considered complete when:
- [ ] every factor has a declared signal source and normalization rule
- [ ] severity thresholds are explicit and stable
- [ ] score composition and aggregation rules are unambiguous
- [ ] factor breakdown shape is locked
- [ ] evidence id scheme matches the rest of the intelligence surface
- [ ] integration and remediation hooks are named so #49 and #51 can design against them
