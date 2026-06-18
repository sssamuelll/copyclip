import json
import os
import shutil
import sqlite3

import pytest

from copyclip.intelligence.playground import (
    FunctionNotFoundError, MarimoSpawnError, PlaygroundLaunchRequest, launch_playground,
)
from copyclip.intelligence.cuaderno.trace import InteractionTrace
from copyclip.intelligence.capture import CaptureError


class FakeRunner:
    def launch(self, notebook_path, mode="edit", trace=None):
        if trace is not None:
            trace.event("launch.spawn", cmd=["python", "-m", "marimo", mode],
                        port=1234, pid=42, mode=mode)
        return "pgid123", "http://127.0.0.1:1234/"

    def kill(self, playground_id):
        return True

    def status(self, playground_id):
        return "running"


class FailingRunner(FakeRunner):
    def launch(self, notebook_path, mode="edit", trace=None):
        raise MarimoSpawnError("boom")


def _conn_with_symbol(kind="function", name="foo"):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE symbols (project_id INT, name TEXT, kind TEXT,"
        " file_path TEXT, line_start INT, module TEXT)")
    conn.execute(
        "INSERT INTO symbols VALUES (1, ?, ?, 'src/copyclip/util.py', 10, 'copyclip.util')",
        (name, kind))
    return conn


def _req(name="foo", call_text=None, call=None, qualname=None):
    d = {
        "source": "cuaderno",
        "function_ref": {"file": "src/copyclip/util.py", "name": name},
        "breadcrumb": "bc",
        "suggested_inputs": ["src/copyclip/foo.py"],
    }
    if qualname is not None:
        d["function_ref"]["qualname"] = qualname
    if call_text is not None:
        d["call_text"] = call_text
    if call is not None:
        d["call"] = call
    return PlaygroundLaunchRequest.from_dict(d)


def _lines(trace):
    return [json.loads(l) for l in trace.path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# Helpers to stub out the cuaderno capture path so existing Marimo-path tests
# are not broken by the unconditional probe_target that the pre-fix code called.
# After the fix, probe_target is only called when needed; these stubs remain
# to keep tests hermetic (no real subprocess).
# ---------------------------------------------------------------------------

_FAKE_DETECT = {"is_async": False, "is_generator": False}
_FAKE_SOURCE_LINES: list = []
# Empty steps — used for tests that explicitly probe the empty-trace → fallback path.
_FAKE_STEPS: list = []


def _one_step():
    """Return a one-element Step list so launch_playground returns StepThroughResponse
    (not FallbackResponse — empty trace now returns fallback per Critical #2)."""
    from copyclip.intelligence.capture import Step
    return [Step(line=1, event="line", changed=[], scope=[])]


def _stub_probe(monkeypatch):
    """Make probe_target return a safe synchronous, non-generator result."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.probe_target",
        lambda *a, **kw: (_FAKE_DETECT, _FAKE_SOURCE_LINES),
    )


def _stub_run_capture(monkeypatch):
    """Make run_capture return a one-element Step[] list (non-empty so
    launch_playground returns StepThroughResponse, not a FallbackResponse).
    The capture functions return (steps, truncated, truncated_reason)."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        lambda *a, **kw: (_one_step(), False, None),
    )


