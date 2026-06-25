# Cuaderno Step-Through (Backend) Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.
**Goal:** For a cuaderno run-request, capture one real execution of the proposed call with our own **hand-rolled bounded `sys.settrace` callback** (under hard caps enforced inside that callback), and return a `StepThroughResponse` trace JSON the React stepper replays — while the Marimo iframe path stays intact for every other source and for the fallback. The proposed call reaches the widget two ways: the **model** proposes a structured `CallDescriptor`, OR the **user** edits a **free-text** call string that the driver `exec`s in the module namespace on confirm.
**Architecture:** A new `capture.py` module owns the call-descriptor type (`function_ref` + `args`/`kwargs`/`ctor`, all injected as `repr()` literals), the free-text call carrier, an eligibility gate, a capture driver that runs our bounded `sys.settrace` callback in a dedicated subprocess under MAX_STEPS + per-value repr size/time caps + a dangerous-type skip-list + a wall-clock guard, and a normalizer that derives `changed` and maps the driver's intermediate trace onto the fixed `Step[]`/`Var` schema (including the `raise` terminal step and `large`/`opaque` value kinds). `launch_playground` branches on `source == "cuaderno"`: eligible → capture → `StepThroughResponse`; ineligible or async/generator/async-generator → `FallbackResponse` reusing the existing Marimo generator+runner. The compositor floor emits the model's **real** call descriptor into the playground widget payload (so the frontend renders the actual invocation, never a fake `name(…)`), and the breadcrumb is renamed to a "step through" phrasing; prompts teach the model to propose `args`/`kwargs`/`ctor`.
**Tech Stack:** Python 3.14, our own `sys.settrace`-based capture (no third-party tracer — `json-tracer` was dropped per spec §0 decision 1; the license rule holds by never copying Online Python Tutor source), stdlib `subprocess` with process-group kill, `dataclasses`, sqlite symbols table, pytest.
---

## File Structure

| File | Created/Modified | Responsibility |
|------|------------------|----------------|
| `src/copyclip/intelligence/capture.py` | **Created** | Call-descriptor type + validation; the free-text call carrier; eligibility gate; the capture-driver orchestration under caps; the raw-trace → `Step[]`/`Var` normalizer (derives `changed`); `StepThroughResponse`/`FallbackResponse` dataclasses. No third-party tracer dependency. |
| `src/copyclip/intelligence/_capture_driver.py` | **Created** | The in-subprocess driver: imports the user's module, builds the invocation from repr-literal args OR `exec`s the user's edited free-text call in the module namespace, installs the bounded `sys.settrace` callback (MAX_STEPS, per-value size/time repr caps, skip-list, wall-clock), runs the call once, prints the raw trace JSON to stdout, records a `raise` terminal step if the call throws. |
| `src/copyclip/intelligence/playground.py` | Modified (`:130-165`, `:500-547`) | `PlaygroundLaunchRequest` gains optional `call` (structured CallDescriptor dict) and `call_text` (user free-text); `launch_playground` branches `source=="cuaderno"` to capture vs the existing Marimo path; new trace events for the capture stages. |
| `src/copyclip/intelligence/server.py` | Modified (`:1620-1660`) | `/api/playground/launch` returns either `StepThroughResponse`/`FallbackResponse` (cuaderno) or `PlaygroundLaunchResponse` (other sources); error codes for `invalid_call_descriptor` / capture failures. |
| `src/copyclip/intelligence/cuaderno/schema.py` | Modified (`:61-71`) | `Widget.playground` gains an optional `call` param so the floor carries the model's **real** proposed descriptor into the widget payload. |
| `src/copyclip/intelligence/cuaderno/compositor.py` | Modified (`:141-169`) | Breadcrumb rename to "Recorre X paso a paso" / "Step through X"; floor emits the playground widget WITH the model-proposed `call` descriptor (real invocation, not a placeholder). |
| `src/copyclip/intelligence/cuaderno/prompts.py` | Modified (`:94-100`, `:197-200`) | Run directive + playground widget spec teach the model to propose `args`/`kwargs`/`ctor` for the step-through. |
| `src/copyclip/intelligence/marimo_runner.py` | Modified (`:167-171`, `:318-337`) | `_best_effort_kill` gains process-group kill (`CREATE_NEW_PROCESS_GROUP`/`start_new_session` at spawn + `signal.CTRL_BREAK_EVENT`/`os.killpg`); fixes the `subprocess.signal.CTRL_BREAK_EVENT` bug. |
| `tests/test_capture.py` | **Created** | Unit tests for descriptor validation, free-text carrier, eligibility, repr-literal injection, EVERY cap firing (MAX_STEPS, repr-time, wall-clock, size, skip-list), the `changed` derivation vs the handoff, raise-terminal step, large/opaque kinds, normalizer schema conformance. |
| `tests/test_playground.py` | Modified (one re-point at `:~1001` + new endpoint/branch tests appended) | Re-point the single behavioral assertion (`test_cuaderno_source_launches_run_mode`); append branch tests (eligible→trace, async→fallback, non-cuaderno→iframe) and endpoint round-trip tests. The 28 `generate_marimo_notebook` template-pinned assertions are UNCHANGED (the template is untouched; see Task 11). |
| `tests/test_cuaderno_playground_floor.py` | Modified | Add breadcrumb-string assertions for the new "step through" phrasing + assert the floor carries the model `call`. |
| `tests/test_marimo_runner.py` | Modified | Assert `_best_effort_kill` group-kills (mock `Popen`, assert `send_signal`/`killpg` path) and that spawn sets the new-process-group flag. |

---

### Task 1: CallDescriptor type + free-text carrier + validation (repr-literal injection guard)

**Files:** `src/copyclip/intelligence/capture.py` (new); `tests/test_capture.py` (new)

> Note: there is no `json-tracer` (or any third-party tracer) dependency to add — spec §0 decision 1 dropped it. Capture is our own bounded `sys.settrace` callback (Task 5). The `playground` extra in `pyproject.toml` is left exactly as-is (`marimo` only).

- [ ] **Step 1: Write failing test** — create `tests/test_capture.py`:
```python
from __future__ import annotations

import pytest

from copyclip.intelligence.playground import FunctionRef
from copyclip.intelligence.capture import (
    CallDescriptor,
    FreeTextCall,
    InvalidCallDescriptorError,
)


def test_call_descriptor_minimal_no_args():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/foo.py", "name": "bar"}})
    assert isinstance(cd.function_ref, FunctionRef)
    assert cd.args == []
    assert cd.kwargs == {}
    assert cd.ctor is None


def test_call_descriptor_args_kwargs_ctor():
    cd = CallDescriptor.from_dict({
        "function_ref": {"file": "src/foo.py", "name": "method_name", "qualname": "Foo.method_name"},
        "args": [1, "x"],
        "kwargs": {"flag": True},
        "ctor": {"args": [42], "kwargs": {"name": "n"}},
    })
    assert cd.args == [1, "x"]
    assert cd.kwargs == {"flag": True}
    assert cd.ctor == {"args": [42], "kwargs": {"name": "n"}}


def test_call_descriptor_rejects_non_json_serializable():
    with pytest.raises(InvalidCallDescriptorError):
        CallDescriptor.from_dict({
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "args": [object()],  # not JSON-serializable
        })


def test_call_descriptor_rejects_non_list_args():
    with pytest.raises(InvalidCallDescriptorError):
        CallDescriptor.from_dict({
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "args": {"not": "a list"},
        })


def test_call_descriptor_rejects_non_string_kwarg_keys():
    with pytest.raises(InvalidCallDescriptorError):
        CallDescriptor.from_dict({
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "kwargs": {"ok": 1, "bad key with space": 2},  # not an identifier
        })


def test_free_text_call_carries_user_expression_verbatim():
    # The USER's edited free text is THEIR own code (spec §10 path 2). It is NOT
    # repr-guarded — it is exec'd in the module namespace on explicit confirm.
    ft = FreeTextCall.from_text("addup(3 + 4)")
    assert ft.text == "addup(3 + 4)"


def test_free_text_call_rejects_blank():
    with pytest.raises(InvalidCallDescriptorError):
        FreeTextCall.from_text("   ")


def test_free_text_call_rejects_multiple_statements():
    # A single expression, not a script: reject semicolons / newlines so the
    # confirm gesture stays "run THIS call", not "run an arbitrary program".
    with pytest.raises(InvalidCallDescriptorError):
        FreeTextCall.from_text("import os; os.system('x')")
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_capture.py -q` → FAIL (`capture` module / `CallDescriptor` / `FreeTextCall` do not exist).

