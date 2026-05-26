# Provenance Protocol (PROV-1) — Identity & Scope Design Spec

**Date**: 2026-05-26
**Status**: Approved for implementation (sub-project #1 of the protocol pivot)
**Tracking**: Strategic pivot triggered by competitive surfacing of Lum1104/Understand-Anything (33K stars, March-May 2026) and meta-architecture verdict by Aurelius Voronov on 2026-05-26
**Decomposition context**: This is sub-project #1 of six. Downstream sub-projects: (#2) canonicalization of existing CopyClip contracts into protocol form, (#3) reference-implementation framing in CopyClip README, (#4) buyer pivot strategy, (#5) enterprise product surface, (#6) adoption / standards strategy.

## Why

CopyClip's existing artifact corpus (`HANDOFF_PACKET_CONTRACT.md`, `MCP_INTENT_AUTHORITY_SPEC.md`, `COGNITIVE_DEBT_CONTRACT.md`, `REACQUAINTANCE_BRIEFING_CONTRACT.md`, `DRIFT_CALIBRATION.md`, `CONTEXTUAL_LEGACY_FORMAT.md`) is already shaped like a protocol specification rather than a product implementation. It is contract-versioned, lifecycle-explicit, provenance-tagged, and projection-aware. The technical investment for a protocol pivot is already done — what is missing is **naming, extraction, branding, and publishing as a protocol** rather than as internal contracts for a product.

The strategic context that forced this decision:

- A competitor (Lum1104/Understand-Anything) reached 33,307 GitHub stars in two months by occupying the **codebase comprehension** category (onboarding to unfamiliar code). CopyClip's wedge is **codebase governance** (retaining ownership over code authored by AI agents) — a structurally different product with a different buyer in a different emotional state. The two are not substitutes.
- A meta-architecture review (Aurelius Voronov, 2026-05-26) identified that CopyClip's underlying architecture is reaching for **protocol** while its marketing performs **product** and its roadmap language ("sentinel") performs **identity**. None of those three are compatible at scale.
- The decision was made to resolve this by committing CopyClip to a hybrid identity: **venture-scale product whose scaling moat is being the canonical reference implementation of a publicly specified protocol for human-agent authorship attribution over codebases.**
- The protocol's wedge is anchored not to developer psychology but to **liability law** — the EU AI Act, SOC2 CC8.1, ISO/IEC 42001, and NIST AI RMF all assume a named human author and provide no equivalence for agentic authorship. As agent velocity increases, the gap between *legal responsibility* and *human comprehension* widens, not narrows. The protocol formalizes the evidence regime that closes the gap.

This spec defines the **identity and scope of the protocol itself**, separate from CopyClip the product. Downstream sub-projects translate this identity into canonical artifacts, repositioning, sales motion, and adoption.

## Foundational decisions

This sub-project closed six decisions through structured brainstorming on 2026-05-26. Each is load-bearing for downstream sub-projects.

| # | Decision | Choice | Rejected alternatives |
|---|---|---|---|
| 1 | **Protocol scope** | Unified suite covering four layers: Authorship Attribution, Scope Authority, Intent Governance, Cognitive Debt | Single-layer (only Auth, only Scope) / pairwise (Auth+Scope) |
| 2 | **Suite architecture** | Core (mandatory) + Extensions (optional). Core = Authorship + Scope. Extensions = Intent + Debt. | Monolithic four-section / sibling family / orthogonal profiles |
| 3 | **Name** | Provenance Protocol (PROV-1) | Quill / HAAS (Human-Agent Authorship Standard) |
| 4 | **Governance** | Commercially-controlled open spec, with explicit migration path to a Foundation (Linux Foundation AI or CNCF) post-traction | Foundation-led from day one / IETF or W3C standards-body track from day one |
| 5 | **Public artifact form** | Spec website + GitHub repo. Canonical document in repo as `SPEC.md`. Sitio generated from repo via MDX. JSON Schema machine-readable per module. | GitHub-repo-only (Anthropic MCP style) / RFC-style numbered drafts (IETF style) |
| 6 | **Tone** | Formal RFC-style (MUST / SHALL / RFC 2119 keywords) in canonical `SPEC.md`. Conversational, example-led in website overview, getting-started, and dev-facing docs. | Uniformly formal everywhere / uniformly conversational everywhere |

## Identity and positioning

**Provenance Protocol** is an open specification that standardizes how a codebase records, exposes, and verifies the **authorship, authority, and intent** of every change in environments where humans and AI agents collaborate.

- **Verb:** standardizes the authorship contract between humans and agents over codebases.
- **Object:** evidence — not code, not graphs, not behavior. The protocol governs *what counts as evidence of authorship and authority*, not what code does or how it is organized.
- **Primary buyer:** compliance, legal, security, cyber-insurance functions in organizations adopting agentic tooling.
- **Secondary buyer:** engineering leadership, DevSecOps, platform teams responsible for governance over AI-generated code.
- **Implementer audience:** any tool that writes, audits, indexes, or delivers codebases under mixed human-agent authorship — IDE assistants, CI/CD systems, code review platforms, SAST tools, compliance auditors.

**Regulatory anchoring:**

- **EU AI Act** Art. 13 (transparency obligations) and Art. 14 (human oversight)
- **SOC2** CC8.1 (change management controls)
- **ISO/IEC 42001** (AI management systems)
- **NIST AI RMF** (govern function, particularly GV-1.4 and GV-1.5)

**What the protocol is not:**

- Not a source format or AST representation
- Not a linter or static-analysis ruleset
- Not a code generation interface
- Not a codebase comprehension or onboarding system (this is Understand-Anything's category and is explicitly different)
- Not a license or copyright assertion mechanism

## Scope and architecture

PROV-1 is a unified protocol with mandatory Core and optional Extensions. Implementers declare which modules they support; compliance claims reflect those declarations.

### Core (mandatory for any PROV-Core compliance claim)

| Module | Identifier | Standardizes |
|---|---|---|
| **Authorship** | `prov.authorship` | Per-commit, per-range, per-symbol attribution: human vs agent (which agent, which session, which model, which prompt lineage), with chain-of-review tracking and revocable trust assertions |
| **Scope** | `prov.scope` | Bounded delegation: handoff packets with declared scope, do-not-touch boundaries, agent-consumable projections, lifecycle states with explicit allowed/disallowed transitions, post-change review summaries |

### Extensions (optional — implementers declare which they support)

| Module | Identifier | Standardizes |
|---|---|---|
| **Intent** | `prov.intent` | Architectural decision records, audit-proposal interface, intent-drift detection, decision-to-code bidirectional linking |
| **Debt** | `prov.debt` | Cognitive-debt scoring: agent-authored ratio with time decay, human-review staleness, dark-zone identification, remediation factor model |

### Compliance claims

An implementer MAY claim any of:

- `PROV-1 Core compliant`
- `PROV-1 Core + Intent compliant`
- `PROV-1 Core + Debt compliant`
- `PROV-1 Full compliant` (Core + both Extensions)

An implementer MUST NOT claim partial Core compliance (e.g., Authorship-only). Core is atomic. Extensions are independently selectable.

### Versioning

- **Spec-level**: strict SemVer (PROV-1.0, PROV-1.1, PROV-2.0). Minor versions are additive and backward-compatible; major versions may break.
- **Module-level**: each module versions independently under the umbrella: `prov.authorship/1.0`, `prov.scope/1.0`, `prov.intent/1.0`, `prov.debt/1.0`. A spec version pins specific module versions; e.g., PROV-1.0 pins `prov.authorship/1.0` + `prov.scope/1.0` for Core.
- **Compatibility statement**: every implementer MUST publish the exact spec and module versions they claim, in a `provenance-compliance.json` manifest at a well-known path.

## Public artifacts

| Artifact | Form | Audience | Tone |
|---|---|---|---|
| `provenance-protocol.org` | Website (Next.js + MDX, generated from repo) | Implementers, curious developers, prospective certifiers | Conversational, example-led |
| `provenance-protocol/spec` (GitHub) | Canonical repository | Implementers, contributors, RFC authors | Mixed (formal canonical doc + dev-friendly READMEs) |
| `SPEC.md` (in repo) | Canonical specification document, Markdown | Compliance officers, auditors, serious implementers | RFC 2119 formal (MUST / SHALL / REQUIRED / SHOULD / MAY) |
| `schemas/*.json` (in repo) | JSON Schema, machine-readable, per module | Validators, code-generation tools, certification automation | N/A (schema) |
| `examples/` (in repo) | Reference examples per module | Implementers learning by example | Concise, real-world |
| `provenance-validator` | CLI + library (Python + TypeScript), Apache 2.0 | Implementers (self-check), auditors (compliance verification) | N/A (tool) |
| Getting-started guide | Site page + repo README | Developers implementing for the first time | Conversational, walkthrough |
| Compliance brief | Site page + downloadable PDF | Compliance, legal counsel, procurement | Formal, regulatory-aligned, citation-friendly |
| Governance page | Site page | Standards-aware stakeholders, prospective Foundation contacts | Formal, transparent about authority and migration path |

**Repository structure:**

```
provenance-protocol/spec/
├── SPEC.md                    # canonical document, RFC-style
├── CHANGELOG.md
├── GOVERNANCE.md              # authority model + Foundation migration plan
├── CERTIFICATION.md           # certification tiers + process
├── schemas/
│   ├── authorship.json
│   ├── scope.json
│   ├── intent.json
│   └── debt.json
├── examples/
│   ├── authorship/
│   ├── scope/
│   ├── intent/
│   └── debt/
├── validator/                 # provenance-validator source
│   ├── python/
│   └── typescript/
├── docs/                      # website MDX source
│   ├── overview.mdx
│   ├── getting-started.mdx
│   ├── compliance-brief.mdx
│   └── modules/
└── README.md
```

## Governance and certification

### Authority model

**Commercially-controlled open spec**, owned by **CopyClip Inc.** (or successor entity).

- The specification text is licensed under **CC-BY 4.0**: any party may read, cite, implement, distribute, or derive from it without permission, provided attribution is preserved.
- The reference validator (`provenance-validator`) is licensed under **Apache 2.0**: any party may use, fork, modify, or embed it.
- The certification mark **"Provenance Protocol Compliant"** is filed with USPTO as a **certification mark** at launch, with equivalent filings in the EU (EUIPO), UK (UKIPO), and Japan (JPO) to follow within 12 months. Registration completes 12-18 months after filing. Use requires passing the certification process.

### Versioning process

- Changes proposed via PROV-RFC documents committed to `rfcs/` directory in the spec repo.
- Discussion in GitHub Issues; formal proposals as Pull Requests.
- Editorial authority retained by CopyClip Inc. until Foundation migration (see below). The editor merges PRs to `SPEC.md` only after RFC discussion has reached substantive consensus.
- Cadence: minor versions every quarter (additive only), major versions no more than annually.

### Certification tiers

| Tier | Description | Cost | Use of mark |
|---|---|---|---|
| **Tier 1: Self-certified** | Implementer runs `provenance-validator` against their implementation, publishes the report in their repository. | Free | May claim `PROV-1 Self-certified Core compliant` (or relevant variant). May not use the registered certification mark. |
| **Tier 2: Verified** | CopyClip Inc. audits the implementation against the spec, runs the validator, reviews the report, issues a verification certificate valid for 12 months. | Paid (revenue path) | May use the registered "Provenance Protocol Compliant — Verified" certification mark in marketing and procurement contexts. |
| **Tier 3: Audited** | Third-party certified auditor (post-Foundation migration) performs an independent audit and issues an attestation suitable for compliance reporting (SOC2, EU AI Act conformity, ISO 42001). | Paid (auditor + Foundation fee) | May use "Provenance Protocol Compliant — Audited" mark with auditor attestation. |

### Foundation migration path

The Foundation migration is the planned long-term governance state, not a near-term target. Triggers:

- ≥10 independent implementations across distinct organizations
- ≥1 enterprise customer paying for Tier 2 certification with ongoing renewals
- ≥1 supportive intent declaration from a major agentic-tooling vendor

Target Foundation: **Linux Foundation AI** or **CNCF**, selected based on which community shape better matches the protocol at migration time.

Ideal timeline: 18-24 months post-launch.

Pre-migration governance MUST publish on the governance page:

- The migration triggers (above)
- A commitment that CopyClip Inc. will donate the specification, the validator, and the certification mark to the chosen Foundation when triggers are met
- A list of current external contributors and their affiliations

This commitment is what prevents Tier 1 self-certification from feeling like vendor lock-in.

## Relationship with CopyClip

**CopyClip is repositioned as the canonical reference implementation of the Provenance Protocol.**

- CopyClip's README, marketing site, and product surface declare this relationship explicitly (refined in sub-project #3).
- CopyClip's product roadmap reorganizes existing features into three categories:
  - **PROV-1 Core** (`prov.authorship` + `prov.scope`): handoff packet generator, agent-consumable projection, lifecycle state machine, attribution tracking
  - **PROV-1 Extensions** (`prov.intent` + `prov.debt`): decision lifecycle, audit_proposal MCP tool, cognitive debt factor model
  - **CopyClip-specific value-add** (not in spec): Atlas3D, MemPalace, Reacquaintance UI, dashboard, conversational ask, marimo playground
- Versioning is independent: CopyClip v0.5.0 may implement PROV-1.0; CopyClip v1.0.0 may implement PROV-1.2; the two version streams do not synchronize.
- CopyClip becomes the first "Verified PROV-1 Full compliant" implementation, used as both proof-of-implementability and marketing reference.
- Brand separation is strict: the `provenance-protocol.org` site does not feature CopyClip beyond a "reference implementation" link. The protocol's identity is independent of any single implementer.

**Critical constraint:** the specification MUST NOT contain anything CopyClip-specific. No field name, no required behavior, no assumption, no dependency may exist only because CopyClip does it that way. Anything CopyClip does that another implementer cannot replicate belongs in the value-add layer, never in the spec.

This constraint is what makes the protocol implementable by competitors (and therefore actually a protocol, not a vendor disguise). If this constraint is violated, the protocol becomes a vendor format and the venture-scale moat collapses to "CopyClip's API."

## Success criteria (for this sub-project)

Sub-project #1 is **complete** when all of the following are true:

- [ ] The repository `provenance-protocol/spec` exists at a public GitHub organization (CopyClip-owned or new dedicated org).
- [ ] `SPEC.md` v0.1-draft is published with full structural sections for Core (`prov.authorship` + `prov.scope`); Extensions (`prov.intent` + `prov.debt`) MAY be present as section headers with `[Extension — draft pending]` placeholders.
- [ ] JSON Schema skeletons for all four modules exist under `schemas/`. Skeletons MAY contain TODO sections for fields not yet specified.
- [ ] The website `provenance-protocol.org` is live with: landing page, overview, getting-started stub, compliance-brief stub, governance page, link to the repository.
- [ ] The certification mark application is filed with USPTO. Filing date is sufficient — registration may take 12-18 months.
- [ ] CopyClip's `README.md` has a placeholder paragraph mentioning "reference implementation of the Provenance Protocol." (Full reframing is sub-project #3.)
- [ ] The versioning scheme is documented on the governance page.
- [ ] The Foundation migration commitment is publicly published on the governance page.
- [ ] The brand-separation constraint (no CopyClip-specific elements in spec) is documented in `GOVERNANCE.md` as an editorial rule.

## Non-goals (explicitly out of scope)

These items are part of downstream sub-projects and MUST NOT be conflated with sub-project #1:

- Complete protocol-conformant rewrite of CopyClip's internals (full alignment is iterative across sub-project #2)
- Comprehensive rewrite of CopyClip's README, website, and marketing surface (sub-project #3)
- Buyer pivot strategy, ICP definition, enterprise sales motion, pricing (sub-project #4)
- Enterprise product surface: RBAC, signed attestations, tamper-evident attribution ledger, compliance reporting exports (sub-project #5)
- Outbound adoption strategy: outreach to Cursor / Cline / Sourcegraph / Anthropic / GitHub, joint announcements, conference talks (sub-project #6)
- Internationalization of the website (English-only at launch)
- Reference implementations in languages beyond Python and TypeScript (these two are sufficient for the validator at launch)
- Detailed `SPEC.md` content for Extension modules (`prov.intent` + `prov.debt`) — placeholders are acceptable at this sub-project's completion
- Migration of existing CopyClip contracts (`HANDOFF_PACKET_CONTRACT.md` etc.) into the new spec — that is sub-project #2

## Open questions

These are deliberately deferred and SHOULD be resolved before or during sub-project #2:

1. **Dedicated GitHub org vs CopyClip-owned org?** A separate org (`provenance-protocol`) signals brand independence more strongly but adds operational overhead. CopyClip-owned (`sssamuelll/provenance-protocol`) is faster to launch but couples brands earlier.
2. **Should `provenance-validator` be a separate repo or live inside the spec repo?** Co-located simplifies discovery; separate repos allow independent versioning of validator vs spec.
3. **Domain acquisition timing.** `provenance-protocol.org` MUST be registered before any public mention of the project. `.com` and `.io` SHOULD also be registered defensively.
4. **Initial spec drafting authorship.** Should the v0.1 draft be authored by the user solo, by the user with a hired technical writer, or extracted-and-edited from existing CopyClip contracts? This affects timeline for sub-project #1 completion.

## References

### Existing CopyClip artifacts that become source material for `SPEC.md`

- `docs/HANDOFF_PACKET_CONTRACT.md` — source for `prov.scope`
- `docs/MCP_INTENT_AUTHORITY_SPEC.md` — source for `prov.intent` and (partially) MCP delivery binding
- `docs/COGNITIVE_DEBT_CONTRACT.md` — source for `prov.debt`
- `docs/REACQUAINTANCE_BRIEFING_CONTRACT.md` — relevant to `prov.authorship` (anchoring on last human-authored commit)
- `docs/DRIFT_CALIBRATION.md` — supplementary for `prov.intent`
- `docs/CONTEXTUAL_LEGACY_FORMAT.md` — supplementary

### Regulatory references

- Regulation (EU) 2024/1689 (EU AI Act), Art. 13 (transparency) and Art. 14 (human oversight)
- AICPA SOC2 Trust Services Criteria, CC8.1 (change management)
- ISO/IEC 42001:2023 (AI management systems)
- NIST AI Risk Management Framework 1.0 (January 2023), Govern function
- IETF RFC 2119 — Key words for use in RFCs to Indicate Requirement Levels

### Strategic source documents

- `docs/COMPETITIVE_BENCHMARK.md` (April 2026) — pre-pivot competitive analysis; predates the surfacing of Lum1104/Understand-Anything
- Brainstorming session transcript, 2026-05-26 (this document is its terminal artifact)
- Voronov meta-architecture verdict, 2026-05-26 (referenced inline under Why)
