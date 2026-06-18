"""In-subprocess capture driver for the cuaderno step-through.

Run as ``python -m copyclip.intelligence._capture_driver <spec.json>``: it
imports the user's module, builds the invocation from repr-literal args (the
MODEL path) OR exec's the user's edited free-text call in the module namespace
(the USER path, spec §10), installs a BOUNDED ``sys.settrace`` callback, runs
the call ONCE, and prints the raw trace JSON to stdout. All bounds (MAX_STEPS,
per-value repr size/time, the dangerous-type skip-list, the wall-clock guard)
are enforced HERE, inside the frame callback.

This is our OWN tracer — no third-party tracer is imported (spec §0 decision 1
dropped json-tracer). The license rule (never copy Online Python Tutor source)
holds by not copying it; we emit our own Step/Var-shaped events directly.

This module is import-safe (the helpers are unit-tested in-process); the
``__main__`` block is what the subprocess executes.
"""
from __future__ import annotations

import importlib
import inspect
import json
import sys
import time
import traceback

MAX_STEPS = 1000
REPR_SIZE_CAP = 1000
REPR_TIME_BUDGET_S = 0.05
WALL_CLOCK_BUDGET_S = 8.0
LARGE_CHILDREN_CAP = 20

# Dangerous-to-repr types: file handles, sockets, DB sessions, lazy proxies
# whose __repr__ may block, hit the network, or mutate.
#
# IMPORTANT: match on MODULE-ANCHORED FQN PREFIXES (e.g. "sqlite3.") — NOT
# on loose type-name substrings — so a user class named ConnectionManager or
# EngineConfig is never wrongly hidden (spec §5 cap 4 + Medium correctness fix).
#
# Each entry is matched as a PREFIX of the fully-qualified "module.TypeName"
# string returned by _type_fqn().  Entries that must match any class in a
# well-known module use the module prefix only (e.g. "sqlalchemy.orm.").
_OPAQUE_FQN_PREFIXES: tuple[str, ...] = (
    # stdlib: io — both the public 'io' alias and the C '_io' backing module
    "io.TextIOWrapper",
    "_io.TextIOWrapper",
    "io.BufferedReader",
    "_io.BufferedReader",
    "io.BufferedWriter",
    "_io.BufferedWriter",
    "io.BufferedRandom",
    "_io.BufferedRandom",
    "io.FileIO",
    "_io.FileIO",
    "io.RawIOBase",
    "_io.RawIOBase",
    "io.BufferedIOBase",
    "_io.BufferedIOBase",
    "io.TextIOBase",
    "_io.TextIOBase",
    # stdlib: socket / ssl
    "socket.socket",
    "ssl.SSLSocket",
    "ssl.SSLObject",
    # stdlib: sqlite3
    "sqlite3.Connection",
    "sqlite3.Cursor",
    # stdlib: subprocess / threading / _thread / multiprocessing
    "subprocess.Popen",
    "threading.Thread",
    "threading.Lock",
    "threading._RLock",
    "_thread.lock",
    "_thread.RLock",
    "multiprocessing.process.BaseProcess",
    # SQLAlchemy (any version — match the module prefix)
    "sqlalchemy.",
    # requests / httpx sessions
    "requests.sessions.Session",
    "httpx.",
    # psycopg2 / pymysql connections
    "psycopg2.",
    "pymysql.",
    # redis
    "redis.",
    # celery
    "celery.",
)

_LARGE_BY_LEN = (list, tuple, set, frozenset, dict, bytes, bytearray)


def _type_fqn(obj: object) -> str:
    t = type(obj)
    mod = getattr(t, "__module__", "")
    return f"{mod}.{t.__qualname__}" if mod and mod != "builtins" else t.__qualname__


def _is_opaque_type(obj: object) -> bool:
    """Return True iff the object should be rendered opaque (never repr'd).

    Matches MODULE-ANCHORED FQN prefixes only — a user class whose name
    contains 'Connection' but lives in __main__ or a project module will NOT
    match any entry (their FQN starts with '__main__.' or 'myproject.', not
    'sqlite3.' etc.).
    """
    fqn = _type_fqn(obj)
    return any(fqn == prefix or fqn.startswith(prefix) for prefix in _OPAQUE_FQN_PREFIXES)


def _safe_repr(obj: object) -> str | None:
    """repr() under a wall-clock budget; None if it raises or overruns."""
    start = time.monotonic()
    try:
        r = repr(obj)
    except Exception:  # noqa: BLE001 — a hostile __repr__ must not crash capture
        return None
    if time.monotonic() - start > REPR_TIME_BUDGET_S:
        return None
    return r


