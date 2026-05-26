# Provenance Protocol (PROV-1) — Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the Provenance Protocol v0.1-draft publicly: dedicated GitHub repo with canonical `SPEC.md`, JSON Schema skeletons, governance and certification docs, a generated website on its own domain, USPTO certification mark filing, and a placeholder reference from CopyClip's README.

**Architecture:** The protocol lives in a new public GitHub repository, separate from the CopyClip codebase. `SPEC.md` is the canonical RFC-style document (RFC 2119 keywords throughout); JSON Schemas under `schemas/` are the machine-readable contract per module. The website is a Next.js 14 (App Router) + MDX site whose content lives in `docs/` inside the same repo and which deploys to Vercel from the same git source. The USPTO certification mark filing runs as a parallel external workstream. CopyClip's repository is touched only minimally — a single paragraph in `README.md` linking to the protocol.

**Tech Stack:** GitHub (repo + Actions for deploy), Next.js 14 App Router, `@next/mdx`, Tailwind CSS, Vercel hosting, Cloudflare DNS, USPTO TEAS RF filing system.

---

## Pre-flight decisions

These resolve the four "Open questions" from the design spec. Each is a defaulted choice; the executing agent MAY revisit with the user before starting Task 1 but SHOULD NOT block on them.

| Open question | Resolution for this plan | Reversibility |
|---|---|---|
| Dedicated GitHub org vs CopyClip-owned org? | `sssamuelll/provenance-protocol` (user-owned, single org). Defer dedicated `provenance-protocol` org until Foundation-migration triggers fire. | Repo can be transferred to a new org later via GitHub's transfer flow; redirects auto-apply. |
| `provenance-validator` co-located or separate repo? | **Out of scope for this sub-project entirely.** JSON Schemas are sufficient for v0.1; the validator becomes its own sub-project (1.5) after spec stabilizes. | Trivially reversible — add validator later. |
| Domain acquisition timing | Acquire `provenance-protocol.org`, `.com`, `.io` BEFORE Task 3 (repo creation), since any public mention requires the domain to be secured. | Domains are non-reversible once acquired (sunk cost), but acquisition itself is independent of every other task. |
| Initial spec drafting authorship | Solo author (the user), extracted-and-edited from existing CopyClip contracts under `docs/`. No technical writer hired for v0.1. | Reversible — content can be rewritten later by a hired writer post-launch. |

---

## File Map

### New repository: `sssamuelll/provenance-protocol`

| File | Action | Responsibility |
|---|---|---|
| `README.md` | Create | Repo entry point; protocol overview + links to website, SPEC.md, governance |
| `SPEC.md` | Create | Canonical specification document, RFC 2119 formal |
| `CHANGELOG.md` | Create | Version history (initial entry: v0.1-draft) |
| `GOVERNANCE.md` | Create | Authority model, versioning process, Foundation migration commitment, brand-separation editorial rule |
| `CERTIFICATION.md` | Create | Three certification tiers, process, marks |
| `LICENSE-SPEC` | Create | CC-BY 4.0 text (applies to SPEC.md and docs) |
| `LICENSE-CODE` | Create | Apache 2.0 text (applies to schemas, examples, future validator) |
| `.gitignore` | Create | Node, Next.js, OS, editor artifacts |
| `schemas/authorship.json` | Create | JSON Schema for `prov.authorship` module |
| `schemas/scope.json` | Create | JSON Schema for `prov.scope` module |
| `schemas/intent.json` | Create | JSON Schema skeleton for `prov.intent` Extension (TODO sections allowed) |
| `schemas/debt.json` | Create | JSON Schema skeleton for `prov.debt` Extension (TODO sections allowed) |
| `examples/authorship/human-only-commit.json` | Create | Example: a commit entirely human-authored |
| `examples/authorship/mixed-agent-commit.json` | Create | Example: a commit with mixed human + agent authorship |
| `examples/scope/bounded-delegation-packet.json` | Create | Example: a complete handoff packet |
| `examples/scope/post-change-review.json` | Create | Example: a post-change review summary |
| `site/package.json` | Create | Next.js + MDX dependencies |
| `site/next.config.mjs` | Create | Next.js config with MDX integration |
| `site/tailwind.config.ts` | Create | Tailwind config |
| `site/tsconfig.json` | Create | TypeScript config |
| `site/app/layout.tsx` | Create | Root layout, header, footer |
| `site/app/page.tsx` | Create | Landing page (`/`) |
| `site/app/overview/page.mdx` | Create | Overview (`/overview`) |
| `site/app/getting-started/page.mdx` | Create | Getting-started stub (`/getting-started`) |
| `site/app/compliance/page.mdx` | Create | Compliance brief stub (`/compliance`) |
| `site/app/governance/page.mdx` | Create | Governance page (mirrors GOVERNANCE.md) |
| `site/app/spec/page.tsx` | Create | SPEC.md viewer (renders the canonical doc with anchor links) |
| `site/components/Header.tsx` | Create | Top nav (Overview / Getting Started / Spec / Governance / Compliance / GitHub) |
| `site/components/Footer.tsx` | Create | License notices, links |
| `site/app/globals.css` | Create | Tailwind base + custom typography |
| `.github/workflows/deploy.yml` | Create | GitHub Action that triggers Vercel deploy on push to `main` |

### Existing repository: `sssamuelll/copyclip`

| File | Action | Responsibility |
|---|---|---|
| `README.md` | Modify (lines 1-15) | Insert placeholder paragraph: "CopyClip is the reference implementation of the Provenance Protocol." Full reframing deferred to sub-project #3. |

### External (not files)

- Domain registrations: `provenance-protocol.org`, `.com`, `.io` (Cloudflare Registrar)
- GitHub repo creation: `sssamuelll/provenance-protocol`
- Vercel project: linked to `sssamuelll/provenance-protocol` repo, `site/` directory
- USPTO TEAS RF filing: certification mark for "Provenance Protocol Compliant"

---

## Source material map

This plan extracts content from existing CopyClip contracts. Each new artifact in the spec repo has a primary source:

| New artifact | Primary source in CopyClip |
|---|---|
| `SPEC.md` — `prov.scope` section | `docs/HANDOFF_PACKET_CONTRACT.md` (660 lines, near-direct translation with brand-separation cleanup) |
| `SPEC.md` — `prov.intent` placeholder | `docs/MCP_INTENT_AUTHORITY_SPEC.md` (referenced for structure only; full content in later sub-project) |
| `SPEC.md` — `prov.debt` placeholder | `docs/COGNITIVE_DEBT_CONTRACT.md` (referenced for structure only) |
| `SPEC.md` — `prov.authorship` section | Composed fresh (no direct source; references `src/copyclip/intelligence/reacquaintance.py` and `cognitive_debt.py` for the agent-author detection mechanism) |
| `schemas/scope.json` | `docs/HANDOFF_PACKET_CONTRACT.md` sections "Top-level handoff packet schema" and "Section contracts" |
| `schemas/intent.json` skeleton | `docs/MCP_INTENT_AUTHORITY_SPEC.md` MCP tool definitions |
| `schemas/debt.json` skeleton | `docs/COGNITIVE_DEBT_CONTRACT.md` factor model |
| Compliance brief (website) | `docs/COMPETITIVE_BENCHMARK.md` § "Where CopyClip is Unique" — generalized to "where PROV-1 closes regulatory gaps" |

The **brand-separation editorial rule** applies throughout extraction: every reference to "CopyClip" in source content becomes either generic protocol language or is removed entirely. No CopyClip-specific behavior, field name, or assumption survives into the spec.

---

### Task 1: Acquire domains

**Files:** none (external workstream)

**Why first:** any public mention of the project requires the domain to be secured. Acquisition is independent of every other task and runs in parallel from here on.

- [ ] **Step 1: Check availability on Cloudflare Registrar**

Open https://dash.cloudflare.com/ → Domain Registration → Search.

Search: `provenance-protocol.org`, `provenance-protocol.com`, `provenance-protocol.io`

Expected: at least `.org` available (industry convention for protocol specs). If `.org` is taken, fall back order: `provenanceprotocol.org`, `provenance.protocol`, `provenance-protocol.dev`. **If the `.org` form is taken, pause and ask the user before proceeding** — alternate naming may invalidate downstream brand work.

- [ ] **Step 2: Purchase available variants**

Purchase `.org`, `.com`, `.io` together for defensive consistency. Approximate cost: $35-55 USD total per year.

- [ ] **Step 3: Note nameservers**

Cloudflare auto-assigns Cloudflare nameservers when purchased through them. Record the assigned NS values; they will be needed for Vercel DNS pointing in Task 14.

- [ ] **Step 4: Add holding page**

For each domain, set a Page Rule that 301-redirects to `provenance-protocol.org` (the canonical). Leave `.org` as a Cloudflare placeholder ("Coming soon — Provenance Protocol v0.1-draft") until Task 14 deploys the real site.

No commit needed — external workstream.

---

### Task 2: Create the spec repository

**Files:**
- Create: repo `sssamuelll/provenance-protocol` on GitHub

- [ ] **Step 1: Create the repo via gh CLI**

Run:

```bash
gh repo create sssamuelll/provenance-protocol \
  --public \
  --description "Provenance Protocol — an open specification for human-agent authorship attribution in codebases under AI co-authorship." \
  --homepage "https://provenance-protocol.org" \
  --add-readme=false
```

Expected output: `https://github.com/sssamuelll/provenance-protocol`

- [ ] **Step 2: Clone locally**

Run:

```bash
git clone https://github.com/sssamuelll/provenance-protocol.git C:/Users/simon/Desktop/projects/provenance-protocol
```

All subsequent file paths in this plan are relative to `C:/Users/simon/Desktop/projects/provenance-protocol` unless explicitly prefixed.

- [ ] **Step 3: Set topics on the repo**

Run:

```bash
gh repo edit sssamuelll/provenance-protocol \
  --add-topic provenance \
  --add-topic protocol \
  --add-topic ai-governance \
  --add-topic ai-authorship \
  --add-topic compliance \
  --add-topic specification \
  --add-topic rfc
```

---

### Task 3: Add root scaffolding (licenses, gitignore, changelog, README stub)

**Files:**
- Create: `LICENSE-SPEC`
- Create: `LICENSE-CODE`
- Create: `.gitignore`
- Create: `CHANGELOG.md`
- Create: `README.md` (initial stub — full version comes in Task 17)

