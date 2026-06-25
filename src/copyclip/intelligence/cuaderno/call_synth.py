"""Stage-1 call synthesis (spec 2026-06-18): lift a runnable call to a target
function from a REAL, fully-literal call-site in the codebase, with AST
re-verification that the call-graph 'calls' edge truly binds to THIS symbol.

Pure + best-effort: DB reads + `ast` only, no model/network/subprocess. Any
failure returns None — the floor then emits the `manual` needs_args widget.
"""
from __future__ import annotations

import ast
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SynthesizedCall:
    """A call lifted from a verified, fully-literal real call-site."""
    args: list
    kwargs: dict
    ctor: Optional[dict]   # {"args": [...], "kwargs": {...}} for a method, else None
    arg_source: str        # always "tests" from this function


@dataclass(frozen=True)
class _Caller:
    name: str
    kind: str
    file_path: str
    line_start: Optional[int]
    line_end: Optional[int]


def _resolve_target_symbol_id(
    conn: sqlite3.Connection, project_id: int, resolved
) -> Optional[int]:
    """Re-find the target's symbols.id (ResolvedFunction carries no id). Uses the
    natural key (project_id, file_path, name, kind, line_start)."""
    if resolved.line_start is None:
        return None
    row = conn.execute(
        "SELECT id FROM symbols WHERE project_id=? AND file_path=? AND name=? "
        "AND kind=? AND line_start=?",
        (project_id, resolved.file, resolved.name, resolved.kind, resolved.line_start),
    ).fetchone()
    return int(row[0]) if row else None


def _candidate_callers(
    conn: sqlite3.Connection, project_id: int, target_id: int
) -> list[_Caller]:
    """Candidate call-sites: callers of `target_id` via 'calls' edges. NAME-BASED
    and possibly false positives — each must be re-verified before lifting."""
    rows = conn.execute(
        "SELECT s.name, s.kind, s.file_path, s.line_start, s.line_end "
        "FROM symbol_edges e JOIN symbols s ON e.from_symbol_id = s.id "
        "WHERE e.project_id=? AND e.to_symbol_id=? AND e.edge_type='calls' "
        "ORDER BY s.file_path, s.line_start",
        (project_id, target_id),
    ).fetchall()
    return [
        _Caller(name=r[0], kind=r[1], file_path=r[2], line_start=r[3], line_end=r[4])
        for r in rows
    ]


@dataclass(frozen=True)
class _Binding:
    module: str               # dotted source module (e.g. "src.pkg.lib")
    orig_name: Optional[str]  # "from m import orig [as bound]" -> orig; "import m" -> None


def _dotted_name(node: ast.AST) -> Optional[str]:
    """Reconstruct a dotted name from a Name/Attribute chain ('a.b.c'), else None."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _import_bindings(tree: ast.Module) -> dict[str, _Binding]:
    """Map module-level bound names to their import binding. Relative imports are
    skipped (v1: unconfirmable without resolving the caller's package)."""
    out: dict[str, _Binding] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import — conservative skip
            mod = node.module or ""
            for alias in node.names:
                bound = alias.asname or alias.name
                out[bound] = _Binding(module=mod, orig_name=alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name
                out[bound] = _Binding(module=alias.name, orig_name=None)
    return out
