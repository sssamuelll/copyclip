"""Stage-1 call synthesis (spec 2026-06-18): lift a runnable call to a target
function from a REAL, fully-literal call-site in the codebase, with AST
re-verification that the call-graph 'calls' edge truly binds to THIS symbol.

Pure + best-effort: DB reads + `ast` only, no model/network/subprocess. Any
failure returns None — the floor then emits the `manual` needs_args widget.
"""
from __future__ import annotations

import ast
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from ..analyzer import _is_test_path
from ..playground import _module_from_file


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


# ---------------------------------------------------------------------------
# Task 5: synthesize_call for plain functions
# ---------------------------------------------------------------------------

def _target_module_is_unambiguous(conn: sqlite3.Connection, project_id: int, resolved) -> bool:
    """True when (resolved.name, resolved.module) identifies a SINGLE file.

    `resolved.module` is derived (playground._module_from_file strips a leading
    `src/`), so two DISTINCT files can collapse to the same dotted module
    (`src/pkg/lib.py` and `pkg/lib.py` both → `pkg.lib`). When that happens an
    import's module string no longer pins a unique file, so a name-based `calls`
    edge + module-string confirmation could lift a call that actually targets the
    OTHER file — a wrong input wearing a `tests` chip. Refuse (→ manual) instead."""
    rows = conn.execute(
        "SELECT DISTINCT file_path FROM symbols WHERE project_id=? AND name=?",
        (project_id, resolved.name),
    ).fetchall()
    same_module_files = {r[0] for r in rows if _module_from_file(r[0]) == resolved.module}
    return len(same_module_files) <= 1


@dataclass(frozen=True)
class _Candidate:
    is_test: bool
    richness: int
    file_path: str
    line: int
    args: list
    kwargs: dict
    ctor: Optional[dict]


def _parse_caller_file(project_root: str, file_path: str) -> Optional[ast.Module]:
    path = os.path.join(project_root, file_path)
    try:
        with open(path, encoding="utf-8") as fh:
            return ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None


def _find_def(
    tree: ast.Module, name: str, line_start: Optional[int]
) -> Optional[ast.AST]:
    """Find the FunctionDef/AsyncFunctionDef named `name`, preferring the one whose
    lineno matches line_start (mirrors compositor._floor_target_arity)."""
    best = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != name:
            continue
        if best is None or node.lineno == line_start:
            best = node
            if node.lineno == line_start:
                break
    return best


def _richness(args: list, kwargs: dict, ctor: Optional[dict]) -> int:
    """Count of non-degenerate literal values, where 'non-degenerate' = not None.
    A present ``''`` / ``0`` / ``False`` / ``[]`` is a real value and DOES count;
    only ``None`` (and absent args) score 0, so an empty/None-only call ranks lowest
    (spec §2.4 'avoid an empty/None-only call that teaches nothing')."""
    n = sum(1 for v in args if v is not None)
    n += sum(1 for v in kwargs.values() if v is not None)
    if ctor is not None:
        n += sum(1 for v in (ctor.get("args") or []) if v is not None)
        n += sum(1 for v in (ctor.get("kwargs") or {}).values() if v is not None)
    return n


def _iter_calls(def_node: ast.AST):
    for node in ast.walk(def_node):
        if isinstance(node, ast.Call):
            yield node


def _class_binds(class_node: ast.AST, bindings: dict[str, _Binding],
                 caller_file: str, resolved) -> bool:
    """True when the constructor reference binds to resolved's class in resolved.module."""
    simple = _dotted_name(class_node)
    if simple is None:
        return False
    simple_name = simple.split(".")[-1]
    if simple_name != resolved.parent_class:
        return False
    if isinstance(class_node, ast.Name):
        if caller_file == resolved.file:
            return True
        b = bindings.get(class_node.id)
        return (
            b is not None
            and b.orig_name == simple_name
            and _import_module_matches(b.module, resolved.module)
        )
    # Attribute chain: mod.ClassName(...)
    prefix = _dotted_name(class_node.value) if isinstance(class_node, ast.Attribute) else None
    if prefix is None:
        return False
    b = bindings.get(prefix)
    return b is not None and _import_module_matches(b.module, resolved.module)


