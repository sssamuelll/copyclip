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


def _insert_insight(conn, pid, path, debt, module=None):
    """Seed an analysis_file_insights row (a FILE's measured cognitive_debt)."""
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, cognitive_debt) "
        "VALUES(?, ?, ?, ?)",
        (pid, path, module, debt),
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
# Fog: cognitive_debt_score on nodes (W4-3)
# A node's fog must be re-derivable from its own citation. In file mode the node
# IS the file, so its score is that file's measured cognitive_debt. Absence of
# measurement is a TYPED UNKNOWN (None), never 0 — "unmeasured" must never read
# as "low debt".
# ---------------------------------------------------------------------------

def test_file_node_carries_measured_debt_score(seeded):
    c, pid = seeded
    _insert_insight(c, pid, "pkg/b.py", 42.0)
    g = get_module_graph(c, pid, scope="pkg/b")
    node = next(m for m in g["modules"] if m["name"] == "pkg/b.py")
    assert node["cognitive_debt_score"] == 42.0


def test_unmeasured_file_node_score_is_none(seeded):
    """A file with no analysis row carries the key with value None (typed
    unknown), not a fabricated 0 and not an absent key."""
    c, pid = seeded
    _insert_insight(c, pid, "pkg/b.py", 42.0)  # b measured; a is not
    g = get_module_graph(c, pid, scope="pkg/b")
    a = next(m for m in g["modules"] if m["name"] == "pkg/a.py")
    assert "cognitive_debt_score" in a
    assert a["cognitive_debt_score"] is None


def test_analyzed_clean_file_scores_zero_not_none(seeded):
    """A file analyzed and found clean (debt 0.0) is DISTINCT from an unmeasured
    file (None). Absence must never collapse into low debt."""
    c, pid = seeded
    _insert_insight(c, pid, "pkg/b.py", 0.0)
    g = get_module_graph(c, pid, scope="pkg/b")
    node = next(m for m in g["modules"] if m["name"] == "pkg/b.py")
    assert node["cognitive_debt_score"] == 0.0
    assert node["cognitive_debt_score"] is not None


def test_directory_node_cites_max_debt_file():
    """D: a MODULE node cites its MAX-debt file (not the alphabetical MIN), so the
    fog the user sees is re-derivable by opening the very file the node cites —
    the brightest node IS the worst file, and that file is what opens."""
    c = sqlite3.connect(":memory:")
    init_schema(c)
    pid = _make_project(c)
    # module pkg/a has two files; aaa.py is the alphabetical MIN, zzz.py the worst
    a1 = _insert_symbol(c, pid, "fn_a1", "pkg/a", "pkg/a/aaa.py")
    _insert_symbol(c, pid, "fn_a2", "pkg/a", "pkg/a/zzz.py")
    b = _insert_symbol(c, pid, "fn_b", "pkg/b", "pkg/b.py")
    _insert_edge(c, pid, a1, b)  # a -> b keeps pkg/a in the graph
    _insert_insight(c, pid, "pkg/a/aaa.py", 10.0)
    _insert_insight(c, pid, "pkg/a/zzz.py", 90.0)
    g = get_module_graph(c, pid)  # directory mode
    node = next(m for m in g["modules"] if m["name"] == "pkg/a")
    assert node["file_path"] == "pkg/a/zzz.py"        # cites the MAX-debt file
    assert node["cognitive_debt_score"] == 90.0       # fog == that file's debt


def test_directory_module_without_analysis_falls_back_to_min():
    """An unanalyzed module keeps the MIN citation (current behavior) and a typed
    unknown score — never a silent MIN-as-fog leak, never a fabricated 0."""
    c = sqlite3.connect(":memory:")
    init_schema(c)
    pid = _make_project(c)
    a1 = _insert_symbol(c, pid, "fn_a1", "pkg/a", "pkg/a/aaa.py")
    _insert_symbol(c, pid, "fn_a2", "pkg/a", "pkg/a/zzz.py")
    b = _insert_symbol(c, pid, "fn_b", "pkg/b", "pkg/b.py")
    _insert_edge(c, pid, a1, b)
    g = get_module_graph(c, pid)  # no analysis rows at all
    node = next(m for m in g["modules"] if m["name"] == "pkg/a")
    assert node["file_path"] == "pkg/a/aaa.py"        # MIN fallback
    assert node["cognitive_debt_score"] is None       # typed unknown


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
