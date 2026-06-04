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
