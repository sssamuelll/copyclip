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
    _is_identifier,  # reuse the existing identifier check
)

# Caps — enforced INSIDE the capture callback (spec §5). Defaults chosen to
# abort well under any launch window and to never OOM the subprocess. These
# mirror the driver's module-level caps (Task 5); the orchestrator reads them
# here only for the outer wall-clock backstop timeout.
MAX_STEPS = 1000
REPR_SIZE_CAP = 1000          # chars; longer values surface as kind:"large"
REPR_TIME_BUDGET_S = 0.05     # per-value __repr__ time cap
WALL_CLOCK_BUDGET_S = 8.0     # whole-capture guard
LARGE_CHILDREN_CAP = 20       # first-N children captured for a large value


class InvalidCallDescriptorError(PlaygroundError):
    error_code = "invalid_call_descriptor"
    http_status = 400


class CaptureError(PlaygroundError):
    error_code = "capture_failed"
    http_status = 500


def _assert_json_serializable(value: object, where: str) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
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
    (spec §6/§10). We constrain it to a SINGLE expression so the confirm gesture
    stays 'run this call', not 'run a script' — the caps still bound execution."""
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
        try:
            compile(text, "<call_text>", "eval")
        except SyntaxError as exc:
            raise InvalidCallDescriptorError(
                f"call_text must be a valid Python expression: {exc}"
            ) from exc
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "trace",
            "trace": [s.to_dict() for s in self.trace],
            "source_lines": self.source_lines,
            "func_name": self.func_name,
            "file_line": self.file_line,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class FallbackResponse:
    reason: str
    iframe_url: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "fallback", "reason": self.reason, "iframe_url": self.iframe_url}


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


def normalize_trace(raw: dict[str, Any]) -> list[Step]:
    """Map the driver's intermediate trace onto the fixed Step[] schema.

    The driver pre-flattens each event's in-scope vars into the Var shape but
    NEVER emits ``changed`` (spec §9): the bare callback records line/event/scope
    only. This normalizer DERIVES ``changed`` by diffing each step's value-text
    against the previous step (the renderer never re-derives it), preserving
    CUMULATIVE scope and stable insertion order.

    First-bind detection keys on EVENT, not on step index: on the ``call`` step
    every var is a function ARGUMENT (a pre-existing input) and does NOT flag — it
    only seeds ``prev``; on a ``line``/``return``/``raise`` step a name not yet in
    ``prev`` is a genuine first-bind and flags. Opaque values never flag.
    """
    events = raw.get("trace", [])
    steps: list[Step] = []
    prev: dict[str, str | None] = {}
    for ev in events:
        event = ev.get("event", "line")
        is_call = event == "call"
        scope = [_var_from_raw(v) for v in ev.get("scope", [])]
        changed: list[str] = []
        for v in scope:
            sig = v.text if v.text is not None else (v.summary, v.meta)
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
            line=int(ev.get("line", 0)),
            event=event,
            changed=changed,
            scope=scope,
            raised=ev.get("raised"),
        ))
    return steps
