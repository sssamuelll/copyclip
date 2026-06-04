# Wave 2 — Shell Core: Front Door + Honesty Backbone

**Date:** 2026-06-04
**Status:** Approved (Samuel, 2026-06-04)
**Parent:** `2026-06-04-cuaderno-shell-consensus-design.md` (Wave 2 of 5)

## Goal

Make the cuaderno the front door of `copyclip`, and make the honesty regime (cheap gate + judge) stop being blind to artifacts — **before** any heavy artifact ships (Wave 3 depends on this gate). Also: collapse AskPage, record the dashboard death date.

## Ratified decisions

| Decision | Ruling |
|---|---|
| Front-door positional | **Clean flip.** `copyclip` and `copyclip <folder>` open the shell (start semantics, `--path <folder>`). Export moves entirely behind `copyclip export [folder] [flags]`. A bare invocation carrying export flags errors with the hint `did you mean 'copyclip export'?`. |
| Uncited-artifact confession | **Frame-level note.** Verdict gains `artifacts_cited`; when a frame has widgets and none cites, a provenance line renders under the banner (same 11px register as `provenance_unjudged`). Per-artifact chrome is Wave 3. |
| Citation collection strategy | **Recursive descent** (not per-kind extractors): future widget kinds are covered for free; a per-kind registry would recreate the blind spot the moment someone forgets to register. Per-kind *summarizers* keep a generic fallback so no kind is ever invisible to the judge. |

## 1. Front door

**Files:** `src/copyclip/__main__.py`, `src/copyclip/intelligence/cli.py`, `README.md` (Quick Start mention of `copyclip export`).

- Bare `copyclip` (today: clipboard export on cwd — the `folder` positional defaults to `"."`) and `copyclip <folder>` now run the `start` flow (`--path <folder>`). `copyclip start` keeps working unchanged.
- New `export` subcommand handled in the intelligence dispatch (alongside start/analyze/mcp/bench/report/update): `copyclip export [folder] [all current export flags]` — the existing `main()` export pipeline moves behind it unmodified (scan → minimize → clipboard). No behavior change inside the pipeline itself.
- Export-flag guard: if the bare/positional invocation carries any export-only flag (`--minimize`, `--prompt`, `--preset`, `--extension`, `--include`, `--exclude`, `--only`, `--view`, `--docstrings`, `--with-dependencies`, `--output`, `--print`), exit 2 with: `these flags belong to the export flow — did you mean 'copyclip export'?`.
- Help text: drop "Project Intelligence & Intent Authority … AI-agent governance via MCP"; the prog description becomes the claim ("Keeps you understanding your own codebase while AI agents write most of it.") with the command list updated (`export` documented, examples flipped).

## 2. Honesty backbone

**Files:** `src/copyclip/intelligence/cuaderno/quality.py`, `judge.py`, `tool_catalog.py` (emit_block description), `frontend/src/components/cuaderno/strings.ts`, `frames/FrameDynamic.tsx`, `src/copyclip/intelligence/cuaderno/i18n.py` (only if a backend-authored string needs it — none expected).

Verified blind spot: `_answer_text` reads only `b.data["text"]`; `_cited_paths` walks `citation` / `citations` / `items[].citation` at the top level of `b.data`; widget payloads live under `b.data["widget"]` — invisible to the gate AND the judge today.

### 2a. Citation collection — recursive descent

`_cited_paths` gains a recursive walk over `b.data["widget"]` for widget blocks: any dict carrying `"citation"` (standard shape: `{kind: "path", path, line_start?, line_end?}` / `{kind: "commit", commit}`) or a `"citations"` list contributes to the cited set. Collected paths join the same `cited` set, so the existing fabricated-grounding check (`codey and cited and read and cited.isdisjoint(read)` → `ungrounded`) covers artifacts with **zero new verdict logic**.

### 2b. Judge visibility — `_artifact_summary`

