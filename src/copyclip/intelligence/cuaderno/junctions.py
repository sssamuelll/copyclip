"""Cruces / Junctions v0.1 — executed-arm overlay over the step-through.

Pure, I/O-free control-flow reading of a completed trace: for each
if/elif/else in the target function, mark which arm the run crossed (taken),
which it did not (not-taken), and — when the trace was truncated — which we
cannot say (unknown). A branch not taken simply produced no trace events.

See docs/superpowers/specs/2026-07-02-cuaderno-cruces-junctions-design.md.
"""
from __future__ import annotations

import ast


def compute_junctions(
    source: str,
    func_line: int | None,
    func_name: str,
    executed_lines: set[int],
    truncated: bool,
) -> list[dict]:
    """Return the if/elif/else junctions of the target function, each arm tagged
    taken=True|False|None. Fails open to [] on any parse/lookup problem so the
    feature is invisible rather than wrong."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    target = _find_func(tree, func_line, func_name)
    if target is None:
        return []
    out: list[dict] = []
    _junctions_in_scope(target.body, executed_lines, truncated, out)
    return out


def _find_func(tree: ast.AST, func_line: int | None, func_name: str):
    funcs = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if func_line is not None:
        for n in funcs:
            if n.lineno == func_line:
                return n
    named = [n for n in funcs if n.name == func_name]
    return named[0] if len(named) == 1 else None


def _classify(kind: str, keyword_line: int, body: list, executed: set[int]):
    """Raw per-arm evidence: (lo, hi, hit, ambiguous).

    An if/elif whose body starts ON its condition line (inline ``if x: a = 1``)
    cannot be confirmed from a line trace: the condition line is recorded on every
    evaluation, regardless of which arm runs. So evidence for such an arm starts
    STRICTLY PAST the condition line — and an inline single-line body has no such
    line, making it 'ambiguous' (indeterminable from line events alone)."""
    lo = body[0].lineno
    hi = body[-1].end_lineno
    ev_lo = lo + 1 if (kind in ("if", "elif") and lo == keyword_line) else lo
    hit = any(ev_lo <= line <= hi for line in executed)
    ambiguous = ev_lo > hi   # inline arm: no line distinctly proves it ran
    return lo, hi, hit, ambiguous


def _build_ladder(node: ast.If, executed: set[int], truncated: bool) -> dict:
    # (kind, keyword_line, body) for each arm of the if/elif/else ladder.
    spans = [("if", node.lineno, node.body)]
    orelse = node.orelse
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_node = orelse[0]
        spans.append(("elif", elif_node.lineno, elif_node.body))
        orelse = elif_node.orelse
    if orelse:
        spans.append(("else", orelse[0].lineno, orelse))
    classified = [(kind, *_classify(kind, kw, body, executed)) for (kind, kw, body) in spans]
    any_hit = any(c[3] for c in classified)   # c = (kind, lo, hi, hit, ambiguous)
    arms = []
    for kind, lo, hi, hit, ambiguous in classified:
        if hit:
            taken: bool | None = True
        elif ambiguous:
            # inline arm with no distinguishable body line: a distinguishable
            # sibling running proves this one did not; otherwise we cannot say.
            taken = False if any_hit else None
        else:
            taken = None if truncated else False
        arms.append({"kind": kind, "lines": [lo, hi], "taken": taken})
    return {"test_line": node.lineno, "arms": arms}


def _ladder_bodies(node: ast.If) -> list[list]:
    """The arm bodies of the ladder, for recursing into nested ifs WITHOUT
    re-treating the elif If-nodes as their own top-level junctions."""
    bodies = [node.body]
    orelse = node.orelse
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_node = orelse[0]
        bodies.append(elif_node.body)
        orelse = elif_node.orelse
    if orelse:
        bodies.append(orelse)
    return bodies


def _generic_child_bodies(node: ast.AST) -> list[list]:
    """Statement-list bodies to descend for nested ifs in the SAME scope
    (For/While/With/Try). Non-If compound statements only — If is handled by
    _build_ladder + _ladder_bodies."""
    out: list[list] = []
    for field in ("body", "orelse", "finalbody"):
        val = getattr(node, field, None)
        if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
            out.append(val)
    for handler in getattr(node, "handlers", []) or []:
        if handler.body:
            out.append(handler.body)
    # match/case bodies live in the SAME frame (match creates no code object);
    # its arms hang off cases[].body, which the field-loop above does not reach.
    for case in getattr(node, "cases", []) or []:
        if case.body:
            out.append(case.body)
    return out


def _junctions_in_scope(stmts: list, executed: set[int], truncated: bool, out: list[dict]) -> None:
    for node in stmts:
        # Nested defs/classes have their OWN code object and are not traced
        # (frame-scoping, _capture_driver.py) — we cannot say which of their
        # branches ran, so we never emit junctions for them.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.If):
            out.append(_build_ladder(node, executed, truncated))
            for body in _ladder_bodies(node):
                _junctions_in_scope(body, executed, truncated, out)
        else:
            for body in _generic_child_bodies(node):
                _junctions_in_scope(body, executed, truncated, out)