- [ ] **Step 3: Minimal impl** — create `src/copyclip/intelligence/capture.py`:
```python
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
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_capture.py -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/capture.py tests/test_capture.py && git commit -m "feat(cuaderno): call descriptor + free-text call carrier with repr-literal injection guard"`

---

### Task 2: Trace schema dataclasses + the raw→Step[] normalizer (derives `changed`)

**Files:** `src/copyclip/intelligence/capture.py` (modify)

- [ ] **Step 1: Write failing test** — append to `tests/test_capture.py`:
```python
from copyclip.intelligence.capture import (
    Step,
    Var,
    normalize_trace,
    StepThroughResponse,
    FallbackResponse,
)


def _raw(events):
    # The driver pre-flattens each event's in-scope vars into the Var shape but
    # NEVER emits `changed` — the normalizer derives it (spec §9).
    return {"trace": events}


def test_normalize_derives_changed_vars_between_steps():
    raw = _raw([
        {"line": 1, "event": "line", "scope": [{"name": "x", "kind": "scalar", "text": "1"}]},
        {"line": 2, "event": "line", "scope": [
            {"name": "x", "kind": "scalar", "text": "1"},
            {"name": "y", "kind": "scalar", "text": "2"},
        ]},
        {"line": 3, "event": "line", "scope": [
            {"name": "x", "kind": "scalar", "text": "9"},
            {"name": "y", "kind": "scalar", "text": "2"},
        ]},
    ])
    steps = normalize_trace(raw)
    assert [s.changed for s in steps] == [["x"], ["y"], ["x"]]
    # scope is CUMULATIVE: every variable ever seen re-rendered each step.
    assert [v.name for v in steps[2].scope] == ["x", "y"]


def test_normalize_changed_matches_handoff_for_canonical_resolve_trace():
    """Spec §9 hard requirement: the DERIVED `changed` must match the handoff's
    hand-authored `changed` for the canonical resolve-trace so capture and the
    React renderer never silently diverge. The driver emits line/event/scope
    only; this proves the normalizer reproduces the handoff's per-step deltas."""
    # Driver-shape input (no `changed`): a tiny slice of the handoff's
    # resolve_function_ref trace — bind `row`, then `resolved`, then return.
    raw = _raw([
        {"line": 255, "event": "call", "scope": [
            {"name": "conn", "kind": "opaque", "label": "sqlite3.Connection"},
            {"name": "project_id", "kind": "scalar", "text": "42"},
        ]},
        {"line": 256, "event": "line", "scope": [
            {"name": "conn", "kind": "opaque", "label": "sqlite3.Connection"},
            {"name": "project_id", "kind": "scalar", "text": "42"},
            {"name": "row", "kind": "large", "summary": "tuple", "meta": "6 items"},
        ]},
        {"line": 257, "event": "line", "scope": [
            {"name": "conn", "kind": "opaque", "label": "sqlite3.Connection"},
            {"name": "project_id", "kind": "scalar", "text": "42"},
            {"name": "row", "kind": "large", "summary": "tuple", "meta": "6 items"},
            {"name": "resolved", "kind": "object", "text": "ResolvedFunction(name='bar')"},
        ]},
    ])
    # Hand-authored `changed`, copied from the handoff's Component fixture:
    handoff_changed = [[], ["row"], ["resolved"]]
    # `conn`/`project_id` are call-frame args present from step 0; the handoff
    # counts neither the opaque `conn` nor unchanged args as moved.
    steps = normalize_trace(raw)
    assert [s.changed for s in steps] == handoff_changed


def test_normalize_emits_raise_terminal_step():
    raw = _raw([
        {"line": 1, "event": "line", "scope": []},
        {"line": 2, "event": "raise", "scope": [],
         "raised": {"type": "KeyError", "message": "'x'"}},
    ])
    steps = normalize_trace(raw)
    assert steps[-1].event == "raise"
    assert steps[-1].raised == {"type": "KeyError", "message": "'x'"}


def test_step_and_var_to_dict_shape():
    s = Step(line=10, event="line", changed=["a"],
             scope=[Var(name="a", kind="large", summary="dict", meta="3 keys",
                        children=[{"name": "k", "text": "1"}])])
    d = s.to_dict()
    assert d == {
        "line": 10, "event": "line", "changed": ["a"],
        "scope": [{"name": "a", "kind": "large", "summary": "dict",
                   "meta": "3 keys", "children": [{"name": "k", "text": "1"}]}],
    }


def test_opaque_var_carries_label_not_text():
    v = Var(name="f", kind="opaque", label="TextIOWrapper")
    assert v.to_dict() == {"name": "f", "kind": "opaque", "label": "TextIOWrapper"}


def test_responses_to_dict():
    st = StepThroughResponse(
        trace=[Step(line=1, event="line", changed=[], scope=[])],
        source_lines=[{"num": 1, "text": "def f():"}],
        func_name="f", file_line="src/foo.py:1", truncated=False)
    assert st.to_dict()["kind"] == "trace"
    assert st.to_dict()["truncated"] is False
    fb = FallbackResponse(reason="async function", iframe_url="http://127.0.0.1:5000/")
    assert fb.to_dict() == {"kind": "fallback", "reason": "async function",
                            "iframe_url": "http://127.0.0.1:5000/"}
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_capture.py -q` → FAIL (`Step`/`Var`/`normalize_trace`/responses undefined).

- [ ] **Step 3: Minimal impl** — append to `src/copyclip/intelligence/capture.py`:
```python
from typing import Literal

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
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_capture.py -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/capture.py tests/test_capture.py && git commit -m "feat(cuaderno): Step/Var trace schema + normalizer that derives changed per spec §9"`

---

### Task 3: Eligibility gate (async / generator / async-generator / un-constructable → fallback)

**Files:** `src/copyclip/intelligence/capture.py` (modify)