- [ ] **Step 1: Add `LICENSE-SPEC` (CC-BY 4.0)**

Copy the canonical CC-BY 4.0 text from https://creativecommons.org/licenses/by/4.0/legalcode.txt into `LICENSE-SPEC`.

Header at top of the file:

```
Provenance Protocol Specification
Copyright (c) 2026 CopyClip Inc.
Licensed under the Creative Commons Attribution 4.0 International License (CC-BY 4.0).

This license applies to SPEC.md, GOVERNANCE.md, CERTIFICATION.md, and all
prose content under docs/ and site/app/**/*.mdx.

For code artifacts (schemas/, examples/, future validator/), see LICENSE-CODE.

----
[full CC-BY 4.0 legal text follows]
```

- [ ] **Step 2: Add `LICENSE-CODE` (Apache 2.0)**

Copy the canonical Apache 2.0 text from https://www.apache.org/licenses/LICENSE-2.0.txt into `LICENSE-CODE`.

Header at top:

```
Provenance Protocol — Code Artifacts
Copyright (c) 2026 CopyClip Inc.
Licensed under the Apache License, Version 2.0.

This license applies to:
- All files under schemas/
- All files under examples/
- The provenance-validator (future addition)
- The site/ Next.js application

For specification prose (SPEC.md, GOVERNANCE.md, CERTIFICATION.md, docs/),
see LICENSE-SPEC (CC-BY 4.0).

----
[full Apache 2.0 license text follows]
```

- [ ] **Step 3: Add `.gitignore`**

Content:

```
# Node / Next.js
node_modules/
.next/
out/
.vercel/
*.tsbuildinfo

# Environment
.env
.env.local
.env.*.local

# OS
.DS_Store
Thumbs.db

# Editors
.vscode/
.idea/
*.swp
*.swo

# Logs
npm-debug.log*
yarn-debug.log*
yarn-error.log*
```

- [ ] **Step 4: Add `CHANGELOG.md`**

Content:

```markdown
# Changelog

All notable changes to the Provenance Protocol specification are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the specification adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.1-draft] — 2026-05-26

### Added
- Initial draft of the Provenance Protocol.
- Core modules: `prov.authorship/0.1`, `prov.scope/0.1`.
- Extension module placeholders: `prov.intent/0.1`, `prov.debt/0.1` (drafts pending).
- JSON Schema skeletons for all four modules.
- Governance model documented in `GOVERNANCE.md`.
- Three certification tiers documented in `CERTIFICATION.md`.
- Brand-separation editorial rule established.
```

- [ ] **Step 5: Add minimal `README.md` (stub)**

Content (full README replaces this in Task 17):

```markdown
# Provenance Protocol

An open specification for human-agent authorship attribution in codebases under AI co-authorship.

**Status:** v0.1-draft — under active development.

- [Specification](./SPEC.md)
- [Governance](./GOVERNANCE.md)
- [Certification](./CERTIFICATION.md)
- Website: https://provenance-protocol.org

## License

- Specification text: [CC-BY 4.0](./LICENSE-SPEC)
- Code artifacts (schemas, examples, validator): [Apache 2.0](./LICENSE-CODE)
```

- [ ] **Step 6: Initial commit**

Run:

```bash
git add LICENSE-SPEC LICENSE-CODE .gitignore CHANGELOG.md README.md
git commit -m "chore: initial scaffolding (licenses, gitignore, changelog, README stub)"
git push origin main
```

---

### Task 4: Write `SPEC.md` — front matter, abstract, terminology, compliance claims

**Files:**
- Create: `SPEC.md`

This task produces the structural skeleton of `SPEC.md` plus the four non-module sections that frame it. The two Core module sections come in Tasks 5 and 6.

- [ ] **Step 1: Write document front matter**

Top of `SPEC.md`:

```markdown
# Provenance Protocol — Specification

**Version:** v0.1-draft
**Date:** 2026-05-26
**Status:** Draft
**Editor:** Samuel Ballesteros (CopyClip Inc.)
**License:** CC-BY 4.0 (see [`LICENSE-SPEC`](./LICENSE-SPEC))

This document specifies version 0.1-draft of the **Provenance Protocol**, an
open standard for recording, exposing, and verifying the authorship, authority,
and intent of code changes in environments where humans and AI agents collaborate.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt)
when, and only when, they appear in all capitals, as shown here.
```

- [ ] **Step 2: Write the Table of Contents**

After the front matter, write a TOC linking to all sections that will exist by end of Task 7:

```markdown
## Table of Contents

1. [Abstract](#1-abstract)
2. [Terminology](#2-terminology)
3. [Compliance Claims](#3-compliance-claims)
4. [Module: `prov.authorship`](#4-module-provauthorship) — Core
5. [Module: `prov.scope`](#5-module-provscope) — Core
6. [Module: `prov.intent`](#6-module-provintent) — Extension (draft pending)
7. [Module: `prov.debt`](#7-module-provdebt) — Extension (draft pending)
8. [Versioning](#8-versioning)
9. [Security Considerations](#9-security-considerations)
10. [Privacy Considerations](#10-privacy-considerations)
11. [References](#11-references)
```

- [ ] **Step 3: Write Section 1 — Abstract**

Approximately 150-250 words. Required content:

- What the protocol standardizes (authorship + authority + intent over codebases).
- The asymmetry it addresses (legal responsibility vs human comprehension under agent velocity).
- The audience for the standard (tools that write, audit, indexed, or deliver codebases under mixed authorship).
- What it does not standardize (source format, AST, code generation, codebase comprehension).
- One sentence on the regulatory anchoring (EU AI Act, SOC2, ISO 42001, NIST AI RMF).

Use formal RFC tone. No marketing language. No first-person.

- [ ] **Step 4: Write Section 2 — Terminology**

Define each term in alphabetical order with an indented definition. Required terms:

- **Agent** — a non-human, non-deterministic actor that proposes or commits code changes via an automated process. An agent has an identity (model + provider + session) and is acting on behalf of one or more humans (the principal).
- **Agent-consumable projection** — the bounded subset of a packet's fields delivered to an agent for execution. Defined formally in `prov.scope`.
- **Attestation** — a cryptographically signed or verifiable claim about a specific change, identity, or authority, emitted by a Provenance-compliant implementation.
- **Authorship** — the recorded identity of the actor(s) responsible for a code change, with provenance metadata about the manner of authorship.
- **Compliant implementation** — a software system that satisfies all REQUIRED behaviors of one or more Provenance Protocol modules at a specified version, as verifiable by the protocol's certification process.
- **Core** — the set of modules MUST-implemented by any compliant implementation: `prov.authorship` and `prov.scope`.
- **Extension** — a module that is OPTIONAL for compliance but, if implemented, MUST conform to its specification. Extensions in v0.1: `prov.intent`, `prov.debt`.
- **Handoff packet** — the structured artifact delivered to an agent when work is delegated. Defined formally in `prov.scope`.
- **Implementer** — an organization or individual that produces a software system claiming Provenance Protocol compliance.
- **Module** — a named, independently-versioned component of the Provenance Protocol. Modules are `prov.authorship`, `prov.scope`, `prov.intent`, `prov.debt` in v0.1.
- **Principal** — the human (or, transitively, organization) on whose behalf an agent operates. Every agent action MUST be traceable to a principal.
- **Provenance** — the verifiable record of who authored, authorized, or intended a change, and under what constraints.

- [ ] **Step 5: Write Section 3 — Compliance Claims**

Define what an implementer is permitted to claim and the rules around it. Required content:

```markdown
## 3. Compliance Claims

An implementer MAY publicly claim one of the following compliance levels:

- `PROV-1 Core compliant` — the implementation fully satisfies both Core modules
  (`prov.authorship` and `prov.scope`) at version 1.0.
- `PROV-1 Core + Intent compliant` — Core plus the `prov.intent` Extension.
- `PROV-1 Core + Debt compliant` — Core plus the `prov.debt` Extension.
- `PROV-1 Full compliant` — Core plus both Extensions.

An implementer MUST NOT claim partial Core compliance. The Core modules are
atomic: implementing only `prov.authorship` without `prov.scope` (or vice versa)
is not a permitted compliance level.

An implementer MUST publish, at a stable well-known path within their distribution
(`/.well-known/provenance-compliance.json` for HTTP-accessible implementations,
or `provenance-compliance.json` at the root of distributable packages), a manifest
declaring:

- The exact specification version (e.g., `PROV-1.0`).
- The exact module versions implemented (e.g., `prov.authorship/1.0`,
  `prov.scope/1.0`).
- The compliance level claimed.
- The certification tier (`self-certified`, `verified`, or `audited`).
- A URL to the implementer's compliance report (REQUIRED for `verified` and
  `audited` tiers).

The schema for `provenance-compliance.json` is defined in
[`schemas/compliance-manifest.json`](./schemas/compliance-manifest.json).

The certification process, mark usage rules, and tier definitions are documented
in [`CERTIFICATION.md`](./CERTIFICATION.md).
```

(Note: `schemas/compliance-manifest.json` will be added in Task 8.)

- [ ] **Step 6: Commit**

Run:

```bash
git add SPEC.md
git commit -m "spec: add SPEC.md front matter, abstract, terminology, compliance claims"
git push origin main
```

---

### Task 5: Write `SPEC.md` Section 4 — `prov.authorship` (Core)

**Files:**
- Modify: `SPEC.md` (append Section 4)

This is the first Core module. It defines how an implementation records WHO authored each change with what manner of authorship. There is no direct source in CopyClip's existing contracts — the existing `agent_authored_ratio` factor (in `src/copyclip/intelligence/cognitive_debt.py`) is a *consumer* of attribution data, not a definition of the attribution format. This section must define the format from first principles.

**Section length target:** 600-900 words.

- [ ] **Step 1: Write the section header and Purpose subsection**

```markdown
## 4. Module: `prov.authorship` — Core

**Module version:** 0.1
**Status:** Core (REQUIRED for any PROV-1 compliance claim)
**Conformance schema:** [`schemas/authorship.json`](./schemas/authorship.json)

### 4.1 Purpose

The `prov.authorship` module standardizes the recording and exposure of
authorship metadata for code changes. A compliant implementation MUST be able
to emit, store, and surface, for every commit or proposed change:

- The set of human principals on whose behalf the change was made.
- The set of agents (if any) that produced any portion of the change.
- The relationship between agents and principals (delegation chain).
- The manner of authorship for each portion of the change (human-typed,
  agent-generated, agent-generated-then-human-reviewed, agent-generated-then-
  human-edited).

This metadata is the foundation on which `prov.scope`, `prov.intent`, and
`prov.debt` operate. Without it, the other modules cannot function.
```