def var_for(name: str, obj: object) -> dict:
    """Build one Var dict (driver shape) honoring the size/time caps + skip-list.

    For _LARGE_BY_LEN objects we call _safe_repr ONCE: if the repr is None or
    too long we demote to large immediately, rather than calling _too_big_repr
    (which calls _safe_repr internally) and then calling _safe_repr again.  That
    old double-call could blow the per-value time budget on a near-budget value.
    """
    if _is_opaque_type(obj):
        return {"name": name, "kind": "opaque", "label": _type_fqn(obj)}
    if isinstance(obj, _LARGE_BY_LEN):
        try:
            n = len(obj)
        except Exception:  # noqa: BLE001
            n = 0
        if n > LARGE_CHILDREN_CAP:
            return _large_var(name, obj, n)
        # Single repr call — avoid the double-call that _too_big_repr would cause.
        r = _safe_repr(obj)
        if r is None or len(r) > REPR_SIZE_CAP:
            return _large_var(name, obj, n)
        kind = "scalar" if isinstance(obj, (int, float, bool, str, bytes, type(None))) else "object"
        return {"name": name, "kind": kind, "text": r}
    r = _safe_repr(obj)
    if r is None:
        return {"name": name, "kind": "opaque", "label": _type_fqn(obj)}
    if len(r) > REPR_SIZE_CAP:
        return _large_var(name, obj, _maybe_len(obj))
    kind = "scalar" if isinstance(obj, (int, float, bool, str, bytes, type(None))) else "object"
    return {"name": name, "kind": kind, "text": r}


def _maybe_len(obj: object) -> int | None:
    try:
        return len(obj)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return None


def _too_big_repr(obj: object) -> bool:
    r = _safe_repr(obj)
    return r is None or len(r) > REPR_SIZE_CAP


def _large_var(name: str, obj: object, n: int | None) -> dict:
    summary = type(obj).__name__
    meta = f"{n:,} items" if n is not None else ""
    children: list[dict[str, str]] = []
    if isinstance(obj, dict):
        meta = f"{n:,} keys" if n is not None else ""
        for k, v in list(obj.items())[:LARGE_CHILDREN_CAP]:
            children.append({"name": _safe_repr(k) or "?", "text": _child_text(v)})
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(list(obj)[:LARGE_CHILDREN_CAP]):
            children.append({"name": str(i), "text": _child_text(v)})
    return {"name": name, "kind": "large", "summary": summary, "meta": meta,
            "children": children}


def _child_text(v: object) -> str:
    r = _safe_repr(v)
    if r is None:
        return f"‹{_type_fqn(v)}›"
    return r if len(r) <= REPR_SIZE_CAP else r[: REPR_SIZE_CAP - 1] + "…"


class _Abort(BaseException):
    """Internal: raised inside the tracer to stop a runaway capture.

    MUST be BaseException (not Exception) so that user code with
    ``except Exception:`` or bare ``except:`` cannot accidentally swallow
    the abort signal — the caps would never fire for such functions.
    The existing ``except _Abort:`` handlers in trace_call/_trace_free_text
    are unaffected because they name _Abort explicitly.
    """


def trace_call(func, args: list, kwargs: dict) -> dict:
    """Run ``func(*args, **kwargs)`` once under a bounded settrace. Returns the
    driver-shape raw trace: {"trace": [event...], "truncated": bool}. The driver
    emits line/event/scope ONLY — `changed` is derived later by normalize_trace.

    A call that raises is recorded as a terminal ``raise`` step, not an error.

    ``exception`` events from sys.settrace are NOT emitted (they are not in the
    Step schema union call|line|return|raise).  When an exception propagates out
    of the function, the outer except-BaseException handler emits a ``raise`` step
    with scope captured from the last exception frame so the terminal snapshot is
    correct.
    """
    code = func.__code__
    own_file = code.co_filename
    events: list[dict] = []
    truncated = {"hit": False}
    started = time.monotonic()
    last_line = {"n": 0}
    # Capture the most recent exception frame's locals so the terminal raise step
    # has a populated scope even when the exception propagated out of the callback.
    last_exc_scope: list[dict] = []

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != own_file:
            return tracer  # stay anchored: skip library frames' lines
        if len(events) >= MAX_STEPS or (time.monotonic() - started) > WALL_CLOCK_BUDGET_S:
            truncated["hit"] = True
            raise _Abort()
        scope = [var_for(k, v) for k, v in frame.f_locals.items()]
        last_line["n"] = frame.f_lineno
        if event == "exception":
            # sys.settrace fires 'exception' when an exception is propagating
            # through the frame. This event is NOT in the schema union — suppress
            # the emit.  Save the scope so the terminal raise step (if this
            # exception propagates out) has a non-empty snapshot.
            last_exc_scope[:] = scope
            return tracer
        events.append({"line": frame.f_lineno, "event": event, "scope": scope})
        return tracer

    sys.settrace(tracer)
    try:
        func(*args, **kwargs)
    except _Abort:
        pass
    except BaseException as exc:  # the call itself threw → terminal raise step
        sys.settrace(None)
        # Use the scope captured from the exception frame (last_exc_scope) so the
        # terminal raise step shows live locals, not an empty snapshot.
        scope_for_raise = last_exc_scope if last_exc_scope else []
        events.append({
            "line": last_line["n"], "event": "raise", "scope": scope_for_raise,
            "raised": {"type": type(exc).__name__, "message": str(exc)},
        })
        return {"trace": events, "truncated": truncated["hit"]}
    finally:
        sys.settrace(None)
    return {"trace": events, "truncated": truncated["hit"]}