def _stub_run_free_text_capture(monkeypatch):
    """Make run_free_text_capture return a one-element Step[] list."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_free_text_capture",
        lambda *a, **kw: (_one_step(), False, None),
    )


# ---------------------------------------------------------------------------
# Original Marimo-path tests (source != "cuaderno" in spirit, but these use
# source="cuaderno" with no call / call_text — after the ctor pre-check they
# go through probe + run_capture; stub both to keep tests hermetic).
# ---------------------------------------------------------------------------


def test_launch_traces_resolve_notebook_spawn_ready(tmp_path, monkeypatch):
    _stub_probe(monkeypatch)
    _stub_run_capture(monkeypatch)
    trace = InteractionTrace.start("launch", tmp_path / "logs", {"source": "cuaderno"})
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
                             FakeRunner(), trace=trace)
    trace.close(outcome="ready")
    # The cuaderno path with a non-empty stub trace returns a StepThroughResponse,
    # not a PlaygroundLaunchResponse; the Marimo runner is NOT exercised here.
    # These assertions verify the trace event sequence for the cuaderno path.
    lines = _lines(trace)
    names = [l["event"] for l in lines]
    assert "launch.resolve" in names
    assert "launch.capture" in names
    resolve = next(l for l in lines if l["event"] == "launch.resolve")
    assert resolve["module"] == "copyclip.util" and resolve["name"] == "foo"


def test_resolve_failure_traces_launch_error_stage_resolve(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(FunctionNotFoundError):
        launch_playground(_req(name="missing"), str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next(l for l in lines if l["event"] == "launch.error")
    assert err["stage"] == "resolve" and "missing" in err["error"]


def test_marimo_happy_path_traces_spawn_notebook_ready(tmp_path):
    """Non-cuaderno source with a passing runner must emit launch.notebook
    (path, input_element), launch.spawn (port, pid, mode), and launch.ready
    (playground_id) in that order.

    This test was the implicit guarantee of the original
    `test_launch_traces_resolve_notebook_spawn_ready` before the cuaderno
    step-through refactor redirected it to the capture path and dropped these
    assertions.  It must live here, not be inlined into the cuaderno path.
    """
    trace = InteractionTrace.start("launch", tmp_path / "logs", {"source": "atlas"})
    req = PlaygroundLaunchRequest.from_dict({
        "source": "atlas",
        "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
        "breadcrumb": "bc",
        "suggested_inputs": ["src/copyclip/foo.py"],
    })
    resp = launch_playground(req, str(tmp_path), _conn_with_symbol(), 1,
                             FakeRunner(), trace=trace)
    trace.close(outcome="ready")

    assert resp.playground_id == "pgid123"
    assert resp.iframe_url == "http://127.0.0.1:1234/"

    lines = _lines(trace)
    names = [l["event"] for l in lines]
    # The full marimo happy-path sequence must be present in order.
    assert "launch.resolve" in names
    assert "launch.notebook" in names
    assert "launch.spawn" in names
    assert "launch.ready" in names
    assert names.index("launch.notebook") < names.index("launch.spawn") < names.index("launch.ready")

    notebook = next(l for l in lines if l["event"] == "launch.notebook")
    assert notebook["path"].endswith("playground.py"), (
        f"launch.notebook.path must end with playground.py, got {notebook['path']!r}"
    )
    assert "mo.ui.text" in notebook["input_element"], (
        f"launch.notebook.input_element must contain mo.ui.text, got {notebook['input_element']!r}"
    )

    spawn = next(l for l in lines if l["event"] == "launch.spawn")
    assert spawn["port"] == 1234
    assert spawn["pid"] == 42
    assert spawn["mode"] == "edit"   # non-cuaderno source uses "edit" mode

    ready = next(l for l in lines if l["event"] == "launch.ready")
    assert ready["playground_id"] == "pgid123"

    # Clean up the notebook temp dir to avoid orphan files.
    shutil.rmtree(os.path.dirname(notebook["path"]), ignore_errors=True)


def test_spawn_failure_traces_launch_error_stage_spawn(tmp_path, monkeypatch):
    """Marimo-path test: source != cuaderno is needed for spawn. Use a non-cuaderno source."""
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    # Use non-cuaderno source to exercise the Marimo spawn path directly.
    req = PlaygroundLaunchRequest.from_dict({
        "source": "atlas",
        "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
        "breadcrumb": "bc",
    })
    with pytest.raises(MarimoSpawnError):
        launch_playground(req, str(tmp_path), _conn_with_symbol(), 1,
                          FailingRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next(l for l in lines if l["event"] == "launch.error")
    assert err["stage"] == "spawn" and "boom" in err["error"]


def test_notebook_stage_failure_traces_launch_error(tmp_path, monkeypatch):
    """When generate_marimo_notebook raises, launch.error with stage='notebook'
    must be recorded and the exception must propagate."""
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    req = PlaygroundLaunchRequest.from_dict({
        "source": "atlas",
        "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
        "breadcrumb": "bc",
    })
    with pytest.raises(OSError, match="disk full"):
        launch_playground(req, str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next((l for l in lines if l.get("event") == "launch.error"), None)
    assert err is not None, "launch.error event was not emitted"
    assert err["stage"] == "notebook"
    assert "disk full" in err["error"]


def test_launch_without_trace_still_works(tmp_path, monkeypatch):
    _stub_probe(monkeypatch)
    _stub_run_capture(monkeypatch)
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
    # cuaderno path with a non-empty stub returns StepThroughResponse (not PlaygroundLaunchResponse)
    from copyclip.intelligence.capture import StepThroughResponse
    assert isinstance(resp, StepThroughResponse)


# ---------------------------------------------------------------------------
# NEW TDD tests for the two issues raised by the code reviewer
# ---------------------------------------------------------------------------


# --- Issue 1: run_capture failure must emit launch.error stage="capture" ---


def test_capture_failure_model_path_emits_launch_error_stage_capture(tmp_path, monkeypatch):
    """Issue 1: run_capture raising CaptureError must emit launch.error with
    stage='capture' before re-raising. Previously the call was bare and the
    trace timeline stayed dark on this failure path."""
    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        lambda *a, **kw: (_ for _ in ()).throw(CaptureError("subprocess exploded")),
    )
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(CaptureError, match="subprocess exploded"):
        launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next((l for l in lines if l.get("event") == "launch.error"), None)
    assert err is not None, "launch.error must be emitted when run_capture raises"
    assert err["stage"] == "capture"
    assert "subprocess exploded" in err["error"]


def test_capture_failure_free_text_path_emits_launch_error_stage_capture(tmp_path, monkeypatch):
    """Issue 1: run_free_text_capture raising CaptureError must emit
    launch.error with stage='capture' before re-raising."""
    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_free_text_capture",
        lambda *a, **kw: (_ for _ in ()).throw(CaptureError("free-text driver died")),
    )
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(CaptureError, match="free-text driver died"):
        launch_playground(_req(call_text="foo(1)"), str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next((l for l in lines if l.get("event") == "launch.error"), None)
    assert err is not None, "launch.error must be emitted when run_free_text_capture raises"
    assert err["stage"] == "capture"
    assert "free-text driver died" in err["error"]


# --- Issue 2: probe_target must NOT be called when ctor pre-check short-circuits ---


def test_probe_not_called_when_ctor_check_short_circuits(tmp_path, monkeypatch):
    """Issue 2: for the model path, the ctor eligibility check (method with no
    ctor) is cheap and must not trigger a probe subprocess. Previously probe_target
    was called unconditionally before any eligibility check, so a fallback-bound
    request always paid for a subprocess spawn that was immediately discarded."""
    probe_call_count = {"n": 0}

    def _counting_probe(*a, **kw):
        probe_call_count["n"] += 1
        return _FAKE_DETECT, _FAKE_SOURCE_LINES

    monkeypatch.setattr("copyclip.intelligence.capture.probe_target", _counting_probe)

    # Method with no ctor proposed — eligibility_reason will decline (ctor check)
    # without needing is_async/is_generator from the probe.
    conn = _conn_with_symbol(kind="method", name="meth")
    req = _req(name="meth", qualname="MyClass.meth")

    # Need Marimo runner to handle the fallback (_cuaderno_fallback → _launch_marimo)
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "pg", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "pg"), exist_ok=True)

    launch_playground(req, str(tmp_path), conn, 1, FakeRunner())

    assert probe_call_count["n"] == 0, (
        "probe_target must not be called when the ctor check alone determines fallback"
    )


def test_probe_called_after_cheap_parse_succeeds_model_path(tmp_path, monkeypatch):
    """Issue 2 complementary: for a regular function (ctor check passes), probe IS
    called exactly once, and the capture proceeds. Verifies the happy path still works
    after deferral restructuring."""
    probe_call_count = {"n": 0}

    def _counting_probe(*a, **kw):
        probe_call_count["n"] += 1
        return _FAKE_DETECT, _FAKE_SOURCE_LINES

    monkeypatch.setattr("copyclip.intelligence.capture.probe_target", _counting_probe)
    _stub_run_capture(monkeypatch)

    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())

    assert probe_call_count["n"] == 1, "probe_target must be called exactly once on success path"
    from copyclip.intelligence.capture import StepThroughResponse
    assert isinstance(resp, StepThroughResponse)


# ---------------------------------------------------------------------------
# Issue: args/kwargs/ctor in widget data must route into CallDescriptor at launch
# ---------------------------------------------------------------------------


def test_request_from_dict_parses_call_args_kwargs_ctor():
    """PlaygroundLaunchRequest.from_dict must parse a 'call' dict with args,
    kwargs, and ctor into req.call — ready to be passed to CallDescriptor.from_dict
    in launch_playground. Without this the model's proposed invocation is silently
    discarded."""
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
        "breadcrumb": "Step through foo with real args",
        "call": {
            "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
            "args": [42, "hello"],
            "kwargs": {"verbose": True},
        },
    })
    assert req.call is not None, "call must be populated from the request dict"
    assert req.call["args"] == [42, "hello"]
    assert req.call["kwargs"] == {"verbose": True}
    assert req.call.get("ctor") is None


def test_request_from_dict_parses_call_with_ctor():
    """A method call with a ctor block must preserve ctor.args and ctor.kwargs."""
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "src/copyclip/util.py", "name": "process"},
        "breadcrumb": "Step through MyClass.process",
        "call": {
            "function_ref": {
                "file": "src/copyclip/util.py",
                "name": "process",
                "qualname": "MyClass.process",
            },
            "args": ["input.txt"],
            "kwargs": {},
            "ctor": {"args": [], "kwargs": {"mode": "strict"}},
        },
    })
    assert req.call is not None
    assert req.call["args"] == ["input.txt"]
    assert req.call["ctor"] == {"args": [], "kwargs": {"mode": "strict"}}


def test_launch_playground_routes_call_args_into_call_descriptor(tmp_path, monkeypatch):
    """End-to-end integration: a cuaderno launch request with call.args/kwargs
    must reach CallDescriptor.from_dict with those exact values — not fall back
    to an empty descriptor. This proves the model's proposed call is not silently
    discarded at the boundary between the widget and the capture path."""
    captured_descriptor = {}

    def _recording_run_capture(cd, resolved, **kw):
        captured_descriptor["args"] = cd.args
        captured_descriptor["kwargs"] = cd.kwargs
        captured_descriptor["ctor"] = cd.ctor
        return (_one_step(), False, None)

    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        _recording_run_capture,
    )

    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
        "breadcrumb": "Step through foo",
        "call": {
            "function_ref": {"file": "src/copyclip/util.py", "name": "foo"},
            "args": [99, "world"],
            "kwargs": {"debug": False},
        },
    })

    launch_playground(req, str(tmp_path), _conn_with_symbol(), 1, FakeRunner())

    assert captured_descriptor, "run_capture was never called — call was silently discarded"
    assert captured_descriptor["args"] == [99, "world"], (
        f"Expected args=[99, 'world'], got {captured_descriptor['args']!r}"
    )
    assert captured_descriptor["kwargs"] == {"debug": False}, (
        f"Expected kwargs={{'debug': False}}, got {captured_descriptor['kwargs']!r}"
    )
    assert captured_descriptor["ctor"] is None


def test_launch_playground_routes_ctor_into_call_descriptor(tmp_path, monkeypatch):
    """A method call with ctor must reach CallDescriptor with ctor intact — the
    ctor pre-check only blocks when ctor IS None; when it's present the probe
    and capture path must proceed with those ctor args."""
    captured_descriptor = {}

    def _recording_run_capture(cd, resolved, **kw):
        captured_descriptor["args"] = cd.args
        captured_descriptor["ctor"] = cd.ctor
        return (_one_step(), False, None)

    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        _recording_run_capture,
    )

    conn = _conn_with_symbol(kind="method", name="process")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {
            "file": "src/copyclip/util.py",
            "name": "process",
            "qualname": "MyClass.process",
        },
        "breadcrumb": "Step through MyClass.process",
        "call": {
            "function_ref": {
                "file": "src/copyclip/util.py",
                "name": "process",
                "qualname": "MyClass.process",
            },
            "args": ["input.txt"],
            "kwargs": {},
            "ctor": {"args": [], "kwargs": {"mode": "strict"}},
        },
    })

    launch_playground(req, str(tmp_path), conn, 1, FakeRunner())

    assert captured_descriptor, "run_capture was never called — call with ctor was silently discarded"
    assert captured_descriptor["args"] == ["input.txt"]
    assert captured_descriptor["ctor"] == {"args": [], "kwargs": {"mode": "strict"}}, (
        f"Expected ctor with mode='strict', got {captured_descriptor['ctor']!r}"
    )


# ---------------------------------------------------------------------------
# NEW: Critical #2 — empty captured trace returns FallbackResponse
# ---------------------------------------------------------------------------

def test_empty_trace_returns_fallback_response(tmp_path, monkeypatch):
    """When run_capture returns an empty Step[] (the call never entered the
    target function), launch_playground must return a FallbackResponse — NOT a
    StepThroughResponse(trace=[]) — so the frontend shows an honest 'nothing ran'
    message instead of mounting an empty stepper."""
    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        lambda *a, **kw: ([], False, None),   # empty trace
    )
    # Make _cuaderno_fallback → _launch_marimo work without a real notebook file.
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "pg", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "pg"), exist_ok=True)

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, FallbackResponse), (
        f"Empty trace must yield FallbackResponse, got {type(resp).__name__}"
    )
    assert "nothing" in resp.reason.lower() or "didn't run" in resp.reason.lower(), (
        f"FallbackResponse.reason must explain why: got {resp.reason!r}"
    )


def test_empty_free_text_trace_returns_fallback_response(tmp_path, monkeypatch):
    """Same guard applies to the free-text path."""
    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_free_text_capture",
        lambda *a, **kw: ([], False, None),
    )
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "pg2", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "pg2"), exist_ok=True)

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(_req(call_text="foo(1)"), str(tmp_path),
                             _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, FallbackResponse), (
        f"Empty free-text trace must yield FallbackResponse, got {type(resp).__name__}"
    )


# ---------------------------------------------------------------------------
# NEW: Critical #3/#5 — _cuaderno_fallback sets playground_id from inner.playground_id
# ---------------------------------------------------------------------------

def test_cuaderno_fallback_sets_playground_id_from_runner(tmp_path, monkeypatch):
    """FallbackResponse.playground_id must come from the Marimo runner's returned
    playground_id (inner.playground_id), not from idFromIframeUrl heuristics.
    The FakeRunner returns 'pgid123' — the FallbackResponse must carry that."""
    # Force the ctor short-circuit path (method with no ctor) → hits _cuaderno_fallback
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "fb", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "fb"), exist_ok=True)

    conn = _conn_with_symbol(kind="method", name="meth")
    req = _req(name="meth", qualname="MyClass.meth")

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(req, str(tmp_path), conn, 1, FakeRunner())
    assert isinstance(resp, FallbackResponse)
    assert resp.playground_id == "pgid123", (
        f"FallbackResponse.playground_id must be the runner's id; "
        f"got {resp.playground_id!r}"
    )


# ---------------------------------------------------------------------------
# NEW: Low display — func_name uses qualname when parent_class is set
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TRACER-CORRECTNESS Fix 2: decorated target → honest fallback at launch
# ---------------------------------------------------------------------------

def test_decorated_target_falls_back_at_launch(tmp_path, monkeypatch):
    """When probe_target reports is_decorated=True, launch_playground must
    decline to a FallbackResponse with an honest reason — never run a capture
    that would null the slab (the wrapper's file != the real body's anchor)."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.probe_target",
        lambda *a, **kw: ({"is_async": False, "is_generator": False, "is_decorated": True},
                          _FAKE_SOURCE_LINES),
    )
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "dec", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "dec"), exist_ok=True)

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, FallbackResponse), (
        f"a decorated target must fall back, got {type(resp).__name__}"
    )
    assert "decorat" in resp.reason.lower(), (
        f"the fallback reason must name the decorator; got {resp.reason!r}"
    )


