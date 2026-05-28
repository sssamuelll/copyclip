# CopyClip Cuaderno Conversacional — Design Spec

**Date:** 2026-05-28
**Status:** Approved for implementation planning
**Supersedes:** [Anchored Playground v1 design](2026-05-22-anchored-playground-design.md) (the v1 surface becomes evidence; v2 reformulates the question)
**Tracking:** to be opened as a new epic; v1 sub-PRs (#98, #99, #102, #103, #110, #113, #115) remain in git history as evidence of the question that was being formulated before it was named.

---

## Why

CopyClip's wedge is **temporal-causal**, not spatial. The user's question is not *"what does this code do"* — it is *"what was decided, and why did I accept that decision without auditing it"*.

The v1 Anchored Playground tried to answer the spatial question with `(función, sample) → output`. That model presupposes every function is local — a pure computation over an input. The functions that actually cost time to understand are **relational**: they participate in a protocol, a sequence, a state. They have no sample. They have context. (Diagnosed by Voronov, 2026-05-28; recorded in `project_copyclip-temporal-causal-wedge` memory.)

The v2 reformulates the surface. When the dev cannot understand a piece of their own AI-generated code, what they need is not to execute the function with a sample. They need **someone to explain** — anchored in the real code, not inventing — what the AI decided and why that was reasonable. That *someone* is an LLM in tutor posture, not in generator posture.

The v2 builds a **conversational surface** where the LLM tutor designs interactive explanations ad-hoc, anchored in the real code as ground truth, at whatever level of abstraction the user's question requires — from "what does this project do" to "why this single line".

Distinguishing claim against `/understand-anything`: that system pre-computes the comprehension system (tours, knowledge graph). CopyClip's v2 **computes-at-query-time** the comprehension surface specific to the question. Different ontology of the same object (code).

> **Unifier sentence (Axiom-0, 2026-05-28):** "Understanding code is not knowing what it does. It is recovering the decision one didn't make."

---

## User model

The user is **dev-archaeologist of their own AI-generated code**.

Phenomenology:

- Knows they constructed the code (with AI assistance), but does not remember the detail-level decisions. Partial authorial memory — fragments of the original prompt, intuition of the general direction, opacity of the specific implementation.
- Not a vibe coder (who is outside the code's time). Not a reader of foreign code (no pretension of authorship). They are an **archaeologist in their own house** — they recognize the furniture but don't remember buying it.
- Central comprehension act: **recover the deliberation that was delegated to the assistant**, at the level of detail the current doubt requires.

Implicit constraints (no need to serve others):

- Solo dev. CopyClip is personal tool (explicit commitment 2026-05-26).
- Knows the domain. The AI does not need to explain what a function or an import is.
- Works on their machine. No cloud, no collaboration, no seats.

A 20-year dev and a learning dev share **the act** ("why this decision?"), not the audience density. The cuaderno unifies the question, not the technical level of the answer.

---

## Surface

The conversational cuaderno is **designed to be the home of CopyClip**. Phase 1 ships it as a new entry point that coexists with the current dashboard; Phase 3 makes it the single home (see *Phasing* below). The description in this section is the **end-state** surface; Phase 1 surface omits widgets and runs alongside legacy pages.

```
┌────────────────────────────────────────────────────────────────┐
│  copyclip — cuaderno                                    [≡]    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   [Active educational frame]                                   │
│                                                                │
│   ━ explanatory text from the LLM                              │
│   ━ executable code blocks with mocks (Phase 2+)               │
│   ━ widgets invoked by the LLM (graph subset, diff, ...) (P2+) │
│   ━ "I got this / I didn't" markers                            │
│                                                                │
│   The frame's CONTENT swaps with each question — no scroll     │
│   history, no accumulation. Bret Victor model: continuous      │
│   state, zoom in/out via the next question.                    │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  > ask whatever you want…                              [send]  │
└────────────────────────────────────────────────────────────────┘
```

Surface principles:

- **Conversational input** at the bottom. Question enters in natural language.
- **Active educational frame** at top. The LLM-designed response. Content is ad-hoc — the LLM composes text + executable code blocks + widgets according to what the question needs.
- **No visible history by default**. The session is saved in the background; the user can invoke it ("show me earlier questions", "go back to the frame from 3 questions ago") but the default view is **one active frame**, not a queue.
- **No sidebar of old pages**. Codebase Map, Reacquaintance, Debt Navigator stop existing as primary pages. The LLM invokes them as widgets inside the frame when applicable. They remain accessible via explicit commands (`/codebase-map`, etc.) as debug tools — not as home.

Access:

- Single URL on the CopyClip default port (currently `4310`) brings up the cuaderno.
- Opening CopyClip → user sees the cuaderno ready to receive their first question. If there is a previous session, the cuaderno resumes it. If it is the user's first time in the project, the cuaderno offers an overview (asking first what interests them).

The session **is** the user's note. There is no separate note layer. Conversation + frames + bookmarks ("this matters") together form the artifact.

---

## Architecture

Three layers. Shape is preserved across all phases; what changes is which primitives exist.

```
┌──────────────────────────────────────────────────────────┐
│  Surface — Cuaderno (frontend)                           │
│  - conversational input                                  │
│  - active frame (text + blocks + widgets)                │
│  - persists session in background                        │
└────────────────────────┬─────────────────────────────────┘
                         │ POST /api/cuaderno/ask
                         │ { question, session_id, ... }
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Compositor — LLM tutor (backend)                        │
│  - parses the question                                   │
│  - decides which primitives to invoke (text/code/widget) │
│  - calls Anchor System for data                          │
│  - composes the frame as structured response (JSON)      │
└────────────────────────┬─────────────────────────────────┘
                         │ tool calls
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Anchor System — ground truth (backend)                  │
│  - access to real code (file reads, AST, symbols DB)     │
│  - access to git (commits, diffs, blame)                 │
│  - access to existing tests                              │
│  - access to transcripts (Claude Code / MemPalace)       │
│  - returns cited evidence (paths, line ranges, commits)  │
└──────────────────────────────────────────────────────────┘
```

**Architectural invariant:** the LLM **never invents**. It receives the question, identifies which pieces of the Anchor System it needs, queries them, cites them in the response. Every LLM claim must be **anchored to recoverable evidence** (path:line, commit SHA, test name). The user must always be able to verify.

This is **agentic loop with strict anchor**: the LLM may request what it needs, but may only assert what the code supports.

### Anchor System primitives (LLM tool calls)

The compositor has structured tool calls. The full list grows as needed; the v1 set:

- `read_file(path, line_range?)` — direct read of source
- `grep_symbols(name?, kind?, file?, module?)` — query symbols DB
- `get_callers(symbol)` — list of call sites
- `get_callees(symbol)` — list of called symbols
- `git_log(path?, limit?)` — recent commits
- `git_blame(path, lines)` — last commit that touched lines
- `git_diff(commit_sha, path)` — diff of a commit
- `find_tests(symbol)` — tests that exercise a symbol
- `read_transcript(reference)` — fetch Claude Code or MemPalace transcript by id (when transcript indexing exists)

---

## Phasing

Phasing is by **structural dependency, not by feature recortado**. Each phase delivers something runnable.

### Phase 1 — Wedge probe

Primitives in the frame:

- **Explanatory text** (markdown render)
- **Code blocks** (not executable yet — syntactic display, with citation to the path:lines they come from)
- **Citation chips** — `▸ src/foo.py:152-164` — clickable, open file in side panel (read-only)
- **Suggested follow-up questions** — clickable buttons that turn into the next user question

What the LLM **does** in Phase 1:

- Receives user question
- Decides which files / symbols / commits it needs to read
- Reads them via the Anchor System (multiple tool call rounds allowed, bounded)
- Composes a structured response: alternation of text + cited code blocks + sub-questions
- Renders in the frame

What is NOT in Phase 1:

- Executable code blocks (requires mock generation; Phase 2)
- Map / sequence diagram / diff viewer widgets (Phase 2)
- Cuaderno replacing home (Phase 3 — only after 1 + 2 validate)

**Hypothesis to validate in Phase 1:** can the LLM in tutor posture, anchored to real code, produce explanations that effectively teach? If yes, continue. If no, the v2 wedge is wrong and we re-think.

### Phase 2 — Pluggable widgets

The Compositor gains the capacity to invoke rich widgets. Each widget is a Lego primitive that the LLM may compose into the frame. Widgets are added **one at a time** in their own mini-spec/PR. Each widget has a JSON contract: the LLM decides to invoke it, the frontend renders it.

Initial widget set (subject to Phase 1 learnings):

- `code_block_executable(code, mocks)` — embedded Marimo block with AI-generated mocks
- `graph_subset(nodes, edges)` — codebase map subgraph, filtered to context
- `sequence_diagram(steps)` — call sequence the AI infers from call sites
- `diff_view(commit_sha, path)` — diff of a relevant commit
- `callers_tree(symbol)` — who calls this symbol

### Phase 3 — Dashboard replacement

The cuaderno transitions from "new view" to "single home". Old pages become debug tools accessible via explicit command. Only occurs **after** Phase 1 + Phase 2 validate the wedge.

---

## How it feels — three examples

### Example A — broad question

> **You:** what does this project do?

Internally the LLM does several tool calls (`read_file('README.md')`, `grep_symbols(kind='module', limit=20)`, `git_log(limit=10)`, `read_file('pyproject.toml')`), reads a relevant subset, synthesizes.

The frame that appears:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CopyClip is a personal tool for understanding code the AI wrote for you.
Three subsystems compose its core:

  1. ANALYZER — parses the repo, extracts symbols, builds a graph
     ▸ src/copyclip/intelligence/analyzer.py:1-50

  2. CODEBASE MAP — frontend that renders that graph as interactive,
     navigable visualization
     ▸ frontend/src/pages/Atlas3DPage.tsx:1-60

  3. PLAYGROUND — surface that executes repo functions with mocks
     (in transition to this cuaderno you are using)
     ▸ src/copyclip/intelligence/playground.py:1-30

Explicit commitment (2026-05-26): not a commercial product. Discipline-
as-artifact — preserve rigor, drop publication aspirations.
  ▸ docs/REJECTED.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Want me to go deeper on one? "the analyzer", "the playground",
"the codebase map", or something more specific.

  [ explore analyzer ]  [ explore playground ]  [ explore codebase map ]
```

Every `▸` is clickable — opens the file in a side panel (read-only) so you can verify.

### Example B — intermediate question

> **You:** how do the analyzer and the playground connect?

The LLM internally: `grep_symbols(file='playground.py')`, `read_file('playground.py', lines=1-50)`, `get_callers('resolve_function_ref')`, `read_file('analyzer.py', lines=150-170)`.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The playground READS data that the analyzer WROTE. The connection is
the `symbols` table in SQLite.

Flow:

  ANALYZER ──writes──▶  symbols (DB)  ◀──reads── PLAYGROUND
     │                                              │
     │ INSERT INTO symbols                          │ SELECT ... WHERE
     │ (name, kind, file_path,                      │ file_path=? AND name=?
     │  line_start, module)                         │ AND kind IN (...)

The analyzer runs in `analyze(root)` and populates the DB:
  ▸ src/copyclip/intelligence/analyzer.py:646-680

The playground reads that DB to resolve the function reference to execute:
  ▸ src/copyclip/intelligence/playground.py:266-292

KEY POINT: the playground derives the Python module from the file path,
NOT from the DB's `module` column. That was fixed in a0dae63 because the
column is slash-style ("copyclip/intelligence") and Python needs dotted
("copyclip.intelligence").
  ▸ src/copyclip/intelligence/playground.py:303-314
  ▸ commit a0dae63

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Want to see the flow in action with an example, or go deeper on a
component?
```

### Example C — atomic question

> **You:** why does `_module_from_relpath` use slash instead of dot?

Internally: `grep_symbols(name='_module_from_relpath')`, `read_file('analyzer.py', lines=152-165)`, `get_callers('_module_from_relpath')`, `git_blame('analyzer.py', lines=152-165)`.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`_module_from_relpath` uses slash because its primary consumer is NOT
Python imports — it's the architecture graph and cross-language queries.

The code:
  ▸ src/copyclip/intelligence/analyzer.py:152-164

  def _module_from_relpath(rel: str) -> str:
      parts = [p for p in rel.split("/") if p]
      if len(parts) <= 1:
          return "root"
      if parts[0] in {"src", "lib"} and len(parts) > 2:
          parts = parts[1:]
      if len(parts) == 2:
          return parts[0] if parts[0] in {"api", "utils"} else parts[1]
      return "/".join(parts[:-1])   # ← returns "copyclip/intelligence"

Callers:
  ▸ analyzer.py:486 (changes detected by module)
  ▸ analyzer.py:660 (insert into symbols.module)

Both consume the result as a path-string for joins, comparisons, and
matching against the architecture graph. Neither uses it as a direct
`from {mod} import`.

The playground DOES need dotted Python, and that's why it derives its
own version (`_module_from_file`) instead of trusting this value:
  ▸ src/copyclip/intelligence/playground.py:501-509

RECOVERED ARCHITECTURAL DECISION: the `symbols.module` field is
multi-language by design. Python is just one of the consumers. Slash
format is the shared format.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Want to see the commit that introduced this separation, or go deeper on
another topic?
```

---

## Anti-scope

Explicitly NOT in this design:

- **Editing the user's source files from the cuaderno.** The cuaderno reads and explains; it never writes back. (The terminal / VS Code / Cursor remain the editing surface.)
- **Multi-language playground execution (Phase 2 executable blocks).** Python only in Phase 2; multi-language tracked in #114 as a separate epic.
- **Real-time collaboration / multi-user sessions.** Personal tool by commitment.
- **Cloud sync or hosted version.** Local only.
- **Agentic code generation in the cuaderno.** The LLM may explain code, propose interpretations, and generate mocks for executable blocks — but it does not propose changes to the user's codebase from inside the cuaderno.
- **Generalized "talk to your repo" RAG.** The anchor system uses tool calls, not vector retrieval. Anchored-citation requirement is the architectural commitment.

---

## Open questions

These do not block Phase 1 start but need answers before Phase 2:

1. **LLM provider and model selection.** Phase 1 should work with Anthropic Claude (already configured for `copyclip start` onboarding). Decision of which exact model (Sonnet / Opus / Haiku) deferred to implementation planning based on latency / cost / quality measured against real questions.
2. **Tool call budget per question.** How many rounds of `read_file` / `grep_symbols` / etc. before composing? Initial cap to be measured against real usage.
3. **Session persistence schema.** Where does the session live? `.copyclip/cuaderno-sessions.db`? Markdown files? Decision deferred — least-effort persistence in Phase 1 (e.g., SQLite alongside `intelligence.db`).
4. **Transcript ingestion.** How does the Anchor System index Claude Code transcripts (stored in `~/.claude/projects/...`) so the LLM can reference the original conversation that produced a piece of code? Out of scope for Phase 1; entered as a stretch goal for late Phase 2.

---

## Success criteria for Phase 1

Phase 1 ships when:

- The user can open CopyClip on this repo (CopyClip itself), ask the three example questions above (and analogous ones), and receive frames structured like Examples A/B/C.
- Every claim in every frame has a verifiable citation (`▸ path:line` or `▸ commit-sha`).
- The frame mutates correctly when a follow-up question is asked — no scroll history, no accumulation.
- Latency: the frame begins streaming text within 5 seconds of `[send]`. Full frame in < 30 seconds for typical questions.
- The hypothesis verdict is recorded: does the LLM-tutor-anchored-to-code model produce explanations that effectively teach? Answer informs whether Phase 2 proceeds, and in what shape.

---

## Related

- Memory: [[copyclip-temporal-causal-wedge]], [[copyclip-personal-tool]], [[voronov-phase-fit]].
- Supersedes: `2026-05-22-anchored-playground-design.md` (v1 spec).
- Open follow-up issue: #114 (multi-language playground execution).
