# The cognitive-load doctrine — CopyClip's organizing invariant

**Date:** 2026-06-12
**Authority:** owner reframe + Voronov-led architectural pass (Voronov, Null Vale, Iris Tane). Unanimous; no contradiction (no Axiom-0 needed).

---

## The reframe (the owner's law)

> "It is a code-UNDERSTANDING tool. Whether the human or the AI wrote the code is
> irrelevant. It will always be useful to have a cuaderno-type tool that can
> explain ANY piece of the code or project in a way that LOWERS its level of
> complexity and the cognitive load it generates."

The authorship axis ("did the human write/decide this?") is rejected as the wrong
axis. The wedge "re-own YOUR accepted AI code" is demoted from organizing principle
to one use case. The organizing goal is now: **lower the complexity and cognitive
load of understanding any code, for anyone, regardless of authorship.**

## THE INVARIANT

> **An explanation may reduce only the COST OF REACHING the structure, never the
> structure that must be reached. Every claim is a doorway with a live,
> always-present descent to the cited real code — never a terminus.**

Voronov's test: *legible = lossy compression with a recoverable original; theater =
the same compression sold AS the original. The check is: is the original
recoverable on descent?*

## THE TRAP (never cross it)

**Never measure or optimize "did cognitive load go down."** Load is a state in a
skull, not a property of an utterance — and **a lie lowers load better than the
truth** (the truth has irreducible structure to carry; the lie has none). Optimize
load directly and **comprehension-theater is the global optimum**: a per-explanation
load-delta is W4-3's refused per-file comprehension score, reborn. **Measure the
staircase, never the climber.**

Two faces of the trap (both are "grounded-but-illegible"):
- **FLOAT** — a fluent summary with nothing reachable beneath it. (The classic IOED.)
- **FLOOD** — everything dumped at once (e.g. a 10-citation wall). *Flooding is
  hiding.* This was the live failure on 2026-06-12: high load, taught nothing.

## THE MECHANISM (checkable, honest load-reduction)

Progressive disclosure where **citation density RISES as abstraction falls**:
- the lead carries **exactly one anchor** (a plain sentence that is a citation read
  aloud, every noun true of the cited code — never a paraphrase standing in for one);
- **a descent block exists for every code claim** — no altitude is empty;
- each level **collapses into the one above without losing truth**, reachable in
  bounded steps;
- the descent path is **ALWAYS-PRESENT-THOUGH-COLLAPSED**, never optional/skippable
  — if the real lines are skippable, altitude becomes a lid, not a staircase.

**Enforcement — what is structurally sealable (Level-2 design council, 2026-06-12):**
legibility itself is NOT structurally sealable. By the doctrine's own logic ("never
measure the climber" + "never INFER"), only two things can be enforced: (a) that a
real step EXISTS beneath a claim — grounding, already sealed by `quality.assess`;
and (b) that the answer does not OPEN with the wall — the open-order nudge. FLOAT (a
fluent summary with nothing reachable beneath) is byte-indistinguishable from a
legible answer except by meaning, so it is NOT catchable structurally; FLOOD's
*greeting* is. Everything past that is the climber's judgment and stays prompt-guided
— not a failure, the doctrine being consistent with itself.

The shipped enforcement is `quality.altitude_violation` (+ a one-shot
`altitude_retry`, behind a passing grounding verdict): a code-question answer whose
FIRST block is a `citation_stack` of >=3 items is rejected and re-emitted lead-first.
Block-KIND + item-count only — never reads text, never judges "plain". It is a
NUDGE, not an invariant: it bans the one witnessed FLOOD-greeting (the 10-hop-wall
reveal) and nothing more; a re-flood at block 2 is not caught, and the retry fires
once. `check 2` (reachable descent) and `check 3` (density monotonicity) from the
proposal were CUT — check 2 is grounding (assess owns it) and as written
false-positives the grep/git tolerance assess deliberately protects; check 3 is INFER.

## Fate of the prior doctrine (clarified, not demolished)

- **exposición, no autoría — UNTOUCHED.** It was never an authorship doctrine; it
  is the fluency-vs-structure membrane confession. It loses only the word "autoría"
  and its domain widens to all code.
- **Axiom-0 — UNTOUCHED, now MORE load-bearing.** It becomes the sole governor
  against IOED: the substrate cannot measure load, so the tool must not fake it.
- **W4-3 (no comprehension score) — UNTOUCHED.** The load-delta IS the refused
  score; the prohibition now reads at the per-explanation level.
- **Generative friction (predict/teach-back) — DEMOTED.** From "the only teacher"
  to one optional altitude-mechanism (an interaction shape that makes the descent
  the human's). Honest form intact; primacy gone.

## Consequences for the build

1. Remove the authorship axis everywhere (no "did you write it?" branch).
2. Rebuild the reveal/explanation around altitude: plain anchored lead → structure
   → full cited detail on descent. Neither FLOAT nor FLOOD.
3. Demote teach-back/predict-first to an optional self-test mode, never the spine.
4. The structural floor is grounding (`assess`) + the open-order nudge
   (`altitude_violation`); "every claim is a doorway" past that is prompt-guided,
   because enforcing it would require INFER, which the doctrine forbids.
5. Forbidden forever: any metric/score of "load reduced for this human."
