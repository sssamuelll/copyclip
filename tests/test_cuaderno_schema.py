from copyclip.intelligence.cuaderno.schema import (
    Citation, Block, Widget, Frame, frame_to_dict, frame_from_dict,
    KNOWN_BLOCK_KINDS, validate_block_dict,
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
