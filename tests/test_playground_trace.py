import json
import os
import shutil
import sqlite3

import pytest

from copyclip.intelligence.playground import (
    FunctionNotFoundError, MarimoSpawnError, PlaygroundLaunchRequest, launch_playground,
)
from copyclip.intelligence.cuaderno.trace import InteractionTrace


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


def _conn_with_symbol():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE symbols (project_id INT, name TEXT, kind TEXT,"
        " file_path TEXT, line_start INT, module TEXT)")
    conn.execute(
        "INSERT INTO symbols VALUES (1, 'foo', 'function', 'src/copyclip/util.py', 10, 'copyclip')")
    return conn


def _req(name="foo"):
    return PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "src/copyclip/util.py", "name": name},
        "breadcrumb": "bc",
        "suggested_inputs": ["src/copyclip/foo.py"],
    })


def _lines(trace):
    return [json.loads(l) for l in trace.path.read_text(encoding="utf-8").splitlines()]


def test_launch_traces_resolve_notebook_spawn_ready(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {"source": "cuaderno"})
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
                             FakeRunner(), trace=trace)
    trace.close(outcome="ready")
    assert resp.playground_id == "pgid123"
    lines = _lines(trace)
    names = [l["event"] for l in lines]
    assert names == ["launch.start", "launch.resolve", "launch.notebook",
                     "launch.spawn", "launch.ready", "launch.end"]
    resolve = lines[1]
    assert resolve["module"] == "copyclip.util" and resolve["name"] == "foo"
    notebook = lines[2]
    assert notebook["path"].endswith("playground.py") and "mo.ui.text" in notebook["input_element"]
    spawn = lines[3]
    assert spawn["port"] == 1234 and spawn["pid"] == 42 and spawn["mode"] == "run"
    assert lines[4]["playground_id"] == "pgid123"
    shutil.rmtree(os.path.dirname(notebook["path"]), ignore_errors=True)


def test_resolve_failure_traces_launch_error_stage_resolve(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(FunctionNotFoundError):
        launch_playground(_req(name="missing"), str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next(l for l in lines if l["event"] == "launch.error")
    assert err["stage"] == "resolve" and "missing" in err["error"]


def test_spawn_failure_traces_launch_error_stage_spawn(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(MarimoSpawnError):
        launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
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
    with pytest.raises(OSError, match="disk full"):
        launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next((l for l in lines if l.get("event") == "launch.error"), None)
    assert err is not None, "launch.error event was not emitted"
    assert err["stage"] == "notebook"
    assert "disk full" in err["error"]


def test_launch_without_trace_still_works(tmp_path):
    real_paths: list[str] = []
    import copyclip.intelligence.playground as _pg
    _original = _pg.generate_marimo_notebook

    def _recording(*args, **kwargs):
        path = _original(*args, **kwargs)
        real_paths.append(path)
        return path

    import shutil as _shutil
    _pg.generate_marimo_notebook = _recording
    try:
        resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
        assert resp.playground_id == "pgid123"
    finally:
        _pg.generate_marimo_notebook = _original
        for p in real_paths:
            nb_dir = os.path.dirname(p)
            if os.path.isdir(nb_dir):
                _shutil.rmtree(nb_dir, ignore_errors=True)
