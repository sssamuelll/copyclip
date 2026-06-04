"""Wave-2 honesty backbone: the gate and judge stop being blind to widgets."""
from copyclip.intelligence.cuaderno.quality import _cited_paths, assess
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.schema import Block, FRAME_STATUS_UNGROUNDED


def _widget_block(widget: dict) -> Block:
    return Block.widget(widget)


def _ledger_with_read(path: str) -> ReadLedger:
    """Helper: ledger that has read one content-bearing file at `path`."""
    led = ReadLedger()
    led.record("read_file", {"path": path, "lines": [{"n": 1, "text": "x"}]})
    return led


def test_cited_paths_descends_into_widget_nodes():
    w = {"kind": "graph_subset",
         "nodes": [{"id": "a", "label": "A",
                    "citation": {"kind": "path", "path": "src/a.py"}}],
         "edges": []}
    paths = _cited_paths([_widget_block(w)])
    assert paths == {"src/a.py"}


def test_cited_paths_collects_nested_citations_lists():
    w = {"kind": "future_kind",
         "groups": [{"items": [{"citations": [
             {"kind": "path", "path": "src/deep.py"},
             {"kind": "commit", "commit": "abc123"},  # commit-kind: not a path
         ]}]}]}
    paths = _cited_paths([_widget_block(w)])
    assert paths == {"src/deep.py"}


def test_non_widget_blocks_unchanged():
    b = Block.code_block("x = 1", "python", citation={"kind": "path", "path": "src/x.py"})
    assert _cited_paths([b]) == {"src/x.py"}


def test_fabricated_grounding_via_widget_seals_ungrounded():
    """Code question; ledger read a.py; the ONLY citation in the answer lives
    inside a widget and points at never-read b.py -> ungrounded."""
    ledger = _ledger_with_read("src/a.py")
    w = {"kind": "graph_subset",
         "nodes": [{"id": "b", "citation": {"kind": "path", "path": "src/b.py"}}],
         "edges": []}
    v = assess(question="how does the parser work?",
               blocks=[Block.paragraph("It parses."), _widget_block(w)],
               ledger=ledger)
    assert v.status == FRAME_STATUS_UNGROUNDED
    assert "unread" in v.reason


from copyclip.intelligence.cuaderno.quality import artifacts_cited


def test_artifacts_cited_none_without_widgets():
    assert artifacts_cited([Block.paragraph("hi")]) is None


def test_artifacts_cited_true_with_cited_widget():
    w = {"kind": "graph_subset",
         "nodes": [{"id": "a", "citation": {"kind": "path", "path": "src/a.py"}}],
         "edges": []}
    assert artifacts_cited([_widget_block(w)]) is True


def test_artifacts_cited_false_with_uncited_widget():
    w = {"kind": "graph_subset", "nodes": [{"id": "a"}], "edges": []}
    assert artifacts_cited([_widget_block(w)]) is False


def test_seal_injects_artifacts_cited():
    from copyclip.intelligence.cuaderno.compositor import _seal
    w = {"kind": "graph_subset", "nodes": [{"id": "a"}], "edges": []}
    frame = _seal("q?", [_widget_block(w)], "answer", {"source": "cheap"})
    assert frame["verdict"]["artifacts_cited"] is False
    frame2 = _seal("q?", [Block.paragraph("hi")], "answer", {"source": "cheap"})
    assert frame2["verdict"]["artifacts_cited"] is None


from copyclip.intelligence.cuaderno.quality import _artifact_summary


def test_artifact_summary_graph_subset():
    w = {"kind": "graph_subset",
         "nodes": [{"id": "a", "label": "Parser"}, {"id": "b", "label": "Lexer"}],
         "edges": [{"from": "a", "to": "b"}]}
    s = _artifact_summary([_widget_block(w)])
    assert "Parser" in s and "Lexer" in s and "->" in s


def test_artifact_summary_unknown_kind_falls_back():
    w = {"kind": "never_seen", "things": [{"label": "X9"}, {"name": "Y7"}]}
    s = _artifact_summary([_widget_block(w)])
    assert "X9" in s and "Y7" in s   # generic fallback: nothing is invisible


def test_artifact_summary_empty_without_widgets():
    assert _artifact_summary([Block.paragraph("hi")]) == ""


def test_judge_fence_includes_artifacts():
    """The judge's user message must contain the [ARTIFACTS] section when the
    answer carries widgets."""
    from copyclip.intelligence.cuaderno import judge as judge_mod
    from copyclip.intelligence.cuaderno.read_ledger import ReadLedger

    captured = {}

    class _Client:
        def messages_create(self, **kw):
            captured["user"] = kw["messages"][0]["content"]
            return {"content": [{"type": "text", "text": '{"decision": "ok", "reason": "fine"}'}]}

    ledger = ReadLedger()
    w = {"kind": "graph_subset", "nodes": [{"id": "n", "label": "Compositor"}], "edges": []}
    judge_mod.judge_answer(client=_Client(), question="q?",
                           blocks=[Block.paragraph("answer"), _widget_block(w)],
                           ledger=ledger, model="m")
    assert "[ARTIFACTS]" in captured["user"]
    assert "Compositor" in captured["user"]


def test_judge_fence_no_artifacts_section_without_widgets():
    """Without widgets the fence must NOT contain [ARTIFACTS]."""
    from copyclip.intelligence.cuaderno import judge as judge_mod
    from copyclip.intelligence.cuaderno.read_ledger import ReadLedger

    captured = {}

    class _Client:
        def messages_create(self, **kw):
            captured["user"] = kw["messages"][0]["content"]
            return {"content": [{"type": "text", "text": '{"decision": "ok", "reason": "fine"}'}]}

    ledger = ReadLedger()
    judge_mod.judge_answer(client=_Client(), question="q?",
                           blocks=[Block.paragraph("answer")],
                           ledger=ledger, model="m")
    assert "[ARTIFACTS]" not in captured["user"]