- [ ] **Step 2: Write Section 4.2 — Authorship Record Structure**

Define the data structure that every implementation MUST be able to emit. Use a JSON example with field-by-field explanation:

```markdown
### 4.2 Authorship Record Structure

An **authorship record** is the canonical structure describing the authorship
of a single commit or change-proposal. A compliant implementation MUST be able
to produce a record conforming to the following structure:

```json
{
  "record_id": "ar_2026_05_26_001",
  "subject": {
    "kind": "commit",
    "ref": "abc123def456",
    "scope": {
      "files": ["src/auth/login.py"],
      "byte_range": null
    }
  },
  "principals": [
    {
      "principal_id": "human:samuel@example.com",
      "kind": "human",
      "display_name": "Samuel Ballesteros"
    }
  ],
  "agents": [
    {
      "agent_id": "agent:claude-opus-4-7/session-xyz",
      "kind": "agent",
      "provider": "anthropic",
      "model": "claude-opus-4-7",
      "session_ref": "session-xyz",
      "principal_ref": "human:samuel@example.com"
    }
  ],
  "authorship_segments": [
    {
      "segment_id": "seg_001",
      "byte_range": [0, 1024],
      "manner": "agent_generated",
      "author_ref": "agent:claude-opus-4-7/session-xyz",
      "reviewed_by": null,
      "edited_by": null
    },
    {
      "segment_id": "seg_002",
      "byte_range": [1024, 1500],
      "manner": "agent_generated_human_edited",
      "author_ref": "agent:claude-opus-4-7/session-xyz",
      "reviewed_by": "human:samuel@example.com",
      "edited_by": "human:samuel@example.com"
    }
  ],
  "recorded_at": "2026-05-26T12:34:56Z",
  "implementation": {
    "name": "copyclip",
    "version": "0.5.0"
  }
}
```

Field requirements:

- `record_id` — REQUIRED. Implementation-unique identifier. MUST be stable across re-emissions.
- `subject` — REQUIRED. Identifies what the record describes.
  - `subject.kind` — REQUIRED. One of `commit`, `proposed_change`, `file_state`.
  - `subject.ref` — REQUIRED. Implementation-specific reference (commit SHA, proposal ID, etc.).
  - `subject.scope` — REQUIRED. Identifies the byte-extent the record covers.
- `principals` — REQUIRED. Array of one or more principals. MUST contain at
  least one human principal unless `agents` is empty.
- `agents` — REQUIRED (MAY be empty array). Each agent MUST reference a principal.
- `authorship_segments` — REQUIRED. Non-overlapping byte ranges covering the
  subject's scope. Every byte MUST be attributable to exactly one segment.
- `authorship_segments[].manner` — REQUIRED. One of: `human_typed`, `agent_generated`,
  `agent_generated_human_reviewed`, `agent_generated_human_edited`, `mixed`.
- `recorded_at` — REQUIRED. ISO 8601 timestamp with timezone.
- `implementation` — REQUIRED. Identifies the compliant implementation emitting the record.
```

- [ ] **Step 3: Write Section 4.3 — Delegation Chain**

```markdown
### 4.3 Delegation Chain

When an agent's work was triggered by another agent (rather than directly by
a human principal), implementations MUST record the full delegation chain.
Each link in the chain MUST identify both the delegator and the delegatee,
and the chain MUST terminate at a human principal.

A delegation chain MUST NOT contain cycles. An implementation MUST reject
attempts to record cyclic chains.

Example:

```json
{
  "agents": [
    {
      "agent_id": "agent:orchestrator/session-abc",
      "principal_ref": "human:samuel@example.com",
      "delegated_to": ["agent:claude-opus-4-7/session-xyz"]
    },
    {
      "agent_id": "agent:claude-opus-4-7/session-xyz",
      "principal_ref": "agent:orchestrator/session-abc"
    }
  ]
}
```

The transitive principal of `agent:claude-opus-4-7/session-xyz` in this
example is `human:samuel@example.com`. Implementations MUST be able to
compute and expose the transitive principal for any agent in any chain.
```

- [ ] **Step 4: Write Section 4.4 — Revocable Trust**

```markdown
### 4.4 Revocable Trust

A principal MAY at any time revoke prior trust assertions about an agent's
authorship. Revocation MUST be recorded as a new authorship record (not by
mutation of the original) and MUST include:

- A reference to the revoked record.
- The reason (free-text, REQUIRED).
- A timestamp.
- The principal performing the revocation.

A revocation does NOT delete the original record. It marks the original as
revoked and chains forward. Auditors and verifiers MUST treat revoked records
as no longer reflecting the principal's current trust state but MUST preserve
them for historical auditability.

Implementations MUST expose revocation status via a `revocation` field on
queries against an authorship record:

```json
{
  "record_id": "ar_2026_05_26_001",
  "revocation": {
    "revoked": true,
    "revoked_by": "human:samuel@example.com",
    "revoked_at": "2026-05-27T09:00:00Z",
    "reason": "Discovered the agent fabricated test results.",
    "revocation_record_id": "ar_2026_05_27_004"
  },
  "...": "..."
}
```
```

- [ ] **Step 5: Write Section 4.5 — Verification**

```markdown
### 4.5 Verification

Compliant implementations MUST provide a verification interface that, given
an authorship record, returns one of:

- `valid` — the record's structure conforms to this specification and its
  internal references resolve.
- `structural_invalid` — the record's structure violates this specification.
- `unresolvable_references` — one or more references in the record cannot be
  resolved (e.g., a `principal_ref` not present in `principals`).
- `revoked` — the record is valid but has been revoked.

The verification interface MAY be exposed via any transport (HTTP API,
command-line tool, library function). The protocol does not mandate a
transport; it mandates the verification semantics.
```

- [ ] **Step 6: Write Section 4.6 — Conformance Checklist**

```markdown
### 4.6 Conformance Checklist

To claim `prov.authorship/0.1` conformance, an implementation MUST:

1. Emit authorship records conforming to §4.2 for every commit or
   proposed change it processes.
2. Support all five `manner` values defined in §4.2.
3. Record and expose delegation chains per §4.3, including transitive
   principal computation.
4. Reject cyclic delegation chains.
5. Support revocable trust per §4.4, preserving revoked records for audit.
6. Provide a verification interface per §4.5.
7. Validate records against [`schemas/authorship.json`](./schemas/authorship.json).
```

- [ ] **Step 7: Commit**

Run:

```bash
git add SPEC.md
git commit -m "spec: add Section 4 — prov.authorship Core module"
git push origin main
```

---

### Task 6: Write `SPEC.md` Section 5 — `prov.scope` (Core)

**Files:**
- Modify: `SPEC.md` (append Section 5)

This is the second Core module. Primary source: `C:/Users/simon/Desktop/projects/copyclip/docs/HANDOFF_PACKET_CONTRACT.md` — a 660-line contract that is already protocol-shaped. This task converts it to RFC 2119 formal style and removes CopyClip-specific references.

**Section length target:** 1200-2000 words (longest section in v0.1).

- [ ] **Step 1: Read the source contract**

Open and read the entire content of:

```
C:/Users/simon/Desktop/projects/copyclip/docs/HANDOFF_PACKET_CONTRACT.md
```

Note its sections and lifecycle states. This is the source material.

- [ ] **Step 2: Write the section header and Purpose subsection**

```markdown
## 5. Module: `prov.scope` — Core

**Module version:** 0.1
**Status:** Core (REQUIRED for any PROV-1 compliance claim)
**Conformance schema:** [`schemas/scope.json`](./schemas/scope.json)

### 5.1 Purpose

The `prov.scope` module standardizes the bounded delegation of work to agents.
Where `prov.authorship` records what happened, `prov.scope` defines what an
agent was permitted to do *before* it acted.

A compliant implementation MUST be able to compose, deliver, and audit
**handoff packets**: structured artifacts that declare the scope, constraints,
and review criteria of a unit of work delegated to an agent.

The module also defines **review summaries**: post-change comparisons between
what the agent did and what the packet permitted.
```

- [ ] **Step 3: Write Section 5.2 — Handoff Packet Structure**

Extract from source contract § "Top-level handoff packet schema" and § "Section contracts". Convert MUST/SHOULD/MAY keywords throughout. Remove CopyClip-specific references (replace `"project": "copyclip"` examples with `"project": "<implementer-defined>"`).

Include the top-level JSON skeleton and per-section requirements for:

- `meta` (packet_id, packet_version, state, timestamps, project, created_by, approved_by, delegation_target, source_task)
- `objective` (summary, task_type, intent, success_definition)
- `scope` (declared_files, declared_modules, supporting_files, out_of_scope_modules, scope_rationale)
- `constraints` (constraint_id, type, summary, source, severity, origin)
- `do_not_touch` (target, reason, severity, source)
- `relevant_decisions` (id, title, status, why_relevant, linked_targets, evidence)
- `risk_dark_zones` (risk_id, area, kind, severity, score, why_it_matters, recommended_guardrail, evidence)
- `questions_to_clarify` (question, priority, blocking, derived_from, resolution)
- `acceptance_criteria` (id, summary, check_type)
- `agent_consumable_packet` (objective, allowed_write_scope, read_scope, constraints, do_not_touch, questions_to_clarify, acceptance_criteria)
- `review_contract` (expected_review_type, compare_scope_against_touched_files, check_decision_conflicts, check_dark_zone_entry, check_blast_radius, required_human_questions)
- `evidence_index` (id, type, label, ref)

Each subsection MUST include:
- Purpose statement (1-2 sentences)
- Shape (JSON example)
- Field-by-field requirements with RFC 2119 keywords

- [ ] **Step 4: Write Section 5.3 — Lifecycle States**

Extract from source contract § "Lifecycle states" and § "State transition rules". Required content:

- **Packet lifecycle**: `draft`, `ready_for_review`, `approved_for_handoff`, `delegated`, `change_received`, `reviewed`, `superseded`, `cancelled`. Document allowed and disallowed transitions in a state-transition table.
- **Execution lifecycle**: `queued`, `running`, `completed`, `failed`, `abandoned`. Document allowed transitions.
- **Review lifecycle**: `not_started`, `generated`, `human_reviewed`, `accepted`, `changes_requested`. Document allowed transitions.
- **Human gate expectations**: which transitions REQUIRE explicit human approval.

