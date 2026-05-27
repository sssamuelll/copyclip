# CopyClip — Rejected Ideas

## Why this file exists

Personal tools fail by infinite refinement of a tool that has stopped being used, not by
lack of features. Without external pressure (users, deadlines, market signal), the only
defense against scope creep is an explicit brake: a written record of technically-good
ideas that the author chose **not** to build, and why.

This file is the brake.

A rejected idea is not a permanent verdict — circumstances may change, the criterion may
evolve, the underlying need may resurface in a form that passes the tests. But it must
be re-justified explicitly. Default behavior on a rejected idea is: stays rejected.

## The rejection criterion

The primary test every CopyClip feature must pass:

> **Does this technique *support* the asymmetry — original author returning to a changed
> codebase — or does it *dissolve* it?**

If it supports the asymmetry, build it (subject to other priorities).
If it dissolves the asymmetry, reject it — even if it would be technically interesting,
even if competitors have it, even if it looks like an obvious win.

### Secondary tests

A feature SHOULD also pass each of these before being built:

- **Friction test.** Can I name a specific recent friction this feature would have
  resolved, with a date? If no, reject — it is being motivated by the hypothetical
  audience, not by my actual pain.
- **Mediation test.** Does this add a new agent layer between me and my code? If yes,
  almost certainly reject — additional agentic intermediation increases cognitive load
  even when it appears to reduce it.
- **Horizon test.** Does the implementation cost match a personal-tool horizon (days
  to weeks of effort, not months)? If no, defer indefinitely.

Failing any one of these is grounds for rejection or significant reframing.

## Rejected ideas

### Semantic Refactor Agent (active-suggestion version) — 2026-05-26

**What it was.** A specialized AI agent that would suggest architectural cleanups based on
detected intent drift. Originally listed in `src/copyclip/roadmap.md` under the long-term
capability goals section.

**Why rejected.** Fails the primary test. The feature would have added a third authorship
category — *"this is code an agent suggested that CopyClip's drift detector triggered"* —
on top of the existing human-vs-agent split that the entire CopyClip architecture exists
to protect. Introducing agentic intermediation, however well-informed by registered
decisions, increases the cognitive load that CopyClip exists to reduce. It would have
claimed to solve the drift problem while quietly making the authorship surface less
legible to its human user.

Also fails the mediation test (adds a new agent layer between author and code).

**What survives.** The drift-detection capability is preserved as **Intent Drift Surface**
— a passive layer that flags regions which have drifted from registered architectural
decisions, surfacing them for the author's inspection. The reformulated version does NOT
propose refactors and does NOT trigger agentic action. Refactor decisions stay with the
author.

**Cost of the rejection.** Loses the ergonomic appeal of *"the tool tells me what to do
about the drift it found."* The author must read the drift surface and decide on response
themselves. This is an acceptable cost — the cognitive load of deciding is precisely
the load the architecture is designed to preserve under the author's ownership.

**Triggered by.** Verdict from the `aurelius-voronov` meta-architect agent during the
post-competitor strategic review (2026-05-26 arc, triggered by the surfacing of
Lum1104/Understand-Anything).

---

## Template for future rejections

Copy-paste this block for each new rejection:

```
### [Feature name] — YYYY-MM-DD

**What it was.** [Concrete description, where it was proposed]

**Why rejected.** Fails the [primary / friction / mediation / horizon] test because [...].

**What survives (if anything).** [Reformulated version, or "nothing"]

**Cost of the rejection.** [What ergonomic / capability gain is being given up]

**Triggered by.** [What surfaced the question — friction, review, observation]
```
