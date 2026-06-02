import math
from copyclip.intelligence.cuaderno.bench.regress import mcnemar, paired_property_diff
from copyclip.intelligence.cuaderno.bench.artifact import QuestionRecord


def test_mcnemar_no_discordant_pairs_is_p1():
    res = mcnemar(b=0, c=0)
    assert res["p"] == 1.0 and res["discordant"] == 0


def test_mcnemar_exact_small_counts():
    # b=6, c=0 -> two-sided exact p = 2 * 0.5**6 = 0.03125 (< 0.05).
    # (b=5,c=0 would give 0.0625, NOT significant — the count must be >=6.)
    res = mcnemar(b=6, c=0)
    assert res["method"] == "exact"
    assert res["p"] < 0.05


def test_mcnemar_symmetric_is_not_significant():
    res = mcnemar(b=4, c=4)
    assert res["p"] > 0.5


def test_mcnemar_large_counts_uses_chi2():
    res = mcnemar(b=30, c=10)
    assert res["method"] == "chi2"
    assert 0.0 <= res["p"] <= 1.0


def _rec(rid, category, **kw):
    base = dict(
        id=rid, category=category, commit_sha="x", question="q", question_lang="es",
        status="answer", verdict={}, blocks=[], cited_paths=[], citations=[],
        read_paths=[], content_bearing_count=1, answer_lang="es", latency_ms=1,
        input_tokens=1, output_tokens=1, cost_usd=0.0, cost_estimated=True,
        asserts=[], question_rollup={},
    )
    base.update(kw)
    return QuestionRecord(**base)


def test_paired_property_diff_language_ok():
    # baseline: q1 language_ok True, q2 False ; candidate: q1 True, q2 True (improved)
    base = [_rec("q1", "language_fidelity", verdict={"language_ok": True}),
            _rec("q2", "language_fidelity", verdict={"language_ok": False})]
    cand = [_rec("q1", "language_fidelity", verdict={"language_ok": True}),
            _rec("q2", "language_fidelity", verdict={"language_ok": True})]
    diff = paired_property_diff(base, cand, axis="language_ok")
    assert diff["baseline_rate"] == 0.5 and diff["candidate_rate"] == 1.0
    assert diff["improved"] == 1 and diff["regressed"] == 0
    assert diff["mcnemar"]["c"] == 1  # one fail->pass
