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
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from .cuaderno.trace import NULL_TRACE


PLAYGROUND_SOURCES = frozenset(
    {
        "atlas",
        "reacquaintance",
        "debt_navigator",
        "decisions",
        "risks",
        "timeline",
        "context_builder",
        "cuaderno",
    }
)

LAUNCHABLE_SYMBOL_KINDS = frozenset({"function", "method", "class"})

# User-supplied symbol fragments (name, qualname parts, parent class) are
# substituted directly into the generated Marimo file as Python identifiers.
# Without validation, `qualname="x;import os;y.method"` would slip into
# `from {mod} import x;import os;y` and execute on spawn.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Cap to keep pathological breadcrumbs from blowing up the template / log files.
_BREADCRUMB_MAX_LEN = 500


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.match(value))


def _sanitize_for_comment(value: str) -> str:
    """Make a string safe to embed in a single-line Python ``#`` comment.

    Replaces any non-printable character (including line terminators ``\\n``,
    ``\\r``, ``U+2028``, ``U+2029``) with a space, and truncates to
    ``_BREADCRUMB_MAX_LEN``. Without this a breadcrumb of
    ``"atlas\\n    import os; os.system('pwn')"`` would escape the comment
    and execute on subprocess spawn.
    """
    if not value:
        return ""
    cleaned = "".join(c if (c == " " or c.isprintable()) else " " for c in value)
    if len(cleaned) > _BREADCRUMB_MAX_LEN:
        cleaned = cleaned[: _BREADCRUMB_MAX_LEN - 3] + "..."
    return cleaned


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
        if not _is_identifier(name):
            raise InvalidFunctionRefError(
                f"function_ref.name must be a Python identifier, got {name!r}"
            )
        line = data.get("line")
        if line is not None and not isinstance(line, int):
            raise InvalidFunctionRefError(
                "function_ref.line must be int when provided"
            )
        qualname = data.get("qualname")
        if qualname is not None:
            if not isinstance(qualname, str):
                raise InvalidFunctionRefError(
                    "function_ref.qualname must be str when provided"
                )
            qparts = qualname.split(".")
            if len(qparts) > 2:
                raise InvalidFunctionRefError(
                    "nested class qualnames (e.g. Outer.Inner.method) are not supported in v1"
                )
            if not all(_is_identifier(p) for p in qparts):
                raise InvalidFunctionRefError(
                    f"function_ref.qualname segments must be Python identifiers, got {qualname!r}"
                )
        if _looks_absolute(file) or os.path.isabs(file):
            raise InvalidFunctionRefError(
                f"function_ref.file must be project-relative, got absolute path: {file!r}"
            )
        if ".." in file.replace("\\", "/").split("/"):
            raise InvalidFunctionRefError(
                f"function_ref.file must not contain '..' segments, got {file!r}"
            )
        return cls(file=file, name=name, line=line, qualname=qualname)