- [ ] **Step 1: Write failing test** — append to `tests/test_capture.py`:
```python
from copyclip.intelligence.playground import ResolvedFunction
from copyclip.intelligence.capture import eligibility_reason


def _resolved(kind="function", parent=None, name="bar"):
    return ResolvedFunction(file="src/copyclip/foo.py", name=name,
                            qualname=(f"{parent}.{name}" if parent else name),
                            kind=kind, module="copyclip.foo",
                            line_start=10, parent_class=parent)


def test_eligible_plain_function_with_no_args_required():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    assert eligibility_reason(cd, _resolved(), is_async=False, is_generator=False) is None


def test_async_function_declines():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=True, is_generator=False)
    assert reason and "async" in reason.lower()


def test_async_generator_declines_with_async_reason():
    # detect_kind reports is_async for an async generator (Task 4); the gate must
    # surface the 'async' reason, not the 'generator' one (spec §7 decline copy).
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=True, is_generator=False)
    assert reason and "async" in reason.lower()


def test_generator_function_declines():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=False, is_generator=True)
    assert reason and "generator" in reason.lower()


def test_method_without_ctor_declines():
    cd = CallDescriptor.from_dict({
        "function_ref": {"file": "src/copyclip/foo.py", "name": "m", "qualname": "Foo.m"},
    })
    reason = eligibility_reason(cd, _resolved(kind="method", parent="Foo", name="m"),
                               is_async=False, is_generator=False)
    assert reason and "constructor" in reason.lower()


def test_method_with_ctor_is_eligible():
    cd = CallDescriptor.from_dict({
        "function_ref": {"file": "src/copyclip/foo.py", "name": "m", "qualname": "Foo.m"},
        "ctor": {"args": [1]},
    })
    assert eligibility_reason(cd, _resolved(kind="method", parent="Foo", name="m"),
                              is_async=False, is_generator=False) is None
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_capture.py -q` → FAIL (`eligibility_reason` undefined).

- [ ] **Step 3: Minimal impl** — add `ResolvedFunction` to the `from .playground import (...)` block at the top of `capture.py`, then append:
```python
def eligibility_reason(
    cd: CallDescriptor,
    resolved: ResolvedFunction,
    *,
    is_async: bool,
    is_generator: bool,
) -> str | None:
    """Return a human reason to DECLINE the step-through, or None if eligible.

    A decline means: fall back to the existing reactive Marimo box (spec §7).
    Async / generator targets are honestly un-representable on a linear
    scrubber; a method with no proposed ctor cannot form a runnable call.

    NOTE: an ASYNC GENERATOR reports is_async=True (Task 4 detect_kind), so it
    declines with the 'async' reason — checked before the generator branch.
    """
    if is_async:
        return "async functions step through as one frame; using the input box instead"
    if is_generator:
        return "generator functions step through as one frame; using the input box instead"
    if resolved.kind == "method" or resolved.parent_class:
        if cd.ctor is None:
            return "this method needs constructor arguments the example did not supply"
    return None
```
Note: `is_async`/`is_generator` come from the driver's import-time probe (`detect_kind`, Task 4); the server passes them through (Task 7). The free-text path (Task 6) skips the structured eligibility gate — a user who edits the call owns its shape — but still imports the target to source-probe and to detect async/generator for the same honest decline.

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_capture.py -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/capture.py tests/test_capture.py && git commit -m "feat(cuaderno): eligibility gate declines async/generator/async-gen/un-constructable to fallback"`

---

### Task 4: The in-subprocess capture driver (bounded settrace; every cap enforced inside the callback)

**Files:** `src/copyclip/intelligence/_capture_driver.py` (new)

- [ ] **Step 1: Write failing test** — append to `tests/test_capture.py` (the driver is exercised end-to-end as a subprocess in Task 6; here we unit-test its pure helpers + a directly-invoked trace, and PROVE every cap fires):
```python
import importlib

driver = importlib.import_module("copyclip.intelligence._capture_driver")


def test_bounded_repr_summarizes_large_collection():
    v = driver.var_for("xs", list(range(5000)))
    assert v["kind"] == "large"
    assert v["summary"] == "list"
    assert "5,000" in v["meta"] or "5000" in v["meta"]
    assert len(v["children"]) <= driver.LARGE_CHILDREN_CAP


def test_bounded_repr_scalar_is_capped_text():
    v = driver.var_for("n", 42)
    assert v["kind"] == "scalar"
    assert v["text"] == "42"


def test_repr_size_cap_demotes_huge_string_to_large():
    # A scalar whose repr exceeds REPR_SIZE_CAP must surface as kind:"large",
    # never inlined whole (spec §5 cap 2 fires).
    v = driver.var_for("s", "x" * (driver.REPR_SIZE_CAP + 500))
    assert v["kind"] == "large"


def test_opaque_skip_list_for_file_handle(tmp_path):
    f = open(tmp_path / "x.txt", "w")
    try:
        v = driver.var_for("fh", f)
        assert v["kind"] == "opaque"
        assert "TextIOWrapper" in v["label"]
        assert "text" not in v  # never repr'd (spec §5 cap 4 fires)
    finally:
        f.close()


def test_repr_that_raises_is_opaque_not_crash():
    class Boom:
        def __repr__(self):
            raise RuntimeError("nope")
    v = driver.var_for("b", Boom())
    assert v["kind"] == "opaque"  # repr failure → opaque, never propagates


def test_repr_time_budget_cap_fires(monkeypatch):
    # spec §5 cap 3: a __repr__ that BLOCKS must not hang the serializer — the
    # per-value time budget aborts it and the value renders opaque.
    monkeypatch.setattr(driver, "REPR_TIME_BUDGET_S", 0.01)

    class Slow:
        def __repr__(self):
            import time as _t
            _t.sleep(0.2)  # blows the 0.01s budget
            return "slow"
    v = driver.var_for("s", Slow())
    assert v["kind"] == "opaque"  # overran the time budget → opaque, not the repr


def test_trace_function_records_steps_and_scope():
    def sample(a):
        b = a + 1
        c = b * 2
        return c
    raw = driver.trace_call(sample, args=[3], kwargs={})
    assert raw["trace"][-1]["event"] == "return"
    assert not raw.get("truncated")
    names = {v["name"] for ev in raw["trace"] for v in ev["scope"]}
    assert {"a", "b", "c"} <= names
    # The driver does NOT emit `changed` — that is the normalizer's job (spec §9).
    assert all("changed" not in ev for ev in raw["trace"])


def test_trace_records_raise_terminal_step():
    def boom(x):
        return {}[x]
    raw = driver.trace_call(boom, args=["k"], kwargs={})
    last = raw["trace"][-1]
    assert last["event"] == "raise"
    assert last["raised"]["type"] == "KeyError"


def test_max_steps_cap_fires(monkeypatch):
    # spec §5 cap 1: a runaway loop truncates, never hangs.
    monkeypatch.setattr(driver, "MAX_STEPS", 20)
    def loopy(n):
        total = 0
        while True:
            total += 1
    raw = driver.trace_call(loopy, args=[0], kwargs={})
    assert raw["truncated"] is True
    assert len(raw["trace"]) <= 25  # MAX_STEPS + a small terminal slack


def test_wall_clock_cap_fires(monkeypatch):
    # spec §5 cap 5: a long-running capture aborts on the wall-clock guard even
    # if it stays under MAX_STEPS (e.g. a slow body per line).
    monkeypatch.setattr(driver, "WALL_CLOCK_BUDGET_S", 0.05)
    monkeypatch.setattr(driver, "MAX_STEPS", 10_000_000)
    def slow_loop(n):
        import time as _t
        total = 0
        for _ in range(10_000_000):
            _t.sleep(0.001)  # each line burns time → trips the 0.05s guard
            total += 1
    raw = driver.trace_call(slow_loop, args=[0], kwargs={})
    assert raw["truncated"] is True
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_capture.py -q` → FAIL (`_capture_driver` does not exist).

- [ ] **Step 3: Minimal impl** — create `src/copyclip/intelligence/_capture_driver.py`:
```python
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
# whose __repr__ may block, hit the network, or mutate. Matched by module-
# qualified type-name substring so we never import optional deps to check.
_OPAQUE_TYPE_MARKERS = (
    "io.TextIOWrapper", "io.BufferedReader", "io.BufferedWriter", "io.BufferedRandom",
    "socket.socket", "ssl.SSLSocket",
    "sqlite3.Connection", "sqlite3.Cursor",
    "Session", "Engine", "Connection",  # SQLAlchemy / requests-style
    "subprocess.Popen", "threading.Thread", "Lock",
)

