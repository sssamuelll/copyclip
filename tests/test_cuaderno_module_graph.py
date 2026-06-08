"""get_module_graph: same-namespace topology from symbol_edges, deterministic caps."""
import sqlite3

import pytest

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.cuaderno.anchor import get_module_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(conn):
    conn.execute("INSERT INTO projects(root_path) VALUES('/p')")
    pid = conn.execute("SELECT id FROM projects").fetchone()[0]
    return pid


def _insert_symbol(conn, pid, name, module, file_path):
    cur = conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, "
        "parent_symbol_id, module) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (pid, name, "function", file_path, 1, 5, None, module),
    )
    conn.commit()
    return cur.lastrowid


def _insert_edge(conn, pid, from_id, to_id, edge_type="calls"):
    conn.execute(
        "INSERT INTO symbol_edges(project_id, from_symbol_id, to_symbol_id, edge_type) "
        "VALUES(?, ?, ?, ?)",
        (pid, from_id, to_id, edge_type),
    )
    conn.commit()


@pytest.fixture
def seeded():
    """Project with 3 modules (pkg/a, pkg/b, pkg/c), one symbol each,
    cross-module call edges a->b and a->c."""
    c = sqlite3.connect(":memory:")
    init_schema(c)
    pid = _make_project(c)

    sym_a = _insert_symbol(c, pid, "fn_a", "pkg/a", "pkg/a.py")
    sym_b = _insert_symbol(c, pid, "fn_b", "pkg/b", "pkg/b.py")
    sym_c = _insert_symbol(c, pid, "fn_c", "pkg/c", "pkg/c.py")

    _insert_edge(c, pid, sym_a, sym_b)  # a -> b
    _insert_edge(c, pid, sym_a, sym_c)  # a -> c

    return c, pid


# ---------------------------------------------------------------------------
# Core correctness
# ---------------------------------------------------------------------------

def test_edges_join_modules_and_nodes_carry_files(seeded):
    c, pid = seeded
    g = get_module_graph(c, pid)
    names = {m["name"] for m in g["modules"]}
    assert {"pkg/a", "pkg/b", "pkg/c"} <= names
    assert all(m["file_path"] for m in g["modules"])
    edge_pairs = {(e["from"], e["to"]) for e in g["edges"]}
    assert ("pkg/a", "pkg/b") in edge_pairs
    for e in g["edges"]:
        assert e["from"] in names and e["to"] in names  # no dangling edges, ever
    assert g["truncated"] is False


def test_empty_scope_keeps_directory_granularity(seeded):
    """The whole-project overview (empty scope) stays at DIRECTORY granularity —
    nodes are module names, the right altitude for 'show me the project'."""
    c, pid = seeded
    g = get_module_graph(c, pid)
    names = {m["name"] for m in g["modules"]}
    assert {"pkg/a", "pkg/b", "pkg/c"} <= names      # modules, not file paths
    assert not any(n.endswith(".py") for n in names)


def test_scope_uses_file_granularity_neighborhood(seeded):
    """A SCOPED query drops to FILE granularity: the node the user names is the
    file itself, surrounded by its real-import neighbors. This is the identity
    fix — 'the analyzer' becomes a node, not a directory it dissolves into."""
    c, pid = seeded
    g = get_module_graph(c, pid, scope="pkg/b")
    names = {m["name"] for m in g["modules"]}
    assert "pkg/b.py" in names                       # the focus, as a FILE node
    assert "pkg/a.py" in names                       # its neighbor (a.py -> b.py)
    assert "pkg/c.py" not in names                   # not adjacent — excluded
    assert ("pkg/a.py", "pkg/b.py") in {(e["from"], e["to"]) for e in g["edges"]}


def test_file_node_cites_itself(seeded):
    """A file node's citation is the file itself — never a sibling. (Regression:
    the directory node copyclip/intelligence was cited as agents.py, so 'the
    analyzer' node pointed at a different file.)"""
    c, pid = seeded
    g = get_module_graph(c, pid, scope="pkg/b")
    assert g["modules"]
    assert all(m["name"] == m["file_path"] for m in g["modules"])


def test_scope_resolves_file_by_path(seeded):
    """The focus substring matches a file PATH, so 'analyzer' finds analyzer.py
    directly as its own node."""
    c, pid = seeded
    core = _insert_symbol(c, pid, "run", "svc/core", "svc/special_analyzer.py")
    dep = _insert_symbol(c, pid, "store", "svc/db", "svc/db.py")
    _insert_edge(c, pid, core, dep)
    g = get_module_graph(c, pid, scope="analyzer")
    names = {m["name"] for m in g["modules"]}
    assert "svc/special_analyzer.py" in names        # the file itself is the node
    assert "svc/db.py" in names                       # its neighbor


def test_scope_resolves_file_by_symbol_name(seeded):
    """The focus substring also matches a SYMBOL name, resolving 'around <symbol>'
    to the file that defines it — even when the name is not in the path."""
    c, pid = seeded
    ui = _insert_symbol(c, pid, "special_widget", "svc/ui", "svc/ui.py")
    rend = _insert_symbol(c, pid, "draw", "svc/render", "svc/render.py")
    _insert_edge(c, pid, ui, rend)
    g = get_module_graph(c, pid, scope="special_widget")
    names = {m["name"] for m in g["modules"]}
    assert "svc/ui.py" in names                       # resolved by symbol name
    assert "svc/render.py" in names                   # its neighbor


