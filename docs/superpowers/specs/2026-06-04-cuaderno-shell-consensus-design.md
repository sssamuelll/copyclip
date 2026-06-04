# CopyClip → Cuaderno-Shell: Consensus Design

**Date:** 2026-06-04
**Status:** Ratified (Samuel + full roster, two consensus rounds)
**Supersedes:** the dashboard-as-peer information architecture; the clipboard-era default entrypoint.

---

## 1. The claim and the ruling

The philosophy (six clauses, adopted 2026-06-04):

1. **The claim:** "CopyClip keeps you understanding your own codebase while AI agents write most of it."
2. **The human is the client.** Agents get bounded views over MCP only.
3. **The wedge is temporal-causal, not spatial.** Comprehension = recovering decisions you didn't make.
4. **Evidence-first honesty.** Verdicts carried, never papered over; observation, not pronouncement.
5. **Personal tool.** One developer's daily use; no team/venture framing.
6. **The cuaderno is the home.**

Samuel's ruling (2026-06-04, constitution for this migration):

- **All of CopyClip becomes the cuaderno.** The cuaderno is a shell "tan capaz como Jupyter": it generates artifacts as complex as interactive graphs (Atlas3D-grade) to explain complex things simply, and hosts marimo playgrounds inline as didactic, runnable examples of what the code does.
- Six dead/inverted surfaces are cut outright (Wave 1 below).
- The playground (marimo) is **not** cut — it is reborn inside the cuaderno.
- Every remaining part finds its shell-native form or dies.

### Workflow reality (recorded 2026-06-04)

Samuel barely authors commits; he **supervises AI work**. Any feature or claim that presumes human-authored commits (e.g. "re-enter through code you actually wrote") targets a workflow he does not have. The meaningful re-entry anchor is the **last point of understanding** (last_seen, checkpoint, got-it marks), not the last point of authorship. README:21 is rewritten around this; the human-authored-commit baseline is **not** built.

---

## 2. The critical finding: the honesty regime is blind to artifacts

Unanimous across the council, verified in source:

- `quality.py` (`_answer_text`, `_cited_paths`) and `judge.py` read only `b.data['text']` and the three citation shapes.
- Widget payloads live under `data['widget']`, carry no text and no citation shape either gate walks.
- **Therefore every widget — including the three that exist today (graph_subset, sequence_diagram, callers_tree) — bypasses both the cheap gate and the judge and seals `answer` unjudged.**

Vale's framing: "you are not adding artifacts to a discipline, you are smuggling them past it." Richter's: "clause 4 dying quietly where it looks most convincing."

**Consequence:** Wave 2 widens the existing gates (never a parallel verifier) **before** any heavy artifact ships. Wave 3's gate proves the widened regime on a real artifact.

## 3. Artifact ontology (council consensus)

- An artifact is **a projection of evidence the ledger already holds** (Voronov) — never a second, unverified channel. Every evidentiary primitive (node/edge/step/example) carries a citation the gate can read.
- Heavy artifacts are **lazy by reference**: `emit_block` carries a data-ref (e.g. `graph:<query>`), never inlined payloads; the shell hydrates.
- Process-class artifacts (marimo) are **re-derivable recipes, not by-value corpses** (Richter): a persisted frame stores a re-launch descriptor, never a live URL/port.
- Artifacts surrender their aesthetic at the door (Tane): one widget chrome, paper-toned, no 26-color rainbow, no black-terminal modal; an artifact must never look more authoritative than its grounding.
- The machinery to confess "this part was not checked" exists for text (provenance notes) and must be mirrored for artifacts (fail-open `unassessed`, never silently `answer`).

## 4. Ratified decisions

| Decision | Ruling |
|---|---|
| "Tan capaz como Jupyter" ceiling | **Exposition, not authorship.** The tutor emits runnable, interactive examples; the human interrogates and plays. No human-editable cells (a second source of truth the judge cannot ground). |
| Subprocess trust boundary | **Spawn-on-click only.** The tutor emits launch descriptors; a real marimo subprocess starts only on explicit human gesture. Artifacts never auto-spawn. |
| Dashboard death date | **Friday 2026-06-19.** The legacy App.tsx router/Sidebar is deleted in Wave 5. No indefinite coexistence. |
| Reacquaintance anchor (README:21) | **Reframe around supervision.** The anchor concept "your last human-authored commit" is a relic; rewrite the claim around last point of understanding (what `last_seen`/`checkpoint` already do). Do not build the human-authored-commit baseline. |
| Marimo didactic honesty | A didactic example must import the **real resolved symbol** (as `generate_marimo_notebook` already does) **or** carry an explicit "illustrative — not your code" disclosure in its data, visible to the judge. |