_LARGE_BY_LEN = (list, tuple, set, frozenset, dict, bytes, bytearray)


def _type_fqn(obj: object) -> str:
    t = type(obj)
    mod = getattr(t, "__module__", "")
    return f"{mod}.{t.__qualname__}" if mod and mod != "builtins" else t.__qualname__


def _is_opaque_type(obj: object) -> bool:
    fqn = _type_fqn(obj)
    name = type(obj).__name__
    return any(m in fqn or m == name for m in _OPAQUE_TYPE_MARKERS)


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
    """Build one Var dict (driver shape) honoring the size/time caps + skip-list."""
    if _is_opaque_type(obj):
        return {"name": name, "kind": "opaque", "label": _type_fqn(obj)}
    if isinstance(obj, _LARGE_BY_LEN):
        try:
            n = len(obj)
        except Exception:  # noqa: BLE001
            n = 0
        if n > LARGE_CHILDREN_CAP or _too_big_repr(obj):
            return _large_var(name, obj, n)
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


class _Abort(Exception):
    """Internal: raised inside the tracer to stop a runaway capture."""


def trace_call(func, args: list, kwargs: dict) -> dict:
    """Run ``func(*args, **kwargs)`` once under a bounded settrace. Returns the
    driver-shape raw trace: {"trace": [event...], "truncated": bool}. The driver
    emits line/event/scope ONLY — `changed` is derived later by normalize_trace.

    A call that raises is recorded as a terminal ``raise`` step, not an error.
    """
    code = func.__code__
    own_file = code.co_filename
    events: list[dict] = []
    truncated = {"hit": False}
    started = time.monotonic()
    last_line = {"n": 0}

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != own_file:
            return tracer  # stay anchored: skip library frames' lines
        if len(events) >= MAX_STEPS or (time.monotonic() - started) > WALL_CLOCK_BUDGET_S:
            truncated["hit"] = True
            raise _Abort()
        scope = [var_for(k, v) for k, v in frame.f_locals.items()]
        last_line["n"] = frame.f_lineno
        events.append({"line": frame.f_lineno, "event": event, "scope": scope})
        return tracer

    sys.settrace(tracer)
    try:
        func(*args, **kwargs)
    except _Abort:
        pass
    except BaseException as exc:  # the call itself threw → terminal raise step
        sys.settrace(None)
        events.append({
            "line": last_line["n"], "event": "raise", "scope": [],
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

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != own_file:
            return tracer
        if len(events) >= MAX_STEPS or (time.monotonic() - started) > WALL_CLOCK_BUDGET_S:
            truncated["hit"] = True
            raise _Abort()
        scope = [var_for(k, v) for k, v in frame.f_locals.items()]
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
        events.append({"line": line, "event": "raise", "scope": [],
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
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_capture.py -q` → PASS. (`test_wall_clock_cap_fires` and `test_max_steps_cap_fires` both terminate quickly because the guard fires inside the callback.)

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/_capture_driver.py tests/test_capture.py && git commit -m "feat(cuaderno): bounded settrace driver — model + free-text paths, every cap proven to fire"`

---

### Task 5: Subprocess orchestration with process-group kill + wall-clock backstop

**Files:** `src/copyclip/intelligence/capture.py` (modify)

- [ ] **Step 1: Write failing test** — append to `tests/test_capture.py`:
```python
import textwrap
from copyclip.intelligence.capture import run_capture, run_free_text_capture, probe_target


def _write_user_module(tmp_path, body):
    (tmp_path / "usermod.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


def test_run_capture_traces_a_real_function(tmp_path):
    root = _write_user_module(tmp_path, """
        def addup(a):
            b = a + 1
            return b * 2
    """)
    resolved = ResolvedFunction(file="usermod.py", name="addup", qualname="addup",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    cd = CallDescriptor.from_dict({"function_ref": {"file": "usermod.py", "name": "addup"},
                                   "args": [3]})
    steps, truncated = run_capture(cd, resolved, project_root=str(root))
    assert truncated is False
    assert steps[-1].event == "return"
    names = {v.name for s in steps for v in s.scope}
    assert {"a", "b"} <= names


def test_run_free_text_capture_executes_user_expression(tmp_path):
    root = _write_user_module(tmp_path, """
        def addup(a):
            b = a + 1
            return b * 2
    """)
    resolved = ResolvedFunction(file="usermod.py", name="addup", qualname="addup",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    ft = FreeTextCall.from_text("addup(3 + 4)")
    steps, truncated = run_free_text_capture(ft, resolved, project_root=str(root))
    assert steps[-1].event == "return"
    names = {v.name for s in steps for v in s.scope}
    assert {"a", "b"} <= names


def test_probe_detects_async(tmp_path):
    root = _write_user_module(tmp_path, """
        async def fetch(x):
            return x
    """)
    resolved = ResolvedFunction(file="usermod.py", name="fetch", qualname="fetch",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    detect, source_lines = probe_target(resolved, project_root=str(root))
    assert detect["is_async"] is True
    assert any("async def fetch" in sl["text"] for sl in source_lines)


def test_probe_detects_async_generator_as_async(tmp_path):
    root = _write_user_module(tmp_path, """
        async def stream(x):
            yield x
    """)
    resolved = ResolvedFunction(file="usermod.py", name="stream", qualname="stream",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    detect, _ = probe_target(resolved, project_root=str(root))
    assert detect["is_async"] is True  # async-gen → async reason, not generator


def test_run_capture_raise_is_terminal_step(tmp_path):
    root = _write_user_module(tmp_path, """
        def boom(k):
            return {}[k]
    """)
    resolved = ResolvedFunction(file="usermod.py", name="boom", qualname="boom",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    cd = CallDescriptor.from_dict({"function_ref": {"file": "usermod.py", "name": "boom"},
                                   "args": ["x"]})
    steps, truncated = run_capture(cd, resolved, project_root=str(root))
    assert steps[-1].event == "raise"
    assert steps[-1].raised["type"] == "KeyError"
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_capture.py -q` → FAIL (`run_capture`/`run_free_text_capture`/`probe_target` undefined).

- [ ] **Step 3: Minimal impl** — append to `src/copyclip/intelligence/capture.py`:
```python
import os
import shutil
import signal
import subprocess
import sys
import tempfile


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


def _run_driver(spec: dict, project_root: str) -> dict:
    """Spawn the driver in the user's env. NEW PROCESS GROUP so a hung capture
    (and any tree it spawned) dies cleanly: CREATE_NEW_PROCESS_GROUP on Windows /
    start_new_session on POSIX (spec §10). The wall-clock guard lives in the
    driver; this is the OUTER backstop in case import itself hangs."""
    td = tempfile.mkdtemp(prefix="copyclip-capture-")
    try:
        spec_path = os.path.join(td, "spec.json")
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
            out, err = proc.communicate()
            raise CaptureError("capture exceeded the wall-clock budget and was killed")
        if proc.returncode != 0 and not out.strip():
            raise CaptureError(f"capture subprocess failed (rc={proc.returncode}): {err[-500:]}")
        try:
            payload = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
        except json.JSONDecodeError as exc:
            raise CaptureError(f"capture produced no parseable trace: {exc}; stderr={err[-300:]}")
        if "error" in payload:
            raise CaptureError(f"capture driver error: {payload['error'][-500:]}")
        return payload
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _kill_group(proc: subprocess.Popen) -> None:
    """Reclaim the whole process group (spec §10). Uses signal.CTRL_BREAK_EVENT
    on Windows (NOT the non-existent subprocess.signal.CTRL_BREAK_EVENT) and
    os.killpg on POSIX, falling back to proc.kill()."""
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def probe_target(resolved: ResolvedFunction, *, project_root: str) -> tuple[dict, list[dict]]:
    """Import-time probe — async/generator detection + source lines — without
    running the user's logic. Returns (detect, source_lines)."""
    payload = _run_driver(
        _spec_for(CallDescriptor(function_ref=resolved_to_ref(resolved)), resolved, probe=True),
        project_root)
    return payload.get("detect", {"is_async": False, "is_generator": False}), \
        payload.get("source_lines", [])


def run_capture(cd: CallDescriptor, resolved: ResolvedFunction, *, project_root: str):
    """MODEL path: run the descriptor call ONCE; return (Step[], truncated)."""
    payload = _run_driver(_spec_for(cd, resolved, probe=False), project_root)
    return normalize_trace(payload), bool(payload.get("truncated"))


def run_free_text_capture(ft: FreeTextCall, resolved: ResolvedFunction, *, project_root: str):
    """USER path: exec the edited free-text call ONCE; return (Step[], truncated)."""
    payload = _run_driver(_free_text_spec(ft, resolved), project_root)
    return normalize_trace(payload), bool(payload.get("truncated"))


def resolved_to_ref(resolved: ResolvedFunction) -> FunctionRef:
    return FunctionRef(file=resolved.file, name=resolved.name, line=resolved.line_start,
                       qualname=resolved.qualname if resolved.qualname != resolved.name else None)
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_capture.py -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/capture.py tests/test_capture.py && git commit -m "feat(cuaderno): capture subprocess orchestration (new process group, model + free-text paths)"`

---

### Task 6: Process-group kill for the EXISTING marimo runner (fix the CTRL_BREAK bug)

**Files:** `src/copyclip/intelligence/marimo_runner.py` (`:167-171` spawn; `:318-337` kill); `tests/test_marimo_runner.py`

Spec §10 names `_best_effort_kill` (`marimo_runner.py:318`) as a place that does NOT group-kill. Two fixes, both small: (a) spawn the marimo child in its own process group; (b) in `_best_effort_kill`, group-kill before falling back to terminate/kill — and use the CORRECT signal name (`signal.CTRL_BREAK_EVENT`, imported from `signal`; the drafted plan's `subprocess.signal.CTRL_BREAK_EVENT` does not exist).

- [ ] **Step 1: Write failing test** — append to `tests/test_marimo_runner.py`:
```python
import signal
import sys
from unittest.mock import MagicMock

from copyclip.intelligence.marimo_runner import MarimoRunner


def test_best_effort_kill_uses_process_group_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    proc = MagicMock()
    proc.poll.return_value = None  # still alive
    proc.wait.side_effect = [__import__("subprocess").TimeoutExpired("x", 1), None]
    MarimoRunner()._best_effort_kill(proc)
    proc.send_signal.assert_any_call(signal.CTRL_BREAK_EVENT)


def test_best_effort_kill_killpg_on_posix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    killed = {}
    monkeypatch.setattr("os.getpgid", lambda pid: 4242)
    monkeypatch.setattr("os.killpg", lambda pgid, sig: killed.setdefault("pgid", (pgid, sig)))
    proc = MagicMock()
    proc.poll.return_value = None
    proc.pid = 999
    proc.wait.side_effect = [__import__("subprocess").TimeoutExpired("x", 1), None]
    MarimoRunner()._best_effort_kill(proc)
    assert killed["pgid"][0] == 4242
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_marimo_runner.py -k best_effort_kill -q` → FAIL (`send_signal`/`killpg` not called).

- [ ] **Step 3: Minimal impl** —
  1. Add `import signal` to the import block (`marimo_runner.py:22-37`).
  2. Spawn the child in a new group (`:167-171`):
```python
            popen_kwargs = {}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    **popen_kwargs,
                )
```
  3. Group-kill first in `_best_effort_kill` (`:318-337`):
```python
    def _best_effort_kill(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        # Reclaim the whole process tree first (spec §10): the child was spawned
        # in its own group, so a single signal reaps any grandchildren too.
        try:
            if sys.platform == "win32":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception:
            pass
        try:
            process.terminate()
        except Exception:
            pass
        try:
            process.wait(timeout=TERMINATE_GRACE_S)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=TERMINATE_GRACE_S)
        except Exception:
            pass
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_marimo_runner.py -q` → PASS (new tests + the existing kill/spawn tests still green).

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/marimo_runner.py tests/test_marimo_runner.py && git commit -m "fix(playground): process-group kill in _best_effort_kill (signal.CTRL_BREAK_EVENT, not subprocess.signal)"`

---

### Task 7: `launch_playground` branches cuaderno → capture, else Marimo

**Files:** `src/copyclip/intelligence/playground.py` (`:130-165` request; `:500-547` orchestrator)

- [ ] **Step 1: Write failing test** — append to `tests/test_playground.py`:
```python
import textwrap as _tw
from copyclip.intelligence.capture import StepThroughResponse, FallbackResponse


def _seed_user_symbol(conn, project_root, body, file_rel, name,
                      kind="function", module="usermod"):
    """Mirror _seed_symbol (tests/test_playground.py:338) but write a REAL
    importable module the capture subprocess can import from project_root."""
    (Path(project_root) / file_rel).write_text(_tw.dedent(body), encoding="utf-8")
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)",
                 (str(project_root), "test"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?",
                           (str(project_root),)).fetchone()[0])
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,"
        "parent_symbol_id,module) VALUES(?,?,?,?,?,?,?,?)",
        (pid, name, kind, file_rel, 1, 5, None, module))
    conn.commit()
    return pid


def test_cuaderno_eligible_returns_trace_response(tmp_path):
    conn = connect(str(tmp_path)); init_schema(conn)
    pid = _seed_user_symbol(conn, tmp_path,
                            "def addup(a):\n    b = a + 1\n    return b * 2\n",
                            "usermod.py", "addup")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "usermod.py", "name": "addup"},
        "call": {"function_ref": {"file": "usermod.py", "name": "addup"}, "args": [3]},
    })
    runner = Mock()
    resp = launch_playground(req, str(tmp_path), conn, pid, runner)
    assert isinstance(resp, StepThroughResponse)
    assert resp.to_dict()["kind"] == "trace"
    assert resp.func_name == "addup"
    runner.launch.assert_not_called()  # the trace path does NOT spawn marimo