For each state machine, present allowed transitions as a Markdown table:

```markdown
| From | To | Conditions |
|---|---|---|
| `draft` | `ready_for_review` | None |
| `ready_for_review` | `approved_for_handoff` | REQUIRES human approval |
| `ready_for_review` | `draft` | None |
| ... | ... | ... |
```

- [ ] **Step 5: Write Section 5.4 — Agent-Consumable Projection**

This is the security-critical part. From source contract § "Human-only vs agent-consumable sections" and § "MCP delivery".

```markdown
### 5.4 Agent-Consumable Projection

A handoff packet contains both human-facing data (notes, full evidence index,
approval metadata) and agent-facing data (objective, allowed scope, constraints
the agent must respect). When a packet is delivered to an agent, the
implementation MUST emit only the **agent-consumable projection**.

The projection MUST include:

- `objective` (verbatim)
- `agent_consumable_packet` (verbatim)
- A flat list of high-severity constraints
- A flat list of unresolved blocking questions
- A flat list of acceptance criteria
- An `agent_ready` boolean and a `warnings` array

The projection MUST NOT include:

- `evidence_index` (full)
- `notes`
- `meta.approved_by`
- Reviewer-only annotations
- Internal scoring or factor breakdowns
- The full `relevant_decisions` array (only `why_relevant` summaries MAY appear)

The rationale: an agent that can read the human-only data may bypass the
declared scope by reasoning over context that was never intended to constrain
or guide its behavior.

An implementation MUST refuse to emit a projection for any packet in a state
outside `approved_for_handoff` or `delegated`, except as `agent_ready: false`
with explicit `warnings`.
```

- [ ] **Step 6: Write Section 5.5 — Review Summary Structure**

Extract from source contract § "Post-change review summary contract". Structure:

```markdown
### 5.5 Review Summary Structure

After delegated work returns, a compliant implementation MUST produce a
**review summary** that compares the change against the packet.

[JSON skeleton with all fields: meta, result, scope_check, decision_conflicts,
blast_radius, dark_zone_entry, unresolved_questions, review_evidence]

[Per-field requirements with RFC 2119 keywords]

A review summary MUST be append-only. To revise a review, an implementation
MUST emit a new review summary referencing the prior one; mutation of an
existing summary is not permitted.
```

- [ ] **Step 7: Write Section 5.6 — Conformance Checklist**

```markdown
### 5.6 Conformance Checklist

To claim `prov.scope/0.1` conformance, an implementation MUST:

1. Compose handoff packets conforming to §5.2.
2. Enforce the lifecycle states and transitions defined in §5.3.
3. Require human approval at the gates documented in §5.3.
4. Emit agent-consumable projections conforming to §5.4 for any packet
   delivery to an agent.
5. Refuse to emit projections for packets not in `approved_for_handoff` or
   `delegated`, except as `agent_ready: false` with warnings.
6. Produce review summaries conforming to §5.5 for delegated changes.
7. Treat review summaries as append-only.
8. Validate packets and summaries against [`schemas/scope.json`](./schemas/scope.json).
```

- [ ] **Step 8: Commit**

Run:

```bash
git add SPEC.md
git commit -m "spec: add Section 5 — prov.scope Core module"
git push origin main
```

---

### Task 7: Write `SPEC.md` Sections 6-11 — Extension placeholders + closing sections

**Files:**
- Modify: `SPEC.md` (append Sections 6 through 11)

- [ ] **Step 1: Write Section 6 — `prov.intent` placeholder**

```markdown
## 6. Module: `prov.intent` — Extension (draft pending)

**Module version:** 0.1 (placeholder)
**Status:** Extension (OPTIONAL — implementations MAY claim Core compliance without supporting this module)
**Conformance schema:** [`schemas/intent.json`](./schemas/intent.json) (skeleton, draft pending)

### 6.1 Purpose (preview)

The `prov.intent` module will standardize the recording and verification of
architectural decisions, the audit-proposal interface (an agent submits a
proposed change and receives an APPROVED / REJECTED decision against recorded
decisions), and intent-drift detection (measuring divergence between recorded
intent and committed implementation).

### 6.2 Status

The full specification of `prov.intent` is **draft pending** and will be
published in a future PROV-1 minor version. Implementers SHOULD NOT claim
`PROV-1 Core + Intent compliant` against this version.

The placeholder is present in v0.1-draft to (a) reserve the module identifier
and namespace, (b) signal the planned extension shape to implementers, and
(c) hold the corresponding schema slot.

The draft will be derived from existing prior art in the reference
implementation; see https://github.com/sssamuelll/copyclip for context.
```

- [ ] **Step 2: Write Section 7 — `prov.debt` placeholder**

Same structure as Section 6, but for `prov.debt`. Purpose preview:

```markdown
### 7.1 Purpose (preview)

The `prov.debt` module will standardize cognitive-debt scoring: the
quantification of code regions that have drifted from the principal's
comprehension. The factor model includes agent-authored ratio with time decay,
human-review staleness, missing-decision linkage, and dark-zone identification
with remediation recommendations.
```

- [ ] **Step 3: Write Section 8 — Versioning**

```markdown
## 8. Versioning

The Provenance Protocol uses two levels of versioning:

### 8.1 Specification version

The specification as a whole follows [Semantic Versioning 2.0](https://semver.org/):

- PATCH (`PROV-1.0.1`): typo and clarification fixes; no semantic change.
- MINOR (`PROV-1.1`): additive changes (new modules, new optional fields,
  new compliance levels). Backward-compatible with implementations of the
  prior MINOR.
- MAJOR (`PROV-2.0`): breaking changes. Implementations of `PROV-1.x` are
  NOT automatically compliant with `PROV-2.0`.

### 8.2 Module version

Each module versions independently:

- `prov.authorship/MAJOR.MINOR`
- `prov.scope/MAJOR.MINOR`
- `prov.intent/MAJOR.MINOR`
- `prov.debt/MAJOR.MINOR`

A specification version pins specific module versions. For example,
`PROV-1.0` pins:

- `prov.authorship/1.0`
- `prov.scope/1.0`
- `prov.intent/1.0` (placeholder — actual module pinning deferred to first
  PROV-1.x where `prov.intent` exits placeholder status)
- `prov.debt/1.0` (placeholder — same as above)

Implementers MUST publish, in their `provenance-compliance.json` manifest,
the exact specification version they target and the exact module versions
they implement.

### 8.3 Versioning process

Changes to the specification proceed via PROV-RFC documents committed to
[`rfcs/`](./rfcs/) in this repository. The process is documented in
[`GOVERNANCE.md`](./GOVERNANCE.md).
```

- [ ] **Step 4: Write Section 9 — Security Considerations**

```markdown
## 9. Security Considerations

### 9.1 Projection bypass

The agent-consumable projection (§5.4) is the primary security boundary
between an agent and the human-only data in a packet. Implementations MUST
ensure no path exists by which an agent can request, infer, or reconstruct
the human-only fields from the projection.

Implementations SHOULD assume the agent is adversarial with respect to
projection boundaries. The projection MUST be the only data the agent
receives during delegation.

### 9.2 Attestation forgery

If a compliant implementation emits cryptographically signed attestations,
the signing key MUST be controlled by the implementation, not by any agent.
Agents MUST NOT be granted signing capability over authorship records.

### 9.3 Revocation race

Revocations (§4.4) propagate by emission of new authorship records. Verifiers
MUST treat revocation as eventually-consistent and SHOULD provide a "verified
at time T" query that respects the revocation history at that timestamp.

### 9.4 Compliance manifest spoofing

The `provenance-compliance.json` manifest (§3) is self-declared by the
implementer. A self-certified manifest MUST NOT be relied upon for compliance
attestations to third parties; only `verified` or `audited` tiers carry
third-party trust.
```

- [ ] **Step 5: Write Section 10 — Privacy Considerations**

```markdown
## 10. Privacy Considerations

### 10.1 Principal identifiers

Principal identifiers (e.g., `human:samuel@example.com`) MAY contain
personal data. Implementations MUST allow principals to use opaque
pseudonyms (e.g., `human:opaque-id-7f3a`) instead of identifiable strings
where required by the deployment context (GDPR, CCPA, employee privacy
agreements).

### 10.2 Authorship granularity

Per-byte authorship attribution (§4.2) reveals fine-grained editing patterns
that MAY be considered surveillance in some employment contexts.
Implementations MUST allow a "coarse mode" that records authorship only at
commit granularity (rather than byte-range) when the deployment context
requires it. A coarse-mode implementation is still PROV-1 Core compliant
provided it documents the chosen granularity in its `provenance-compliance.json`.

### 10.3 Cross-organization disclosure

Authorship records that span organizations (e.g., a contributor commits to
an open-source project on behalf of a different employer) MUST NOT leak the
principal's employer identity unless the principal explicitly opts in.
```

- [ ] **Step 6: Write Section 11 — References**

```markdown
## 11. References

### 11.1 Normative

- RFC 2119, "Key words for use in RFCs to Indicate Requirement Levels", March 1997.
- ISO 8601:2004, "Data elements and interchange formats — Information interchange — Representation of dates and times".
- IETF RFC 8259, "The JavaScript Object Notation (JSON) Data Interchange Format", December 2017.
- JSON Schema draft 2020-12, https://json-schema.org/draft/2020-12/schema

### 11.2 Informative

- Regulation (EU) 2024/1689 (EU AI Act).
- AICPA Trust Services Criteria, SOC2.
- ISO/IEC 42001:2023, "Information technology — Artificial intelligence — Management system".
- NIST AI Risk Management Framework 1.0, January 2023.
- W3C PROV Data Model, https://www.w3.org/TR/prov-dm/
```

- [ ] **Step 7: Commit**

Run:

```bash
git add SPEC.md
git commit -m "spec: add Sections 6-11 — extension placeholders, versioning, security, privacy, references"
git push origin main
```

---

### Task 8: Write JSON Schema skeletons for all four modules

**Files:**
- Create: `schemas/authorship.json`
- Create: `schemas/scope.json`
- Create: `schemas/intent.json`
- Create: `schemas/debt.json`
- Create: `schemas/compliance-manifest.json`

Each schema uses JSON Schema draft 2020-12.

