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
    w = {"kind": "graph_view",
         "nodes": [{"id": "pkg/a", "label": "a"}, {"id": "pkg/b", "label": "b"}],
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
         "nodes": [{"id": "main", "label": "main"}, {"id": "parse", "label": "parse"}],
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
