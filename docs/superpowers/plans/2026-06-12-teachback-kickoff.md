# Kickoff — ⑥ "Say it back" (teach-back), Phase 2 close

**Date:** 2026-06-12
**Strategy:** Comprehension benchmark ⑥ (active recall / teach-back), the last Phase-2 item.
**Decision authority:** the witness-event-ledger junta + Axiom-0 adjudication (2026-06-12).

---

## The honest form (locked by Axiom-0 + Lyra)

Teach-back's load-bearing claim — "you said X but the code does Y" — requires the
system to read *what a human sentence meant* against the code. That is **INFER
reading a mind the tutor swore never to read**; quality.assess closes over CITE∩CITE,
and a teach-back diff has one inferred operand. So the active ingredient (the diff)
**is** the forbidden act. Axiom-0: teach-back ships only as *cited-truth-beside-the-
text-with-silence*. Lyra: the **generative friction IS the lever** — the human
committing an explanation before the reveal is what teaches; **capture is
pedagogically inert theater** and carries doctrine-cost. So we ship the friction,
free, and capture nothing.

## The consequence: ⑥ is NOT an anchor

Every prior strategy (①–⑤) added a server-owned anchor because each had a real
primitive to compute. ⑥ has none:

- The **reveal** is already produced by `get_call_path` (the static cited slice —
  ①) or `read_file`. Server-owned, grounded. No new computation.
- The **prediction/explanation** is the human's, and is **never persisted, never
  scored, never diffed**. Zero substrate touched → zero breach surface.

⑥'s REVEAL is grounded the way ④'s is (a server-owned anchor, the turn boundary
the withhold, nothing about the human stored), and nothing it persists can breach.
But its POSE is NOT honest the way ④'s is — **CORRECTION (Serrano, 2026-06-12):**
④'s pose is PREDICT-from-name/site and needs no prior model; ⑥ shipped a RECALL
pose ("explain in your own words") that presupposes a model the wedge reader —
accepted-but-never-internalized code — does not have. Sharing a reveal anchor does
NOT make them share an honest pose. The first live run proved it (the reader had
nothing to recall). The cognitive-load doctrine
(`docs/superpowers/2026-06-12-cognitive-load-doctrine.md`) supersedes this kickoff:
teach-back is DEMOTED to an optional self-test, re-posed as predict-from-SITE, and
the DEFAULT is to explain by altitude, not to quiz.

## What ships

- **`prompts.py`**: a teach-back bullet in "How to explore", generalizing ④'s
  predict-then-reveal to *explain-it-back*:
  - pose ONE teach-back prompt as a followup ("before I show you — explain how `X`
    works in your own words") and STOP;
  - on the NEXT turn, reveal the cited ground truth (`get_call_path` / `read_file`)
    **beside** their words and let THEM compare;
  - **NEVER** diff the explanation against the code, **NEVER** tell them what they
    missed or got wrong, **NEVER** score or grade it — judging what their sentence
    meant is reading a mind the substrate cannot witness;
  - persist nothing about what they said.
- **`tests/test_cuaderno_prompt.py`**: lock the teach-back honesty invariants
  (the pose exists; the reveal goes *beside*; never-diff / never-score present).

## Deliberately NOT done

- No `recall_pass` event, no ledger, no persistence — Axiom-0: an event table is
  innocent but unnecessary here; the lever is the friction, not the capture.
- No new anchor — the reveal reuses `get_call_path`.
- No structural gate for "didn't score the human" — detecting a score/diff in prose
  is itself INFER; it cannot be a CITE∩CITE gate. The discipline lives in the prompt
  and is backed structurally only by the fact that nothing about the human is
  persisted and every reveal block is already grounded by quality.assess.

## Definition of done

The new prompt tests red→green; full suite green (minus the 3 known local-env
artifacts); PR; squash-merge; sync; memory updated. Phase 2 closes: ①–⑤ + both
honesty gates + ⑥.
