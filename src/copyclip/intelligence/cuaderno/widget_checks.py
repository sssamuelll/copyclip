"""Emit-time verification for evidence-bearing widgets (Wave 3, spec §4b).
A graph_view must be a SUBSET of this turn's graph evidence; a playground
recipe must pass launch-grade validation at emit, not at click."""
from __future__ import annotations

from typing import Any, Optional

from ..playground import FunctionRef


class GraphEvidence:
    """What graph tools returned this turn: admissible nodes and edges."""

    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.edges: set[tuple[str, str]] = set()

    def add_module_graph(self, result: dict) -> None:
        for m in result.get("modules") or []:
            if isinstance(m, dict) and m.get("name"):
                self.nodes.add(str(m["name"]))
        for e in result.get("edges") or []:
            if isinstance(e, dict) and e.get("from") and e.get("to"):
                self.edges.add((str(e["from"]), str(e["to"])))

    def add_callers(self, symbol: str, result: dict) -> None:
        self.nodes.add(symbol)
        for c in result.get("callers") or []:
            if isinstance(c, dict) and c.get("name"):
                self.nodes.add(str(c["name"]))
                self.edges.add((str(c["name"]), symbol))

    def add_callees(self, symbol: str, result: dict) -> None:
        self.nodes.add(symbol)
        for c in result.get("callees") or []:
            if isinstance(c, dict) and c.get("name"):
                self.nodes.add(str(c["name"]))
                self.edges.add((symbol, str(c["name"])))


def _check_graph_view(w: dict, ev: GraphEvidence) -> Optional[str]:
    for n in w.get("nodes") or []:
        nid = n.get("id") if isinstance(n, dict) else None
        if nid is None or str(nid) not in ev.nodes:
            return f"graph_view node {nid!r} is not in this turn's graph evidence"
    for e in w.get("edges") or []:
        pair = (str(e.get("from")), str(e.get("to"))) if isinstance(e, dict) else ("?", "?")
        if pair not in ev.edges:
            return f"graph_view edge {pair[0]} -> {pair[1]} is not in this turn's graph evidence"
    return None


def _check_playground(w: dict) -> Optional[str]:
    fr = w.get("function_ref")
    if not isinstance(fr, dict):
        return "playground widget missing function_ref"
    try:
        FunctionRef.from_dict(fr)
    except Exception as exc:  # noqa: BLE001 — any validation failure means: do not offer this recipe
        return f"playground function_ref invalid: {exc}"
    if not isinstance(w.get("breadcrumb"), str) or not w["breadcrumb"].strip():
        return "playground widget missing breadcrumb"
    return None


def validate_widget_payload(block: Any, evidence: GraphEvidence) -> Optional[str]:
    """None = ok; else a reason string (rides the existing invalid_block ack)."""
    if not isinstance(block, dict) or block.get("kind") != "widget":
        return None
    w = block.get("widget")
    if not isinstance(w, dict):
        return None
    if w.get("kind") == "graph_view":
        return _check_graph_view(w, evidence)
    if w.get("kind") == "playground":
        return _check_playground(w)
    return None