- [ ] **Step 1: Write `schemas/authorship.json`**

Translate the structure in §4.2 of `SPEC.md` to a complete JSON Schema. Required at minimum:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://provenance-protocol.org/schemas/authorship/0.1",
  "title": "Provenance Authorship Record",
  "description": "An authorship record per prov.authorship module of the Provenance Protocol v0.1-draft.",
  "type": "object",
  "required": ["record_id", "subject", "principals", "agents", "authorship_segments", "recorded_at", "implementation"],
  "properties": {
    "record_id": { "type": "string", "minLength": 1 },
    "subject": {
      "type": "object",
      "required": ["kind", "ref", "scope"],
      "properties": {
        "kind": { "enum": ["commit", "proposed_change", "file_state"] },
        "ref": { "type": "string" },
        "scope": {
          "type": "object",
          "required": ["files"],
          "properties": {
            "files": { "type": "array", "items": { "type": "string" } },
            "byte_range": {
              "anyOf": [
                { "type": "null" },
                { "type": "array", "items": { "type": "integer" }, "minItems": 2, "maxItems": 2 }
              ]
            }
          }
        }
      }
    },
    "principals": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["principal_id", "kind"],
        "properties": {
          "principal_id": { "type": "string" },
          "kind": { "enum": ["human", "organization"] },
          "display_name": { "type": "string" }
        }
      }
    },
    "agents": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["agent_id", "kind", "principal_ref"],
        "properties": {
          "agent_id": { "type": "string" },
          "kind": { "const": "agent" },
          "provider": { "type": "string" },
          "model": { "type": "string" },
          "session_ref": { "type": "string" },
          "principal_ref": { "type": "string" },
          "delegated_to": { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "authorship_segments": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["segment_id", "byte_range", "manner", "author_ref"],
        "properties": {
          "segment_id": { "type": "string" },
          "byte_range": { "type": "array", "items": { "type": "integer" }, "minItems": 2, "maxItems": 2 },
          "manner": { "enum": ["human_typed", "agent_generated", "agent_generated_human_reviewed", "agent_generated_human_edited", "mixed"] },
          "author_ref": { "type": "string" },
          "reviewed_by": { "anyOf": [{ "type": "null" }, { "type": "string" }] },
          "edited_by": { "anyOf": [{ "type": "null" }, { "type": "string" }] }
        }
      }
    },
    "recorded_at": { "type": "string", "format": "date-time" },
    "implementation": {
      "type": "object",
      "required": ["name", "version"],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" }
      }
    },
    "revocation": {
      "type": "object",
      "required": ["revoked", "revoked_by", "revoked_at", "reason", "revocation_record_id"],
      "properties": {
        "revoked": { "const": true },
        "revoked_by": { "type": "string" },
        "revoked_at": { "type": "string", "format": "date-time" },
        "reason": { "type": "string", "minLength": 1 },
        "revocation_record_id": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 2: Write `schemas/scope.json`**

Translate the full handoff packet structure from §5.2-5.5 of `SPEC.md` (and the source `HANDOFF_PACKET_CONTRACT.md`) into JSON Schema. This will be the longest schema file (~300-400 lines of JSON).

Required top-level: `meta`, `objective`, `scope`, `constraints`, `do_not_touch`, `relevant_decisions`, `risk_dark_zones`, `questions_to_clarify`, `acceptance_criteria`, `agent_consumable_packet`, `review_contract`, `evidence_index`, `notes`.

For each, translate the field-level requirements from `SPEC.md` §5.2 into JSON Schema constraints. Use `enum` for fixed value lists (lifecycle states, severity levels, origin types). Use `required` arrays to enforce mandatory fields. Use `$ref` to share common types (e.g., evidence reference shape).

- [ ] **Step 3: Write `schemas/intent.json` skeleton**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://provenance-protocol.org/schemas/intent/0.1",
  "title": "Provenance Intent Record (skeleton — draft pending)",
  "description": "Placeholder schema for the prov.intent Extension module. Full structure to be defined in a future PROV-1.x version.",
  "type": "object",
  "x-status": "draft-pending",
  "x-note": "This schema is a placeholder reserving the namespace and identifier. Do not implement against it for compliance claims."
}
```

- [ ] **Step 4: Write `schemas/debt.json` skeleton**

Same shape as `intent.json` but for `prov.debt`. Include `x-status: draft-pending` and the same warning.

- [ ] **Step 5: Write `schemas/compliance-manifest.json`**

The schema referenced in `SPEC.md` §3:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://provenance-protocol.org/schemas/compliance-manifest/0.1",
  "title": "Provenance Compliance Manifest",
  "description": "Self-published manifest declaring an implementation's Provenance Protocol compliance.",
  "type": "object",
  "required": ["specification_version", "modules", "compliance_level", "certification_tier"],
  "properties": {
    "specification_version": {
      "type": "string",
      "pattern": "^PROV-\\d+\\.\\d+(\\.\\d+)?(-draft)?$"
    },
    "modules": {
      "type": "object",
      "required": ["prov.authorship", "prov.scope"],
      "properties": {
        "prov.authorship": { "type": "string", "pattern": "^\\d+\\.\\d+$" },
        "prov.scope": { "type": "string", "pattern": "^\\d+\\.\\d+$" },
        "prov.intent": { "type": "string", "pattern": "^\\d+\\.\\d+$" },
        "prov.debt": { "type": "string", "pattern": "^\\d+\\.\\d+$" }
      }
    },
    "compliance_level": {
      "enum": ["PROV-1 Core compliant", "PROV-1 Core + Intent compliant", "PROV-1 Core + Debt compliant", "PROV-1 Full compliant"]
    },
    "certification_tier": {
      "enum": ["self-certified", "verified", "audited"]
    },
    "compliance_report_url": {
      "type": "string",
      "format": "uri"
    },
    "implementation": {
      "type": "object",
      "required": ["name", "version"],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" }
      }
    }
  },
  "allOf": [
    {
      "if": { "properties": { "certification_tier": { "enum": ["verified", "audited"] } } },
      "then": { "required": ["compliance_report_url"] }
    }
  ]
}
```

- [ ] **Step 6: Validate all schemas parse**

Run (in repo root):

```bash
npx --yes ajv-cli compile -s schemas/authorship.json
npx --yes ajv-cli compile -s schemas/scope.json
npx --yes ajv-cli compile -s schemas/intent.json
npx --yes ajv-cli compile -s schemas/debt.json
npx --yes ajv-cli compile -s schemas/compliance-manifest.json
```

Expected: each prints `schema <name> is valid` with no errors.

- [ ] **Step 7: Commit**

Run:

```bash
git add schemas/
git commit -m "spec: add JSON Schemas for all four modules and compliance manifest"
git push origin main
```

---

### Task 9: Write Core examples

**Files:**
- Create: `examples/authorship/human-only-commit.json`
- Create: `examples/authorship/mixed-agent-commit.json`
- Create: `examples/authorship/delegation-chain.json`
- Create: `examples/scope/bounded-delegation-packet.json`
- Create: `examples/scope/post-change-review.json`
- Create: `examples/compliance-manifest-example.json`

Each example MUST validate against its corresponding schema.

- [ ] **Step 1: Write `examples/authorship/human-only-commit.json`**

A complete, valid authorship record for a commit entirely human-authored:

```json
{
  "record_id": "ar_2026_05_26_001",
  "subject": {
    "kind": "commit",
    "ref": "a1b2c3d4e5f6789012345678901234567890abcd",
    "scope": {
      "files": ["README.md"],
      "byte_range": null
    }
  },
  "principals": [
    {
      "principal_id": "human:alice@example.com",
      "kind": "human",
      "display_name": "Alice Johnson"
    }
  ],
  "agents": [],
  "authorship_segments": [
    {
      "segment_id": "seg_001",
      "byte_range": [0, 4521],
      "manner": "human_typed",
      "author_ref": "human:alice@example.com",
      "reviewed_by": null,
      "edited_by": null
    }
  ],
  "recorded_at": "2026-05-26T10:00:00Z",
  "implementation": {
    "name": "example-implementation",
    "version": "0.1.0"
  }
}
```

- [ ] **Step 2: Write `examples/authorship/mixed-agent-commit.json`**

A commit where an agent wrote a function and a human reviewed-and-edited the surrounding code. Include all five `manner` values where applicable; demonstrate the full agent metadata structure.

- [ ] **Step 3: Write `examples/authorship/delegation-chain.json`**

An authorship record where an orchestrator agent delegated to a sub-agent. Demonstrate the `delegated_to` field and the transitive principal resolution.

- [ ] **Step 4: Write `examples/scope/bounded-delegation-packet.json`**

A full handoff packet in `approved_for_handoff` state with realistic scope, constraints, and questions. Use `[]` and `null` where appropriate; do not omit required fields.

- [ ] **Step 5: Write `examples/scope/post-change-review.json`**

A review summary showing one out-of-scope touch and one decision conflict; verdict `changes_requested`.

- [ ] **Step 6: Write `examples/compliance-manifest-example.json`**

An example `provenance-compliance.json` for a hypothetical `PROV-1 Full compliant` implementation at the `verified` tier.

- [ ] **Step 7: Validate every example against its schema**

Run:

```bash
npx --yes ajv-cli validate -s schemas/authorship.json -d examples/authorship/*.json
npx --yes ajv-cli validate -s schemas/scope.json -d examples/scope/*.json
npx --yes ajv-cli validate -s schemas/compliance-manifest.json -d examples/compliance-manifest-example.json
```

Expected: every example reports `valid`.

- [ ] **Step 8: Commit**

Run:

```bash
git add examples/
git commit -m "spec: add validated examples for prov.authorship, prov.scope, compliance manifest"
git push origin main
```

---

### Task 10: Write `GOVERNANCE.md`

**Files:**
- Create: `GOVERNANCE.md`

- [ ] **Step 1: Write the full document**

Content (final, not a placeholder):

```markdown
# Governance

## Authority

The **Provenance Protocol** specification is currently maintained by
**CopyClip Inc.** as the editorial authority. The specification text is
licensed under [CC-BY 4.0](./LICENSE-SPEC); the schemas and reference code
are licensed under [Apache 2.0](./LICENSE-CODE).

The certification mark "Provenance Protocol Compliant" is filed with the
USPTO and equivalent registries as a **certification mark**. Use of the mark
is governed by [`CERTIFICATION.md`](./CERTIFICATION.md).

## Versioning process

Changes to the specification proceed via **PROV-RFC** documents.

1. Anyone MAY propose a change by opening a Pull Request adding a new
   document under `rfcs/`. The document follows the [PROV-RFC template](./rfcs/TEMPLATE.md).
2. Discussion takes place in GitHub Issues and PR review threads.
3. The editor (currently CopyClip Inc.) merges a PROV-RFC when substantive
   community discussion has concluded and consensus has been reached.
4. Merged PROV-RFCs are folded into `SPEC.md` in the next MINOR or MAJOR
   release as appropriate.

Cadence:

- PATCH releases: as needed (typo fixes, clarifications).
- MINOR releases: no more frequently than quarterly.
- MAJOR releases: no more frequently than annually.

## Editorial rules

### Brand-separation rule

The specification MUST NOT contain any element (field name, required behavior,
identifier, assumption) that exists solely because the reference implementation
(CopyClip) does it that way. Anything CopyClip does that another implementer
cannot reasonably replicate belongs in CopyClip's product surface, not in the
specification.

This rule is enforced at PR review time. PRs that violate it MUST be revised
or rejected.

### No implementer favoritism

The specification MUST be implementable by any party — including direct
competitors of CopyClip Inc. — without recourse to CopyClip's private code,
data, or infrastructure. PRs that introduce dependencies on CopyClip-private
components MUST be revised or rejected.

### RFC 2119 keyword discipline

Normative requirements MUST use RFC 2119 keywords in ALL CAPS. Non-normative
prose MUST NOT use RFC 2119 keywords; it MAY use the same words in lowercase
without normative meaning.

## Foundation migration commitment

CopyClip Inc. commits to transferring editorial authority over the
specification, the schemas, the validator (when published), and the
certification mark to a vendor-neutral foundation when the following triggers
are met:

- At least 10 independent implementations across distinct organizations
  publish compliant `provenance-compliance.json` manifests.
- At least one enterprise customer pays for the Verified certification tier
  with at least one annual renewal.
- At least one major agentic-tooling vendor publicly declares intent to
  implement the protocol.

The target foundation is **Linux Foundation AI** or **CNCF**, selected at
migration time based on which community shape better matches the protocol's
implementer base.

Ideal timeline: 18-24 months from v0.1-draft publication.

This commitment is public and irrevocable: the only conditions are the
triggers above, and CopyClip Inc. MAY NOT add new conditions retroactively.

## Current contributors

| Contributor | Affiliation | Role |
|---|---|---|
| Samuel Ballesteros | CopyClip Inc. | Editor, primary author |

(External contributors will be listed here as PROV-RFCs are merged.)
```

- [ ] **Step 2: Commit**

Run:

```bash
git add GOVERNANCE.md
git commit -m "docs: add GOVERNANCE.md with authority, versioning, brand-separation rule, Foundation migration commitment"
git push origin main
```

---

### Task 11: Write `CERTIFICATION.md`

**Files:**
- Create: `CERTIFICATION.md`

- [ ] **Step 1: Write the full document**

```markdown
# Certification

The Provenance Protocol defines three certification tiers. Each tier carries
different trust signals and use rights for the registered certification mark.

## Tier 1: Self-certified

**Cost:** Free.

**Process:**

1. Implement the modules you intend to claim (Core, or Core + Extensions).
2. Validate your implementation against the JSON Schemas in [`schemas/`](./schemas/).
3. Publish a `provenance-compliance.json` manifest conforming to the schema
   in [`schemas/compliance-manifest.json`](./schemas/compliance-manifest.json).
4. Publish a compliance report in your repository documenting how each
   conformance checklist item in `SPEC.md` is satisfied.

**Use rights:**

- MAY claim, in plain prose: "PROV-1 Self-certified Core compliant" (or relevant variant).
- MUST NOT use the registered "Provenance Protocol Compliant" certification mark.
- MUST NOT use logos or visual identifiers implying third-party verification.

## Tier 2: Verified

**Cost:** Paid. Pricing schedule: https://provenance-protocol.org/certification

**Process:**

1. Complete the Tier 1 self-certification steps.
2. Submit a verification request via https://provenance-protocol.org/certification/request
3. CopyClip Inc. reviews:
   - The published `provenance-compliance.json` manifest.
   - The compliance report.
   - The implementation source code (if open) or a code walkthrough (if closed).
   - The behavior of the implementation against a test suite derived from
     the conformance checklists in `SPEC.md`.
4. CopyClip Inc. issues a verification certificate valid for 12 months.

**Use rights:**

- MAY use the registered "Provenance Protocol Compliant — Verified" mark in
  marketing, procurement responses, and product documentation.
- MUST display the certificate's expiration date alongside the mark.
- MUST re-verify annually to retain the right to use the mark.

## Tier 3: Audited

**Available:** Post-Foundation migration only.

**Cost:** Set by the auditor (independent of the Foundation).

**Process:**

1. Engage a third-party auditor accredited by the Foundation.
2. The auditor performs an independent assessment against `SPEC.md`.
3. The auditor issues an attestation suitable for use in compliance reporting
   (SOC2, EU AI Act conformity, ISO 42001).

**Use rights:**

- MAY use the "Provenance Protocol Compliant — Audited" mark with the auditor's
  attestation reference.
- MAY cite the attestation in third-party compliance frameworks.

## Mark usage

The "Provenance Protocol Compliant" certification mark is owned by CopyClip Inc.
and is being registered with USPTO and equivalent registries.

Unauthorized use of the mark (without an active Tier 2 verification or Tier 3
audit) is a violation of the mark holder's rights and MAY result in legal
action.

Use of the words "Provenance Protocol" and "PROV-1" in descriptive contexts
(documentation, marketing, blog posts, articles) is **freely permitted** and
does not constitute mark usage.

## Revocation

CopyClip Inc. MAY revoke a Tier 2 verification if the implementation:

- Misrepresents its compliance level in the `provenance-compliance.json` manifest.
- Modifies behavior post-verification in ways that violate previously-verified
  conformance.
- Uses the mark in misleading contexts.

Revocation requires written notice and a 30-day cure period.
```

- [ ] **Step 2: Commit**

Run:

```bash
git add CERTIFICATION.md
git commit -m "docs: add CERTIFICATION.md with three tiers and mark usage rules"
git push origin main
```

---

### Task 12: Scaffold the Next.js + MDX website

**Files:**
- Create: `site/package.json`
- Create: `site/next.config.mjs`
- Create: `site/tailwind.config.ts`
- Create: `site/postcss.config.mjs`
- Create: `site/tsconfig.json`
- Create: `site/app/layout.tsx`
- Create: `site/app/globals.css`
- Create: `site/components/Header.tsx`
- Create: `site/components/Footer.tsx`

- [ ] **Step 1: Initialize the Next.js project**

Run from `site/` directory (create the directory first):

```bash
mkdir -p site && cd site
npx --yes create-next-app@latest . \
  --typescript \
  --tailwind \
  --app \
  --src-dir=false \
  --no-eslint \
  --import-alias "@/*" \
  --use-npm
```

Accept defaults for any remaining prompts. After completion, `site/` contains
a working Next.js scaffold.

- [ ] **Step 2: Add MDX dependencies**

In `site/`, run:

```bash
npm install @next/mdx @mdx-js/loader @mdx-js/react @types/mdx
```

- [ ] **Step 3: Configure MDX in `next.config.mjs`**

Replace `site/next.config.mjs` content with:

```javascript
import createMDX from '@next/mdx';

const withMDX = createMDX({});

/** @type {import('next').NextConfig} */
const nextConfig = {
  pageExtensions: ['ts', 'tsx', 'js', 'jsx', 'md', 'mdx'],
};

export default withMDX(nextConfig);
```

- [ ] **Step 4: Replace `site/app/layout.tsx`**

```tsx
import './globals.css';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';

export const metadata = {
  title: 'Provenance Protocol',
  description: 'An open specification for human-agent authorship attribution in codebases under AI co-authorship.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-white text-zinc-900">
        <Header />
        <main className="flex-1 max-w-4xl mx-auto px-6 py-12 w-full">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Create `site/components/Header.tsx`**

```tsx
import Link from 'next/link';

export function Header() {
  return (
    <header className="border-b border-zinc-200">
      <nav className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-8">
        <Link href="/" className="font-semibold tracking-tight">
          Provenance Protocol
        </Link>
        <ul className="flex items-center gap-6 text-sm text-zinc-600">
          <li><Link href="/overview" className="hover:text-zinc-900">Overview</Link></li>
          <li><Link href="/getting-started" className="hover:text-zinc-900">Getting started</Link></li>
          <li><Link href="/spec" className="hover:text-zinc-900">Spec</Link></li>
          <li><Link href="/governance" className="hover:text-zinc-900">Governance</Link></li>
          <li><Link href="/compliance" className="hover:text-zinc-900">Compliance</Link></li>
          <li><a href="https://github.com/sssamuelll/provenance-protocol" className="hover:text-zinc-900">GitHub</a></li>
        </ul>
      </nav>
    </header>
  );
}
```

- [ ] **Step 6: Create `site/components/Footer.tsx`**

```tsx
export function Footer() {
  return (
    <footer className="border-t border-zinc-200 mt-12">
      <div className="max-w-4xl mx-auto px-6 py-8 text-sm text-zinc-500">
        <p>
          Specification text licensed under{' '}
          <a href="https://creativecommons.org/licenses/by/4.0/" className="underline hover:text-zinc-900">CC-BY 4.0</a>.
          Code artifacts licensed under{' '}
          <a href="https://www.apache.org/licenses/LICENSE-2.0" className="underline hover:text-zinc-900">Apache 2.0</a>.
        </p>
        <p className="mt-2">
          &copy; 2026 CopyClip Inc.
          {' · '}
          <a href="https://github.com/sssamuelll/provenance-protocol" className="underline hover:text-zinc-900">GitHub</a>
        </p>
      </div>
    </footer>
  );
}
```

- [ ] **Step 7: Verify the scaffold builds**

In `site/`, run:

```bash
npm run build
```

Expected: build succeeds with no errors. Warnings about missing `app/page.tsx` are acceptable (will be created in Task 13).

- [ ] **Step 8: Commit**

Run from repo root:

```bash
git add site/
git commit -m "site: scaffold Next.js 14 App Router with MDX, Tailwind, header, footer"
git push origin main
```

---

### Task 13: Write website content pages

**Files:**
- Create: `site/app/page.tsx`
- Create: `site/app/overview/page.mdx`
- Create: `site/app/getting-started/page.mdx`
- Create: `site/app/compliance/page.mdx`
- Create: `site/app/governance/page.mdx`
- Create: `site/app/spec/page.tsx`

- [ ] **Step 1: Write `site/app/page.tsx` (landing page)**

```tsx
import Link from 'next/link';

export default function Home() {
  return (
    <div className="space-y-12">
      <section className="space-y-6 pt-12">
        <h1 className="text-5xl font-semibold tracking-tight text-zinc-900">
          The Provenance Protocol
        </h1>
        <p className="text-xl text-zinc-700 max-w-2xl leading-relaxed">
          An open specification for human-agent authorship attribution in codebases
          under AI co-authorship.
        </p>
        <div className="flex gap-3 pt-4">
          <Link
            href="/getting-started"
            className="rounded-md bg-zinc-900 text-white px-5 py-2.5 text-sm font-medium hover:bg-zinc-700 transition"
          >
            Get started
          </Link>
          <Link
            href="/spec"
            className="rounded-md border border-zinc-200 px-5 py-2.5 text-sm font-medium hover:border-zinc-400 transition"
          >
            Read the spec
          </Link>
        </div>
        <p className="text-sm text-zinc-500 pt-2">
          v0.1-draft &middot; under active development
        </p>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-8">
        <Link href="/overview" className="block rounded-lg border border-zinc-200 p-6 hover:border-zinc-400 transition">
          <h2 className="text-lg font-semibold mb-2">What it standardizes</h2>
          <p className="text-zinc-600 text-sm leading-relaxed">
            The authorship contract between humans and agents over a codebase:
            who wrote what, with what authority, under what intent.
          </p>
        </Link>
        <Link href="/compliance" className="block rounded-lg border border-zinc-200 p-6 hover:border-zinc-400 transition">
          <h2 className="text-lg font-semibold mb-2">Why it matters</h2>
          <p className="text-zinc-600 text-sm leading-relaxed">
            Regulatory frameworks (EU AI Act, SOC2, ISO 42001, NIST AI RMF)
            assume a named human author. The protocol formalizes the evidence
            regime that satisfies them under agentic authorship.
          </p>
        </Link>
        <Link href="/getting-started" className="block rounded-lg border border-zinc-200 p-6 hover:border-zinc-400 transition">
          <h2 className="text-lg font-semibold mb-2">Implement it</h2>
          <p className="text-zinc-600 text-sm leading-relaxed">
            Core modules (`prov.authorship`, `prov.scope`) plus optional
            Extensions (`prov.intent`, `prov.debt`). JSON Schemas, examples,
            and conformance checklists are open and machine-readable.
          </p>
        </Link>
        <Link href="/governance" className="block rounded-lg border border-zinc-200 p-6 hover:border-zinc-400 transition">
          <h2 className="text-lg font-semibold mb-2">Governance</h2>
          <p className="text-zinc-600 text-sm leading-relaxed">
            Open spec under CC-BY 4.0. Public commitment to Foundation
            migration when adoption triggers are met.
          </p>
        </Link>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Write `site/app/overview/page.mdx`**

```mdx
# Overview

The **Provenance Protocol** standardizes how a codebase records, exposes, and
verifies the authorship, authority, and intent of every change in environments
where humans and AI agents collaborate.

It addresses a structural asymmetry: regulatory frameworks (EU AI Act, SOC2,
ISO 42001, NIST AI RMF) assume a named human author. Agentic coding tools
generate code on behalf of that human at velocities the human cannot
comprehend. The gap between *legal responsibility* and *human comprehension*
widens as agents improve. The protocol formalizes the evidence regime that
closes the gap.

## What it standardizes

Four modules:

- **`prov.authorship`** (Core) — per-commit, per-symbol, per-byte attribution:
  human vs agent, with delegation chains and revocable trust.
- **`prov.scope`** (Core) — bounded delegation: handoff packets with declared
  scope, do-not-touch boundaries, agent-consumable projections, lifecycle
  state machines, and post-change review summaries.
- **`prov.intent`** (Extension, draft pending) — architectural decisions,
  audit-proposal interface, intent-drift detection.
- **`prov.debt`** (Extension, draft pending) — cognitive-debt scoring:
  agent-authored ratio with time decay, human-review staleness, dark-zone
  identification.

## What it does not standardize

- Source format or AST representation.
- Linters or static-analysis rulesets.
- Code generation interfaces.
- Codebase comprehension or onboarding systems.
- Licenses or copyright assertions.

## Status

v0.1-draft. The Core modules are specified. Extensions are placeholders
reserving namespace and identifier; full specifications follow in future
PROV-1.x versions.

## Read further

- [Getting started](/getting-started) — implement the protocol in your tool.
- [Spec](/spec) — the canonical RFC-style document.
- [Compliance brief](/compliance) — for compliance, legal, and procurement.
- [Governance](/governance) — authority, versioning, Foundation migration.
```

- [ ] **Step 3: Write `site/app/getting-started/page.mdx` (stub)**

```mdx
# Getting started

> This is a stub. A full implementer guide will be published alongside PROV-1.0.

## Minimum viable compliance

To claim `PROV-1 Self-certified Core compliant`:

1. Implement the Core modules (`prov.authorship` and `prov.scope`) per the
   [specification](/spec).
2. Validate your data structures against the JSON Schemas:
   - https://provenance-protocol.org/schemas/authorship/0.1
   - https://provenance-protocol.org/schemas/scope/0.1
3. Publish a `provenance-compliance.json` manifest at a stable well-known path.
4. Publish a compliance report documenting each conformance checklist item
   from the spec.

## Reference implementation

[CopyClip](https://github.com/sssamuelll/copyclip) is the reference
implementation. Its source is available for inspection.

## Help

- Open an issue: https://github.com/sssamuelll/provenance-protocol/issues
- Read the spec: [/spec](/spec)
```

- [ ] **Step 4: Write `site/app/compliance/page.mdx` (stub)**

```mdx
# Compliance brief

> A stub for compliance, legal, and procurement functions. A downloadable PDF
> version will follow PROV-1.0.

## Why this exists

Regulatory and contractual frameworks that govern software change management
were drafted under the assumption that a named human authored each change.
These include:

- **EU AI Act** (Regulation 2024/1689), Articles 13 (transparency) and 14
  (human oversight).
- **SOC2** Trust Services Criteria, CC8.1 (change management).
- **ISO/IEC 42001:2023** (AI management systems).
- **NIST AI RMF 1.0** (govern function).

Adopting AI coding tools introduces a gap: the human responsible under these
frameworks no longer authored a substantial portion of the code they are
accountable for.

The Provenance Protocol formalizes the evidence regime that closes this gap.

## What an implementer provides

A `PROV-1 Verified` implementation provides:

- Per-change authorship records identifying human principals and agents.
- Delegation chains terminating at human principals.
- Bounded handoff packets recording what each agent was permitted to do.
- Post-change review summaries comparing actual behavior against permission.
- An auditable `provenance-compliance.json` manifest.

These artifacts are designed to be citable in compliance reporting and
defensible in audit.

## Verification

Self-certification is free and verifiable from any party. Third-party
verification (Tier 2) is available through CopyClip Inc.; third-party audit
(Tier 3) becomes available after Foundation migration.

See [`CERTIFICATION.md`](https://github.com/sssamuelll/provenance-protocol/blob/main/CERTIFICATION.md)
for the full process.
```

- [ ] **Step 5: Write `site/app/governance/page.mdx`**

```mdx
# Governance

The full governance model is documented in
[`GOVERNANCE.md`](https://github.com/sssamuelll/provenance-protocol/blob/main/GOVERNANCE.md).

## Summary

- **Editor:** CopyClip Inc. (current); transition to a vendor-neutral
  foundation when adoption triggers are met.
- **Spec license:** CC-BY 4.0. Anyone may read, cite, implement, and derive
  from the specification.
- **Code license:** Apache 2.0. Anyone may use, fork, modify, or embed the
  schemas and reference code.
- **Versioning:** SemVer at the specification level; independent versioning
  at the module level.
- **Change process:** PROV-RFC documents via Pull Request; community
  discussion via GitHub Issues.

## Foundation migration commitment

CopyClip Inc. commits to transferring editorial authority over the specification,
schemas, validator, and certification mark to a vendor-neutral foundation
(Linux Foundation AI or CNCF) when:

- At least 10 independent implementations exist.
- At least one enterprise pays for Verified certification with renewal.
- At least one major agentic-tooling vendor commits to implementation.

This commitment is public and irrevocable. New conditions MAY NOT be added
retroactively.

Ideal timeline: 18-24 months from v0.1-draft publication.

## Brand-separation rule

The specification MUST NOT contain anything that exists solely because the
reference implementation (CopyClip) does it that way. Implementer parity is
maintained as an editorial discipline.
```

- [ ] **Step 6: Write `site/app/spec/page.tsx` (renders SPEC.md)**

```tsx
import { promises as fs } from 'fs';
import path from 'path';
import { compileMDX } from 'next-mdx-remote/rsc';

export default async function SpecPage() {
  // Read SPEC.md from the repo root (one level above site/)
  const specPath = path.join(process.cwd(), '..', 'SPEC.md');
  const source = await fs.readFile(specPath, 'utf8');
  const { content } = await compileMDX({ source });
  return <article className="prose prose-zinc max-w-none">{content}</article>;
}
```

Install dependency in `site/`:

```bash
npm install next-mdx-remote
```

Add Tailwind typography plugin to `site/tailwind.config.ts`:

```typescript
import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx,mdx}', './components/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [require('@tailwindcss/typography')],
};

export default config;
```

Install:

```bash
npm install -D @tailwindcss/typography
```

- [ ] **Step 7: Verify the site builds**

In `site/`, run:

```bash
npm run build
```

Expected: build succeeds. SPEC.md page renders.

- [ ] **Step 8: Commit**

Run from repo root:

```bash
git add site/
git commit -m "site: add landing, overview, getting-started, compliance, governance, spec pages"
git push origin main
```

---

### Task 14: Deploy the website to Vercel

**Files:**
- Create: `.github/workflows/deploy.yml` (optional — Vercel auto-deploys from GitHub)

- [ ] **Step 1: Create a Vercel account if needed**

Sign up at https://vercel.com using the same GitHub account (`sssamuelll`).

- [ ] **Step 2: Import the repo**

In the Vercel dashboard:

1. Click "Add New" → "Project".
2. Select `sssamuelll/provenance-protocol`.
3. When configuring, set **Root Directory** to `site`.
4. Framework: **Next.js** (auto-detected).
5. Build command: `npm run build` (default).
6. Output directory: `.next` (default).
7. Click "Deploy".

Wait for the initial deploy to succeed. Vercel assigns a preview URL like
`provenance-protocol-xxx.vercel.app`.

- [ ] **Step 3: Add the custom domain**

In Vercel project settings → Domains:

1. Add `provenance-protocol.org`.
2. Vercel shows the DNS records to add (typically a CNAME or A record).
3. Switch to Cloudflare → DNS for `provenance-protocol.org`.
4. Add the records Vercel showed. Set proxy status to DNS-only (grey cloud)
   for the Vercel records.
5. Wait for DNS propagation (typically <5 minutes).
6. Vercel auto-issues a TLS certificate via Let's Encrypt.

- [ ] **Step 4: Add the `www` redirect**

Add `www.provenance-protocol.org` in Vercel Domains. Set it to redirect to
`provenance-protocol.org` (Vercel handles this with a click).

- [ ] **Step 5: Add the `.com` and `.io` redirects**

In Cloudflare for each of `provenance-protocol.com` and `provenance-protocol.io`:

- Create a Page Rule: `provenance-protocol.com/*` → 301 forward to
  `https://provenance-protocol.org/$1`.
- Same for `.io`.

- [ ] **Step 6: Verify the live site**

Open https://provenance-protocol.org. Expected:

- Landing page renders.
- All navigation links work.
- `/spec` renders SPEC.md as formatted HTML.
- HTTPS certificate is valid.

- [ ] **Step 7: Commit any deploy config changes**

If you needed a `vercel.json` for advanced config:

```bash
git add vercel.json
git commit -m "site: add Vercel deploy config"
git push origin main
```

(If not, skip this step.)

---

### Task 15: File the USPTO certification mark application

**Files:** none (external legal workstream)

**Why now and not earlier:** filing requires the domain and basic public presence to demonstrate the mark is in use (or imminent use). Tasks 1-14 establish both.

- [ ] **Step 1: Decide the filing entity**

The mark holder MUST be a legal entity. Options:

- **CopyClip Inc.** if already incorporated.
- **Samuel Ballesteros (DBA: CopyClip)** if not yet incorporated. Filing under
  individual name is permitted; transferring the mark to a future Inc. is a
  paperwork step.

If undecided, file as individual and assign to the entity later. The TEAS RF
form has an "Assignment" path.

- [ ] **Step 2: Prepare the filing materials**

Required fields for USPTO TEAS RF (Reduced Fee):

- Applicant name and address.
- Mark: `PROVENANCE PROTOCOL COMPLIANT` (standard character claim — no logo).
- Filing basis: **Section 1(a)** (use in commerce) if Tier 1 self-certification
  is live by filing time; **Section 1(b)** (intent to use) otherwise. Section
  1(b) is safer and converts to 1(a) later via a Statement of Use.
- Goods/services class: **Class 42** (computer and scientific services) —
  "Quality control and certification services in the field of software
  authorship governance, namely, certifying that software products conform to
  the Provenance Protocol specification."
- Specimens: for 1(a), submit a screenshot of `provenance-protocol.org`
  showing the mark in use. For 1(b), no specimens until conversion.
- Filing fee: $250-350 per class (varies by filing type).

- [ ] **Step 3: File**

Go to https://teas.uspto.gov/ccr/cm and complete the TEAS RF form.

Pay the fee. Receive a serial number. Expected processing time to first
examiner action: 6-8 months. Total time to registration: 12-18 months.

- [ ] **Step 4: Record the serial number**

Add a note to `CERTIFICATION.md` (commit separately):

```markdown
## Filing status

USPTO certification mark application:
- Filed: 2026-MM-DD
- Serial number: <number>
- Basis: Section 1(b) — intent to use [or 1(a) — use in commerce]
- Status: Pending examination
```

Run:

```bash
git add CERTIFICATION.md
git commit -m "docs: record USPTO filing serial number for certification mark"
git push origin main
```

- [ ] **Step 5: Schedule EU, UK, Japan filings**

For each, file separately within 12 months to claim Paris Convention priority
from the USPTO filing date:

- **EU**: file with EUIPO (https://euipo.europa.eu/) — EU trademark covers all 27 member states.
- **UK**: file with UKIPO (https://www.gov.uk/apply-trade-mark) — required separately post-Brexit.
- **Japan**: file with JPO (https://www.jpo.go.jp/e/) via a Japanese trademark attorney.

These are calendar items, not code tasks. Add to your personal task tracker
with deadline (USPTO filing date + 11 months).

---

### Task 16: Update CopyClip `README.md` with placeholder paragraph

**Files:**
- Modify: `C:/Users/simon/Desktop/projects/copyclip/README.md` (after line 14)

This is a *minimal* update for sub-project #1. Full reframing is sub-project #3.

- [ ] **Step 1: Insert the placeholder paragraph**

In `C:/Users/simon/Desktop/projects/copyclip/README.md`, after line 14
(`> Current version: v0.4.0. See [CHANGELOG.md](CHANGELOG.md) for shipped features.`),
insert:

```markdown

---

CopyClip is the reference implementation of the
[Provenance Protocol](https://provenance-protocol.org), an open specification
for human-agent authorship attribution in codebases under AI co-authorship.
Implementing PROV-1 Core (and the Intent and Debt Extensions, when published)
is the long-term north star for CopyClip's intelligence layer.
```

(Note the leading `---` to create a visual separator from the preceding line.)

- [ ] **Step 2: Commit in the CopyClip repo**

Run from `C:/Users/simon/Desktop/projects/copyclip`:

```bash
git add README.md
git commit -m "docs: add placeholder reference to Provenance Protocol

CopyClip is the reference implementation of the Provenance Protocol (PROV-1).
Full repositioning of README, marketing, and roadmap is deferred to
sub-project #3 of the protocol pivot.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push origin main
```

---

### Task 17: Final verification against success criteria

**Files:** none (verification only)

- [ ] **Step 1: Walk each success criterion from the design spec**

Open `C:/Users/simon/Desktop/projects/copyclip/docs/superpowers/specs/2026-05-26-provenance-protocol-identity-design.md`
and read § "Success criteria (for this sub-project)". For each checkbox,
verify the corresponding artifact exists and works:

| Criterion | Verification |
|---|---|
| Repo `provenance-protocol/spec` exists at public GitHub org | Visit https://github.com/sssamuelll/provenance-protocol |
| `SPEC.md` v0.1-draft published with Core sections | View https://github.com/sssamuelll/provenance-protocol/blob/main/SPEC.md |
| JSON Schema skeletons for all 4 modules | List `schemas/` directory; verify each parses |
| Website live with required pages | Visit https://provenance-protocol.org and each subpage |
| Certification mark filed | Check USPTO TEAS receipt; serial number recorded in `CERTIFICATION.md` |
| CopyClip README placeholder paragraph added | Open https://github.com/sssamuelll/copyclip/blob/main/README.md, find paragraph |
| Versioning scheme documented | Visit https://provenance-protocol.org/governance or open `GOVERNANCE.md` |
| Foundation migration commitment public | Same — verify the commitment is visible |
| Brand-separation constraint documented in `GOVERNANCE.md` | Open `GOVERNANCE.md`, find "Brand-separation rule" section |

- [ ] **Step 2: Run schema validation one more time**

In the spec repo root, run:

```bash
npx --yes ajv-cli validate -s schemas/authorship.json -d "examples/authorship/*.json"
npx --yes ajv-cli validate -s schemas/scope.json -d "examples/scope/*.json"
npx --yes ajv-cli validate -s schemas/compliance-manifest.json -d examples/compliance-manifest-example.json
```

Expected: every example reports `valid`.

- [ ] **Step 3: Run the site build one more time**

In `site/`, run:

```bash
npm run build
```

Expected: build succeeds. No type errors. No MDX compile errors.

- [ ] **Step 4: Smoke-check live URLs**

Open in a browser:

- https://provenance-protocol.org
- https://provenance-protocol.org/overview
- https://provenance-protocol.org/getting-started
- https://provenance-protocol.org/spec
- https://provenance-protocol.org/governance
- https://provenance-protocol.org/compliance
- https://provenance-protocol.com (should redirect to .org)
- https://provenance-protocol.io (should redirect to .org)

Every URL MUST return HTTP 200 (or 301 → 200 for the redirects), serve valid
TLS, and render without browser console errors.

- [ ] **Step 5: Tag the v0.1-draft release**

In the spec repo:

```bash
git tag -a v0.1-draft -m "Provenance Protocol v0.1-draft — initial public release"
git push origin v0.1-draft
gh release create v0.1-draft \
  --title "v0.1-draft" \
  --notes "Initial public release of the Provenance Protocol specification. See CHANGELOG.md for details."
```

- [ ] **Step 6: Announce internally**

Sub-project #1 is complete. The protocol exists publicly. The next sub-project
(canonicalization of remaining CopyClip contracts into PROV-1.x Extensions) can
begin. Communicate the completion to any stakeholders (in this case: the user).

---

## Self-review notes

This plan was reviewed against the design spec on 2026-05-26 for:

- **Spec coverage:** every "Success criterion" in the design spec has at least
  one corresponding task. Verified.
- **Placeholder scan:** the only `[Extension — draft pending]` placeholders are
  in `SPEC.md` Sections 6-7 and `schemas/intent.json` / `schemas/debt.json`,
  which is exactly what the design spec permits. No TODO / TBD in code or
  schema content.
- **Type consistency:** authorship record field names (`record_id`,
  `principals`, `agents`, `authorship_segments`, `recorded_at`) are used
  identically in `SPEC.md` §4, `schemas/authorship.json`, and the examples.
  Handoff packet field names are used identically across `SPEC.md` §5,
  `schemas/scope.json`, and the examples.
- **Out-of-scope:** the `provenance-validator` is explicitly out of scope for
  this sub-project (resolved as a pre-flight decision). The plan does not
  include validator tasks.

Pre-flight open questions resolved at the top of the plan; the executing agent
MAY revisit with the user but SHOULD NOT block.
