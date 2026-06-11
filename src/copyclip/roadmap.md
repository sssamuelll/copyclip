# 🚀 CopyClip — Capability Roadmap

> Runtime/package version is currently `v0.4.0`. This describes product capability
> direction, not a strict semver changelog.

## The surface: the cuaderno

CopyClip **is** the cuaderno — an evidence-first tutor over a codebase you
increasingly did not write by hand. It keeps the author's intention connected
across the bursts of AI-assisted development; the gap between bursts is where
ownership leaks. Everything it shows is anchored to real code, git, or the
decision ledger — *exposición, no autoría*.

The legacy dashboard (the `App.tsx` router, the Sidebar, and the absorbed pages)
was retired in Wave 5 (2026-06). Each question class it answered now lives in a
cited tutor tool or widget; three auxiliary views survive — **codebase map**,
**safe handoff**, **settings** — reached from the cuaderno's ⊞ menu. MCP exposes
the same bounded, audited views to external agents.

## ✅ Shipped baseline
- [x] **Cuaderno:** evidence-first tutor; answers stream as cited blocks + widgets; the human ratifies decision status (the one write).
- [x] **MCP server:** bounded, audited project views for external agents (intent manifesto, context bundle, audit, heat, handoff).
- [x] **Codebase map:** interactive graph of the codebase (a survivor side surface).
- [x] **Safe handoff:** bounded delegation packets with pre-delegation review.
- [x] **Heat:** maintenance/attention pressure per file, from the live composite engine.
- [x] **In-situ setup + background analysis:** LLM config and re-index from settings; analysis follows the rhythm of bursts.

## 🎯 Forward (≤3)
1. **Cruces / Junctions v0.1** ([#146]) — in the playground, show *which branch executed the input you just edited*, as a computed value, never narrated. High-level debugging anchored to a real run.
2. **Pulso** ([#152]) — continuous, incremental, background analysis that follows the rhythm of development bursts (filesystem watch or commit trigger, non-intrusive notices). The connective tissue that lets CopyClip survive the gap between bursts.
3. **Intent Drift Surface** — a passive layer that flags code regions drifted from registered architectural decisions and surfaces the drift to the author for inspection. Never proposes refactors or triggers agentic action — *exposición, no autoría*.

[#146]: https://github.com/sssamuelll/copyclip/issues/146
[#152]: https://github.com/sssamuelll/copyclip/issues/152

# 🎯 Vision
A personal cognitive sentinel for the author — the tool that lets him stay
attached to his own codebases as AI agents write more of the code. If others
with the same pain eventually find it useful, that's downstream of the author's
own daily use working.
