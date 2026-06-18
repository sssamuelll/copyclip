"""Heat v2: decision_gap activation-gate.

decision_gap fired on ~200/203 files because this repo barely links decisions —
a project-level documentation fact wearing a per-file costume, saturating the
score. When the PROJECT links no decisions at all, decision_gap is not a per-file
signal: it deactivates (leaves the denominator) instead of firing at 100. When
the project DOES use decisions, a file lacking one is a real gap and still fires.
"""
import sqlite3

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.cognitive_debt import build_debt_breakdown

NOW = 1_700_000_000.0


def _conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    c.execute("INSERT INTO projects(id, root_path, name) VALUES(1,'/p','P')")
    return c


def _file(c, path, module):
    c.execute("INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(1,?,?,?,?,?)", (path, "python", 100, 1.0, "h-" + path))
    c.execute("INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity) VALUES(1,?,?,?,?)", (path, module, "[]", 5))


def _decision_gap(bd):
    return next(f for f in bd["factor_breakdown"] if f["factor_id"] == "decision_gap")


def test_deactivates_when_project_links_no_decisions():
    c = _conn()
    _file(c, "src/a.py", "a")
    bd = build_debt_breakdown(c, 1, "file", "src/a.py", now_ts=NOW)
    dg = _decision_gap(bd)
    assert dg["signal_available"] is False  # project fact, not a per-file signal


def test_fires_per_file_when_project_uses_decisions():
    c = _conn()
    _file(c, "src/a.py", "a")
    _file(c, "src/b.py", "b")
    c.execute("INSERT INTO decisions(project_id,title,summary,status) VALUES(1,'D','x','accepted')")
    c.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(1,'file','src/a.py')")

    a = _decision_gap(build_debt_breakdown(c, 1, "file", "src/a.py", now_ts=NOW))
    b = _decision_gap(build_debt_breakdown(c, 1, "file", "src/b.py", now_ts=NOW))
    assert a["signal_available"] is True and a["normalized_contribution"] == 0.0     # linked
    assert b["signal_available"] is True and b["normalized_contribution"] == 100.0   # real gap


def test_agent_authored_ratio_factor_is_gone():
    c = _conn()
    _file(c, "src/a.py", "a")
    bd = build_debt_breakdown(c, 1, "file", "src/a.py", now_ts=NOW)
    ids = {f["factor_id"] for f in bd["factor_breakdown"]}
    assert "agent_authored_ratio" not in ids  # the dead W4-3 signal is deleted
