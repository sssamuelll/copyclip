# Kickoff — "What else does this touch?" (strategy ④, comprehension benchmark)

> One PR. The first generative-friction strategy (predict-then-reveal); opens Phase 2. From `docs/superpowers/research/2026-06-12-code-comprehension-benchmark.md` strategy #4.

## 1. The wedge this serves

"If you changed this signature, which call sites break?" The human PREDICTS the blast radius before the tool reveals it. Generative friction (the testing/pretesting effect) without the playground: the reveal is real, cited static topology, and the human's own guess sitting beside it does the pedagogical work the tool is forbidden to narrate.

## 2. The constraint we must respect

④ is generative — it needs the human to predict *before* the reveal. But the renderer is a single top-down scroll with **no withhold primitive** (§7 open question): a prediction prompt and its reveal in the same answer would print the answer key right below the question. And the §4 honesty line forbids turning any guess-vs-graph gap into a stored/shown number (that rebuilds the refused W4-3 comprehension score).

## 3. Locked decisions

1. **The reveal is a new deterministic anchor `anchor.get_blast_radius(conn, project_id, symbol, *, file=None)`** — honest by construction (the server computes the real radius; the model never assembles or hallucinates the edges). It reuses `get_callers` (the call sites that break on a signature change) and `get_reverse_dependents` (transitively impacted modules) on the symbol's file, returning one cited artifact with counts. `kind="static_blast_radius"`.
2. **The prediction is delivered across TWO turns via the existing `followups` mechanism** — no new surface. Turn 1: the tutor POSES the prediction ("before I show you — which call sites break if you change `X`?") and stops; it does NOT reveal. Turn 2: the human answers in the ask bar, and the tutor calls `get_blast_radius` and reveals. The turn boundary IS the withhold; the answer key never prints under its own question.
3. **Nothing is persisted.** The "witnessed prediction event, logged never scored" the benchmark mentions waits for the deferred witness-event ledger (Lyra's open question). v1 ships the reveal + the generative interaction shape with **zero persistence** — so there is nothing that could be read back as a per-file score. Event-logging arrives only with the ledger, and even then as an event, never a score.
4. **Honesty gate:** the reveal is cited **static topology, NOT runtime** (`kind="static_blast_radius"`; the tutor must say so, never present it as observed execution). A matching prediction proves the guess matched *these cited edges*, **never** "you understand the blast radius." Reverse-dependents are module-level (a directory's reach), callers are symbol-level (exact call sites) — label each for what it is.
5. **No two-state "change-it-and-see"** — `playgroundSlot` is single-slot; relaunch evicts the baseline (§6 cut). The reveal is the cited graph, not a perturbation.

## 4. Contract

```
get_blast_radius(conn, project_id, symbol, *, file=None)
  -> {
       "symbol": <queried name>,
       "entry": {name, kind, file_path, line_start, line_end} | None,
       "entry_candidates": [ {name, file_path, line_start}, ... ],   # only when ambiguous
       "direct_callers":   [ {name, kind, file_path, line_start}, ... ],  # break on signature change
       "caller_count": <int>,
       "impacted_modules": [ "<module>", ... ],   # transitive reverse-dependents
       "target_module": "<module>" | "unknown",
       "module_count": <int>,
       "kind": "static_blast_radius",
       "note": <str>?,    # set when the symbol is not indexed
     }
```

## 5. TDD plan (red → green)

`tests/test_anchor_blast_radius.py`:
- direct callers listed, each with a citation (file + line)
- impacted modules from reverse-dependents on the symbol's file
- `caller_count` / `module_count`
- unknown symbol → `entry=None`, empty, note
- ambiguous entry lists `entry_candidates`
- a leaf symbol in an isolated module → no callers, no impact
- `kind == "static_blast_radius"`

`tests/test_cuaderno_tool_catalog.py`: add `get_blast_radius` to the names set + a dispatch test.

Then: tool def + dispatch; `prompts.py` predict-then-reveal guidance; verify live on the real repo DB.

## 6. Out of scope (this PR)

Persisting the prediction event (waits for the witness-event ledger; even then event-not-score). `find_tests`/`git_archaeology` enrichment of the reveal (the tutor can already call them; the deterministic core is callers + reverse-deps). File-level blast (use the existing `get_reverse_dependents`). Any in-frame curtain / guess-capture surface primitive (the turn boundary is the withhold for now).
