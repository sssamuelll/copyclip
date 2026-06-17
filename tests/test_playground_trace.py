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
_FAKE_STEPS: list = []


def _stub_probe(monkeypatch):
    """Make probe_target return a safe synchronous, non-generator result."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.probe_target",
        lambda *a, **kw: (_FAKE_DETECT, _FAKE_SOURCE_LINES),
    )


def _stub_run_capture(monkeypatch):
    """Make run_capture return an empty Step[] list."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_capture",
        lambda *a, **kw: (_FAKE_STEPS, False),
    )


def _stub_run_free_text_capture(monkeypatch):
    """Make run_free_text_capture return an empty Step[] list."""
    monkeypatch.setattr(
        "copyclip.intelligence.capture.run_free_text_capture",
        lambda *a, **kw: (_FAKE_STEPS, False),
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
    # The cuaderno path with empty steps returns a StepThroughResponse, not a
    # PlaygroundLaunchResponse; the Marimo runner is NOT exercised here.
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
    # cuaderno path with stubs returns a StepThroughResponse (not PlaygroundLaunchResponse)
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
