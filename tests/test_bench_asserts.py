from copyclip.intelligence.cuaderno.bench.asserts import (
    AssertContext, run_asserts, ASSERTS,
)
from copyclip.intelligence.cuaderno.bench.artifact import QuestionRecord


def _rec(**kw):
    base = dict(
        id="q", category="c", commit_sha="sha", question="¿cómo?", question_lang="es",
        status="answer", verdict={"grounded": True, "responsive": True,
                                  "language_ok": True, "source": "judge"},
        blocks=[{"kind": "paragraph", "text": "lee compositor.py"}],
        cited_paths=["src/compositor.py"],
        citations=[{"kind": "path", "path": "src/compositor.py",
                    "line_start": 10, "line_end": 20}],
        read_paths=["src/compositor.py"], content_bearing_count=2, answer_lang="es",
        latency_ms=1, input_tokens=1, output_tokens=1, cost_usd=0.0, cost_estimated=True,
    )
    base.update(kw)
    return QuestionRecord(**base)


def _ctx(lengths=None):
    if lengths is None:
        lengths = {"src/compositor.py": 100}
    return AssertContext(file_length_fn=lambda p: lengths.get(p))


def test_status_in_and_is():
    r = _rec(status="answer")
    out = run_asserts(r, [{"type": "status_in", "value": ["answer", "off_target"]},
                          {"type": "status_is", "value": "ungrounded"}], _ctx())
    assert out[0].outcome == "pass"
    assert out[1].outcome == "fail"


def test_cites_path_matching():
    r = _rec()
    ok = run_asserts(r, [{"type": "cites_path_matching", "value": r"compositor\.py$"}], _ctx())[0]
    bad = run_asserts(r, [{"type": "cites_path_matching", "value": r"nope\.py$"}], _ctx())[0]
    assert ok.outcome == "pass" and bad.outcome == "fail"


def test_cites_commit():
    r = _rec(citations=[{"kind": "commit", "commit": "e4400af"}])
    out = run_asserts(r, [{"type": "cites_commit"}], _ctx())[0]
    assert out.outcome == "pass"
    r2 = _rec()  # only a path citation
    out2 = run_asserts(r2, [{"type": "cites_commit"}], _ctx())[0]
    assert out2.outcome == "fail"


def test_mentions():
    r = _rec(blocks=[{"kind": "paragraph", "text": "El Compositor compone frames"}])
    out = run_asserts(r, [{"type": "mentions", "value": "compositor"}], _ctx())[0]
    assert out.outcome == "pass"  # case-folded


def test_language_is():
    r = _rec(answer_lang="es")
    out = run_asserts(r, [{"type": "language_is", "value": "es"},
                          {"type": "language_is", "value": "en"}], _ctx())
    assert out[0].outcome == "pass" and out[1].outcome == "fail"


def test_min_content_bearing_reads():
    r = _rec(content_bearing_count=2)
    out = run_asserts(r, [{"type": "min_content_bearing_reads", "value": 2},
                          {"type": "min_content_bearing_reads", "value": 3}], _ctx())
    assert out[0].outcome == "pass" and out[1].outcome == "fail"


def test_no_unread_citations():
    good = _rec(cited_paths=["a.py"], read_paths=["a.py", "b.py"])
    bad = _rec(cited_paths=["ghost.py"], read_paths=["a.py"])
    assert run_asserts(good, [{"type": "no_unread_citations"}], _ctx())[0].outcome == "pass"
    assert run_asserts(bad, [{"type": "no_unread_citations"}], _ctx())[0].outcome == "fail"


def test_cited_lines_within_eof():
    inside = _rec(citations=[{"kind": "path", "path": "src/compositor.py",
                              "line_start": 10, "line_end": 20}])
    past = _rec(citations=[{"kind": "path", "path": "src/compositor.py",
                            "line_start": 10, "line_end": 999}])
    no_range = _rec(citations=[{"kind": "path", "path": "src/compositor.py"}])
    ctx = _ctx({"src/compositor.py": 100})
    assert run_asserts(inside, [{"type": "cited_lines_within_eof"}], ctx)[0].outcome == "pass"
    assert run_asserts(past, [{"type": "cited_lines_within_eof"}], ctx)[0].outcome == "fail"
    # No line range -> vacuously passes
    assert run_asserts(no_range, [{"type": "cited_lines_within_eof"}], ctx)[0].outcome == "pass"
    # Unknown file length -> inconclusive (cannot verify)
    unk = _ctx({})
    assert run_asserts(inside, [{"type": "cited_lines_within_eof"}], unk)[0].outcome == "inconclusive"


def test_harvested_axes_none_is_inconclusive():
    r_known = _rec(verdict={"responsive": True, "grounded": True})
    r_unknown = _rec(verdict={"responsive": None, "grounded": None, "source": "unjudged"})
    assert run_asserts(r_known, [{"type": "harvested_responsive", "value": True}], _ctx())[0].outcome == "pass"
    assert run_asserts(r_unknown, [{"type": "harvested_responsive", "value": True}], _ctx())[0].outcome == "inconclusive"
    assert run_asserts(_rec(verdict=None), [{"type": "harvested_grounded", "value": True}], _ctx())[0].outcome == "inconclusive"


def test_unknown_assert_type_raises():
    import pytest
    with pytest.raises(KeyError):
        run_asserts(_rec(), [{"type": "no_such_assert"}], _ctx())
