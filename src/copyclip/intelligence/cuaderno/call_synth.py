"""Stage-1 call synthesis (spec 2026-06-18): lift a runnable call to a target
function from a REAL, fully-literal call-site in the codebase, with AST
re-verification that the call-graph 'calls' edge truly binds to THIS symbol.

Pure + best-effort: DB reads + `ast` only, no model/network/subprocess. Any
failure returns None — the floor then emits the `manual` needs_args widget.
"""
from __future__ import annotations

import ast
import json
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


# playground._module_from_file (which produces resolved.module) strips ONLY a
# leading "src/", so tolerate exactly that one source root on the import side.
_SRC_ROOTS = ("src",)


def _strip_src_root(module: str) -> str:
    head, _, rest = module.partition(".")
    if head in _SRC_ROOTS and rest:
        return rest
    return module


def _import_module_matches(import_module: str, resolved_module: str) -> bool:
    """True when the caller's import module identifies resolved.module. resolved.module
    is already src-stripped (playground._module_from_file), so tolerate a leading
    `src.` on the import side. NOTE: a module string is not a unique file id — the
    `_target_module_is_unambiguous` guard (Task 5) ensures (name, module) -> one file
    so this string match is sound."""
    if not import_module or not resolved_module:
        return False
    return (
        import_module == resolved_module
        or _strip_src_root(import_module) == resolved_module
    )


def _function_call_confirms(
    call_node: ast.Call, bindings: dict[str, _Binding], caller_file: str, resolved
) -> bool:
    """True when call_node binds to the plain-function target `resolved`."""
    func = call_node.func
    if isinstance(func, ast.Name):
        # A bare name defined in the SAME file as the target is a same-module call.
        # (A module-level def shadows any same-named import for the whole module, so
        # the bare name binds to the local def — which IS the target.)
        if caller_file == resolved.file and func.id == resolved.name:
            return True
        # Imported call — handles both the plain `target()` and the aliased
        # `from m import target as tgt; tgt()` forms (look up the bound name first,
        # then confirm the ORIGINAL imported name is the target and the module matches).
        b = bindings.get(func.id)
        if b is None or b.orig_name != resolved.name:
            return False
        return _import_module_matches(b.module, resolved.module)
    if isinstance(func, ast.Attribute):
        if func.attr != resolved.name:
            return False
        prefix = _dotted_name(func.value)
        if prefix is None:
            return False
        b = bindings.get(prefix)
        if b is None:
            return False
        return _import_module_matches(b.module, resolved.module)
    return False


def _is_json_literal(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def _lift_literal_args(call_node: ast.Call) -> Optional[tuple[list, dict]]:
    """Lift (args, kwargs) as literal, JSON-serializable values, or None if any
    argument is non-literal, a splat, or not JSON-serializable."""
    args: list = []
    for a in call_node.args:
        if isinstance(a, ast.Starred):
            return None
        try:
            value = ast.literal_eval(a)
        except (ValueError, SyntaxError, TypeError):
            return None
        if not _is_json_literal(value):
            return None
        args.append(value)
    kwargs: dict = {}
    for kw in call_node.keywords:
        if kw.arg is None:  # **kwargs splat
            return None
        try:
            value = ast.literal_eval(kw.value)
        except (ValueError, SyntaxError, TypeError):
            return None
        if not _is_json_literal(value):
            return None
        kwargs[kw.arg] = value
    return args, kwargs
