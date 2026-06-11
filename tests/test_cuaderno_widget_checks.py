"""Emit-time verification: graphs must be subsets of this turn's evidence;
playground recipes must pass launch-grade validation at emit."""
from copyclip.intelligence.cuaderno.widget_checks import (
    validate_widget_payload, GraphEvidence)


def _ev():
    ev = GraphEvidence()
    ev.add_module_graph({"modules": [{"name": "pkg/a", "file_path": "src/pkg/a.py"},
                                     {"name": "pkg/b", "file_path": "src/pkg/b.py"}],
                         "edges": [{"from": "pkg/a", "to": "pkg/b", "weight": 1}],
                         "truncated": False})
    return ev


def test_graph_subset_passes():
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a", "citation": {"kind": "path", "path": "src/pkg/a.py"}},
                   {"id": "pkg/b", "label": "b", "citation": {"kind": "path", "path": "src/pkg/b.py"}}],
         "edges": [{"from": "pkg/a", "to": "pkg/b"}]}
    assert validate_widget_payload({"kind": "widget", "widget": w}, _ev()) is None


def test_invented_edge_rejected():
    # Nodes carry citations so the membership+citation checks pass and only the
    # edge-membership check fires — isolating exactly what this test claims.
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a", "citation": {"kind": "path", "path": "src/pkg/a.py"}},
                   {"id": "pkg/b", "label": "b", "citation": {"kind": "path", "path": "src/pkg/b.py"}}],
         "edges": [{"from": "pkg/b", "to": "pkg/a"}]}   # reversed: not in evidence
    reason = validate_widget_payload({"kind": "widget", "widget": w}, _ev())
    assert reason and "edge" in reason


def test_invented_node_rejected():
    w = {"kind": "graph_view", "nodes": [{"id": "pkg/zz", "label": "zz"}], "edges": []}
    reason = validate_widget_payload({"kind": "widget", "widget": w}, _ev())
    assert reason and "node" in reason


def test_callers_evidence_admits_symbol_edges():
    ev = GraphEvidence()
    ev.add_callers("parse", {"callers": [
        {"name": "main", "kind": "function", "file_path": "src/m.py", "line_start": 2}]})
    w = {"kind": "graph_view",
         "nodes": [{"id": "main", "label": "main", "citation": {"kind": "path", "path": "src/m.py"}},
                   {"id": "parse", "label": "parse", "citation": {"kind": "path", "path": "src/parse.py"}}],
         "edges": [{"from": "main", "to": "parse"}]}
    assert validate_widget_payload({"kind": "widget", "widget": w}, ev) is None


def test_bad_recipe_rejected_at_emit():
    w = {"kind": "playground",
         "function_ref": {"file": "../etc/x.py", "name": "f"}, "breadcrumb": "b"}
    reason = validate_widget_payload({"kind": "widget", "widget": w}, GraphEvidence())
    assert reason and "function_ref" in reason


def test_good_recipe_passes():
    w = {"kind": "playground",
         "function_ref": {"file": "src/pkg/a.py", "name": "f", "line": 3},
         "breadcrumb": "b",
         "citation": {"kind": "path", "path": "src/pkg/a.py", "line_start": 3}}
    assert validate_widget_payload({"kind": "widget", "widget": w}, GraphEvidence()) is None


def test_non_graph_widgets_unaffected():
    w = {"kind": "sequence_diagram", "actors": [], "steps": []}
    assert validate_widget_payload({"kind": "widget", "widget": w}, GraphEvidence()) is None


def test_uncited_node_rejected():
    ev = _ev()
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a"}],   # in evidence, but no citation
         "edges": []}
    reason = validate_widget_payload({"kind": "widget", "widget": w}, ev)
    assert reason and "citation" in reason


# ---------------------------------------------------------------------------
# STAMP: fog value and citation are server-authoritative (W4-3).
# The gate only proves a citation EXISTS; the invariant demands the VALUE be
# demonstrable. After validation, the server stamps each node's fog score AND
# citation from this turn's evidence, so a model-fabricated number cannot cross
# — citation and value share one referent (one row).
# ---------------------------------------------------------------------------

def _ev_with_debt():
    ev = GraphEvidence()
    ev.add_module_graph({
        "modules": [
            {"name": "pkg/a", "file_path": "src/pkg/a/zzz.py", "cognitive_debt_score": 90.0},
            {"name": "pkg/b", "file_path": "src/pkg/b.py", "cognitive_debt_score": None},
        ],
        "edges": [{"from": "pkg/a", "to": "pkg/b", "weight": 1}],
        "truncated": False,
    })
    return ev


def test_add_module_graph_records_node_meta():
    ev = _ev_with_debt()
    assert ev.node_meta["pkg/a"] == {"file_path": "src/pkg/a/zzz.py",
                                     "cognitive_debt_score": 90.0}
    assert ev.node_meta["pkg/b"]["cognitive_debt_score"] is None


def test_stamp_overwrites_fabricated_fog():
    from copyclip.intelligence.cuaderno.widget_checks import stamp_widget_payload
    ev = _ev_with_debt()
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a",
                    "citation": {"kind": "path", "path": "src/pkg/a/zzz.py"},
                    "cognitive_debt_score": 5.0}],   # the model lies: claims 5.0
         "edges": []}
    stamp_widget_payload({"kind": "widget", "widget": w}, ev)
    assert w["nodes"][0]["cognitive_debt_score"] == 90.0   # authoritative wins


def test_stamp_sets_authoritative_citation():
    from copyclip.intelligence.cuaderno.widget_checks import stamp_widget_payload
    ev = _ev_with_debt()
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a",
                    "citation": {"kind": "path", "path": "WRONG/file.py"}}],
         "edges": []}
    stamp_widget_payload({"kind": "widget", "widget": w}, ev)
    assert w["nodes"][0]["citation"] == {"kind": "path", "path": "src/pkg/a/zzz.py"}


def test_stamp_unmeasured_node_score_is_none():
    from copyclip.intelligence.cuaderno.widget_checks import stamp_widget_payload
    ev = _ev_with_debt()
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/b", "label": "b",
                    "citation": {"kind": "path", "path": "src/pkg/b.py"},
                    "cognitive_debt_score": 12.0}],   # model invents a number
         "edges": []}
    stamp_widget_payload({"kind": "widget", "widget": w}, ev)
    assert w["nodes"][0]["cognitive_debt_score"] is None   # absence, not a value


def test_stamp_symbol_node_drops_fog_and_keeps_citation():
    """A caller/callee symbol node has no debt CONCEPT (debt is per-file). Stamp
    DROPS any model-supplied fog (so a fabricated score can't cross AND the node
    isn't mislabeled 'unmeasured') and leaves its line-precise citation intact."""
    from copyclip.intelligence.cuaderno.widget_checks import stamp_widget_payload
    ev = GraphEvidence()
    ev.add_callers("parse", {"callers": [
        {"name": "main", "kind": "function", "file_path": "src/m.py", "line_start": 2}]})
    w = {"kind": "graph_view",
         "nodes": [{"id": "main", "label": "main",
                    "citation": {"kind": "path", "path": "src/m.py", "line_start": 2},
                    "cognitive_debt_score": 7.0}],   # model fabrication
         "edges": []}
    stamp_widget_payload({"kind": "widget", "widget": w}, ev)
    assert "cognitive_debt_score" not in w["nodes"][0]   # dropped, not nulled
    assert w["nodes"][0]["citation"] == {"kind": "path", "path": "src/m.py", "line_start": 2}
