# Kickoff — ⑤ "The plan, reassembled" → `get_commit_change_graph`

**Date:** 2026-06-12
**Strategy:** Comprehension benchmark ⑤ (delocalized-plan stitching), Phase 2.
**Decision authority:** 6-lens roster council (Null Vale, Halberg, Voronov, Serrano, Wren, Cassian) — run `plan-reassembled-council`, 2026-06-12. One BLOCKER, five HIGH, unanimous on a single seam.

---

## The wedge this serves

A solo dev re-owning code an AI wrote and they accepted. An AI burst's change is
*delocalized* — scattered across the tree. Coming back, the human sees the files
one at a time and cannot see the shape of the change. ⑤ lays the cited pieces of
**one commit's change** side by side so the human can reassemble the intent
*in their own head*. The tool exposes witnessed structure; the human supplies
meaning. That division of labor is the doctrine.

## What the council killed, and why

The original design — `get_plan_reassembled`, a "spine" of files bound into "the
plan" — **lies in the noun**, and the lie passes `quality.assess` because every
citation is real:

- **The seam (BLOCKER).** `symbol_edges` is HEAD-state and timeless;
  `file_changes` is historical. The commit selects the *node-set* (witnessed,
  past); a pre-existing *global* edge draws the *line* (witnessed at HEAD, not at
  the burst). "This is the burst's plan structure" is the **unwitnessed product**
  — the *mirror* of the banned co-occurrence glue (temporal selection + timeless
  edge → a temporal membership claim).
- **Edit-set ≠ intent-set (Voronov).** `file_changes(commit)` witnesses what was
  *edited*; "plan" asserts what was *intended*. Planned-but-unedited files vanish;
  incidentally-edited files sharing a HEAD edge get promoted into "the skeleton."
- **Coverage (Halberg, empirical).** Only **45 / 2603** changed files have any
  parsed symbol. **63% (49/78)** of multi-file AI bursts return an empty spine.
  Silence on unparsed files reads as "no relationship" when the truth is "never
  witnessed."
- **The ledger is dead here (Cassian/Halberg).** `decision_refs` is **1-of-283**
  non-silent. A decision-sourced edge can never fire on this repo and cannot be
  TDD'd against real data.