# ---------------------------------------------------------------------------
# TRACER-CORRECTNESS Fix 5: truncated_reason carries through to the response
# ---------------------------------------------------------------------------

def test_truncated_reason_carried_on_step_through_response(tmp_path, monkeypatch):
    """run_capture returns (steps, truncated, truncated_reason); the
    StepThroughResponse must carry truncated_reason so the frontend can show the
    right message (steps overflow vs wall-clock overrun)."""
    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        lambda *a, **kw: (_one_step(), True, "time"),
    )
    from copyclip.intelligence.capture import StepThroughResponse
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, StepThroughResponse)
    assert resp.truncated is True
    assert resp.truncated_reason == "time", (
        f"StepThroughResponse must carry truncated_reason; got {resp.truncated_reason!r}"
    )
    assert resp.to_dict()["truncated_reason"] == "time"


def test_truncated_reason_none_serializes_on_response(tmp_path, monkeypatch):
    """A non-truncated trace serializes truncated_reason=None."""
    _stub_probe(monkeypatch)
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        lambda *a, **kw: (_one_step(), False, None),
    )
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
    assert resp.to_dict()["truncated"] is False
    assert resp.to_dict()["truncated_reason"] is None


def test_func_name_uses_qualname_when_method(tmp_path, monkeypatch):
    """StepThroughResponse.func_name must be resolved.qualname (e.g. 'MyClass.process')
    when parent_class is set, so the stepper shows class context."""
    captured_response = {}

    _stub_probe(monkeypatch)

    def _recording_run_capture(cd, resolved, **kw):
        # Return a non-empty trace so we don't hit the empty-trace fallback
        from copyclip.intelligence.capture import Step
        steps = [Step(line=1, event="line", changed=[], scope=[])]
        return steps, False, None

    monkeypatch.setattr("copyclip.intelligence.capture.run_capture", _recording_run_capture)

    conn = _conn_with_symbol(kind="method", name="process")
    req = PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {
            "file": "src/copyclip/util.py",
            "name": "process",
            "qualname": "MyClass.process",
        },
        "breadcrumb": "Step through MyClass.process",
        "call": {
            "function_ref": {
                "file": "src/copyclip/util.py",
                "name": "process",
                "qualname": "MyClass.process",
            },
            "args": [],
            "kwargs": {},
            "ctor": {"args": [], "kwargs": {}},
        },
    })

    from copyclip.intelligence.capture import StepThroughResponse
    resp = launch_playground(req, str(tmp_path), conn, 1, FakeRunner())
    assert isinstance(resp, StepThroughResponse), f"Expected StepThroughResponse, got {type(resp).__name__}"
    assert resp.func_name == "MyClass.process", (
        f"func_name must be qualname when parent_class is set; got {resp.func_name!r}"
    )


