# 🚀 CopyClip — Capability Roadmap

> Runtime/package version is currently `v0.4.0`. This describes product capability
> direction, not a strict semver changelog. Last reconciled **2026-07-07** against
> `main` @ `eb92344` — the previous list carried Cruces and Pulso as "Forward"
> after both had already shipped; corrected here.

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

## ✅ Shipped

**Baseline**
- [x] **Cuaderno:** evidence-first tutor; answers stream (SSE) as cited blocks + widgets; the human ratifies decision status (the one write).
- [x] **MCP server:** bounded, audited project views for external agents (intent manifesto, context bundle, audit, heat, handoff).
- [x] **Codebase map**, **safe handoff**, **in-situ setup + background analysis** — the surviving side surfaces and the re-index rhythm.

**Answer honesty (engine/quality)**
- [x] **Multi-provider** LLM (DeepSeek default, OpenAI-compat adapter) with SSE streaming.
- [x] **Answer quality:** a deterministic evidence gate plus a semantic judge, with two-world abstention — an answer it cannot stand behind abstains rather than asserts.

**The comprehension ladder** — six tutor moves, each a deterministic anchor over real substrate, each withholding the interpretive act; subordinated under the cognitive-load / explain-by-altitude doctrine:
- [x] ① Walk the path · ② Accepted, not decided · ③ Hasn't been back · ④ Blast radius · ⑤ Commit change graph · ⑥ Teach-back.

**The playground arc** — one paid-for capture, read ever more cheaply, never a control surface, never a fabrication:
- [x] **Run a symbol** with a real example (the boundary).
- [x] **Guided step-through** — record-then-replay of the real run, line by line (#177).
- [x] **Call synthesis** — auto-fill a runnable call lifted from real usage (#178).
- [x] **Cruces / Junctions v0.1** — which `if`/`elif`/`else` arm the run crossed, computed, tri-state honest (`null` when the trace was truncated, never overclaimed) (#179).

**Pulso** — clocks that follow the rhythm of bursts, not the wall clock:
- [x] **Last contact** (burst-recency from the `Co-Authored-By` AI-burst signal) and **Last visit** (decision ratification as a second clock) (#162–166). Heat v2 dropped the dead `agent_authored_ratio` factor.

## 🎯 Forward (≤3)

*(reconciled 2026-07-07; the prior #1 Cruces and #2 Pulso both shipped)*

1. **Cruces / Junctions v0.2 — control-flow C** ([#146]) — extend the executed-arm
   overlay beyond the `if` ladder: loops (`for`/`while` ran-vs-skipped + iteration
   counts), `try`/`except`/`finally`, ternaries, `match`/`case`. Loop
   iteration-identity is a joint fix — it also unlocks the step-through's deferred
   loop-folding. Built from real captured cases, never speculation.
2. **Intent Drift Surface** — a passive layer that flags code regions drifted from
   registered architectural decisions, for the author to inspect. Never proposes
   refactors or triggers agentic action — *exposición, no autoría*. **Honest
   precursor:** the decision ledger is nearly empty, so *populating decisions*
   likely has to precede the feature — drift needs something to drift *from*.
3. **Aprendizaje / active-recall** — the family that would consume the write-only
   `got_it` and the ④/⑥ prediction events. **Gated on one deliberate decision:
   the witness-event ledger** — the substrate that unblocks it sits one refactor
   from becoming the per-file comprehension score the doctrine forbids. Decide it
   consciously, do not drift into it; its current *absence* is what protects the
   doctrine.

**Held / gated (deliberately not in the ≤3):** Pulso's continuous background infra
(commit-trigger + WAL; filesystem-watch was rejected in the kickoff) and its
burst→gap→reconnection ledger; polyglot playground *execution* (static analysis is
already polyglot via tree-sitter, execution is Python-only — gate on real demand);
the eval-harness (Phase B noise-floor is the gate before trusting any regression
delta).

[#146]: https://github.com/sssamuelll/copyclip/issues/146

# 🎯 Vision
A personal cognitive sentinel for the author — the tool that lets him stay
attached to his own codebases as AI agents write more of the code. If others
with the same pain eventually find it useful, that's downstream of the author's
own daily use working.