- **Naming (Wren).** "plan" is a mind-state word (the *authoring AI's* intent);
  "reassembled" implies the human now holds it. Both violate the NEVER list.

## The reframe (the locked decision)

**The subject is THE COMMIT — never "the burst," never "the plan."**

The anchor reports: *"Commit `<sha>` (AI-attributed) changed these N files. At
HEAD, here is the cited call graph among them."* Every word is witnessed. The
human knows their squash-merge workflow makes commit ≈ PR ≈ burst — the tool
never makes that leap. This **dissolves the BLOCKER** (no claim crosses the seam)
instead of patching it. Novelty over `get_module_graph`: the node-set is *scoped
to one commit's `file_changes`* (a temporal axis module_graph lacks), partitioned
with coverage + as-of-HEAD provenance.

## Locked contract

```
get_commit_change_graph(conn, project_id, *, commit=None, file=None,
                        max_files=60) -> dict
```

**Burst resolution precedence (Serrano):**
1. `commit=` given → resolve that exact sha or sha-prefix. Not in `commits` →
   `note`, empty graph.
2. else `file=` given → most-recent **AI-attributed** commit touching it
   (`file_changes` JOIN `commits` WHERE `ai_attributed=1` ORDER BY date DESC,
   tie-break sha ASC). None → `note`, empty graph.
3. else (neither) → `note: "pass a commit sha or a file"`, empty graph.
   **No "most-recent AI overall" fallback** — it lands on docs/1-file commits and
   2000+-file import blobs (Halberg). Paths normalized `\\`→`/` like all anchor.py.

**Nodes** = distinct `file_path` in that commit's `file_changes`.

**Edge** between changed files A,B iff a `symbol_edges` (edge_type='calls') row
connects a symbol in A to a symbol in B, **both endpoints among the changed
files**. Reuse `_file_graph`'s edge SQL scoped to the changed set; **do not author
new edge logic** (Cassian). Each edge is **cited** (from-symbol@A:line →
to-symbol@B:line) and carries **`as_of: "head"`** — a non-droppable temporal
qualifier (Null Vale: the edge is a link AT HEAD, never proven AT the burst).

**Partition (honest labels — Wren):**
- `linked`: changed files with ≥1 witnessed as-of-HEAD edge to another changed
  file. (NOT "spine" — that asserts essentialness the substrate never witnessed;
  tests/config can be load-bearing.)
- `co_changed_unlinked`: changed files with no such edge **in the current index**.
  Each carries a `reason`:
  - `not_indexed` — file has **zero** symbols in the index (deleted, non-code
    `.md`/`.json`, or unparsed language). Absence-of-witness, not absence-of-link.
  - `no_edge_in_index` — file HAS symbols but none edges to another changed file
    *in the current index*. Still not "no relationship exists" — the index is
    known-incomplete.
  The label string surfaced is **verbatim**: `"co-changed; no witnessed
  structural link in the current index"`. Never "no structural link exists."

**Coverage (Halberg — required for Axiom-0):** return `changed_file_count` and
`indexed_file_count` (files with ≥1 symbol) so an empty `linked` reads as
"index incomplete," never "files unrelated."

**Caps:** `linked` + `co_changed_unlinked` capped at `max_files` total; set
`truncated: true` if exceeded (import-blob guard).

**`kind: "static_change_graph"`** — keeps the family's anti-runtime `static_`
prefix (`static_call_slice`, `static_blast_radius`); drops "plan". The docstring
+ tool description carry the family's anti-runtime sentence: *static intra-commit
topology, NOT execution order, NOT a held plan.*

**Return shape** (flat `edges` list — each inter-changed-file edge cited once,
matching the `get_module_graph` nodes+edges family, rather than per-file nesting):
```python
{
  "commit": {"sha","date","message","ai_attributed"} | None,
  "resolved_via": "commit" | "file" | None,
  "changed_file_count": int,
  "indexed_file_count": int,
  "linked": [file_path, ...],                  # files with >=1 inter-changed edge
  "edges": [{"from_file","from_symbol","from_line",
             "to_file","to_symbol","to_line","as_of":"head"}, ...],
  "co_changed_unlinked": [{"file_path","reason"}, ...],
  "kind": "static_change_graph",
  "truncated": bool,
  "note": str?,   # only when the burst could not be resolved
}
```

## Cut to POST-SHIP (Cassian)

- **`decision_ref` edge source** — 1-of-283 on this repo, untestable against real
  data. v0.1 rests on `symbol_edges` only. (When the ledger comes alive — the
  recurring substrate gap from ② — add it, typed distinctly, NOT `static_`.)
- **Git-diff burst-scoped edges** (Null Vale's only-honest-witness path): parse
  the commit's own diff for a reference *textually introduced in this commit* that
  resolves to a symbol in another changed file — the sole way to witness "this
  burst created this link." Real, but expensive (diff parse + ref resolution) and
  still bounded by the 45/2603 coverage. Defer; name it as the upgrade.
- **Multi-commit union** ("these 3 commits were one burst" is itself inference).
  Resolve-one-commit-and-stop.

## NEVER (additions for this anchor)

- Never call the result "the plan" or say it is "reassembled" — the subject is the
  **commit**; the human reassembles intent themselves.
- Never drop the `as_of: "head"` stamp from an edge or render it as burst-internal.
- Never let `co_changed_unlinked` read as "no structural link exists" — only "none
  in the current index."
- Never render the graph as execution/authoring order (static topology).
- Never surface `additions`/`deletions`, edge weights, or any ranking — one step
  from a refused per-file number.

## Red tests (write first, watch fail)

1. `linked` files carry **cited** edges (from/to symbol + line), `as_of="head"`.
2. A co-changed file with symbols but no inter-changed-file edge →
   `co_changed_unlinked` reason `no_edge_in_index`.
3. A co-changed file with **zero** symbols → reason `not_indexed`.
4. Resolution by explicit `commit=` (sha-prefix).
5. Resolution by `file=` picks the most-recent **AI** commit touching it.
6. `commit=` precedence when both passed.
7. Neither passed → `note`, empty graph, no crash.
8. `file=` with no AI commit → `note`, empty graph.
9. Coverage counts: `changed_file_count` / `indexed_file_count` correct.
10. Single-file commit → no edges, the one file in `co_changed_unlinked`.
11. `kind == "static_change_graph"`; `max_files` truncation sets `truncated`.

## Wiring (after green)

- `tool_catalog.py`: definition (description encodes commit-not-plan,
  as-of-HEAD, coverage, anti-runtime) + dispatch branch + names-set test.
- `prompts.py`: "How to explore" bullet — emit `linked` as a cited
  `citation_stack` / module-graph-style block, surface coverage when `linked`
  empty, stamp as-of-HEAD, NEVER say "the plan," launchable from a
  `get_entry_cue`/`get_last_contact` file.
- `test_cuaderno_tool_catalog.py`: add `get_commit_change_graph` to the names
  set + a dispatch test.

## Definition of done

Strict TDD green; full suite (minus 3 known local-env artifacts); live-verified on
`./.copyclip/intelligence.db` (the 4-file `88e7358567` burst → full `linked`; the
24-file `203ea885c0` teardown → all `co_changed_unlinked` with honest reasons);
PR; squash-merge on green; sync main; delete branch; memory updated.