# ===========================================================================
# ORCHESTRATION Fix 1: BOTH dispatch paths must run the SAME eligibility gate
# (async/generator/decorated decline + eligibility_reason) BEFORE spawning.
# Today the free-text branch skips eligibility_reason — unify via one helper.
# ===========================================================================


def test_free_text_path_declines_async_target(tmp_path, monkeypatch):
    """The free-text (USER) path must decline an async target via the SAME gate
    the structured path uses — async functions step as one frame."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.probe_target",
        lambda *a, **kw: ({"is_async": True, "is_generator": False, "is_decorated": False},
                          _FAKE_SOURCE_LINES),
    )
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "ft_async", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "ft_async"), exist_ok=True)

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(_req(call_text="foo(1)"), str(tmp_path),
                             _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, FallbackResponse)
    assert "async" in resp.reason.lower()


def test_free_text_path_declines_generator_target(tmp_path, monkeypatch):
    """The free-text path must decline a generator target via the SAME gate."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.probe_target",
        lambda *a, **kw: ({"is_async": False, "is_generator": True, "is_decorated": False},
                          _FAKE_SOURCE_LINES),
    )
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "ft_gen", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "ft_gen"), exist_ok=True)

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(_req(call_text="foo(1)"), str(tmp_path),
                             _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, FallbackResponse)
    assert "generator" in resp.reason.lower()


