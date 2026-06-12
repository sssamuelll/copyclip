# Kickoff — Walk the path (strategy ①, comprehension benchmark)

> One PR. The spine of the comprehension build: the **static downstream call slice**, honest by construction (the slice IS its citations). From `docs/superpowers/research/2026-06-12-code-comprehension-benchmark.md` strategy #1.

## 1. The wedge this serves

"Walk me through how `X` works end-to-end." Today the tutor answers by chaining `get_callees` by name, hop by hop, narrating the connective tissue — which means the model *assembles* the path and can drift (wrong hop, hallucinated edge, name-collision between two symbols). The benchmark's whole thesis is that this strategy is safe only when the slice is **computed deterministically from the call graph**, so every hop is a real, verifiable citation and the tool narrates nothing the substrate did not witness.

## 2. Locked decisions

1. **New deterministic anchor `anchor.get_call_path`.** It walks `symbol_edges` (`edge_type='calls'`) from an entry symbol, breadth-first, **by `symbol_id`** (never by name — name-walking is ambiguous and not cycle-safe), capped by depth and node count. Returns an ordered list of hops, each carrying a real citation (`file_path` + `line_start..line_end`).
2. **Name is `get_call_path`, NOT `trace_*`.** `trace.py` already exists for *execution* tracing (the playground). This is **static call structure**, and naming it "trace" would imply runtime — the exact honesty trap the council forbade (rendering static topology as observed runtime). The return carries `"kind": "static_call_slice"` and the tool description says STATIC, not execution order.
3. **Honest by construction.** No new substrate. The walk reads the same `symbols`/`symbol_edges` index `get_callees`/`get_module_graph` already read. A missing edge yields a *shorter* slice (acceptable, fails-short not false); a present edge always points at a real indexed symbol with a real citation.
4. **Caps:** `max_depth=4`, `max_nodes=40` (avoid the token-draining fan-out that would hit the round-8 `CLOSING_DIRECTIVE`). `truncated=True` when the node cap is hit; `max_depth` is returned so the tutor can say "limited to depth N".
5. **Ambiguous entry** (same name, multiple symbols): prefer an optional `file` disambiguator, else first by `(file_path, line_start)`, and return `entry_candidates` so the tutor stays honest about which one it walked.
6. **Tutor renders it as an ordered `citation_stack`** — one citation per hop, `note` = the call relationship. **No SequenceDiagram for this** (it duplicates the edge-set in a weaker visual that reads as runtime — benchmark §6 cut). Prompt guidance in `prompts.py`.
7. **The "predict-the-next-hop" gesture is v2.** It needs an in-frame withhold/guess-capture primitive the renderer does not have yet (benchmark §7 open question). v1 ships the honest cited slice; v2 flips one hop from viewing to responding.

## 3. Contract

```
get_call_path(conn, project_id, symbol, *, file=None, max_depth=4, max_nodes=40)
  -> {
       "symbol": <queried name>,
       "entry": {name, kind, file_path, line_start, line_end} | None,
       "entry_candidates": [ {name, file_path, line_start}, ... ],   # only when ambiguous
       "hops": [ {symbol, kind, file_path, line_start, line_end, depth, calls_from}, ... ],
       "kind": "static_call_slice",
       "max_depth": <int>,
       "truncated": <bool>,
       "note": <str>?,    # set when entry is None / nothing to walk
     }
```
- `hops[0]` is the entry itself (`depth=0`, `calls_from=None`); subsequent hops are BFS order.
- A symbol reached twice appears once (first encounter) — cycle-safe, no duplicate citations.

## 4. TDD plan (red → green)

`tests/test_anchor_get_call_path.py`:
- entry resolution + a single downstream hop, hop carries a citation
- transitive multi-hop, depth ordering (0,1,2…)
- cycle is safe (A→B→A terminates, A once)
- `max_depth` bounds the slice
- `max_nodes` truncates (`truncated=True`)
- unknown symbol → `entry=None`, empty hops, `note`
- ambiguous entry lists `entry_candidates`
- `kind == "static_call_slice"`

`tests/test_cuaderno_tool_catalog.py`: add `get_call_path` to the tool-names set (RED) + a dispatch test.

Then: tool def + dispatch in `tool_catalog.py`; guidance in `prompts.py`; verify live on the real repo DB.

## 5. Out of scope (this PR)

Predict-the-next-hop gesture (v2, needs the withhold primitive); `get_last_contact` entry-anchoring (prompt-level, the tutor picks a last-contact file's symbol as entry — no code); upstream/caller slice; tests-in-the-slice enrichment (`find_tests` per hop).
