"""Anchored Playground bridge: contract, resolver, and Marimo notebook generator.

The architectural contract lives in
docs/superpowers/specs/2026-05-22-anchored-playground-design.md.

This module owns the bridge between dashboard surfaces (Atlas3D, Reacquaintance,
Debt Navigator, etc.) and Marimo subprocesses. It does NOT spawn or manage
subprocesses — that responsibility belongs to marimo_runner.py (issue #88). The
runner is consumed via the MarimoRunner Protocol below so this module can be
tested in isolation with a mock.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


PLAYGROUND_SOURCES = frozenset(
    {
        "atlas",
        "reacquaintance",
        "debt_navigator",
        "decisions",
        "risks",
        "timeline",
        "context_builder",
    }
)

LAUNCHABLE_SYMBOL_KINDS = frozenset({"function", "method", "class"})


# ---------------------------------------------------------------------------
# Wire shape (mirrors the TypeScript types in the design spec)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FunctionRef:
    file: str
    name: str
    line: int | None = None
    qualname: str | None = None

    @classmethod
    def from_dict(cls, data: object) -> "FunctionRef":
        if not isinstance(data, dict):
            raise InvalidFunctionRefError("function_ref must be an object")
        file = data.get("file")
        name = data.get("name")
        if not isinstance(file, str) or not file:
            raise InvalidFunctionRefError("function_ref.file is required")
        if not isinstance(name, str) or not name:
            raise InvalidFunctionRefError("function_ref.name is required")
        line = data.get("line")
        if line is not None and not isinstance(line, int):
            raise InvalidFunctionRefError(
                "function_ref.line must be int when provided"
            )
        qualname = data.get("qualname")
        if qualname is not None and not isinstance(qualname, str):
            raise InvalidFunctionRefError(
                "function_ref.qualname must be str when provided"
            )
        if _looks_absolute(file) or os.path.isabs(file):
            raise InvalidFunctionRefError(
                f"function_ref.file must be project-relative, got absolute path: {file!r}"
            )
        return cls(file=file, name=name, line=line, qualname=qualname)


@dataclass(frozen=True)
class PlaygroundLaunchRequest:
    source: str
    function_ref: FunctionRef
    deps_hint: list[str] | None = None
    suggested_inputs: list[object] | None = None
    breadcrumb: str = ""

    @classmethod
    def from_dict(cls, data: object) -> "PlaygroundLaunchRequest":
        if not isinstance(data, dict):
            raise InvalidRequestError("request body must be an object")
        source = data.get("source")
        if source not in PLAYGROUND_SOURCES:
            raise InvalidRequestError(
                f"source must be one of {sorted(PLAYGROUND_SOURCES)}, got {source!r}"
            )
        ref = FunctionRef.from_dict(data.get("function_ref") or {})
        deps_hint = data.get("deps_hint")
        if deps_hint is not None and not isinstance(deps_hint, list):
            raise InvalidRequestError("deps_hint must be a list when provided")
        suggested = data.get("suggested_inputs")
        if suggested is not None and not isinstance(suggested, list):
            raise InvalidRequestError(
                "suggested_inputs must be a list when provided"
            )
        breadcrumb = data.get("breadcrumb") or ""
        if not isinstance(breadcrumb, str):
            raise InvalidRequestError("breadcrumb must be a string")
        return cls(
            source=str(source),
            function_ref=ref,
            deps_hint=[str(x) for x in deps_hint] if deps_hint else None,
            suggested_inputs=list(suggested) if suggested else None,
            breadcrumb=breadcrumb,
        )


@dataclass(frozen=True)
class PlaygroundLaunchResponse:
    playground_id: str
    iframe_url: str

    def to_dict(self) -> dict:
        return {
            "playground_id": self.playground_id,
            "iframe_url": self.iframe_url,
        }


# ---------------------------------------------------------------------------
# Runner Protocol — real implementation lands in marimo_runner.py (issue #88)
# ---------------------------------------------------------------------------


class MarimoRunner(Protocol):
    def launch(self, notebook_path: str) -> tuple[str, str]:
        """Return (playground_id, iframe_url) after a healthy spawn."""
        ...

    def kill(self, playground_id: str) -> bool:
        ...

    def status(self, playground_id: str) -> str:
        ...


# ---------------------------------------------------------------------------
# Error classes — endpoints catch these and emit JSON with stable codes
# ---------------------------------------------------------------------------


class PlaygroundError(Exception):
    error_code: str = "playground_error"
    http_status: int = 500


class InvalidRequestError(PlaygroundError):
    error_code = "invalid_request"
    http_status = 400


class InvalidFunctionRefError(PlaygroundError):
    error_code = "invalid_function_ref"
    http_status = 400


class FunctionNotFoundError(PlaygroundError):
    error_code = "function_not_found"
    http_status = 404


class MarimoNotInstalledError(PlaygroundError):
    error_code = "marimo_not_installed"
    http_status = 503


class MarimoSpawnError(PlaygroundError):
    error_code = "marimo_spawn_failed"
    http_status = 500


class NoFreePortError(PlaygroundError):
    error_code = "no_free_port"
    http_status = 503


# ---------------------------------------------------------------------------
# Resolver: look up FunctionRef in the analyzer's symbol table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedFunction:
    file: str
    name: str
    qualname: str
    kind: str
    module: str
    line_start: int | None
    parent_class: str | None


def resolve_function_ref(
    conn: sqlite3.Connection,
    project_id: int,
    ref: FunctionRef,
) -> ResolvedFunction:
    """Look up a FunctionRef in the symbols table. Raises FunctionNotFoundError on miss."""
    qualname = ref.qualname or ref.name
    parent_class: str | None = None
    if "." in qualname:
        head, tail = qualname.split(".", 1)
        if head and tail and "." not in tail:
            parent_class = head

    if parent_class:
        row = conn.execute(
            """
            SELECT name, kind, file_path, line_start, module
            FROM symbols
            WHERE project_id=? AND file_path=? AND name=?
              AND kind IN ('method','function')
            ORDER BY line_start
            LIMIT 1
            """,
            (project_id, ref.file, ref.name),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT name, kind, file_path, line_start, module
            FROM symbols
            WHERE project_id=? AND file_path=? AND name=?
              AND kind IN ('function','method','class')
            ORDER BY CASE kind
                WHEN 'function' THEN 0
                WHEN 'class' THEN 1
                ELSE 2
            END
            LIMIT 1
            """,
            (project_id, ref.file, ref.name),
        ).fetchone()

    if not row:
        raise FunctionNotFoundError(
            f"no symbol {ref.name!r} found in {ref.file!r}"
        )

    db_name = row[0]
    db_kind = row[1]
    db_file = row[2]
    db_line = row[3]
    db_module = row[4] or _module_from_file(ref.file)

    final_qualname = qualname if parent_class else db_name
    return ResolvedFunction(
        file=db_file,
        name=db_name,
        qualname=final_qualname,
        kind=db_kind,
        module=db_module,
        line_start=db_line,
        parent_class=parent_class,
    )