def test_free_text_path_declines_decorated_target(tmp_path, monkeypatch):
    """The free-text path must decline a decorated target via the SAME gate —
    the wrapper's file is not the body's anchor."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.probe_target",
        lambda *a, **kw: ({"is_async": False, "is_generator": False, "is_decorated": True},
                          _FAKE_SOURCE_LINES),
    )
    monkeypatch.setattr(
        "copyclip.intelligence.playground.generate_marimo_notebook",
        lambda *a, **k: os.path.join(str(tmp_path), "ft_dec", "playground.py"),
    )
    os.makedirs(os.path.join(str(tmp_path), "ft_dec"), exist_ok=True)

    from copyclip.intelligence.capture import FallbackResponse
    resp = launch_playground(_req(call_text="foo(1)"), str(tmp_path),
                             _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, FallbackResponse)
    assert "decorat" in resp.reason.lower()


def test_free_text_path_runs_when_eligible(tmp_path, monkeypatch):
    """An eligible target on the free-text path still runs the capture (the gate
    must not over-decline a plain function)."""
    _stub_probe(monkeypatch)
    _stub_run_free_text_capture(monkeypatch)
    from copyclip.intelligence.capture import StepThroughResponse
    resp = launch_playground(_req(call_text="foo(1)"), str(tmp_path),
                             _conn_with_symbol(), 1, FakeRunner())
    assert isinstance(resp, StepThroughResponse)


def test_free_text_method_target_runs_user_supplied_ctor(tmp_path, monkeypatch):
    """For a METHOD target on the free-text path, the user types the whole call
    (ctor included), so the method-without-ctor decline must NOT fire — the gate
    treats the user's text as supplying the constructor."""
    _stub_probe(monkeypatch)
    _stub_run_free_text_capture(monkeypatch)
    conn = _conn_with_symbol(kind="method", name="meth")
    req = _req(name="meth", qualname="MyClass.meth", call_text="MyClass(1).meth(2)")
    from copyclip.intelligence.capture import StepThroughResponse
    resp = launch_playground(req, str(tmp_path), conn, 1, FakeRunner())
    assert isinstance(resp, StepThroughResponse), (
        "a method on the free-text path supplies its ctor by text and must run"
    )
