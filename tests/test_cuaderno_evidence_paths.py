"""Wave-3 gate fix: paths returned by evidence tools count as comparable —
a DB-grounded graph citation must not be condemned as fabricated."""
from copyclip.intelligence.cuaderno.quality import assess
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.schema import Block, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED


def test_ledger_harvests_file_paths_from_tool_results():
    led = ReadLedger()
    led.record("get_callers", {"callers": [
        {"name": "f", "kind": "function", "file_path": "src/a.py", "line_start": 3},
        {"name": "g", "kind": "function", "file_path": "src/b.py", "line_start": 9},
    ]})
    assert {"src/a.py", "src/b.py"} <= led.evidence_paths
    assert led.read_paths == set()   # read_paths stays read_file/list_dir-only


def test_ledger_harvests_module_graph_paths():
    led = ReadLedger()
    led.record("get_module_graph", {"modules": [
        {"name": "copyclip/intelligence", "file_path": "src/copyclip/intelligence/db.py"},
    ], "edges": [], "truncated": False})
    assert "src/copyclip/intelligence/db.py" in led.evidence_paths


def test_error_results_not_harvested():
    led = ReadLedger()
    led.record("get_callers", {"error": "boom", "callers": [{"file_path": "src/x.py"}]})
    assert led.evidence_paths == set()


def test_db_grounded_widget_citation_is_not_condemned():
    """read one file + cite a tool-evidenced other via a widget -> answer, not ungrounded."""
    led = ReadLedger()
    led.record("read_file", {"path": "src/x.py", "lines": [{"n": 1, "text": "x"}]})
    led.record("get_callers", {"callers": [
        {"name": "f", "kind": "function", "file_path": "src/a.py", "line_start": 3}]})
    w = {"kind": "graph_view",
         "nodes": [{"id": "a", "label": "a", "citation": {"kind": "path", "path": "src/a.py"}}],
         "edges": []}
    v = assess(question="how does a work?",
               blocks=[Block.paragraph("so..."), Block.widget(w)], ledger=led)
    assert v.status == FRAME_STATUS_ANSWER


def test_true_fabrication_still_seals():
    """citing a path NEITHER read NOR tool-evidenced still seals ungrounded."""
    led = ReadLedger()
    led.record("read_file", {"path": "src/x.py", "lines": [{"n": 1, "text": "x"}]})
    b = Block.code_block("y", "python", citation={"kind": "path", "path": "src/never.py"})
    v = assess(question="how does y work?", blocks=[b], ledger=led)
    assert v.status == FRAME_STATUS_UNGROUNDED