# ---------------------------------------------------------------------------
# Marimo notebook generator
# ---------------------------------------------------------------------------


_NOTEBOOK_TEMPLATE = '''import marimo

app = marimo.App(width="medium")


@app.cell
def __():
    # CopyClip auto-loaded cell
    # Source: {source}
    # Breadcrumb: {breadcrumb}
    import sys
    sys.path.insert(0, {project_root!r})
{imports_block}
    return ({exported_symbols},)


@app.cell
def __({exported_symbols}):
{sample_block}
    return result, sample,


@app.cell
def __():
    # Free cell: experiment freely
    return


if __name__ == "__main__":
    app.run()
'''


def generate_marimo_notebook(
    req: PlaygroundLaunchRequest,
    project_root: str,
    resolved: ResolvedFunction,
    *,
    temp_dir: str | None = None,
) -> str:
    """Write a runnable Marimo .py file to a temp dir and return its absolute path.

    Cleanup of the temp dir is the runner's responsibility (see marimo_runner.py).
    """
    td = temp_dir or tempfile.mkdtemp(prefix="copyclip-playground-")
    notebook_path = os.path.join(td, "playground.py")
    imports_block, exported_symbols, call_expr = _build_symbol_resolution(resolved)
    sample_block = _build_sample_block(req.suggested_inputs, call_expr)
    content = _NOTEBOOK_TEMPLATE.format(
        source=req.source,
        breadcrumb=req.breadcrumb or "<unspecified>",
        project_root=os.path.abspath(project_root),
        imports_block=imports_block,
        exported_symbols=exported_symbols,
        sample_block=sample_block,
    )
    Path(notebook_path).write_text(content, encoding="utf-8")
    return notebook_path