def _method_call_confirms_and_lifts(
    call_node: ast.Call, bindings: dict[str, _Binding], caller_file: str, resolved
) -> Optional[tuple[list, dict, dict]]:
    """Confirm + lift an inline ``ClassName(<lit>).method(<lit>)`` call. Returns
    (method_args, method_kwargs, ctor) or None."""
    func = call_node.func
    if not isinstance(func, ast.Attribute) or func.attr != resolved.name:
        return None
    inner = func.value
    if not isinstance(inner, ast.Call):  # not inline construction (e.g. obj.method())
        return None
    if not _class_binds(inner.func, bindings, caller_file, resolved):
        return None
    method_lits = _lift_literal_args(call_node)
    ctor_lits = _lift_literal_args(inner)
    if method_lits is None or ctor_lits is None:
        return None
    m_args, m_kwargs = method_lits
    c_args, c_kwargs = ctor_lits
    return m_args, m_kwargs, {"args": c_args, "kwargs": c_kwargs}


def synthesize_call(
    resolved, conn: sqlite3.Connection, project_id: int, project_root: Optional[str]
) -> Optional[SynthesizedCall]:
    """Lift a runnable call to `resolved` from a verified, fully-literal real
    call-site. None when none exists (the floor then emits the `manual` widget).
    Best-effort: any failure returns None and never raises into the floor."""
    try:
        if conn is None or project_id is None or not project_root:
            return None
        if resolved.line_start is None:
            return None
        if resolved.kind == "class":
            # A class-name run-request: lifting ClassName(args) has no ctor handling.
            return None
        if not _target_module_is_unambiguous(conn, project_id, resolved):
            # Module string is not a unique file id -> refuse (false-confirm guard).
            return None
        is_method = resolved.kind == "method" or bool(resolved.parent_class)
        # Nested-class methods are out of v1 scope (fold only renders 2-segment
        # qualnames); a method with no parent_class cannot be constructed.
        if is_method and not resolved.parent_class:
            return None
        target_id = _resolve_target_symbol_id(conn, project_id, resolved)
        if target_id is None:
            return None
        candidates: list[_Candidate] = []
        for caller in _candidate_callers(conn, project_id, target_id):
            tree = _parse_caller_file(project_root, caller.file_path)
            if tree is None:
                continue
            bindings = _import_bindings(tree)
            def_node = _find_def(tree, caller.name, caller.line_start)
            if def_node is None:
                continue
            is_test = _is_test_path(caller.file_path)
            for call_node in _iter_calls(def_node):
                if is_method:
                    lifted = _method_call_confirms_and_lifts(
                        call_node, bindings, caller.file_path, resolved)
                    if lifted is None:
                        continue
                    m_args, m_kwargs, ctor = lifted
                    candidates.append(_Candidate(
                        is_test=is_test, richness=_richness(m_args, m_kwargs, ctor),
                        file_path=caller.file_path, line=call_node.lineno,
                        args=m_args, kwargs=m_kwargs, ctor=ctor,
                    ))
                else:
                    if not _function_call_confirms(call_node, bindings, caller.file_path, resolved):
                        continue
                    lifted = _lift_literal_args(call_node)
                    if lifted is None:
                        continue
                    a, k = lifted
                    candidates.append(_Candidate(
                        is_test=is_test, richness=_richness(a, k, None),
                        file_path=caller.file_path, line=call_node.lineno,
                        args=a, kwargs=k, ctor=None,
                    ))
        if not candidates:
            return None
        best = sorted(
            candidates,
            key=lambda c: (not c.is_test, -c.richness, c.file_path, c.line),
        )[0]
        return SynthesizedCall(args=best.args, kwargs=best.kwargs, ctor=best.ctor,
                               arg_source="tests")
    except Exception:  # noqa: BLE001 — best-effort; never raise into the floor
        return None
