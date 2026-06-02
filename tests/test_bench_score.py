from copyclip.intelligence.cuaderno.bench.score import (
    question_rollup, scorecard,
)
from copyclip.intelligence.cuaderno.bench.artifact import QuestionRecord


def _rec(**kw):
    base = dict(
        id="q", category="grounded_happy_path", commit_sha="x", question="q",
        question_lang="es", status="answer", verdict={"grounded": True},
        blocks=[], cited_paths=[], citations=[], read_paths=[],
        content_bearing_count=1, answer_lang="es", latency_ms=100,
        input_tokens=10, output_tokens=10, cost_usd=0.0, cost_estimated=True,
        asserts=[], question_rollup={},
    )
    base.update(kw)
    return QuestionRecord(**base)


def test_question_rollup_all_pass():
    res = [{"type": "a", "outcome": "pass"}, {"type": "b", "outcome": "pass"}]
    roll = question_rollup(res)
    assert roll == {"all_pass": True, "n_pass": 2, "n_fail": 0, "n_inconclusive": 0}


def test_question_rollup_fail_blocks_all_pass():
    res = [{"type": "a", "outcome": "pass"}, {"type": "b", "outcome": "fail"},
           {"type": "c", "outcome": "inconclusive"}]
    roll = question_rollup(res)
    assert roll["all_pass"] is False and roll["n_fail"] == 1 and roll["n_inconclusive"] == 1


def test_scorecard_status_distribution_and_abstention_matrix():
    items = [
        # should-answer, answered correctly
        _rec(id="a1", category="grounded_happy_path", status="answer"),
        # should-answer but abstained -> false abstention
        _rec(id="a2", category="grounded_happy_path", status="insufficient_evidence"),
        # should-abstain, abstained correctly
        _rec(id="b1", category="must_abstain", status="insufficient_evidence"),
        # should-abstain but answered -> false answer (fabrication)
        _rec(id="b2", category="must_not_fabricate", status="answer"),
    ]
    sc = scorecard(items)
    assert sc["status_distribution"]["answer"] == 2
    assert sc["status_distribution"]["insufficient_evidence"] == 2
    m = sc["abstention"]
    assert m["false_abstention"] == 1   # a2
    assert m["false_answer"] == 1       # b2
    assert m["correct"] == 2            # a1, b1


def test_scorecard_axis_rate_excludes_none():
    items = [
        _rec(id="r1", verdict={"grounded": True}),
        _rec(id="r2", verdict={"grounded": False}),
        _rec(id="r3", verdict={"grounded": None}),   # excluded
    ]
    sc = scorecard(items)
    # 1 of 2 conclusive -> 0.5
    assert sc["axis_rates"]["grounded"] == 0.5