Open (deferred to their wave's spec):
- Atlas graph data contract for first ship (full `/api/architecture/graph` vs tutor-supplied subset) — Wave 3 spec.
- Which ≤3 roadmap items survive — Samuel, at Wave 5.

## 5. Dispositions (17 parts, conflicts arbitrated by Axiom-0)

Axiom-0's invariant: *a capability survives at the layer where it is irreducible under the shell; the surface that merely renders it does not survive.*

| Part | Disposition | Wave |
|---|---|---|
| Bare CLI clipboard export flow | COMMAND (`copyclip export`; bare entry opens the shell) | 2 |
| cuaderno-as-peer routing / dashboard IA | ABSORB_THEN_DELETE (death scheduled 2026-06-19) | 2→5 |
| Atlas 3D codebase map | ARTIFACT (renderer decoupled to pure data-prop widget; page dies) | 3 |
| Ask Project (AskPage) | ABSORB_THEN_DELETE (absorption already happened in the compositor; name it) | 2 |
| MCP "Intent Oracle" server | TOOL (rename off Oracle/Authority; audit verdict returns to the human) | 5 |
| Reacquaintance anchor claim | CLAIM_FIX (supervision reframe, §4) | anytime |
| Read/write ledger claim (README:60) | CLAIM_FIX (per-turn tutor reads feeding the gate) | anytime |
| "Propagation Oracle" (ImpactSimulator) | TOOL (reverse-dependents as tutor tool; fabricated ≥6 severity dies) | 4 |
| Structure Graph (ArchitecturePage) | ARTIFACT (rides the Wave-3 graph widget; no second renderer) | 4 |
| "Distortion Field" (RisksPage) | ABSORB_THEN_DELETE (risk rows as cited callout blocks) | 4 |
| "Intent Field" kanban (PlanningPage) | ABSORB_THEN_DELETE (decision-ledger data survives as blocks) | 4 |
| Mystical labels + programmatic " field" suffix | CLAIM_FIX (rename to function; delete App.tsx suffix) | anytime |
| Dashboard vs cuaderno design-system split | ABSORB_THEN_DELETE (all chrome reconciles under cuaderno.css; nebula palette dies) | 4 |
| Settings "Configuration Nexus" | SIDE_SURFACE (the one legitimate non-conversational survivor; paper re-skin) | 3 |
| Context Forge (ContextBuilderPage) | TOOL (`/api/issues` survives the page; tutor tool is its new consumer) | 4 |
| Roadmap direction | CLAIM_FIX (≤3 items, temporal-causal, feeding the cuaderno) | 5 |
| CLI self-description ("Intent Authority") | CLAIM_FIX (align with the claim) | 2 |

## 6. The five waves

Each wave gates on verification before the next.

1. **Wave 1 — Ratified cuts** (edit mode; plan: `docs/superpowers/plans/2026-06-04-wave-1-ratified-cuts.md`). Order: cache.py → IssuesPage → agents framework → AtlasPage → NarrativePage+identity/drift → OpsPage+alerts. Preserve `/api/issues` (ContextBuilderPage) and `/api/analyze/*` (DebtNavigatorPage).
2. **Wave 2 — Shell core.** Front-door handover (`copyclip` opens the shell; `copyclip export`); the honesty backbone (widget citations + `_artifact_summary` + fail-open `unassessed`); bench/i18n artifact coverage; AskPage collapse; death date recorded.
3. **Wave 3 — Proof artifacts.** Graph artifact (decoupled renderer, data-ref hydration, paper-toned subset first); marimo artifact (launch descriptor, spawn-on-click, four runtime states incl. "runtime ended" — never a dead iframe); Settings re-skinned as side surface. *Gets its own spec/plan.*
4. **Wave 4 — Absorption by question-class, not by page.** Temporal-causal cluster (reacquaintance/timeline/decisions/changes) collapses to existing git_* tools; risks → cited callouts; impact + context-builder → tutor tools; full chrome reconciliation. *Gets its own plan.*
5. **Wave 5 — Scheduled retirement (2026-06-19).** Legacy router/Sidebar deleted; orphaned api.* methods swept; MCP rename; README/roadmap honesty sweep.

## 7. Risks the plan must respect

1. **Honesty blind spot** (§2) — Wave 2 before any heavy artifact. Highest risk.
2. **Subprocess leak:** no frame-close→kill hook exists; cap=5 then `NoFreePortError`. Spawn-on-click + explicit kill hook in Wave 3.
3. **Dead iframe on restore:** persist a recipe, never a URL; render an explicit dead-runtime state, never `null`.
4. **Fabricated pedagogy:** didactic marimo must run the real symbol or disclose "illustrative" (judge-visible).
5. **Deletion reflex over-cuts:** `/api/issues` and `/api/analyze/*` are quarantined from the Wave-1-trained delete reflex.
6. **Dashboard-2.0 accretion:** a widget kind costs ~3 LOC; an ARTIFACT is earned only by an irreducibly visual answer. Absorb per question-class.
7. **Bench baseline drift:** artifact-aware asserts + intentional, reviewed corpus_sha regeneration (never silent).

## 8. Provenance

Consensus round 1 (philosophy roast): Serrano, Richter, Voronov, Vale, Rune, Halberg, Tane → 24 parts in tension; judges Lyra + Cassian agreed 24/24; Axiom-0 arbitrated Ask Project.
Consensus round 2 (under the ruling): Plumb (calibration), Amina (55-impact map), Kenji (pipeline fidelity map) → council (Voronov, Richter, Halberg, Serrano, Tane, Vale) → re-disposition (Lyra, Cassian; 3 conflicts → Axiom-0) → wave plan.
Corrections the calibration caught: `marimo_runner.py` exists and is real (373 LOC; stale briefing said absent); SettingsPage shares zero analyze plumbing (DebtNavigator is the live co-consumer); NarrativePage does not consume identity/drift (AtlasPage is the sole consumer); flow_diagram's `self.cache` is an unrelated in-class dict.