def test_focus_file_survives_truncation():
    """Under a tight cap the focus FILE node is never pruned for a higher-degree
    neighbor."""
    c = sqlite3.connect(":memory:")
    init_schema(c)
    pid = _make_project(c)
    a = _insert_symbol(c, pid, "fn_a", "pkg/a", "pkg/a.py")  # hub, degree 3
    b = _insert_symbol(c, pid, "fn_b", "pkg/b", "pkg/b.py")
    cc = _insert_symbol(c, pid, "fn_c", "pkg/c", "pkg/c.py")
    d = _insert_symbol(c, pid, "fn_d", "pkg/d", "pkg/d.py")
    _insert_edge(c, pid, a, b)
    _insert_edge(c, pid, a, cc)
    _insert_edge(c, pid, a, d)
    g = get_module_graph(c, pid, scope="pkg/b", max_modules=1)
    assert "pkg/b.py" in {m["name"] for m in g["modules"]}
    assert g["truncated"] is True


def test_scope_no_match_returns_empty(seeded):
    c, pid = seeded
    g = get_module_graph(c, pid, scope="does-not-exist")
    assert g == {"modules": [], "edges": [], "truncated": False}


def test_caps_are_deterministic_and_prune_edges(seeded):
    c, pid = seeded
    g = get_module_graph(c, pid, max_modules=2, max_edges=80)
    assert len(g["modules"]) == 2
    assert g["truncated"] is True
    names = {m["name"] for m in g["modules"]}
    for e in g["edges"]:
        assert e["from"] in names and e["to"] in names


def test_empty_project_returns_empty_graph():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    c.execute("INSERT INTO projects(root_path) VALUES('/p')")
    pid = c.execute("SELECT id FROM projects").fetchone()[0]
    g = get_module_graph(c, pid)
    assert g == {"modules": [], "edges": [], "truncated": False}


def test_edges_include_weight(seeded):
    """Edge dicts must carry a 'weight' key (aggregated call count)."""
    c, pid = seeded
    g = get_module_graph(c, pid)
    for e in g["edges"]:
        assert "weight" in e
        assert e["weight"] >= 1


def test_same_module_edges_are_excluded(seeded):
    """Intra-module edges (from == to) must never appear."""
    c, pid = seeded
    # Add an intra-module edge on pkg/a
    sym_a2 = _insert_symbol(c, pid, "fn_a2", "pkg/a", "pkg/a.py")
    sym_a3 = _insert_symbol(c, pid, "fn_a3", "pkg/a", "pkg/a.py")
    _insert_edge(c, pid, sym_a2, sym_a3)
    g = get_module_graph(c, pid)
    for e in g["edges"]:
        assert e["from"] != e["to"]


# ---------------------------------------------------------------------------
# Dispatcher integration
# ---------------------------------------------------------------------------

def test_dispatch_get_module_graph_not_unknown_tool(seeded):
    """Dispatch must route get_module_graph; must NOT return unknown_tool."""
    c, pid = seeded
    from copyclip.intelligence.cuaderno.tool_catalog import dispatch_tool
    out = dispatch_tool(
        "get_module_graph",
        {},
        project_root="/p",
        project_id=pid,
        conn=c,
    )
    assert "error" not in out, f"dispatch returned error: {out}"
    assert "modules" in out
    assert "edges" in out


def test_dispatch_get_module_graph_scope_arg(seeded):
    """Dispatcher passes scope through; a scoped query yields the file neighborhood."""
    c, pid = seeded
    from copyclip.intelligence.cuaderno.tool_catalog import dispatch_tool
    out = dispatch_tool(
        "get_module_graph",
        {"scope": "pkg/b"},
        project_root="/p",
        project_id=pid,
        conn=c,
    )
    names = {m["name"] for m in out["modules"]}
    assert "pkg/b.py" in names and "pkg/a.py" in names


# ---------------------------------------------------------------------------
# Tool catalog completeness
# ---------------------------------------------------------------------------

def test_tool_definitions_include_get_module_graph():
    from copyclip.intelligence.cuaderno.tool_catalog import build_tool_definitions
    names = {t["name"] for t in build_tool_definitions()}
    assert "get_module_graph" in names


# ---------------------------------------------------------------------------
# ReadLedger content-bearing
# ---------------------------------------------------------------------------

def test_read_ledger_counts_module_graph_as_content_bearing(seeded):
    """A get_module_graph result with non-empty modules is content-bearing."""
    c, pid = seeded
    from copyclip.intelligence.cuaderno.read_ledger import is_content_bearing_read
    result = get_module_graph(c, pid)
    assert result["modules"]  # ensure fixture has content
    assert is_content_bearing_read("get_module_graph", result) is True


def test_read_ledger_empty_module_graph_not_content_bearing():
    """An empty module graph must NOT count as content-bearing."""
    from copyclip.intelligence.cuaderno.read_ledger import is_content_bearing_read
    result = {"modules": [], "edges": [], "truncated": False}
    assert is_content_bearing_read("get_module_graph", result) is False