@dataclass(frozen=True)
class PlaygroundLaunchRequest:
    source: str
    function_ref: FunctionRef
    deps_hint: list[str] | None = None
    suggested_inputs: list[object] | None = None
    breadcrumb: str = ""
    call: object | None = None  # cuaderno: model's CallDescriptor dict (raw; parsed in launch_playground)
    call_text: str | None = None  # cuaderno: user's free-text call expression

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
        call = data.get("call")
        call_text = data.get("call_text")
        if call_text is not None and not isinstance(call_text, str):
            raise InvalidRequestError("call_text must be a string when provided")
        return cls(
            source=str(source),
            function_ref=ref,
            deps_hint=[str(x) for x in deps_hint] if deps_hint else None,
            suggested_inputs=list(suggested) if suggested else None,
            breadcrumb=breadcrumb,
            call=call,
            call_text=call_text,
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
    def launch(self, notebook_path: str, mode: str = "edit", trace: object = None) -> tuple[str, str]:
        """Return (playground_id, iframe_url) after a healthy spawn."""
        ...

    def kill(self, playground_id: str) -> bool:
        ...

    def status(
        self, playground_id: str
    ) -> Literal["running", "exited", "missing"]:
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
    # Derive the importable dotted module from the canonical FILE path, never from
    # symbols.module: the analyzer stores `module` slash-style at directory
    # granularity (e.g. 'copyclip/intelligence'), which is neither dotted nor
    # file-level, so `from {module} import {name}` would be unimportable. The file
    # path yields the real module ('copyclip.intelligence.analyzer').
    db_module = _module_from_file(db_file)

    # The module string is embedded directly in `from {mod} import ...`.
    # Reject anything that isn't a dotted sequence of identifiers — protects
    # against files like `2legit.py` or `foo-bar.py` reaching the generator.
    if not db_module or not all(_is_identifier(seg) for seg in db_module.split(".")):
        raise FunctionNotFoundError(
            f"file {ref.file!r} does not map to an importable Python module "
            f"(derived module: {db_module!r})"
        )

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
    import marimo as mo
    import sys
    sys.path.insert(0, {project_root!r})
{imports_block}
    # {source} · {breadcrumb}
    return mo, {exported_symbols}


@app.cell
def __(mo):
    # Run mode hides code, so the notebook must SAY what it is.
    mo.md({header_md!r})
    return


@app.cell
def __(mo):
    # The input — change it and the result below re-runs.
    sample = {input_element}
    sample
    return (sample,)


@app.cell
def __({exported_symbols}, mo, sample):
    value = sample.value
    result = {call_expr}
    # The full invocation, live: flipping the input changes the call AND the result.
    mo.md("`" + {call_prefix!r} + "(" + repr(value) + ")` → `" + repr(result) + "`")
    return (result,)


@app.cell
def __({exported_symbols}, mo):
    # The source rides along, collapsed: the branch is visible while you cross it.
    import inspect as _inspect
    try:
        _src = _inspect.getsource({exported_symbols})
    except (OSError, TypeError):
        _src = "# source unavailable"
    mo.accordion({{{file_line!r}: mo.md("```python\\n" + _src + "\\n```")}})
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
    imports_block, exported_symbols, call_expr, call_prefix = _build_symbol_resolution(resolved)
    input_element = _build_input_element(req.suggested_inputs)
    # source is already validated against the PLAYGROUND_SOURCES whitelist, but
    # we sanitize both fields anyway as defense in depth — these end up inside
    # single-line ``#`` comments.
    safe_source = _sanitize_for_comment(req.source)
    safe_breadcrumb = _sanitize_for_comment(req.breadcrumb) or "<unspecified>"
    # The visible header: every piece is injection-guarded upstream (qualname and
    # file are identifier/path-validated by FunctionRef, source is whitelisted)
    # and injected as a repr literal anyway. The breadcrumb deliberately stays a
    # code comment — it is free text and must never reach a runnable line.
    file_line = resolved.file + (f":{resolved.line_start}" if resolved.line_start else "")
    header_md = f"### `{resolved.qualname}`\n\n`{file_line}` · {safe_source}"
    content = _NOTEBOOK_TEMPLATE.format(
        source=safe_source,
        breadcrumb=safe_breadcrumb,
        project_root=os.path.abspath(project_root),
        imports_block=imports_block,
        exported_symbols=exported_symbols,
        input_element=input_element,
        call_expr=call_expr,
        call_prefix=call_prefix,
        header_md=header_md,
        file_line=file_line,
    )
    Path(notebook_path).write_text(content, encoding="utf-8")
    return notebook_path


def _build_symbol_resolution(resolved: ResolvedFunction) -> tuple[str, str, str, str]:
    """Return (imports_block, exported_symbols, call_expr, call_prefix) per the
    spec's Symbol resolution rules. ``call_prefix`` is the display form of the
    callable (the call_expr minus its ``(value)``), shown in the live result line.

    Staticmethod / classmethod detection is deferred; we default methods to the
    instance form ``Foo(...).method(sample)`` per the spec fallback.
    """
    mod = resolved.module
    name = resolved.name
    parent = resolved.parent_class

    if parent and parent != name:
        imports = f"    from {mod} import {parent}"
        exported = parent
        call_prefix = f"{parent}(...).{name}"
    else:
        imports = f"    from {mod} import {name}"
        exported = name
        call_prefix = name

    return imports, exported, f"{call_prefix}(value)", call_prefix


def _build_input_element(suggested_inputs: list[object] | None) -> str:
    """The RHS of ``sample = ...``: a LIVE marimo input control, so changing it
    re-runs the function in-process (reactive), never a frozen literal.

    A single string becomes a free-text box the dev can retype — the grabbable
    input that makes 'change it and watch the branch move' real. Two or more
    inputs (or a single non-string) become a type-preserving dropdown — the
    'try this / now try that' contrast. No inputs falls back to an empty text
    box; the notebook never ships computing ``None``."""
    if (
        suggested_inputs
        and len(suggested_inputs) == 1
        and isinstance(suggested_inputs[0], str)
    ):
        return f'mo.ui.text(value={suggested_inputs[0]!r}, label="input", full_width=True)'
    if suggested_inputs:
        seen: set[str] = set()
        pairs: list[str] = []
        first_label: str | None = None
        for x in suggested_inputs:
            label = x if isinstance(x, str) else repr(x)
            base, i = label, 2
            while label in seen:
                label = f"{base} ({i})"
                i += 1
            seen.add(label)
            if first_label is None:
                first_label = label
            pairs.append(f"{label!r}: {x!r}")
        options = "{" + ", ".join(pairs) + "}"
        return f'mo.ui.dropdown(options={options}, value={first_label!r}, label="input")'
    return 'mo.ui.text(value="", label="input", full_width=True)'


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def launch_playground(
    req: PlaygroundLaunchRequest,
    project_root: str,
    conn: sqlite3.Connection,
    pid: int,
    runner: MarimoRunner,
    trace: object = None,
) -> "PlaygroundLaunchResponse | StepThroughResponse | FallbackResponse":
    """Resolve, generate, launch. May raise PlaygroundError subclasses.

    For source == "cuaderno": runs the model's CallDescriptor OR the user's
    free-text call in a bounded subprocess and returns a StepThroughResponse
    (trace) or FallbackResponse (async/generator → Marimo fallback).

    For all other sources: generates a Marimo notebook and returns
    PlaygroundLaunchResponse (iframe_url). If the runner fails after the
    notebook has been written, the temp dir is cleaned up best-effort so we
    don't leak per-request directories in the common error path. Crash-cleanup
    of orphans across CopyClip restarts is the runner's responsibility on
    startup (see spec, "Orphan cleanup").

    `trace` is an optional InteractionTrace (spec 2026-06-10): each stage emits
    a `launch.*` event; failures emit `launch.error` with the failing stage.
    """
    # Import here to avoid a forward-reference cycle; capture imports playground.
    from .capture import (
        CallDescriptor,
        CaptureError,
        FreeTextCall,
        StepThroughResponse,
        FallbackResponse,
        eligibility_reason,
        run_capture,
        run_free_text_capture,
        probe_target,
    )
    trace = trace if trace is not None else NULL_TRACE
    try:
        resolved = resolve_function_ref(conn, pid, req.function_ref)
    except Exception as exc:
        trace.event("launch.error", stage="resolve", error=str(exc) or type(exc).__name__)
        raise
    trace.event("launch.resolve", file=resolved.file, name=resolved.name,
                qualname=resolved.qualname, kind=resolved.kind,
                module=resolved.module, line_start=resolved.line_start,
                parent_class=resolved.parent_class)

    if req.source == "cuaderno":
        file_line = resolved.file + (f":{resolved.line_start}" if resolved.line_start else "")
        if req.call_text is not None:  # USER free-text path (spec §6/§10)
            # Parse first (cheap — no subprocess). Probe only after parse succeeds
            # so source_lines is not fetched for a path that cannot proceed.
            try:
                ft = FreeTextCall.from_text(req.call_text)
            except PlaygroundError as exc:
                trace.event("launch.error", stage="call_text", error=str(exc))
                raise
            detect, source_lines = probe_target(resolved, project_root=project_root)
            if detect["is_async"] or detect["is_generator"]:
                reason = (
                    "async functions step through as one frame; using the input box instead"
                    if detect["is_async"]
                    else "generator functions step through as one frame; using the input box instead"
                )
                trace.event("launch.capture", outcome="fallback", reason=reason)
                return _cuaderno_fallback(req, project_root, resolved, runner, reason, trace)
            try:
                steps, truncated = run_free_text_capture(ft, resolved, project_root=project_root)
            except CaptureError as exc:
                trace.event("launch.error", stage="capture", error=str(exc))
                raise
        else:  # MODEL structured-descriptor path
            # Parse first (cheap — no subprocess).
            try:
                cd = (CallDescriptor.from_dict(req.call) if req.call is not None
                      else CallDescriptor(function_ref=req.function_ref))
            except PlaygroundError as exc:
                trace.event("launch.error", stage="descriptor", error=str(exc))
                raise
            # Cheap ctor eligibility short-circuit: method with no proposed ctor
            # declines without any subprocess spawn. Defer probe until this passes.
            if (resolved.kind == "method" or resolved.parent_class) and cd.ctor is None:
                reason = "this method needs constructor arguments the example did not supply"
                trace.event("launch.capture", outcome="fallback", reason=reason)
                return _cuaderno_fallback(req, project_root, resolved, runner, reason, trace)
            detect, source_lines = probe_target(resolved, project_root=project_root)
            reason = eligibility_reason(cd, resolved, is_async=detect["is_async"],
                                        is_generator=detect["is_generator"])
            if reason is not None:
                trace.event("launch.capture", outcome="fallback", reason=reason)
                return _cuaderno_fallback(req, project_root, resolved, runner, reason, trace)
            try:
                steps, truncated = run_capture(cd, resolved, project_root=project_root)
            except CaptureError as exc:
                trace.event("launch.error", stage="capture", error=str(exc))
                raise
        # Critical #2: an empty trace means the call never entered the target
        # function — return a FallbackResponse so the frontend shows an honest
        # "nothing ran" note instead of mounting an empty stepper (spec §8).
        if not steps:
            reason = "that call didn't run the function — nothing to step through"
            trace.event("launch.capture", outcome="fallback", reason=reason)
            return _cuaderno_fallback(req, project_root, resolved, runner, reason, trace)
        trace.event("launch.capture", outcome="trace", steps=len(steps), truncated=truncated)
        # Low display #6: for a method, use qualname (e.g. "MyClass.process") so
        # the stepper header shows class context; fall back to name otherwise.
        func_name = (resolved.qualname if resolved.parent_class else resolved.name)
        return StepThroughResponse(
            trace=steps, source_lines=source_lines, func_name=func_name,
            file_line=file_line, truncated=truncated)

    # Non-cuaderno sources: the Marimo iframe path is UNCHANGED.
    return _launch_marimo(req, project_root, resolved, runner, trace)


def _launch_marimo(
    req: PlaygroundLaunchRequest,
    project_root: str,
    resolved: ResolvedFunction,
    runner: MarimoRunner,
    trace: object,
) -> PlaygroundLaunchResponse:
    """Generate a Marimo notebook and spawn via the runner. This is the
    original launch_playground tail, extracted verbatim so the cuaderno
    fallback can reuse it without duplicating spawn logic."""
    try:
        notebook_path = generate_marimo_notebook(req, project_root, resolved)
    except Exception as exc:
        trace.event("launch.error", stage="notebook", error=str(exc) or type(exc).__name__)
        raise
    trace.event("launch.notebook", path=notebook_path,
                input_element=_build_input_element(req.suggested_inputs),
                deps_hint=req.deps_hint)
    mode = "run" if req.source == "cuaderno" else "edit"
    try:
        playground_id, iframe_url = runner.launch(notebook_path, mode=mode, trace=trace)
    except Exception as exc:
        trace.event("launch.error", stage="spawn", error=str(exc) or type(exc).__name__)
        shutil.rmtree(os.path.dirname(notebook_path), ignore_errors=True)
        raise
    trace.event("launch.ready", playground_id=playground_id, iframe_url=iframe_url)
    return PlaygroundLaunchResponse(
        playground_id=playground_id,
        iframe_url=iframe_url,
    )


def _cuaderno_fallback(
    req: PlaygroundLaunchRequest,
    project_root: str,
    resolved: ResolvedFunction,
    runner: MarimoRunner,
    reason: str,
    trace: object,
) -> "FallbackResponse":
    """Decline the step-through, fall back to the Marimo reactive box.

    Sets playground_id from inner.playground_id (spec §8) so the frontend can
    use it for the live-state id, /status poll, and reap — NOT idFromIframeUrl.
    """
    from .capture import FallbackResponse
    inner = _launch_marimo(req, project_root, resolved, runner, trace)
    return FallbackResponse(reason=reason, iframe_url=inner.iframe_url,
                            playground_id=inner.playground_id)


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
    def launch(self, notebook_path: str, mode: str = "edit", trace: object = None) -> tuple[str, str]:
        raise MarimoSpawnError(
            "marimo subprocess manager not yet implemented (issue #88); "
            f"notebook generated at {notebook_path}"
        )

    def kill(self, playground_id: str) -> bool:
        return False

    def status(
        self, playground_id: str
    ) -> Literal["running", "exited", "missing"]:
        return "missing"
