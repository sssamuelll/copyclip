import os
import textwrap

from copyclip.intelligence.capture import StepThroughResponse, Step
from copyclip.intelligence import playground as pg
from copyclip.intelligence.playground import ResolvedFunction


def test_to_dict_includes_junctions():
    resp = StepThroughResponse(
        trace=[Step(line=3, event="line", changed=[], scope=[])],
        source_lines=[{"num": 3, "text": "if x:"}],
        func_name="f", file_line="a.py:2", truncated=False, truncated_reason=None,
        junctions=[{"test_line": 3, "arms": [{"kind": "if", "lines": [4, 4], "taken": True}]}],
    )
    d = resp.to_dict()
    assert d["junctions"] == [{"test_line": 3, "arms": [{"kind": "if", "lines": [4, 4], "taken": True}]}]


def test_to_dict_junctions_defaults_empty():
    resp = StepThroughResponse(
        trace=[], source_lines=[], func_name="f", file_line="a.py:1",
        truncated=False, truncated_reason=None,
    )
    assert resp.to_dict()["junctions"] == []


def test_junctions_for_reads_file_and_computes(tmp_path):
    src = textwrap.dedent(
        """\
        def f(x):
            if x > 0:
                a = 1
            else:
                a = -1
            return a
        """
    )
    (tmp_path / "m.py").write_text(src, encoding="utf-8")
    resolved = ResolvedFunction(
        file="m.py", name="f", qualname="f", kind="function",
        module="m", line_start=1, parent_class=None,
    )
    j = pg._junctions_for(resolved, str(tmp_path), {2, 3, 6}, False)
    assert j == [{"test_line": 2, "arms": [
        {"kind": "if", "lines": [3, 3], "taken": True},
        {"kind": "else", "lines": [5, 5], "taken": False},
    ]}]


def test_junctions_for_missing_file_returns_empty():
    resolved = ResolvedFunction(
        file="nope.py", name="f", qualname="f", kind="function",
        module="m", line_start=1, parent_class=None,
    )
    assert pg._junctions_for(resolved, os.getcwd(), {1}, False) == []