def _build_symbol_resolution(resolved: ResolvedFunction) -> tuple[str, str, str]:
    """Return (imports_block, exported_symbols, call_expr) per the spec's Symbol resolution rules.

    Staticmethod / classmethod detection is deferred; we default methods to the
    instance form ``Foo(...).method(sample)`` per the spec fallback.
    """
    mod = resolved.module
    name = resolved.name
    parent = resolved.parent_class

    if parent and parent != name:
        imports = f"    from {mod} import {parent}"
        exported = parent
        call_expr = f"{parent}(...).{name}(sample)"
    else:
        imports = f"    from {mod} import {name}"
        exported = name
        call_expr = f"{name}(sample)"

    return imports, exported, call_expr


def _build_sample_block(
    suggested_inputs: list[object] | None, call_expr: str
) -> str:
    """Indented body of the second cell. v1: uses only the first suggested input."""
    indent = "    "
    if not suggested_inputs:
        callable_repr = call_expr.split("(", 1)[0]
        lines = [
            f"{indent}# Suggested input",
            f"{indent}# TODO: supply input",
            f"{indent}sample = None",
            f"{indent}result = None  # call {callable_repr}(sample) once sample is set",
        ]
    else:
        first = suggested_inputs[0]
        try:
            sample_repr = repr(first)
        except Exception:
            sample_repr = "None"
        lines = [
            f"{indent}# Suggested input",
            f"{indent}sample = {sample_repr}",
            f"{indent}result = {call_expr}",
            f"{indent}result",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def launch_playground(
    req: PlaygroundLaunchRequest,
    project_root: str,
    conn: sqlite3.Connection,
    pid: int,
    runner: MarimoRunner,
) -> PlaygroundLaunchResponse:
    """Resolve, generate, launch. May raise PlaygroundError subclasses."""
    resolved = resolve_function_ref(conn, pid, req.function_ref)
    notebook_path = generate_marimo_notebook(req, project_root, resolved)
    playground_id, iframe_url = runner.launch(notebook_path)
    return PlaygroundLaunchResponse(
        playground_id=playground_id,
        iframe_url=iframe_url,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_absolute(path: str) -> bool:
    """Detect absolute paths cross-platform.

    os.path.isabs is platform-dependent and does not catch POSIX-style absolute
    paths on Windows. We treat leading '/' or '\\' as absolute everywhere, plus
    the Windows 'C:' drive prefix.
    """
    if not path:
        return False
    if path.startswith("/") or path.startswith("\\"):
        return True
    if len(path) >= 2 and path[1] == ":":
        return True
    return False


def _module_from_file(file_path: str) -> str:
    """'src/copyclip/foo.py' → 'copyclip.foo'. Strips leading 'src/' to match the project layout."""
    norm = file_path.replace("\\", "/")
    if norm.endswith(".py"):
        norm = norm[:-3]
    parts = [p for p in norm.split("/") if p]
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


# ---------------------------------------------------------------------------
# Temporary stub runner — remove the fallback import in server.py when
# marimo_runner.py lands (issue #88). Keeps endpoint contract testable
# end-to-end against stable JSON error codes in the meantime.
# ---------------------------------------------------------------------------


class StubMarimoRunner:
    def launch(self, notebook_path: str) -> tuple[str, str]:
        raise MarimoSpawnError(
            "marimo subprocess manager not yet implemented (issue #88); "
            f"notebook generated at {notebook_path}"
        )

    def kill(self, playground_id: str) -> bool:
        return False

    def status(self, playground_id: str) -> str:
        return "missing"