New `_artifact_summary(blocks) -> str`: deterministic textual rendering of widget claims.
- Per-kind summarizers: `graph_subset` → node labels + `A -> B` edge list; `sequence_diagram` → `actor: step text` lines; `callers_tree` → root + caller names.
- Generic fallback for unknown kinds: flatten any `label` / `text` / `name` / `id` string fields found recursively. **No widget kind is ever invisible.**
- `judge_answer` puts `_answer_text(blocks) + "\n\n[ARTIFACTS]\n" + _artifact_summary(blocks)` between the fences (artifact section omitted when there are no widgets).
- **Language detection is untouched**: `assess` keeps using prose-only `_answer_text` (node labels would skew es/en detection).

### 2c. Verdict axis + confession

- `artifacts_cited: Optional[bool]`: `None` = frame has no widgets; `True` = ≥1 widget citation collected; `False` = widgets present, zero citations. **Computed in `_seal`** (compositor.py — the single chokepoint every sealed frame passes through) from the blocks, and injected into whichever verdict dict is being persisted. Verified necessity: `cheap_verdict_dict` and `judge_verdict_dict` REPLACE each other (compositor.py:63/66/260/277) — an axis computed only in the cheap layer would be lost on the judged path, which is the common path for `answer` frames.
- Fail-open: `False` never changes `status` and never blocks — it confesses.
- Frontend: when `frame.verdict?.artifacts_cited === false`, FrameDynamic renders a provenance line (same style/position as the existing `provenance_unjudged` note; both can appear — stack them): es `'los diagramas de esta respuesta no citan código leído'` / en `'the diagrams in this answer cite no read code'` via `strings.ts` key `provenance_artifacts_uncited`.
- `tool_catalog.py` emit_block description: widget primitives that assert something about the code MUST carry a `citation` (standard shape) on the node/step/caller they ground.

## 3. AskPage collapse

**Files:** `frontend/src/pages/AskPage.tsx` (delete), `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`, possibly `src/copyclip/intelligence/server.py` + `frontend/src/api/client.ts` + types.

- Delete AskPage + its sidebar entry (`ask`) + its `Page` union member + router branch.
- `/api/ask` route dies ONLY if a consumer sweep proves AskPage was its sole consumer. `ask_project.py` (the module) is expected to survive — check its other importers (reacquaintance/MCP/server helpers) before touching anything beyond the route. Wave-1 discipline: prove, then cut; quarantine anything with a live consumer.

## 4. Dashboard death date

**Files:** `src/copyclip/roadmap.md`.

Record: the legacy App.tsx router + Sidebar + remaining dashboard pages are deleted in Wave 5, dated **Friday 2026-06-19** (ratified). The escape hatch (cuaderno's existing dashboard toggle) already exists; nothing else changes in Wave 2.

## 5. Bench coverage

**Files:** `src/copyclip/intelligence/cuaderno/bench/asserts.py`.

New assert type `has_artifact`: `{type: "has_artifact", kind?: str, cited?: bool}` — passes when the answer contains ≥1 widget (of `kind` if given; with ≥1 collected citation if `cited: true`). Additive only; the existing corpus rows are untouched → **corpus_sha does not change this wave**.

## 6. Testing (TDD per piece)

- Collector: widget with node citations → paths collected; widget without → empty contribution; nested citation shapes; non-widget blocks unaffected (existing tests stay green).
- Fabricated grounding via widget: code question, ledger read `a.py`, widget citing only `b.py`, no prose citations → `ungrounded`.
- `_artifact_summary`: each of the 3 kinds renders deterministically; unknown kind hits the generic fallback (non-empty).
- Judge fence: answer text includes the `[ARTIFACTS]` section when widgets exist; absent when not.
- Verdict axis: None / True / False across the three frame shapes; persisted verdict round-trips.
- Front door: bare invocation routes to start; positional folder routes to start with that path; export flag on bare invocation exits 2 with the hint; `copyclip export .` runs the old pipeline.
- Frontend: `tsc -b` via `npm --prefix frontend run build` (no test runner, by standing decision).

## Out of scope (later waves)

Per-artifact chrome and runtime states (Wave 3); graph/marimo artifact kinds (Wave 3); absorption of remaining pages (Wave 4); README/roadmap full honesty sweep + MCP rename + legacy shell deletion (Wave 5); `identity_drift_snapshots`/alert-table write-side cleanup (Wave 5).
