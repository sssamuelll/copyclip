"""Cuaderno step-through capture (spec 2026-06-16).

A run-request for source "cuaderno" no longer mounts a Marimo iframe: the
model proposes a complete CALL DESCRIPTOR (or the user edits a free-text call),
we run that call ONCE under our own bounded ``sys.settrace`` callback in a
dedicated subprocess (bounded by MAX_STEPS + per-value repr size/time caps +
a dangerous-type skip-list + a wall-clock guard), and we return a Step[] trace
the React stepper replays client-side.

Two authorized consent paths (spec §10):
  1. The MODEL's proposed args/kwargs/ctor are injected as repr() literals,
     never raw source — the same discipline FunctionRef already applies to
     identifiers and paths. This guards against a garbled model proposal.
  2. The USER's edited free-text call is THEIR own code, exec'd in the module
     namespace (REPL-like) only on explicit confirm, under the same pytest
     trust boundary. The repr-literal guard protects against the model, not
     against the user editing their own call. Caps still apply.

There is NO third-party tracer dependency: the capture is our own settrace
callback (spec §0 decision 1 dropped json-tracer). The license rule (never
copy Online Python Tutor source) holds by not copying it — we emit our own
Step/Var schema directly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .playground import (
    FunctionRef,
    PlaygroundError,
    ResolvedFunction,
    _is_identifier,  # reuse the existing identifier check
)

# Caps — single source of truth lives in _capture_driver (which is import-safe
# per its own docstring).  Import them here so the outer wall-clock backstop
# (communicate timeout = WALL_CLOCK_BUDGET_S + 4.0) always references the same
# value as the in-driver guard, with no risk of the two drifting.
from ._capture_driver import (  # noqa: E402
    MAX_STEPS,
    REPR_SIZE_CAP,
    REPR_TIME_BUDGET_S,
    WALL_CLOCK_BUDGET_S,
    LARGE_CHILDREN_CAP,
)

# Concurrency ceiling — each capture is a real interpreter subprocess (PR #177
# safety fix 2). Marimo iframe playgrounds cap at MAX_CONCURRENT_PLAYGROUNDS=5
# in marimo_runner; the capture pool MUST mirror that so a burst of run-requests
# cannot fan out an unbounded number of subprocesses. A saturated pool returns
# CaptureBusyError (503), never blocks the HTTP worker waiting for a permit.
MAX_CONCURRENT_CAPTURES = 5


class InvalidCallDescriptorError(PlaygroundError):
    error_code = "invalid_call_descriptor"
    http_status = 400


class CaptureError(PlaygroundError):
    error_code = "capture_failed"
    http_status = 500


class CaptureBusyError(PlaygroundError):
    """The capture pool is saturated (mirrors marimo_runner's playground cap).

    Raised when MAX_CONCURRENT_CAPTURES subprocesses are already in flight so the
    endpoint can return a stable 503 instead of fanning out unbounded subprocesses
    (each capture is a real Python interpreter spawn)."""
    error_code = "capture_busy"
    http_status = 503


def _assert_json_serializable(value: object, where: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        # Raised for non-serializable types AND for NaN/Inf (which browser
        # JSON.parse cannot handle — json.dumps accepts them by default as
        # 'NaN'/'Infinity', which is non-standard and breaks in the browser).
        raise InvalidCallDescriptorError(
            f"{where} must be JSON-serializable, got {type(value).__name__}: {exc}"
        ) from exc


@dataclass(frozen=True)
class CallDescriptor:
    """The MODEL's proposed invocation (consent path 1). All values are
    repr()-literal-guarded JSON literals."""
    function_ref: FunctionRef
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    ctor: dict[str, Any] | None = None  # {"args": [...], "kwargs": {...}}

    @classmethod
    def from_dict(cls, data: object) -> "CallDescriptor":
        if not isinstance(data, dict):
            raise InvalidCallDescriptorError("call descriptor must be an object")
        ref = FunctionRef.from_dict(data.get("function_ref") or {})
        args = cls._parse_args(data.get("args"), "args")
        kwargs = cls._parse_kwargs(data.get("kwargs"), "kwargs")
        ctor_raw = data.get("ctor")
        ctor: dict[str, Any] | None = None
        if ctor_raw is not None:
            if not isinstance(ctor_raw, dict):
                raise InvalidCallDescriptorError("ctor must be an object when provided")
            ctor = {
                "args": cls._parse_args(ctor_raw.get("args"), "ctor.args"),
                "kwargs": cls._parse_kwargs(ctor_raw.get("kwargs"), "ctor.kwargs"),
            }
        return cls(function_ref=ref, args=args, kwargs=kwargs, ctor=ctor)

    @staticmethod
    def _parse_args(raw: object, where: str) -> list[Any]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise InvalidCallDescriptorError(f"{where} must be a list when provided")
        for v in raw:
            _assert_json_serializable(v, f"{where} element")
        return list(raw)

    @staticmethod
    def _parse_kwargs(raw: object, where: str) -> dict[str, Any]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise InvalidCallDescriptorError(f"{where} must be an object when provided")
        out: dict[str, Any] = {}
        for k, v in raw.items():
            if not isinstance(k, str) or not _is_identifier(k):
                raise InvalidCallDescriptorError(
                    f"{where} key must be a Python identifier, got {k!r}"
                )
            _assert_json_serializable(v, f"{where}[{k!r}]")
            out[k] = v
        return out


@dataclass(frozen=True)
class FreeTextCall:
    """The USER's edited free-text call (consent path 2). NOT repr-guarded:
    it is the user's own expression, exec'd in the module namespace on confirm
    (spec §6/§10). We constrain it to a SINGLE Python expression (which may have
    side effects) so the confirm gesture stays scoped to one expression, not a
    script — the caps still bound execution time."""
    text: str

    @classmethod
    def from_text(cls, raw: object) -> "FreeTextCall":
        if not isinstance(raw, str) or not raw.strip():
            raise InvalidCallDescriptorError("call_text must be a non-empty string")
        text = raw.strip()
        if ";" in text or "\n" in text:
            raise InvalidCallDescriptorError(
                "call_text must be a single expression (no ';' or newlines)"
            )
        import ast as _ast
        try:
            parsed = _ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise InvalidCallDescriptorError(
                f"call_text must be a valid Python expression: {exc}"
            ) from exc
        # Constrain to a Call node so the confirm gesture is always "run a call",
        # not an arbitrary expression with unrelated side-effects.
        if not isinstance(parsed.body, _ast.Call):
            raise InvalidCallDescriptorError(
                "call_text must be a function-call expression (e.g. 'foo(1, x=2)')"
            )
        return cls(text=text)


# ---------------------------------------------------------------------------
# Task 2: Trace schema dataclasses + raw→Step[] normalizer (derives `changed`)
# ---------------------------------------------------------------------------

from typing import Literal  # noqa: E402 — appended after the dataclasses block

StepEvent = Literal["call", "line", "return", "raise"]
VarKind = Literal["scalar", "object", "opaque", "large"]


@dataclass(frozen=True)
class Var:
    name: str
    kind: VarKind
    text: str | None = None       # scalar/object: capped repr
    label: str | None = None      # opaque: type name only (never repr'd)
    summary: str | None = None    # large: "dict" | "DataFrame" | "list" | ...
    meta: str | None = None       # large: "3 keys" | "1000×12" | "5,000 items"
    children: list[dict[str, str]] | None = None  # large: first-N entries

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "kind": self.kind}
        if self.text is not None:
            d["text"] = self.text
        if self.label is not None:
            d["label"] = self.label
        if self.summary is not None:
            d["summary"] = self.summary
        if self.meta is not None:
            d["meta"] = self.meta
        if self.children is not None:
            d["children"] = self.children
        return d


@dataclass(frozen=True)
class Step:
    line: int
    event: StepEvent
    changed: list[str]
    scope: list[Var]
    raised: dict[str, str] | None = None  # only on the final step if it threw

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "line": self.line,
            "event": self.event,
            "changed": list(self.changed),
            "scope": [v.to_dict() for v in self.scope],
        }
        if self.raised is not None:
            d["raised"] = self.raised
        return d


@dataclass(frozen=True)
class StepThroughResponse:
    trace: list[Step]
    source_lines: list[dict[str, Any]]
    func_name: str
    file_line: str
    truncated: bool
    # PR #177 fix 5: split the bare `truncated` bool into a REASON so the frontend
    # shows the right message — 'steps' (MAX_STEPS overflow) vs 'time' (wall-clock
    # overrun) — and never conflates truncation with a terminal raise. None when
    # the trace completed cleanly.
    truncated_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "trace",
            "trace": [s.to_dict() for s in self.trace],
            "source_lines": self.source_lines,
            "func_name": self.func_name,
            "file_line": self.file_line,
            "truncated": self.truncated,
            "truncated_reason": self.truncated_reason,
        }


@dataclass(frozen=True)
class FallbackResponse:
    reason: str
    iframe_url: str
    playground_id: str  # required — set from inner.playground_id in _cuaderno_fallback (spec §8)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "fallback", "reason": self.reason,
                "iframe_url": self.iframe_url, "playground_id": self.playground_id}


def _var_from_raw(raw: dict[str, Any]) -> Var:
    return Var(
        name=str(raw.get("name", "")),
        kind=raw.get("kind", "scalar"),
        text=raw.get("text"),
        label=raw.get("label"),
        summary=raw.get("summary"),
        meta=raw.get("meta"),
        children=raw.get("children"),
    )


def _var_signature(v: Var) -> Any:
    """The change-detection signature for one Var.

    PR #177 fix 4 (change-derivation under-reports): keying a large var on
    ``(summary, meta)`` alone misses an IN-PLACE mutation whose summary/meta stay
    stable (e.g. a 30-item list whose 0th element changed). Fold the captured
    ``children`` into the large signature so a same-summary content change still
    flags. ``children`` are already capped at capture (LARGE_CHILDREN_CAP) and are
    plain (name, text) dicts, so this stays cheap and side-effect-free — no extra
    repr / len / id call here.

    For scalar/object vars the signature is the capped repr text.
    """
    if v.text is not None:
        return v.text
    if v.kind == "large":
        # Tuple-of-tuples so it is hashable/comparable and stable across steps.
        child_sig = tuple(
            (c.get("name"), c.get("text")) for c in (v.children or [])
        )
        return (v.summary, v.meta, child_sig)
    return (v.summary, v.meta)


def normalize_trace(raw: dict[str, Any], *, source_lines: list[dict[str, Any]] | None = None) -> list[Step]:
    """Map the driver's intermediate trace onto the fixed Step[] schema.

    The driver pre-flattens each event's in-scope vars into the Var shape but
    NEVER emits ``changed`` (spec §9): the bare callback records line/event/scope
    only. This normalizer DERIVES ``changed`` by diffing each step's value-text
    against the previous step (the renderer never re-derives it).

    **Scope completeness is the DRIVER's contract, not the normalizer's.**
    The driver MUST emit the full in-scope snapshot at every step (spec §9's
    "ALL in-scope vars at this step" requirement).  The normalizer passes
    ``ev["scope"]`` straight through — it does NOT accumulate vars across steps.
    A driver that emits incremental (delta-only) scope would produce incomplete
    ``Step.scope`` lists; the normalizer cannot detect or compensate for that.

    First-bind detection keys on EVENT, not on step index: on the ``call`` step
    every var is a function ARGUMENT (a pre-existing input) and does NOT flag — it
    only seeds ``prev``; on a ``line``/``return``/``raise`` step a name not yet in
    ``prev`` is a genuine first-bind and flags. Opaque values never flag.

    Defense-in-depth (PR #177 fix 1): if ``source_lines`` is supplied, any step
    whose ``line`` falls OUTSIDE the captured source range is DROPPED — a foreign
    frame (a helper sibling, a leaked library frame) can never null the slab or
    mis-anchor on the target's source pane even if frame-scoping ever regressed.
    With no ``source_lines`` (back-compat / unit tests) every step is kept.
    """
    events = raw.get("trace", [])
    lo = hi = None
    if source_lines:
        nums = [sl.get("num") for sl in source_lines if isinstance(sl.get("num"), int)]
        if nums:
            lo, hi = min(nums), max(nums)
    steps: list[Step] = []
    # Maps var name → its last observed signature (see _var_signature).
    prev: dict[str, Any] = {}
    for ev in events:
        line = int(ev.get("line", 0))
        # Defense-in-depth: drop any step anchored outside the known source range.
        # A line==0 sentinel (e.g. a raise before the target body ran) is exempt
        # so a terminal raise is never silently swallowed.
        if lo is not None and line != 0 and not (lo <= line <= hi):
            continue
        event = ev.get("event", "line")
        is_call = event == "call"
        scope = [_var_from_raw(v) for v in ev.get("scope", [])]
        changed: list[str] = []
        for v in scope:
            sig = _var_signature(v)
            seen = v.name in prev
            if v.kind == "opaque":
                prev[v.name] = sig  # opaque never flags (spec §9); still seed prev
                continue
            if not seen:
                # Genuine first-bind flags, EXCEPT on the call step (args are
                # pre-existing inputs): the call step only seeds prev.
                if not is_call:
                    changed.append(v.name)
            elif prev[v.name] != sig:
                changed.append(v.name)
            prev[v.name] = sig
        steps.append(Step(
            line=line,
            event=event,
            changed=changed,
            scope=scope,
            raised=ev.get("raised"),
        ))
    return steps


# ---------------------------------------------------------------------------
# Task 3: Eligibility gate
# ---------------------------------------------------------------------------


def eligibility_reason(
    cd: CallDescriptor,
    resolved: ResolvedFunction,
    *,
    is_async: bool,
    is_generator: bool,
    is_decorated: bool = False,
) -> str | None:
    """Return a human reason to DECLINE the step-through, or None if eligible.

    A decline means: fall back to the existing reactive Marimo box (spec §7).
    Async / generator targets are honestly un-representable on a linear
    scrubber; a method with no proposed ctor cannot form a runnable call.

    NOTE: an ASYNC GENERATOR reports is_async=True (Task 4 detect_kind), so it
    declines with the 'async' reason — checked before the generator branch.

    PR #177 fix 2 (empty-trace honesty): a DECORATED target makes the capture
    anchor on the wrapper's file/code, so the real body is never traced and the
    capture comes back empty. Detect it at probe time and decline with an honest
    reason rather than ship an empty stepper or a misleading "didn't run" note.
    """
    if is_async:
        return "async functions step through as one frame; using the input box instead"
    if is_generator:
        return "generator functions step through as one frame; using the input box instead"
    if is_decorated:
        return ("this function is decorated, so the step-through can't anchor on its "
                "body; using the input box instead")
    if resolved.kind == "method" or resolved.parent_class:
        if cd.ctor is None:
            return "this method needs constructor arguments the example did not supply"
    return None


# ---------------------------------------------------------------------------
# Task 5: Subprocess orchestration — process-group kill + wall-clock backstop
# ---------------------------------------------------------------------------

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

# Bounded permit pool for in-flight capture subprocesses (PR #177 safety fix 2).
# A non-blocking acquire keeps a saturated pool from parking the HTTP worker; the
# caller raises CaptureBusyError (503) instead. Bounded at MAX_CONCURRENT_CAPTURES
# to mirror marimo_runner.MAX_CONCURRENT_PLAYGROUNDS.
_CAPTURE_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_CAPTURES)


def _spec_for(cd: CallDescriptor, resolved: ResolvedFunction, *, probe: bool) -> dict:
    spec: dict[str, Any] = {
        "module": resolved.module,
        "name": resolved.name,
        "parent_class": resolved.parent_class,
        "args": cd.args,
        "kwargs": cd.kwargs,
        "probe": probe,
    }
    if cd.ctor is not None:
        spec["ctor"] = cd.ctor
    return spec


def _free_text_spec(ft: FreeTextCall, resolved: ResolvedFunction) -> dict:
    return {
        "module": resolved.module,
        "name": resolved.name,
        "parent_class": resolved.parent_class,
        "call_text": ft.text,
        "probe": False,
    }


_TRACE_FILE_NAME = "trace.json"


def _run_driver(spec: dict, project_root: str) -> dict:
    """Spawn the driver in the user's env and return the parsed trace payload.

    NEW PROCESS GROUP so a hung capture (and any tree it spawned) dies cleanly:
    CREATE_NEW_PROCESS_GROUP on Windows / start_new_session on POSIX (spec §10).

    Timeout discipline (PR #177 safety fix 5): the in-driver MAX_STEPS / WALL_CLOCK
    / per-value caps are BEST-EFFORT — they only fire at trace-event boundaries, so
    a single blocking C call or a hostile ``__repr__`` is NOT bounded by them. The
    SOLE HARD bound on total wall time is THIS function's
    ``communicate(timeout=WALL_CLOCK_BUDGET_S + 4.0)`` outer subprocess timeout: on
    overrun we reclaim the whole process tree and raise CaptureError.

    stdout demux (PR #177 safety fix 4): the user's real code shares the
    subprocess's stdout with us, so a user ``print`` / C flush / atexit line would
    corrupt a stdout-parsed trace. The driver instead writes the trace JSON to a
    KNOWN file (``trace.json`` in the spec temp dir) and redirects the user's own
    stdout to stderr; we read the trace from that file and never parse stdout. When
    the subprocess exits non-zero we do NOT attempt any parse — a crash surfaces as
    a clean subprocess-failed CaptureError, not a wrong-cause parse error.

    Concurrency (PR #177 safety fix 2): a non-blocking semaphore acquire bounds the
    number of in-flight captures to MAX_CONCURRENT_CAPTURES; a saturated pool raises
    CaptureBusyError (503) rather than blocking the HTTP worker or fanning out.
    """
    if not _CAPTURE_SEMAPHORE.acquire(blocking=False):
        raise CaptureBusyError(
            f"max {MAX_CONCURRENT_CAPTURES} captures already running; "
            "wait for one to finish before launching another"
        )
    td = tempfile.mkdtemp(prefix="copyclip-capture-")
    try:
        spec_path = os.path.join(td, "spec.json")
        trace_path = os.path.join(td, _TRACE_FILE_NAME)
        spec = {**spec, "trace_path": trace_path}
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        cmd = [sys.executable, "-m", "copyclip.intelligence._capture_driver", spec_path]
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [os.path.abspath(project_root), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        popen_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=os.path.abspath(project_root), env=env, text=True, **popen_kwargs,
        )
        try:
            out, err = proc.communicate(timeout=WALL_CLOCK_BUDGET_S + 4.0)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            # Medium robustness: bound the post-kill drain so a pipe-holding
            # grandchild (e.g. a spawned subprocess the user's code started)
            # cannot hang the HTTP worker forever (spec §10 process-group kill).
            try:
                proc.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
            raise CaptureError("capture exceeded the wall-clock budget and was killed")
        # A non-zero rc is an infra/crash failure: do NOT try to parse anything as a
        # trace (the user's stdout is NOT the trace channel — fix 4). Surface the rc
        # and a stderr tail directly so the cause is honest.
        if proc.returncode != 0:
            raise CaptureError(
                f"capture subprocess failed (rc={proc.returncode}): {err[-500:]}")
        # Trace lives in a known file, never stdout. A missing/empty file means the
        # driver produced nothing parseable (distinct from a crash above).
        try:
            with open(trace_path, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            raise CaptureError(
                f"capture produced no trace file: {exc}; stderr={err[-300:]}")
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise CaptureError(
                f"capture produced no parseable trace: {exc}; stderr={err[-300:]}")
        if "error" in payload:
            raise CaptureError(f"capture driver error: {payload['error'][-500:]}")
        return payload
    finally:
        shutil.rmtree(td, ignore_errors=True)
        _CAPTURE_SEMAPHORE.release()


# Short grace between the cooperative CTRL_BREAK / SIGTERM signal and the
# forced tree reclaim, so a child that handles the signal can exit cleanly.
_KILL_GRACE_S = 1.5


def _reclaim_tree(pid: int) -> None:
    """Force-kill a process AND every descendant by pid (PR #177 safety fix 6).

    On Windows, TerminateProcess (proc.kill) kills only the target — grandchildren
    a hung capture spawned would leak. psutil (already a marimo_runner dep) walks
    the live tree and kills each member, so a spawned subprocess the user's code
    started is reclaimed too. Best-effort: a process that already exited or that we
    cannot signal is skipped."""
    try:
        import psutil  # local import — only needed on the kill path
        parent = psutil.Process(pid)
    except Exception:  # noqa: BLE001 — process gone / psutil unavailable
        return
    procs = []
    try:
        procs = parent.children(recursive=True)
    except Exception:  # noqa: BLE001
        pass
    procs.append(parent)
    for p in procs:
        try:
            p.kill()
        except Exception:  # noqa: BLE001
            pass


def _kill_group(proc: subprocess.Popen) -> None:
    """Reclaim the whole process TREE (spec §10 + PR #177 safety fix 6).

    First send the cooperative group signal — CTRL_BREAK_EVENT on Windows (NOT the
    non-existent subprocess.signal.CTRL_BREAK_EVENT), SIGTERM to the group on POSIX
    — then give it a short grace (proc.wait) so a child that handles the signal can
    exit on its own. On overrun we reclaim the tree: psutil children().kill() on
    Windows (TerminateProcess alone leaks grandchildren), os.killpg(SIGKILL) on
    POSIX. proc.kill() is the final fallback."""
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=_KILL_GRACE_S)
        return  # exited within the grace window — nothing left to reclaim
    except Exception:  # noqa: BLE001 — TimeoutExpired or a non-waitable mock
        pass
    try:
        if sys.platform == "win32":
            _reclaim_tree(proc.pid)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def resolved_to_ref(resolved: ResolvedFunction) -> FunctionRef:
    return FunctionRef(file=resolved.file, name=resolved.name, line=resolved.line_start,
                       qualname=resolved.qualname if resolved.qualname != resolved.name else None)


def probe_target(resolved: ResolvedFunction, *, project_root: str) -> tuple[dict, list[dict]]:
    """Import-time probe — async/generator detection + source lines — without
    running the user's logic. Returns (detect, source_lines)."""
    payload = _run_driver(
        _spec_for(CallDescriptor(function_ref=resolved_to_ref(resolved)), resolved, probe=True),
        project_root)
    return payload.get("detect", {"is_async": False, "is_generator": False}), \
        payload.get("source_lines", [])


def _truncated_reason_of(payload: dict) -> str | None:
    """Normalize the driver's truncated_reason ('steps'|'time'|None). Back-compat:
    an older driver that only emits `truncated:true` (no reason) is reported as
    'steps' (the historical default cause) so the frontend never sees a truthy
    truncated with a null reason."""
    if not payload.get("truncated"):
        return None
    reason = payload.get("truncated_reason")
    return reason if reason in ("steps", "time") else "steps"


def run_capture(cd: CallDescriptor, resolved: ResolvedFunction, *, project_root: str,
                source_lines: list[dict[str, Any]] | None = None):
    """MODEL path: run the descriptor call ONCE; return
    (Step[], truncated, truncated_reason). ``source_lines`` (when supplied) gates
    the defense-in-depth out-of-range filter in normalize_trace (PR #177 fix 1)."""
    payload = _run_driver(_spec_for(cd, resolved, probe=False), project_root)
    steps = normalize_trace(payload, source_lines=source_lines)
    return steps, bool(payload.get("truncated")), _truncated_reason_of(payload)


def run_free_text_capture(ft: FreeTextCall, resolved: ResolvedFunction, *, project_root: str,
                          source_lines: list[dict[str, Any]] | None = None):
    """USER path: exec the edited free-text call ONCE; return
    (Step[], truncated, truncated_reason)."""
    payload = _run_driver(_free_text_spec(ft, resolved), project_root)
    steps = normalize_trace(payload, source_lines=source_lines)
    return steps, bool(payload.get("truncated")), _truncated_reason_of(payload)