def test_cuaderno_free_text_call_returns_trace(tmp_path):
    conn = connect(str(tmp_path)); init_schema(conn)
    pid = _seed_user_symbol(conn, tmp_path,
                            "def addup(a):\n    b = a + 1\n    return b * 2\n",
                            "usermod.py", "addup")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "usermod.py", "name": "addup"},
        "call_text": "addup(3 + 4)",  # USER free-text path (spec §6/§10)
    })
    resp = launch_playground(req, str(tmp_path), conn, pid, Mock())
    assert isinstance(resp, StepThroughResponse)
    assert resp.to_dict()["kind"] == "trace"


def test_cuaderno_async_falls_back_to_marimo(tmp_path):
    conn = connect(str(tmp_path)); init_schema(conn)
    pid = _seed_user_symbol(conn, tmp_path,
                            "async def fetch(x):\n    return x\n",
                            "usermod.py", "fetch")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "usermod.py", "name": "fetch"},
        "call": {"function_ref": {"file": "usermod.py", "name": "fetch"}, "args": [1]},
    })
    runner = Mock(); runner.launch.return_value = ("pg1", "http://127.0.0.1:5000/")
    resp = launch_playground(req, str(tmp_path), conn, pid, runner)
    assert isinstance(resp, FallbackResponse)
    assert resp.iframe_url == "http://127.0.0.1:5000/"
    runner.launch.assert_called_once()
    assert runner.launch.call_args.kwargs.get("mode") == "run"


