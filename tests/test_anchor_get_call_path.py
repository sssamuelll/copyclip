"""Walk the path (comprehension strategy ①) — the static downstream call slice.

`get_call_path` walks `symbol_edges` (edge_type='calls') from an entry symbol,
breadth-first, BY symbol_id (cycle-safe, name-collision-safe), capped. Every hop
carries a real citation — the slice IS its citations. It is STATIC call
structure, never a runtime/execution trace.
"""
import sqlite3

from copyclip.intelligence.cuaderno.anchor import get_call_path
from copyclip.intelligence.db import init_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    cur = conn.execute("INSERT INTO projects(root_path,name) VALUES('/p','P')")
    return conn, int(cur.lastrowid)


def _sym(conn, pid, name, file, ls, le, kind="function"):
    cur = conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
        "VALUES(?,?,?,?,?,?)",
        (pid, name, kind, file, ls, le),
    )
    return int(cur.lastrowid)


def _calls(conn, pid, frm, to):
    conn.execute(
        "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
        "VALUES(?,?,?,'calls')",
        (pid, frm, to),
    )


def test_single_hop_carries_a_real_citation():
    conn, pid = _conn()
    a = _sym(conn, pid, "a", "src/a.py", 1, 5)
    b = _sym(conn, pid, "b", "src/b.py", 10, 20)
    _calls(conn, pid, a, b)
    out = get_call_path(conn, pid, "a")
    assert [h["symbol"] for h in out["hops"]] == ["a", "b"]
    b_hop = out["hops"][1]
    assert b_hop["file_path"] == "src/b.py"
    assert b_hop["line_start"] == 10 and b_hop["line_end"] == 20
    assert b_hop["depth"] == 1 and b_hop["calls_from"] == "a"
    assert out["entry"]["name"] == "a"
    assert out["kind"] == "static_call_slice"


def test_entry_is_hop_zero():
    conn, pid = _conn()
    a = _sym(conn, pid, "a", "src/a.py", 1, 5)
    out = get_call_path(conn, pid, "a")
    assert out["hops"][0]["symbol"] == "a"
    assert out["hops"][0]["depth"] == 0
    assert out["hops"][0]["calls_from"] is None


def test_transitive_walk_is_depth_ordered():
    conn, pid = _conn()
    a = _sym(conn, pid, "a", "f.py", 1, 2)
    b = _sym(conn, pid, "b", "f.py", 3, 4)
    c = _sym(conn, pid, "c", "f.py", 5, 6)
    _calls(conn, pid, a, b)
    _calls(conn, pid, b, c)
    out = get_call_path(conn, pid, "a")
    assert [h["symbol"] for h in out["hops"]] == ["a", "b", "c"]
    assert [h["depth"] for h in out["hops"]] == [0, 1, 2]


def test_cycle_is_safe():
    conn, pid = _conn()
    a = _sym(conn, pid, "a", "f.py", 1, 2)
    b = _sym(conn, pid, "b", "f.py", 3, 4)
    _calls(conn, pid, a, b)
    _calls(conn, pid, b, a)  # back-edge
    out = get_call_path(conn, pid, "a")
    assert [h["symbol"] for h in out["hops"]] == ["a", "b"]  # a appears once
    assert out["truncated"] is False


def test_max_depth_bounds_the_slice():
    conn, pid = _conn()
    prev = _sym(conn, pid, "n0", "f.py", 1, 1)
    for i in range(1, 5):  # n0 -> n1 -> n2 -> n3 -> n4
        cur = _sym(conn, pid, f"n{i}", "f.py", i + 1, i + 1)
        _calls(conn, pid, prev, cur)
        prev = cur
    out = get_call_path(conn, pid, "n0", max_depth=2)
    assert [h["symbol"] for h in out["hops"]] == ["n0", "n1", "n2"]
    assert out["max_depth"] == 2


def test_max_nodes_truncates():
    conn, pid = _conn()
    a = _sym(conn, pid, "a", "f.py", 1, 1)
    for nm, ln in (("b", 2), ("c", 3), ("d", 4)):
        s = _sym(conn, pid, nm, "f.py", ln, ln)
        _calls(conn, pid, a, s)
    out = get_call_path(conn, pid, "a", max_nodes=2)
    assert len(out["hops"]) == 2  # entry + one callee
    assert out["truncated"] is True


def test_depth_cap_is_flagged_when_callees_lie_below():
    conn, pid = _conn()
    prev = _sym(conn, pid, "n0", "f.py", 1, 1)
    for i in range(1, 4):  # n0 -> n1 -> n2 -> n3
        cur = _sym(conn, pid, f"n{i}", "f.py", i + 1, i + 1)
        _calls(conn, pid, prev, cur)
        prev = cur
    out = get_call_path(conn, pid, "n0", max_depth=2)
    # n2 sits at the depth limit but still calls n3 (not shown) -> honest flag
    assert out["depth_capped"] is True


def test_no_depth_cap_when_slice_is_complete():
    conn, pid = _conn()
    a = _sym(conn, pid, "a", "f.py", 1, 1)
    b = _sym(conn, pid, "b", "f.py", 2, 2)  # leaf
    _calls(conn, pid, a, b)
    out = get_call_path(conn, pid, "a")
    assert out["depth_capped"] is False


def test_unknown_symbol_is_silent_with_a_note():
    conn, pid = _conn()
    out = get_call_path(conn, pid, "ghost")
    assert out["entry"] is None
    assert out["hops"] == []
    assert "note" in out


def test_symbol_with_no_callees():
    conn, pid = _conn()
    _sym(conn, pid, "leaf", "f.py", 1, 2)
    out = get_call_path(conn, pid, "leaf")
    assert [h["symbol"] for h in out["hops"]] == ["leaf"]
    assert out["truncated"] is False


def test_ambiguous_entry_lists_candidates():
    conn, pid = _conn()
    f1 = _sym(conn, pid, "f", "src/x.py", 1, 2)
    _sym(conn, pid, "f", "src/y.py", 1, 2)
    g = _sym(conn, pid, "g", "src/g.py", 1, 2)
    _calls(conn, pid, f1, g)
    out = get_call_path(conn, pid, "f")
    assert len(out["entry_candidates"]) == 2
    # walked the first by (file_path, line_start) -> src/x.py
    assert out["entry"]["file_path"] == "src/x.py"


def test_file_disambiguates_entry():
    conn, pid = _conn()
    _sym(conn, pid, "f", "src/x.py", 1, 2)
    _sym(conn, pid, "f", "src/y.py", 1, 2)
    out = get_call_path(conn, pid, "f", file="src/y.py")
    assert out["entry"]["file_path"] == "src/y.py"
    assert out["entry_candidates"] == []
