"""What else does this touch (comprehension strategy ④) — the static blast radius.

`get_blast_radius` is the REVEAL half of the predict-then-reveal loop: the call
sites that break if a symbol's signature changes (symbol-level) plus the modules
transitively impacted (reverse-dependents). Honest by construction — the server
computes the real edges; the model never assembles them. It is STATIC topology,
not runtime: a matching prediction matched THESE cited edges, never 'you
understand the blast radius'.
"""
import sqlite3

from copyclip.intelligence.cuaderno.anchor import get_blast_radius
from copyclip.intelligence.db import init_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    cur = conn.execute("INSERT INTO projects(root_path,name) VALUES('/p','P')")
    return conn, int(cur.lastrowid)


def _sym(conn, pid, name, file, ls, le, kind="function"):
    cur = conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
        "VALUES(?,?,?,?,?,?)", (pid, name, kind, file, ls, le))
    return int(cur.lastrowid)


def _calls(conn, pid, frm, to):
    conn.execute(
        "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
        "VALUES(?,?,?,'calls')", (pid, frm, to))


def _module(conn, pid, name, prefix):
    conn.execute("INSERT INTO modules(project_id,name,path_prefix) VALUES(?,?,?)",
                 (pid, name, prefix))


def _dep(conn, pid, frm, to):
    conn.execute(
        "INSERT INTO dependencies(project_id,from_module,to_module,edge_type) "
        "VALUES(?,?,?,'import')", (pid, frm, to))


def test_direct_callers_listed_with_citations():
    conn, pid = _conn()
    x = _sym(conn, pid, "x", "src/core/x.py", 10, 20)
    a = _sym(conn, pid, "a", "src/api/a.py", 1, 5)
    b = _sym(conn, pid, "b", "src/api/b.py", 1, 5)
    _calls(conn, pid, a, x)
    _calls(conn, pid, b, x)
    out = get_blast_radius(conn, pid, "x")
    names = {c["name"] for c in out["direct_callers"]}
    assert names == {"a", "b"}
    a_caller = next(c for c in out["direct_callers"] if c["name"] == "a")
    assert a_caller["file_path"] == "src/api/a.py" and a_caller["line_start"] == 1
    assert out["caller_count"] == 2
    assert out["kind"] == "static_blast_radius"


def test_impacted_modules_from_reverse_dependents():
    conn, pid = _conn()
    _sym(conn, pid, "x", "src/core/x.py", 1, 2)
    _module(conn, pid, "core", "src/core/")
    _module(conn, pid, "api", "src/api/")
    _dep(conn, pid, "api", "core")  # api depends on core -> changing core impacts api
    out = get_blast_radius(conn, pid, "x")
    assert out["target_module"] == "core"
    assert out["impacted_modules"] == ["api"]
    assert out["module_count"] == 1


def test_unknown_symbol_is_silent_with_note():
    conn, pid = _conn()
    out = get_blast_radius(conn, pid, "ghost")
    assert out["entry"] is None
    assert out["direct_callers"] == [] and out["impacted_modules"] == []
    assert "note" in out


def test_leaf_symbol_in_isolated_module_has_no_blast():
    conn, pid = _conn()
    _sym(conn, pid, "lonely", "src/x.py", 1, 2)
    out = get_blast_radius(conn, pid, "lonely")
    assert out["caller_count"] == 0
    assert out["module_count"] == 0


def test_ambiguous_entry_lists_candidates():
    conn, pid = _conn()
    _sym(conn, pid, "f", "src/x.py", 1, 2)
    _sym(conn, pid, "f", "src/y.py", 1, 2)
    out = get_blast_radius(conn, pid, "f")
    assert len(out["entry_candidates"]) == 2
    assert out["entry"]["file_path"] == "src/x.py"  # first by (file_path, line_start)


def test_file_disambiguates_entry():
    conn, pid = _conn()
    _sym(conn, pid, "f", "src/x.py", 1, 2)
    _sym(conn, pid, "f", "src/y.py", 1, 2)
    out = get_blast_radius(conn, pid, "f", file="src/y.py")
    assert out["entry"]["file_path"] == "src/y.py"
    assert out["entry_candidates"] == []
