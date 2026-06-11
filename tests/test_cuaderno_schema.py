from copyclip.intelligence.cuaderno.schema import (
    Citation, Block, Widget, Frame, frame_to_dict, frame_from_dict,
    KNOWN_BLOCK_KINDS, validate_block_dict,
    FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED, FRAME_STATUS_LEGACY,
    KNOWN_FRAME_STATUSES,
)


def test_path_citation_round_trip():
    c = Citation(path="src/foo.py", line_start=10, line_end=20)
    d = c.to_dict()
    assert d == {"kind": "path", "path": "src/foo.py", "line_start": 10, "line_end": 20}
    assert Citation.from_dict(d) == c


def test_commit_citation_round_trip():
    c = Citation(commit="a0dae63")
    assert c.to_dict() == {"kind": "commit", "commit": "a0dae63"}
    assert Citation.from_dict({"kind": "commit", "commit": "a0dae63"}) == c


def test_frame_round_trip_full():
    f = Frame(
        question="what does this project do?",
        blocks=[
            Block.lead("CopyClip is a personal tool."),
            Block.paragraph("Three subsystems compose its core."),
            Block.ordered_list([
                {"head": "Analyzer", "desc": "Parses the repo.",
                 "citation": Citation(path="src/foo.py", line_start=1, line_end=50).to_dict()},
            ]),
            Block.code_block(code="def f(): pass", language="python",
                             citation=Citation(path="x.py", line_start=1).to_dict()),
            Block.ascii_block(text="A -> B"),
            Block.citation(citation=Citation(path="x.py").to_dict()),
            Block.citation_stack(items=[
                {"citation": Citation(path="a.py").to_dict(), "note": "fix"},
            ]),
            Block.callout(kicker="key point", text="explanation",
                          citations=[Citation(commit="abc1234").to_dict()]),
            Block.widget(widget=Widget.graph_subset(
                nodes=[{"id": "a", "label": "analyzer.py", "you": False}],
                edges=[],
            ).to_dict()),
            Block.followups(items=[
                {"label": "the analyzer", "question": "explore the analyzer"},
            ]),
        ],
    )
    d = frame_to_dict(f)
    f2 = frame_from_dict(d)
    assert frame_to_dict(f2) == d


def test_validate_block_dict_accepts_known_kind():
    assert validate_block_dict({"kind": "lead", "text": "hi"}) is None
    assert validate_block_dict({"kind": "paragraph", "text": "x"}) is None


def test_validate_block_dict_rejects_unknown_kind():
    reason = validate_block_dict({"kind": "bogus", "text": "x"})
    assert reason is not None and "bogus" in reason


def test_validate_block_dict_rejects_non_object():
    assert validate_block_dict("nope") is not None
    assert validate_block_dict({"text": "no kind"}) is not None


def test_known_block_kinds_matches_constructors():
    assert KNOWN_BLOCK_KINDS == {
        "lead", "paragraph", "ordered_list", "code_block", "ascii_block",
        "citation", "citation_stack", "callout", "widget", "followups",
    }


def test_frame_defaults_to_answer_status():
    f = Frame(question="q", blocks=[Block.lead("hi")])
    assert f.status == FRAME_STATUS_ANSWER


def test_frame_to_dict_includes_status():
    f = Frame(question="q", blocks=[Block.lead("hi")], status=FRAME_STATUS_UNGROUNDED)
    d = frame_to_dict(f)
    assert d["status"] == FRAME_STATUS_UNGROUNDED
    assert d["question"] == "q"
    assert d["blocks"] == [{"kind": "lead", "text": "hi"}]


def test_frame_from_dict_defaults_absent_status_to_legacy():
    legacy = {"question": "q", "blocks": [{"kind": "lead", "text": "hi"}]}
    f = frame_from_dict(legacy)
    assert f.status == FRAME_STATUS_LEGACY


def test_frame_status_round_trip():
    f = Frame(question="q", blocks=[Block.paragraph("p")], status=FRAME_STATUS_UNGROUNDED)
    assert frame_from_dict(frame_to_dict(f)).status == FRAME_STATUS_UNGROUNDED


def test_known_frame_statuses_membership():
    assert FRAME_STATUS_ANSWER in KNOWN_FRAME_STATUSES
    assert FRAME_STATUS_LEGACY in KNOWN_FRAME_STATUSES


def test_off_target_status_known():
    from copyclip.intelligence.cuaderno.schema import (
        FRAME_STATUS_OFF_TARGET, KNOWN_FRAME_STATUSES,
    )
    assert FRAME_STATUS_OFF_TARGET == "off_target"
    assert FRAME_STATUS_OFF_TARGET in KNOWN_FRAME_STATUSES


def test_frame_carries_verdict_round_trip():
    from copyclip.intelligence.cuaderno.schema import Frame, Block, frame_to_dict, frame_from_dict
    vd = {"grounded": True, "responsive": False, "source": "judge"}
    f = Frame(question="q", blocks=[Block.lead("x")], status="off_target", verdict=vd)
    d = frame_to_dict(f)
    assert d["verdict"] == vd and d["status"] == "off_target"
    assert frame_from_dict(d).verdict == vd


def test_frame_verdict_defaults_none_for_legacy():
    from copyclip.intelligence.cuaderno.schema import frame_from_dict
    f = frame_from_dict({"question": "q", "blocks": [{"kind": "lead", "text": "x"}]})
    assert f.verdict is None and f.status == "legacy"


# W4-2: a callout is the cuaderno's claim block; in an evidence-first surface a
# claim without evidence is fabrication, so a callout MUST carry a citation.
def test_callout_without_citation_rejected():
    reason = validate_block_dict({"kind": "callout", "kicker": "risk", "text": "this area is risky"})
    assert reason and "citation" in reason


def test_callout_empty_citations_rejected():
    reason = validate_block_dict({"kind": "callout", "kicker": "k", "text": "t", "citations": []})
    assert reason and "citation" in reason


def test_callout_with_path_citation_ok():
    ok = validate_block_dict({
        "kind": "callout", "kicker": "risk", "text": "churn-heavy",
        "citations": [{"kind": "path", "path": "src/x.py"}],
    })
    assert ok is None


def test_callout_with_commit_citation_ok():
    ok = validate_block_dict({
        "kind": "callout", "kicker": "decision", "text": "anchored",
        "citations": [{"kind": "commit", "commit": "a0dae63"}],
    })
    assert ok is None
