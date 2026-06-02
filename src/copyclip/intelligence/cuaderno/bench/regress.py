from __future__ import annotations

import math
from typing import Any, Optional

from .artifact import QuestionRecord


def mcnemar(b: int, c: int) -> dict[str, Any]:
    """Paired-difference significance over discordant pairs.

    b = passed-in-baseline, failed-in-candidate (a regression)
    c = failed-in-baseline, passed-in-candidate (an improvement)
    Returns p (two-sided), the method used, and the raw counts.
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "discordant": 0, "p": 1.0, "method": "none"}
    if n < 25:
        # exact two-sided binomial against p=0.5
        k = min(b, c)
        tail = sum(math.comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
        p = min(1.0, 2.0 * tail)
        return {"b": b, "c": c, "discordant": n, "p": round(p, 6), "method": "exact"}
    # chi-square 1 df with continuity correction; survival via erfc
    stat = (abs(b - c) - 1) ** 2 / n
    p = math.erfc(math.sqrt(stat / 2.0))
    return {"b": b, "c": c, "discordant": n, "p": round(p, 6),
            "method": "chi2", "statistic": round(stat, 4)}


def _axis_pass(rec: QuestionRecord, axis: str) -> Optional[bool]:
    """A question 'passes' the axis if the harvested verdict axis is True;
    fails if False; None (unobserved) is excluded from the paired test."""
    return (rec.verdict or {}).get(axis)


def paired_property_diff(baseline: list[QuestionRecord],
                         candidate: list[QuestionRecord],
                         *, axis: str) -> dict[str, Any]:
    """Pair baseline vs candidate by question id on a boolean axis, compute
    rates + improved/regressed counts + McNemar. Questions where either side is
    None (unobserved) are dropped from the paired comparison."""
    by_id_base = {r.id: r for r in baseline}
    by_id_cand = {r.id: r for r in candidate}
    common = [i for i in by_id_base if i in by_id_cand]

    b = c = base_pass = cand_pass = paired = 0
    for i in common:
        pv = _axis_pass(by_id_base[i], axis)
        qv = _axis_pass(by_id_cand[i], axis)
        if pv is None or qv is None:
            continue
        paired += 1
        base_pass += 1 if pv else 0
        cand_pass += 1 if qv else 0
        if pv and not qv:
            b += 1
        elif (not pv) and qv:
            c += 1

    return {
        "axis": axis,
        "paired": paired,
        "baseline_rate": round(base_pass / paired, 4) if paired else None,
        "candidate_rate": round(cand_pass / paired, 4) if paired else None,
        "regressed": b,
        "improved": c,
        "mcnemar": mcnemar(b, c),
    }


# Scope-A honesty banner: without a measured noise floor (Phase B), small deltas
# are not resolvable. Reports embed this so a small green/red is never read as
# significant.
SCOPE_A_CAVEAT = (
    "Scope A: single run per build, no measured noise floor. Only large, "
    "consistent shifts are resolvable; treat a small delta (or a McNemar p that "
    "is not decisive) as NOT a real regression until Phase B measures the floor."
)
