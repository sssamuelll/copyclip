# Kickoff — "Hasn't been back" (strategy ③, comprehension benchmark)

> One PR. The entry cue that closes Phase 1. From `docs/superpowers/research/2026-06-12-code-comprehension-benchmark.md` strategy #3. Launches ① Walk the path (#167) and ② Accepted-not-decided (#168).

## 1. The wedge this serves

The proactive launching point: when the human opens the cuaderno or asks "where do I start / what should I revisit", surface the single most-overdue AI burst they have not returned to — and offer ONE followup that re-derives it (① the call slice, or ② the recorded rationale). The data already exists (Pulso `get_last_contact`); ③ turns it from an on-demand list into the curated, honest entry cue.

## 2. The problem with reusing `get_last_contact` as-is

`get_last_contact` SELECTS candidates by the persisted snapshot (`pulso_last_contact_days IS NOT NULL`) and appends every row — even ones where the LIVE recompute (`build_last_contact`) says the human is already current (it appends with `detail=None`). So it can surface a file as "N days unreturned" when the human came back. For an on-demand list that is a minor quirk; for a **proactive entry cue** it is exactly the comprehension-theater the benchmark warned about ("fires on a file the human revisited yesterday"). The cue must be live-verified.

## 3. Locked decisions

1. **New function `pulso.build_entry_cue(conn, project_id, *, now=None, stale_after_days=14)`** — picks the single most-overdue hasn't-been-back file, or `None` (silent).
2. **Live verdict decides, snapshot only selects.** Candidates come from `pulso_last_contact_days IS NOT NULL`, but each is re-run through `build_last_contact` LIVE; only files where the human genuinely has not returned (non-`None`) survive. Pick the max live `last_contact_days` (tie → path asc).
3. **Analysis-recency gate (the new build).** Each candidate carries the age of its `analysis_file_insights.updated_at` (UTC `CURRENT_TIMESTAMP`) as `analyzed_age_days`, and `stale = analyzed_age_days > stale_after_days`. The cue never asserts a current gap past what the substrate witnessed: when `stale`, the tutor scopes the claim to "as of the last analysis N days ago" instead of stating a present-tense gap. `updated_at` missing → `analyzed_age_days=None`, `stale=False` (no over-claim of staleness).
4. **Honesty gate:** the FILE is stale, never the mind. This is recency + a launch, never a comprehension claim. NULL/absence stays silent.
5. **New anchor `anchor.get_entry_cue(conn, project_id)`** → `{"entry_cue": <dict>|None}`. Tool + dispatch + `prompts.py` guidance: on a cue, emit ONE cited `callout` ("an AI burst shaped `X` ~N days ago; you haven't been back") + ONE `followups` item that launches `get_rationale` or `get_call_path` on that file — **never the playground**. Silent when `None`.

## 4. Contract

```
build_entry_cue(conn, project_id, *, now=None, stale_after_days=14)
  -> {
       "file_path": <posix>,
       "last_contact_days": <int, live>,
       "ai_burst_days": <int, live>,
       "last_contact_source": "git"|"decision"|None,
       "never_human_touched": <bool>,
       "analyzed_age_days": <int>|None,   # age of the file's snapshot
       "stale": <bool>,                   # snapshot older than stale_after_days
     }
   | None    # nothing honest to surface

get_entry_cue(conn, project_id) -> {"entry_cue": <the above>|None}
```

## 5. TDD plan (red → green)

`tests/test_pulso_entry_cue.py`:
- picks the most-overdue file among several live candidates
- skips a file the human RETURNED to (live `None`) even if its snapshot column is a positive number; `None` if it was the only candidate
- silent (`None`) when there are no candidates
- carries `analyzed_age_days` and flips `stale` at the `stale_after_days` threshold
- `updated_at` missing → `analyzed_age_days=None`, `stale=False`

`tests/test_cuaderno_tool_catalog.py`: add `get_entry_cue` to the names set + a dispatch test.

Then: tool def + dispatch; `prompts.py` guidance; verify live on the real repo DB.

## 6. Out of scope (this PR)

Fixing `get_last_contact`'s persisted-vs-live append quirk (separate, has tested behavior — the entry cue sidesteps it by recomputing live). Surfacing the cue automatically in the empty frame (the cue is a tool the tutor invokes on entry/"where do I start"; an always-on frame widget is a later surface change). Multi-file ranked cue list (one launch by design).