def test_non_cuaderno_source_unchanged_marimo_iframe(tmp_path):
    conn = connect(str(tmp_path)); init_schema(conn)
    pid = _seed_user_symbol(conn, tmp_path,
                            "def addup(a):\n    return a\n",
                            "usermod.py", "addup")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "atlas",
        "function_ref": {"file": "usermod.py", "name": "addup"},
    })
    runner = Mock(); runner.launch.return_value = ("pg2", "http://127.0.0.1:5001/")
    resp = launch_playground(req, str(tmp_path), conn, pid, runner)
    assert isinstance(resp, PlaygroundLaunchResponse)
    assert resp.iframe_url == "http://127.0.0.1:5001/"
    assert runner.launch.call_args.kwargs.get("mode") == "edit"
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_playground.py -k "cuaderno or non_cuaderno" -q` → FAIL (`call`/`call_text` not parsed; no branch).

- [ ] **Step 3: Minimal impl** — in `playground.py`:
  1. Add to `PlaygroundLaunchRequest` (`:130-136`): `call: object | None = None` (kept as the raw dict to avoid a circular import; `capture.CallDescriptor.from_dict` parses it inside `launch_playground`) and `call_text: str | None = None`. In `from_dict` (`:159-165`), read `data.get("call")` (pass through unchanged) and `data.get("call_text")` (validate it is a string-or-None):
```python
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
```
  2. Widen `launch_playground`'s return annotation from `-> PlaygroundLaunchResponse` (`playground.py:507`) to `-> PlaygroundLaunchResponse | StepThroughResponse | FallbackResponse` (it now returns all three; the annotation must not lie). Then rewrite the tail (after the `launch.resolve` event at `:527`) to branch on source:
```python
    if req.source == "cuaderno":
        from .capture import (
            CallDescriptor, FreeTextCall, StepThroughResponse, FallbackResponse,
            eligibility_reason, run_capture, run_free_text_capture, probe_target,
        )
        detect, source_lines = probe_target(resolved, project_root=project_root)
        file_line = resolved.file + (f":{resolved.line_start}" if resolved.line_start else "")
        if req.call_text is not None:  # USER free-text path (spec §6/§10)
            try:
                ft = FreeTextCall.from_text(req.call_text)
            except PlaygroundError as exc:
                trace.event("launch.error", stage="call_text", error=str(exc))
                raise
            if detect["is_async"] or detect["is_generator"]:
                reason = ("async functions step through as one frame; using the input box instead"
                          if detect["is_async"]
                          else "generator functions step through as one frame; using the input box instead")
                trace.event("launch.capture", outcome="fallback", reason=reason)
                return _cuaderno_fallback(req, project_root, resolved, runner, reason, trace)
            steps, truncated = run_free_text_capture(ft, resolved, project_root=project_root)
        else:  # MODEL structured-descriptor path
            try:
                cd = CallDescriptor.from_dict(req.call) if req.call is not None \
                    else CallDescriptor(function_ref=req.function_ref)
            except PlaygroundError as exc:
                trace.event("launch.error", stage="descriptor", error=str(exc))
                raise
            reason = eligibility_reason(cd, resolved, is_async=detect["is_async"],
                                        is_generator=detect["is_generator"])
            if reason is not None:
                trace.event("launch.capture", outcome="fallback", reason=reason)
                return _cuaderno_fallback(req, project_root, resolved, runner, reason, trace)
            steps, truncated = run_capture(cd, resolved, project_root=project_root)
        trace.event("launch.capture", outcome="trace", steps=len(steps), truncated=truncated)
        return StepThroughResponse(
            trace=steps, source_lines=source_lines, func_name=resolved.name,
            file_line=file_line, truncated=truncated)
    # Non-cuaderno sources: the Marimo iframe path is UNCHANGED.
    return _launch_marimo(req, project_root, resolved, runner, trace)
```
  3. Extract the existing notebook-gen + `runner.launch` tail (`:528-547`) into a helper `_launch_marimo(req, project_root, resolved, runner, trace) -> PlaygroundLaunchResponse` that keeps the `launch.notebook` / `launch.ready` events, the source-keyed `mode = "run" if req.source == "cuaderno" else "edit"`, and the temp-dir cleanup-on-spawn-failure exactly as today.
  4. Add `_cuaderno_fallback(...)`:
```python
def _cuaderno_fallback(req, project_root, resolved, runner, reason, trace):
    from .capture import FallbackResponse
    inner = _launch_marimo(req, project_root, resolved, runner, trace)
    return FallbackResponse(reason=reason, iframe_url=inner.iframe_url)
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_playground.py -k "cuaderno or non_cuaderno" -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/playground.py tests/test_playground.py && git commit -m "feat(cuaderno): launch_playground branches cuaderno to capture (model + free-text), keeps marimo elsewhere"`

---

### Task 8: Server endpoint returns trace/fallback for cuaderno, stable error codes

**Files:** `src/copyclip/intelligence/server.py` (`:1620-1660`)

- [ ] **Step 1: Write failing test** — append to `tests/test_playground.py`. The `running_server_with_user_symbol` fixture is built by copying the EXISTING `_start_server_with_runner` (`tests/test_playground.py:566`) but writing a real importable module and seeding its symbol via `_seed_user_symbol` (Task 7) instead of the canned reacquaintance row:
```python
import pytest


@pytest.fixture
def running_server_with_user_symbol():
    """Like _start_server_with_runner (tests/test_playground.py:566) but seeds a
    REAL importable usermod.addup so the capture subprocess can import it."""
    td = tempfile.mkdtemp(prefix="copyclip-pg-test-")
    root = str(Path(td).absolute())
    (Path(root) / "usermod.py").write_text(
        "def addup(a):\n    b = a + 1\n    return b * 2\n", encoding="utf-8")
    conn = connect(root)
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?",
                           (root,)).fetchone()[0])
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,"
        "parent_symbol_id,module) VALUES(?,?,?,?,?,?,?,?)",
        (pid, "addup", "function", "usermod.py", 1, 3, None, "usermod"))
    conn.commit()
    conn.close()

    port = _free_port()
    th = threading.Thread(
        target=run_server,
        kwargs={"project_root": root, "port": port, "playground_runner": Mock()},
        daemon=True,
    )
    th.start()
    _wait_port(port)
    yield f"http://127.0.0.1:{port}", root


def test_endpoint_cuaderno_returns_trace_kind(running_server_with_user_symbol):
    base, _ = running_server_with_user_symbol
    status, body = _post_json(base + "/api/playground/launch", {
        "source": "cuaderno",
        "function_ref": {"file": "usermod.py", "name": "addup"},
        "call": {"function_ref": {"file": "usermod.py", "name": "addup"}, "args": [3]},
    })
    assert status == 200
    assert body["kind"] == "trace"
    assert body["func_name"] == "addup"
    assert isinstance(body["trace"], list)
    assert "iframe_url" not in body  # trace path mounts the React stepper, no iframe


