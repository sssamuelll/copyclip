from __future__ import annotations

import statistics
from typing import Any

from .artifact import QuestionRecord

_ABSTAIN_CATEGORIES = {"must_abstain", "must_not_fabricate"}
_ABSTAIN_STATUSES = {"ungrounded", "insufficient_evidence"}
_AXES = ("grounded", "responsive", "language_ok")


def question_rollup(assert_results: list[dict]) -> dict:
    n_pass = sum(1 for a in assert_results if a["outcome"] == "pass")
    n_fail = sum(1 for a in assert_results if a["outcome"] == "fail")
    n_incon = sum(1 for a in assert_results if a["outcome"] == "inconclusive")
    return {"all_pass": n_fail == 0 and n_pass > 0 or (n_fail == 0 and n_incon == 0),
            "n_pass": n_pass, "n_fail": n_fail, "n_inconclusive": n_incon}


def _rate(items, axis):
    vals = [(it.verdict or {}).get(axis) for it in items]
    conclusive = [v for v in vals if v is not None]
    if not conclusive:
        return None
    return round(sum(1 for v in conclusive if v) / len(conclusive), 4)


def scorecard(items: list[QuestionRecord]) -> dict[str, Any]:
    status_dist: dict[str, int] = {}
    for it in items:
        status_dist[it.status] = status_dist.get(it.status, 0) + 1

    # Abstention confusion matrix
    false_abstention = false_answer = correct = 0
    for it in items:
        should_abstain = it.category in _ABSTAIN_CATEGORIES
        abstained = it.status in _ABSTAIN_STATUSES
        if should_abstain and abstained:
            correct += 1
        elif (not should_abstain) and (not abstained):
            correct += 1
        elif should_abstain and not abstained:
            false_answer += 1
        else:  # should answer but abstained
            false_abstention += 1

    latencies = [it.latency_ms for it in items if it.latency_ms]
    costs = [it.cost_usd for it in items]
    any_estimated = any(it.cost_estimated for it in items)

    n = len(items)
    all_pass = sum(1 for it in items if it.question_rollup.get("all_pass"))

    return {
        "n_questions": n,
        "all_pass_rate": round(all_pass / n, 4) if n else 0.0,
        "status_distribution": status_dist,
        "axis_rates": {ax: _rate(items, ax) for ax in _AXES},
        "abstention": {"correct": correct, "false_abstention": false_abstention,
                       "false_answer": false_answer},
        "n_inconclusive_questions": sum(1 for it in items
                                        if it.question_rollup.get("n_inconclusive", 0) > 0),
        "latency_ms": {
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "p90": round(_p90(latencies), 1) if latencies else None,
        },
        "cost_usd": {"total": round(sum(costs), 6), "estimated": any_estimated},
    }


def _p90(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, int(round(0.9 * (len(s) - 1))))
    return s[k]