def _build_invocation(spec: dict):
    """Import the module, resolve the callable, and return (callable, args, kwargs).

    Methods build ``Foo(*ctor.args, **ctor.kwargs).method`` first, so the
    captured trace anchors on the METHOD body, not the constructor.
    """
    module = importlib.import_module(spec["module"])
    name = spec["name"]
    parent = spec.get("parent_class")
    args = spec.get("args", [])
    kwargs = spec.get("kwargs", {})
    if parent:
        cls = getattr(module, parent)
        ctor = spec.get("ctor") or {}
        instance = cls(*ctor.get("args", []), **ctor.get("kwargs", {}))
        return getattr(instance, name), args, kwargs
    return getattr(module, name), args, kwargs


def _trace_free_text(spec: dict) -> dict:
    """USER path (spec §6/§10): exec the user's edited free-text call in the
    target module's namespace under the SAME bounded callback. The expression is
    the user's own code (pytest-equivalent trust); caps still apply. We anchor
    the tracer on the target function's file so only the user's Python is traced.

    ``exception`` events are suppressed (not in the schema union); the terminal
    raise step captures scope from the last exception frame.
    """
    module = importlib.import_module(spec["module"])
    parent = spec.get("parent_class")
    target = getattr(getattr(module, parent), spec["name"]) if parent \
        else getattr(module, spec["name"])
    own_file = target.__code__.co_filename
    text = spec["call_text"]
    ns = dict(vars(module))
    events: list[dict] = []
    truncated = {"hit": False}
    started = time.monotonic()
    code_obj = compile(text, "<call_text>", "eval")
    last_exc_scope: list[dict] = []

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != own_file:
            return tracer
        if len(events) >= MAX_STEPS or (time.monotonic() - started) > WALL_CLOCK_BUDGET_S:
            truncated["hit"] = True
            raise _Abort()
        scope = [var_for(k, v) for k, v in frame.f_locals.items()]
        if event == "exception":
            # Suppress — not in the schema union; save scope for terminal raise.
            last_exc_scope[:] = scope
            return tracer
        events.append({"line": frame.f_lineno, "event": event, "scope": scope})
        return tracer

    sys.settrace(tracer)
    try:
        eval(code_obj, ns, ns)
    except _Abort:
        pass
    except BaseException as exc:
        sys.settrace(None)
        line = events[-1]["line"] if events else 0
        scope_for_raise = last_exc_scope if last_exc_scope else []
        events.append({"line": line, "event": "raise", "scope": scope_for_raise,
                       "raised": {"type": type(exc).__name__, "message": str(exc)}})
        return {"trace": events, "truncated": truncated["hit"]}
    finally:
        sys.settrace(None)
    return {"trace": events, "truncated": truncated["hit"]}


def detect_kind(spec: dict) -> dict:
    """Re-derive async/generator at import time so the server can fall back
    BEFORE running real code. An async generator reports is_async=True so the
    eligibility gate declines it with the 'async' reason (spec §7); is_generator
    stays for SYNC generators only. Returns {"is_async":bool,"is_generator":bool}."""
    module = importlib.import_module(spec["module"])
    parent = spec.get("parent_class")
    target = getattr(getattr(module, parent), spec["name"]) if parent \
        else getattr(module, spec["name"])
    is_async = inspect.iscoroutinefunction(target) or inspect.isasyncgenfunction(target)
    return {
        "is_async": is_async,
        "is_generator": inspect.isgeneratorfunction(target),
    }


def source_lines_for(spec: dict) -> list[dict]:
    module = importlib.import_module(spec["module"])
    parent = spec.get("parent_class")
    target = getattr(getattr(module, parent), spec["name"]) if parent \
        else getattr(module, spec["name"])
    try:
        src, start = inspect.getsourcelines(target)
    except (OSError, TypeError):
        return []
    return [{"num": start + i, "text": line.rstrip("\n")} for i, line in enumerate(src)]


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as fh:
        spec = json.loads(fh.read())
    if spec.get("probe"):  # eligibility/source probe — never runs user logic
        out = {"detect": detect_kind(spec), "source_lines": source_lines_for(spec)}
        print(json.dumps(out))
        return 0
    if spec.get("call_text"):  # USER free-text path (spec §6/§10)
        raw = _trace_free_text(spec)
    else:  # MODEL structured-descriptor path
        callable_, args, kwargs = _build_invocation(spec)
        raw = trace_call(callable_, args, kwargs)
    print(json.dumps(raw))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception:  # noqa: BLE001 — surface import/build errors as a clean payload
        print(json.dumps({"error": traceback.format_exc()}))
        sys.exit(3)