def test_endpoint_invalid_call_descriptor_is_400(running_server_with_user_symbol):
    base, _ = running_server_with_user_symbol
    status, body = _post_json(base + "/api/playground/launch", {
        "source": "cuaderno",
        "function_ref": {"file": "usermod.py", "name": "addup"},
        "call": {"function_ref": {"file": "usermod.py", "name": "addup"},
                 "kwargs": {"bad key": 1}},  # non-identifier kwarg key
    })
    assert status == 400
    assert body["error"] == "invalid_call_descriptor"
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_playground.py -k "endpoint_cuaderno or invalid_call" -q` → FAIL (no `invalid_call_descriptor` mapping yet wired through the endpoint).

- [ ] **Step 3: Minimal impl** — in `server.py` `:1639-1643`:
```python
                        req = PlaygroundLaunchRequest.from_dict(data)
                        parsed_ok = True
                        response = launch_playground(req, root, conn, pid,
                                                     playground_runner, trace=ltrace)
                        # cuaderno may return StepThroughResponse/FallbackResponse;
                        # all three expose .to_dict() with a discriminating field.
                        self._json(response.to_dict())
                        ltrace.close(outcome="ready")
```
`response.to_dict()` already works for all three response dataclasses (each defines it), so no special-casing. The error block at `:1645-1655` already catches `PlaygroundError`; `InvalidCallDescriptorError` and `CaptureError` are `PlaygroundError` subclasses (Task 1) carrying `error_code` + `http_status`, so they emit `{"error": "invalid_call_descriptor", ...}` (400) and `{"error": "capture_failed", ...}` (500) with no further wiring. The `from .capture import ...` lives inside `launch_playground`, so the server module does not gain a hard capture import at module load.

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_playground.py -k "endpoint_cuaderno or invalid_call" -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/server.py tests/test_playground.py && git commit -m "feat(cuaderno): launch endpoint returns trace/fallback for cuaderno with stable error codes"`

---

### Task 9: Floor carries the model's REAL call descriptor + breadcrumb rename

**Files:** `src/copyclip/intelligence/cuaderno/schema.py` (`:61-71`); `src/copyclip/intelligence/cuaderno/compositor.py` (`:156-164`); `tests/test_cuaderno_playground_floor.py`

The frontend must render the REAL invocation, never a placeholder `name(…)` (spec §6). So the floor emits the model's proposed `call` descriptor into the widget payload, AND the breadcrumb reads as a walkthrough.

- [ ] **Step 1: Write failing test** — append to `tests/test_cuaderno_playground_floor.py` (reuse the existing `_seed_symbol_project` helper + `_construct_playground_floor` already imported in this module):
```python
from copyclip.intelligence.cuaderno.compositor import _construct_playground_floor


def test_floor_breadcrumb_is_step_through_spanish(tmp_path: Path):
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)
    block, reason = _construct_playground_floor(
        "ejecuta _module_from_relpath", conn, pid, ledger=None, emitted=[])
    assert reason is None
    w = block.to_dict()["widget"]
    assert w["breadcrumb"] == "Recorre _module_from_relpath paso a paso"


def test_floor_breadcrumb_is_step_through_english(tmp_path: Path):
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)
    block, reason = _construct_playground_floor(
        "run _module_from_relpath", conn, pid, ledger=None, emitted=[])
    assert reason is None
    w = block.to_dict()["widget"]
    assert w["breadcrumb"] == "Step through _module_from_relpath"


def test_floor_emits_real_call_descriptor(tmp_path: Path):
    # spec §6: the widget must carry a REAL call so the frontend renders the
    # actual invocation, not a fake placeholder. The floor seeds a bare call
    # (function_ref only) when it has no model-proposed args — the frontend's
    # editable free-text field then shows `name(...)` from the real ref.
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)
    block, reason = _construct_playground_floor(
        "run _module_from_relpath", conn, pid, ledger=None, emitted=[])
    assert reason is None
    w = block.to_dict()["widget"]
    assert w["call"]["function_ref"]["name"] == "_module_from_relpath"
    assert w["call"]["function_ref"]["file"] == "src/copyclip/intelligence/analyzer.py"
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/test_cuaderno_playground_floor.py -k "step_through or real_call" -q` → FAIL (old breadcrumb string; no `call` in the widget).

- [ ] **Step 3: Minimal impl** —
  1. `schema.py` `:61-71` — add an optional `call` param to `Widget.playground`:
```python
    @staticmethod
    def playground(function_ref: dict, breadcrumb: str,
                   suggested_inputs: Optional[list] = None,
                   call: Optional[dict] = None) -> "Widget":
        citation: dict[str, Any] = {"kind": "path", "path": function_ref.get("file")}
        if function_ref.get("line") is not None:
            citation["line_start"] = function_ref["line"]
        d: dict[str, Any] = {"function_ref": function_ref, "breadcrumb": breadcrumb,
                             "citation": citation}
        if suggested_inputs is not None:
            d["suggested_inputs"] = suggested_inputs
        if call is not None:
            d["call"] = call
        return Widget(kind="playground", data=d)
```
  2. `compositor.py` `:161-164` — rename the breadcrumb AND pass the real call descriptor (the floor has no model-proposed args, so it emits a bare call with just the `function_ref`; the frontend's free-text field renders the real `name(...)` from it):
```python
    # `lang` is ALREADY bound one line above (compositor.py:161,
    # `lang = detect_language(question)`) — do NOT re-declare it. Edit only the
    # breadcrumb + the widget block (:162-164), reusing the existing `lang`:
    breadcrumb = (f"Recorre {resolved.name} paso a paso"
                  if lang == "es" else f"Step through {resolved.name}")
    call = {"function_ref": fr}
    block = Block.widget(
        Widget.playground(function_ref=fr, breadcrumb=breadcrumb, call=call).to_dict())
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/test_cuaderno_playground_floor.py -q` → PASS. Then grep `tests/` for the OLD breadcrumb strings (`con un ejemplo` / `with an example`) and update any pre-existing assertion in the SAME commit; re-run the cuaderno floor + widget-check suites (`tests/test_cuaderno_widget_checks.py`, `tests/test_cuaderno_artifact_honesty.py`) to confirm the added `call` key passes widget validation.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/cuaderno/schema.py src/copyclip/intelligence/cuaderno/compositor.py tests/ && git commit -m "feat(cuaderno): floor emits real call descriptor + 'Step through X' breadcrumb"`

---

### Task 10: Prompts teach the model to propose args/kwargs/ctor

**Files:** `src/copyclip/intelligence/cuaderno/prompts.py` (`:94-100` run directive; `:197-200` widget spec)

The model's proposed `args`/`kwargs`/`ctor` must reach the widget payload (Task 9 carries them) so the frontend shows the REAL call.

- [ ] **Step 1: Write failing test** — append to the existing prompt test module (or create `tests/test_prompts_playground.py`):
```python
from copyclip.intelligence.cuaderno.prompts import (
    WIDGET_RECOVERY_DIRECTIVE_RUN, SYSTEM_PROMPT,
)


def test_run_directive_mentions_call_descriptor_fields():
    t = WIDGET_RECOVERY_DIRECTIVE_RUN
    assert "args" in t and "kwargs" in t and "ctor" in t
    assert "step through" in t.lower()


def test_system_prompt_playground_spec_documents_call_fields():
    s = SYSTEM_PROMPT
    assert '"args"' in s and '"kwargs"' in s and '"ctor"' in s
```

- [ ] **Step 2: Run it (expected FAIL)** — `python -m pytest tests/ -k "run_directive_mentions or system_prompt_playground_spec" -q` → FAIL.

- [ ] **Step 3: Minimal impl** —
  `prompts.py` `:94-100`:
```python
WIDGET_RECOVERY_DIRECTIVE_RUN = (
    "You asked for a RUNNABLE example, so do not answer in prose — emit a "
    "playground widget whose function_ref names the real symbol you located this "
    "turn (its file and name). Propose a COMPLETE call so it can be stepped "
    "through: \"args\" (positional) and \"kwargs\" (keyword) that exercise it, and "
    "for a method, \"ctor\" {args?, kwargs?} to build the instance. Use simple "
    "JSON-serializable literals only. Add a one-line breadcrumb. Only if no real, "
    "importable symbol resolves should you say so briefly. Then call finish."
)
```
  `prompts.py` `:197-200` (playground spec inside SYSTEM_PROMPT):
```python
- {"kind": "playground", "function_ref": {"file": "...", "name": "...", "line": <int>?, "qualname": "..."?},
   "breadcrumb": "one-line description",
   "args": [...]?, "kwargs": {...}?, "ctor": {"args": [...]?, "kwargs": {...}?}?}
   a runnable example descriptor; function_ref must name a real symbol you located this turn;
   args/kwargs/ctor are the proposed call (JSON-serializable literals only — injected as repr,
   never raw code); for a method, ctor builds the instance. never invent paths.
```

- [ ] **Step 4: Run it (expected PASS)** — `python -m pytest tests/ -k "run_directive_mentions or system_prompt_playground_spec" -q` → PASS.

- [ ] **Step 5: Commit** — `git add src/copyclip/intelligence/cuaderno/prompts.py tests/ && git commit -m "feat(cuaderno): prompts teach the model to propose args/kwargs/ctor for step-through"`

---

### Task 11: Re-point the one behavioral Marimo test (the template is UNCHANGED)

**Files:** `tests/test_playground.py` (`:~1001`)

The Marimo notebook template is **not edited** by this plan: the iframe path is intact, `generate_marimo_notebook` is still called verbatim by `_launch_marimo` (Task 7 only extracted the spawn tail into a helper; the `_NOTEBOOK_TEMPLATE.format(...)` call is byte-for-byte the same). So the 28 `test_generate_notebook_*` template-pinned assertions (`:~100-345`) PASS UNCHANGED — they call `generate_marimo_notebook` directly and never touch the launch branch. (This corrects the File-Structure overclaim in the drafted plan: only ONE assertion changes behavior, plus the new appended tests; the template block itself is untouched.)

The single behavior change is `test_cuaderno_source_launches_run_mode` (`:~1001`): a cuaderno run with an ELIGIBLE descriptor no longer calls `runner.launch`. Re-point it to assert the FALLBACK path still launches `mode="run"`, keeping coverage of the source-keyed mode dispatch.

- [ ] **Step 1: Update the one behavioral assertion** — replace `test_cuaderno_source_launches_run_mode` (`:~1001`):
```python
def test_cuaderno_fallback_launches_run_mode(tmp_path):
    conn = connect(str(tmp_path)); init_schema(conn)
    pid = _seed_user_symbol(conn, tmp_path,
                            "async def fetch(x):\n    return x\n",
                            "usermod.py", "fetch")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "usermod.py", "name": "fetch"},
        "call": {"function_ref": {"file": "usermod.py", "name": "fetch"}, "args": [1]},
    })
    runner = Mock(); runner.launch.return_value = ("pg", "http://127.0.0.1:5000/")
    launch_playground(req, str(tmp_path), conn, pid, runner)
    assert runner.launch.call_args.kwargs.get("mode") == "run"
