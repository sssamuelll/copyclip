# Kickoff — "Accepted, not decided" (strategy ②, comprehension benchmark)

> One PR. The wedge in one cited sentence. From `docs/superpowers/research/2026-06-12-code-comprehension-benchmark.md` strategy #2. Pairs with ① Walk the path (#167).

## 1. The wedge this serves

"Why does this exist? / Why was it done this way?" For AI-burst code the honest answer is often: *there is no recorded why — you accepted it, you did not decide it.* Today the tutor can recover decisions (`get_decisions`, `git_archaeology`) but nothing **deterministically** distinguishes *recovered intent* from *absence of intent* — so a model can paraphrase a plausible purpose and it passes every `quality.assess` check (null-vale's central trap: a confident invented "why" is the highest-authority comprehension-theater).

## 2. Locked decisions

1. **New deterministic anchor `anchor.get_rationale(conn, project_id, file)`** (DB-only, like `get_last_contact`). It computes a **verdict the system owns, not the model**: does recorded rationale exist for this file?
2. **The verdict is the absence-gate** (the "modeled on `_floored_frame`" build the benchmark called the only mandatory new work in Phase 1). It is computed in Python from the ledger, so "accepted, not decided" is **honest by construction** — the model surfaces a constant string, it does not author the judgment.
3. **Recorded rationale = a decision references the file** — directly (`decision_refs` `ref_type='file'`, the trustworthy edge per Pulso v0.2.1) OR via a commit that touched the file (`ref_type='commit'`). Commit *messages* are history, not deliberation; they do not count as "decided."
4. **Three verdicts:**
   - `recovered` — ≥1 decision references the file → present them cited.
   - `accepted_not_decided` — the file has commits but **no** decision → stamp the constant. `ai_shaped` (any `commits.ai_attributed` touched it) is surfaced so the tutor can say "an AI burst shaped it", cited.
   - `untracked` — no commits and no decisions → a note, **no stamp** (we cannot prove it was even accepted).
5. **The stamp is a module constant**, the single source of truth, exact benchmark phrasing: `"no recorded rationale; this was accepted, not decided."`
6. **No timestamp fix.** The benchmark flagged a `decision_history` `CURRENT_TIMESTAMP` (local) vs ISO-8601 UTC mismatch. **Verified empirically as a non-bug:** SQLite `CURRENT_TIMESTAMP` is UTC (not local); `pulso._parse_git_iso` already normalizes it to aware-UTC and orders correctly against git dates. The premise ("CURRENT_TIMESTAMP is local") was false. Documented, not patched.
7. **Tutor rendering:** recovered decisions as a cited `citation_stack` ("this exists because…"); when `accepted_not_decided`, **one** `callout` carrying the stamp verbatim; NEVER invent a why. Guidance in `prompts.py`.

## 3. Contract

```
get_rationale(conn, project_id, file)
  -> {
       "file": <posix path>,
       "decisions": [ {id, title, status, source_type, summary, matched_via:"file"|"commit"}, ... ],
       "commits":   [ {sha, author, date, message, ai_attributed}, ... ],   # cited by sha
       "has_recorded_rationale": <bool>,
       "ai_shaped": <bool>,
       "verdict": "recovered" | "accepted_not_decided" | "untracked",
       "stamp": "no recorded rationale; this was accepted, not decided." | None,
     }
```

## 4. TDD plan (red → green)

`tests/test_anchor_get_rationale.py`:
- recovers a direct `file`-ref decision (`matched_via="file"`, verdict `recovered`, stamp None)
- recovers a `commit`-ref decision for a commit that touched the file (`matched_via="commit"`)
- `accepted_not_decided` when commits (incl. AI) touched the file but no decision → stamp == constant
- `ai_shaped` True iff an `ai_attributed` commit touched it
- `untracked` when no commits and no decisions → stamp None
- the stamp equals the exact benchmark phrasing (a regression lock on the wording)
- commits cited by sha

`tests/test_cuaderno_tool_catalog.py`: add `get_rationale` to the names set + a dispatch test.

Then: tool def + dispatch; `prompts.py` guidance; verify live on the real repo DB.

## 5. Out of scope (this PR)

**Compositor-level enforcement** of the absence-gate (rejecting/resealing a frame where the model emits a "why" claim about an `accepted_not_decided` file) — the bulletproof version null-vale wants; it touches the `quality.assess`/`_floored_frame` grounding loop and is the explicit hardening follow-up. This PR ships the deterministic *verdict* (the honest primitive) + strong prompt instruction. Also out: symbol-level rationale (file granularity only); the `decision_links` glob path (fuzzy, excluded by design).
