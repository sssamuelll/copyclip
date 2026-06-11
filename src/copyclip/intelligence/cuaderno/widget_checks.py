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
        # Per module-node authoritative metadata: name -> {file_path, heat}.
        # This is the channel the STAMP reads so the heat and citation that cross
        # to the human are the server's computation, not the model's utterance.
        self.node_meta: dict[str, dict] = {}

    def add_module_graph(self, result: dict) -> None:
        for m in result.get("modules") or []:
            if isinstance(m, dict) and m.get("name"):
                name = str(m["name"])
                self.nodes.add(name)
                self.node_meta[name] = {
                    "file_path": m.get("file_path"),
                    "heat": m.get("heat"),
                }
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
    # Check order: node membership → edge membership → per-node citations.
    # Membership failures are diagnosed first so the caller sees the most
    # actionable rejection reason.
    for n in w.get("nodes") or []:
        nid = n.get("id") if isinstance(n, dict) else None
        if nid is None or str(nid) not in ev.nodes:
            return f"graph_view node {nid!r} is not in this turn's graph evidence"
    for e in w.get("edges") or []:
        pair = (str(e.get("from")), str(e.get("to"))) if isinstance(e, dict) else ("?", "?")
        if pair not in ev.edges:
            return f"graph_view edge {pair[0]} -> {pair[1]} is not in this turn's graph evidence"
    for n in w.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        citation = n.get("citation")
        if not isinstance(citation, dict) or not citation.get("path"):
            return f"graph_view node {nid!r} carries no citation"
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


def _stamp_graph_view(w: dict, ev: GraphEvidence) -> None:
    """Make each node's fog and citation server-authoritative. The gate proves a
    citation exists; the invariant demands the VALUE be demonstrable — so the
    score the human sees and the file it cites are taken from THIS turn's evidence
    (one row), overwriting whatever the model emitted. A node with no measured
    debt (a symbol from get_callers/get_callees, or an unanalyzed module) gets a
    typed unknown (None); a symbol node keeps its line-precise citation."""
    for n in w.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        meta = ev.node_meta.get(str(n.get("id")))
        if meta is None:
            # Not a heat-bearing node (e.g. a symbol from get_callers/get_callees):
            # heat is per-file, so this node has no heat CONCEPT. Drop any
            # model-supplied value — a fabrication can't cross, and the node is
            # not mislabeled "unmeasured" (absent != null). Citation untouched.
            n.pop("heat", None)
            continue
        # A module/file node: the heat is the server's (number = measured,
        # None = the module exists but wasn't analyzed — a typed unknown), and
        # the citation is the same row the heat came from (one referent).
        n["heat"] = meta.get("heat")
        file_path = meta.get("file_path")
        if file_path:
            n["citation"] = {"kind": "path", "path": file_path}


def stamp_widget_payload(block: Any, evidence: GraphEvidence) -> None:
    """Mutate a validated widget so its evidence-bearing values are the server's,
    not the model's. Call AFTER validate_widget_payload returns None."""
    if not isinstance(block, dict) or block.get("kind") != "widget":
        return
    w = block.get("widget")
    if isinstance(w, dict) and w.get("kind") == "graph_view":
        _stamp_graph_view(w, evidence)