```

- [ ] **Step 2: Run the full template-pinned set (expected PASS)** — `python -m pytest tests/test_playground.py -q`. The 28 generator assertions (`test_generate_notebook_*`) call `generate_marimo_notebook` directly and pass unchanged. Expected: all green.

- [ ] **Step 3: If any template assertion regressed** — it means the `_launch_marimo` extraction (Task 7 Step 3) drifted from the original tail. Open `src/copyclip/intelligence/playground.py` and confirm `_launch_marimo` calls `generate_marimo_notebook(...)` / `_NOTEBOOK_TEMPLATE.format(...)` with the identical arguments and mode logic as the pre-extraction `launch_playground` tail (Task 7 Step 3 required this verbatim). Fix the helper to match; re-run.

- [ ] **Step 4: Run the whole backend suite (expected PASS)** — `python -m pytest tests/test_playground.py tests/test_capture.py -q` → all PASS.

- [ ] **Step 5: Commit** — `git add tests/test_playground.py && git commit -m "test(cuaderno): re-point run-mode assertion to the fallback path; template tests intact"`

---

### Task 12: Full-suite verification + writing-plans self-review

**Files:** none (verification only)

- [ ] **Step 1: Run the entire backend test suite** — `python -m pytest -q` → expected: all PASS (no regressions in the cuaderno pipeline, the floor widget validation, the Marimo path, or the marimo-runner kill tests).

- [ ] **Step 2: Confirm license + packaging hygiene** — `grep -rin "json.tracer\|json_tracer\|pg_logger\|ExecutionVisualizer\|pgbovine" src/ pyproject.toml` returns NOTHING: capture is our own bounded `sys.settrace` callback (spec §0 decision 1), there is no third-party tracer dependency, and no Online Python Tutor source is in the tree. Confirm the `playground` extra in `pyproject.toml` lists `marimo` only (unchanged by this plan). Confirm the handoff's `support.js` is not shipped (frontend plan's concern; note it for the reviewer).

- [ ] **Step 3: Self-review against the writing-plans checklist** — verify:
  - Every referenced type/function is defined in some task: `CallDescriptor`, `FreeTextCall`, `Step`, `Var`, `StepThroughResponse`, `FallbackResponse`, `normalize_trace`, `eligibility_reason`, `run_capture`, `run_free_text_capture`, `probe_target`, `detect_kind`, `var_for`, `trace_call`, `_trace_free_text`, `_launch_marimo`, `_cuaderno_fallback`, `_kill_group`.
  - Every step is one action; no placeholders; all paths exact.
  - Both §10 consent paths exist: model `CallDescriptor` (repr-guarded, Task 1) and user `FreeTextCall` (exec'd in module namespace, Tasks 1/4/7).
  - Every §5 cap has a test that PROVES it fires: MAX_STEPS (`test_max_steps_cap_fires`), repr-time (`test_repr_time_budget_cap_fires`), wall-clock (`test_wall_clock_cap_fires`), repr-size (`test_repr_size_cap_demotes_huge_string_to_large`), skip-list (`test_opaque_skip_list_for_file_handle`).
  - `changed` is DERIVED in `normalize_trace` and proven against the handoff (`test_normalize_changed_matches_handoff_for_canonical_resolve_trace`); the driver never emits `changed` (`test_trace_function_records_steps_and_scope`).
  - `detect_kind` reports `is_async` for async-generators (`test_probe_detects_async_generator_as_async`), `is_generator` for sync generators only.
  - Process-group kill is wired into the EXISTING `_best_effort_kill` with `signal.CTRL_BREAK_EVENT` (Task 6), NOT `subprocess.signal.CTRL_BREAK_EVENT`.
  - The Marimo template is provably untouched (Task 11); the wire schema (`Step`/`Var`/`StepThroughResponse`/`FallbackResponse`/`CallDescriptor`) matches spec §4/§9 verbatim.
  - The `Var.meta` docstring example uses `1000×12` (the × multiplication sign, matching spec §9 and the frontend type), not `1000x12` — confirm in `capture.py` Task 2 and `_capture_driver.py` Task 4.
  - Loop FOLDING is descoped (spec §0 decision 3): the flat `Step[]` schema carries no iteration metadata; change-markers + "next change" run off the flat `Step[]` client-side (frontend plan); this backend plan emits no fold data and the schema is unchanged.
  Note any deviation here for the reviewer.

- [ ] **Step 4: Commit (if Step 3 produced doc/test touch-ups)** — `git commit -am "test(cuaderno): full-suite verification for step-through backend"` (skip if nothing changed).
