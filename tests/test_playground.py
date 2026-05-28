"""Tests for the Anchored Playground backend foundation (issue #87).

Covers:
- Wire-shape parsing and validation (FunctionRef, PlaygroundLaunchRequest)
- Module-from-file path conversion
- Marimo notebook generation (valid Python, empty inputs, method qualname,
  first-input-only semantics)
- Resolver against a seeded sqlite symbols table
- Orchestrator (launch_playground) with a Mock runner
- StubMarimoRunner placeholder behaviour
- HTTP endpoints (POST /launch, DELETE /{id}, GET /{id}/status) with an
  injected Mock runner
"""

from __future__ import annotations

import ast
import json
import socket
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock
from urllib import request
from urllib.error import HTTPError

import pytest

from copyclip.intelligence.db import connect, init_schema
from copyclip.intelligence.playground import (
    FunctionNotFoundError,
    FunctionRef,
    InvalidFunctionRefError,
    InvalidRequestError,
    MarimoNotInstalledError,
    MarimoSpawnError,
    PlaygroundLaunchRequest,
    PlaygroundLaunchResponse,
    ResolvedFunction,
    StubMarimoRunner,
    _module_from_file,
    generate_marimo_notebook,
    launch_playground,
    resolve_function_ref,
)
from copyclip.intelligence.server import run_server


# ---------------------------------------------------------------------------
# Wire-shape parsing
# ---------------------------------------------------------------------------


def test_function_ref_from_dict_minimal():
    ref = FunctionRef.from_dict({"file": "src/foo.py", "name": "bar"})
    assert ref.file == "src/foo.py"
    assert ref.name == "bar"
    assert ref.line is None
    assert ref.qualname is None


def test_function_ref_from_dict_full():
    ref = FunctionRef.from_dict(
        {"file": "src/foo.py", "name": "method_name", "line": 42, "qualname": "Foo.method_name"}
    )
    assert ref.line == 42
    assert ref.qualname == "Foo.method_name"


def test_function_ref_rejects_absolute_posix_path():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"file": "/abs/foo.py", "name": "bar"})


def test_function_ref_rejects_absolute_windows_path():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"file": "C:/abs/foo.py", "name": "bar"})


def test_function_ref_rejects_missing_file():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"name": "bar"})


def test_function_ref_rejects_missing_name():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"file": "src/foo.py"})


def test_request_from_dict_minimal():
    req = PlaygroundLaunchRequest.from_dict(
        {
            "source": "atlas",
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "breadcrumb": "Atlas -> src/foo.py -> bar()",
        }
    )
    assert req.source == "atlas"
    assert req.function_ref.name == "bar"
    assert req.breadcrumb == "Atlas -> src/foo.py -> bar()"


def test_request_rejects_invalid_source():
    with pytest.raises(InvalidRequestError):
        PlaygroundLaunchRequest.from_dict(
            {"source": "made_up", "function_ref": {"file": "src/foo.py", "name": "bar"}}
        )


def test_response_to_dict_no_expires_at():
    res = PlaygroundLaunchResponse(playground_id="abc", iframe_url="http://127.0.0.1:5000/")
    payload = res.to_dict()
    assert payload == {"playground_id": "abc", "iframe_url": "http://127.0.0.1:5000/"}
    assert "expires_at" not in payload


# ---------------------------------------------------------------------------
# Module-from-file helper
# ---------------------------------------------------------------------------


def test_module_from_file_strips_src_prefix():
    assert _module_from_file("src/copyclip/foo.py") == "copyclip.foo"
    assert (
        _module_from_file("src/copyclip/intelligence/reacquaintance.py")
        == "copyclip.intelligence.reacquaintance"
    )


def test_module_from_file_handles_no_src_prefix():
    assert _module_from_file("tests/test_foo.py") == "tests.test_foo"


def test_module_from_file_normalises_windows_separators():
    assert _module_from_file("src\\copyclip\\foo.py") == "copyclip.foo"


# ---------------------------------------------------------------------------
# Notebook generator
# ---------------------------------------------------------------------------


def _make_resolved(
    *,
    name: str = "bar",
    module: str = "copyclip.foo",
    parent: str | None = None,
    kind: str = "function",
    file: str = "src/copyclip/foo.py",
) -> ResolvedFunction:
    return ResolvedFunction(
        file=file,
        name=name,
        qualname=f"{parent}.{name}" if parent else name,
        kind=kind,
        module=module,
        line_start=10,
        parent_class=parent,
    )


def test_generate_notebook_writes_valid_python(tmp_path):
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/copyclip/foo.py", name="bar"),
        suggested_inputs=[42],
        breadcrumb="test",
    )
    nb = generate_marimo_notebook(req, str(tmp_path), _make_resolved(), temp_dir=str(tmp_path))
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    assert "from copyclip.foo import bar" in content
    assert "result = bar(sample)" in content
    assert "sample = 42" in content


def test_generate_notebook_handles_empty_inputs(tmp_path):
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/copyclip/foo.py", name="bar"),
        breadcrumb="test",
    )
    nb = generate_marimo_notebook(req, str(tmp_path), _make_resolved(), temp_dir=str(tmp_path))
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    assert "# TODO: supply input" in content
    assert "result = bar(sample)" not in content


def test_generate_notebook_method_qualname(tmp_path):
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(
            file="src/copyclip/foo.py", name="method_name", qualname="Foo.method_name"
        ),
        suggested_inputs=[1],
        breadcrumb="test",
    )
    nb = generate_marimo_notebook(
        req,
        str(tmp_path),
        _make_resolved(name="method_name", parent="Foo", kind="method"),
        temp_dir=str(tmp_path),
    )
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    assert "from copyclip.foo import Foo" in content
    assert "Foo(...).method_name(sample)" in content


def test_generate_notebook_uses_first_input_only(tmp_path):
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/copyclip/foo.py", name="bar"),
        suggested_inputs=[7, 99, 1000],
        breadcrumb="test",
    )
    nb = generate_marimo_notebook(req, str(tmp_path), _make_resolved(), temp_dir=str(tmp_path))
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    assert "sample = 7" in content
    assert "sample = 99" not in content
    assert "sample = 1000" not in content


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def _seed_project(conn: sqlite3.Connection, root: str = "/proj") -> int:
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
    return int(row[0])


def _seed_symbol(
    conn: sqlite3.Connection,
    pid: int,
    *,
    name: str,
    kind: str,
    file_path: str,
    module: str | None = None,
    line_start: int = 10,
) -> None:
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, name, kind, file_path, line_start, line_start + 5, None, module),
    )
    conn.commit()


def test_resolve_function_ref_finds_function():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(conn, pid, name="bar", kind="function", file_path="src/foo.py", module="foo")
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/foo.py", name="bar"))
    assert resolved.name == "bar"
    assert resolved.kind == "function"
    assert resolved.module == "foo"
    assert resolved.parent_class is None


def test_resolve_function_ref_method_with_qualname():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(
        conn, pid, name="method_name", kind="method", file_path="src/foo.py", module="foo"
    )
    resolved = resolve_function_ref(
        conn,
        pid,
        FunctionRef(file="src/foo.py", name="method_name", qualname="Foo.method_name"),
    )
    assert resolved.parent_class == "Foo"
    assert resolved.qualname == "Foo.method_name"


def test_resolve_function_ref_raises_on_missing():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    with pytest.raises(FunctionNotFoundError):
        resolve_function_ref(conn, pid, FunctionRef(file="src/missing.py", name="nope"))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_launch_playground_calls_runner_with_generated_path(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(conn, pid, name="bar", kind="function", file_path="src/foo.py", module="foo")

    mock_runner = Mock()
    mock_runner.launch.return_value = ("test-id-123", "http://127.0.0.1:5000/")

    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/foo.py", name="bar"),
        suggested_inputs=[1],
        breadcrumb="test",
    )
    response = launch_playground(req, str(tmp_path), conn, pid, mock_runner)

    assert response.playground_id == "test-id-123"
    assert response.iframe_url == "http://127.0.0.1:5000/"
    mock_runner.launch.assert_called_once()
    notebook_path = mock_runner.launch.call_args[0][0]
    assert Path(notebook_path).exists()
    assert Path(notebook_path).name == "playground.py"


def test_launch_playground_propagates_marimo_not_installed(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(conn, pid, name="bar", kind="function", file_path="src/foo.py", module="foo")

    mock_runner = Mock()
    mock_runner.launch.side_effect = MarimoNotInstalledError("marimo missing")

    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/foo.py", name="bar"),
        breadcrumb="test",
    )
    with pytest.raises(MarimoNotInstalledError):
        launch_playground(req, str(tmp_path), conn, pid, mock_runner)


# ---------------------------------------------------------------------------
# StubMarimoRunner
# ---------------------------------------------------------------------------


def test_stub_runner_kill_returns_false():
    assert StubMarimoRunner().kill("any-id") is False


def test_stub_runner_status_returns_missing():
    assert StubMarimoRunner().status("any-id") == "missing"


def test_stub_runner_launch_raises_spawn_error(tmp_path):
    nb = tmp_path / "playground.py"
    nb.write_text("import marimo\napp = marimo.App()\n", encoding="utf-8")
    with pytest.raises(MarimoSpawnError) as exc:
        StubMarimoRunner().launch(str(nb))
    assert "not yet implemented" in str(exc.value)


# ---------------------------------------------------------------------------
# HTTP endpoints (Mock runner injected via run_server kwarg)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(port: int, timeout_s: float = 3.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"server did not start on {port} in time")


def _seed_playground_project(conn: sqlite3.Connection, root: str) -> int:
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    pid = int(
        conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0]
    )
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            pid,
            "build_reacquaintance_briefing",
            "function",
            "src/copyclip/intelligence/reacquaintance.py",
            1,
            10,
            None,
            "copyclip.intelligence.reacquaintance",
        ),
    )
    conn.commit()
    return pid


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, method="POST", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def _delete_json(url: str) -> tuple[int, dict]:
    req = request.Request(url, method="DELETE")
    try:
        with request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def _get_json(url: str) -> tuple[int, dict]:
    try:
        with request.urlopen(url, timeout=3) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def _start_server_with_runner(runner) -> tuple[str, int]:
    """Spin up a server bound to a fresh tempdir with the given runner injected.

    Returns (root, port) — caller is responsible for nothing (thread is daemon).
    """
    td = tempfile.mkdtemp(prefix="copyclip-pg-test-")
    root = str(Path(td).absolute())
    conn = connect(root)
    init_schema(conn)
    _seed_playground_project(conn, root)
    conn.close()

    port = _free_port()
    th = threading.Thread(
        target=run_server,
        kwargs={"project_root": root, "port": port, "playground_runner": runner},
        daemon=True,
    )
    th.start()
    _wait_port(port)
    return root, port


def test_launch_endpoint_returns_runner_response():
    mock_runner = Mock()
    mock_runner.launch.return_value = ("uuid-runner", "http://127.0.0.1:9999/")
    _, port = _start_server_with_runner(mock_runner)

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "atlas",
            "function_ref": {
                "file": "src/copyclip/intelligence/reacquaintance.py",
                "name": "build_reacquaintance_briefing",
            },
            "breadcrumb": "test",
        },
    )
    assert status == 200
    assert body["playground_id"] == "uuid-runner"
    assert body["iframe_url"] == "http://127.0.0.1:9999/"
    assert "expires_at" not in body
    mock_runner.launch.assert_called_once()


def test_launch_endpoint_returns_marimo_not_installed():
    mock_runner = Mock()
    mock_runner.launch.side_effect = MarimoNotInstalledError("not installed")
    _, port = _start_server_with_runner(mock_runner)

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "atlas",
            "function_ref": {
                "file": "src/copyclip/intelligence/reacquaintance.py",
                "name": "build_reacquaintance_briefing",
            },
            "breadcrumb": "test",
        },
    )
    assert status == 503
    assert body["error"] == "marimo_not_installed"
    assert body["install_hint"] == "pip install copyclip[playground]"


def test_launch_endpoint_rejects_absolute_path():
    _, port = _start_server_with_runner(Mock())

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "atlas",
            "function_ref": {"file": "/abs/path/foo.py", "name": "bar"},
            "breadcrumb": "test",
        },
    )
    assert status == 400
    assert body["error"] == "invalid_function_ref"


def test_launch_endpoint_rejects_unknown_source():
    _, port = _start_server_with_runner(Mock())

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "made_up_surface",
            "function_ref": {
                "file": "src/copyclip/intelligence/reacquaintance.py",
                "name": "build_reacquaintance_briefing",
            },
            "breadcrumb": "test",
        },
    )
    assert status == 400
    assert body["error"] == "invalid_request"


def test_launch_endpoint_function_not_found():
    _, port = _start_server_with_runner(Mock())

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "atlas",
            "function_ref": {
                "file": "src/copyclip/intelligence/reacquaintance.py",
                "name": "no_such_function_anywhere",
            },
            "breadcrumb": "test",
        },
    )
    assert status == 404
    assert body["error"] == "function_not_found"


def test_delete_endpoint_calls_runner_kill():
    mock_runner = Mock()
    mock_runner.kill.return_value = True
    _, port = _start_server_with_runner(mock_runner)

    status, body = _delete_json(f"http://127.0.0.1:{port}/api/playground/some-uuid")
    assert status == 200
    assert body == {"ok": True, "id": "some-uuid"}
    mock_runner.kill.assert_called_once_with("some-uuid")


def test_delete_endpoint_returns_404_when_kill_returns_false():
    mock_runner = Mock()
    mock_runner.kill.return_value = False
    _, port = _start_server_with_runner(mock_runner)

    status, body = _delete_json(f"http://127.0.0.1:{port}/api/playground/missing-uuid")
    assert status == 404
    assert body["error"] == "playground_not_found"


def test_status_endpoint_returns_runner_status_running():
    mock_runner = Mock()
    mock_runner.status.return_value = "running"
    _, port = _start_server_with_runner(mock_runner)

    status, body = _get_json(f"http://127.0.0.1:{port}/api/playground/abc/status")
    assert status == 200
    assert body == {"status": "running", "id": "abc"}


def test_status_endpoint_returns_runner_status_exited():
    mock_runner = Mock()
    mock_runner.status.return_value = "exited"
    _, port = _start_server_with_runner(mock_runner)

    status, body = _get_json(f"http://127.0.0.1:{port}/api/playground/abc/status")
    assert status == 200
    assert body["status"] == "exited"


def test_status_endpoint_returns_runner_status_missing():
    mock_runner = Mock()
    mock_runner.status.return_value = "missing"
    _, port = _start_server_with_runner(mock_runner)

    status, body = _get_json(f"http://127.0.0.1:{port}/api/playground/unknown/status")
    assert status == 200
    assert body["status"] == "missing"


# ---------------------------------------------------------------------------
# Security & robustness regression tests
# (post-review additions; see PR #98 review for context)
# ---------------------------------------------------------------------------


def test_function_ref_rejects_non_identifier_name():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"file": "src/foo.py", "name": "bar; import os"})


def test_function_ref_rejects_qualname_injection():
    """qualname='x;import os;y.real_method' would otherwise inject `import os`
    into the generated `from {mod} import x;import os;y` statement."""
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict(
            {
                "file": "src/foo.py",
                "name": "real_method",
                "qualname": "x;import os;y.real_method",
            }
        )


def test_function_ref_rejects_nested_qualname():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict(
            {
                "file": "src/foo.py",
                "name": "method_name",
                "qualname": "Outer.Inner.method_name",
            }
        )


def test_function_ref_rejects_path_traversal():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"file": "../../../etc/passwd.py", "name": "bar"})


def test_function_ref_rejects_path_traversal_windows_separators():
    with pytest.raises(InvalidFunctionRefError):
        FunctionRef.from_dict({"file": "src\\..\\..\\etc.py", "name": "bar"})


def test_generate_notebook_sanitizes_newline_in_breadcrumb(tmp_path):
    """A breadcrumb with a newline must not escape the comment line and run
    as code on subprocess spawn."""
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/copyclip/foo.py", name="bar"),
        suggested_inputs=[1],
        breadcrumb="atlas\n    import os; os.system('pwn')",
    )
    nb = generate_marimo_notebook(req, str(tmp_path), _make_resolved(), temp_dir=str(tmp_path))
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    # The whole payload must collapse to a single `# Breadcrumb:` comment line,
    # and `os.system` must NOT appear on any non-comment line.
    breadcrumb_lines = [
        ln for ln in content.splitlines() if ln.lstrip().startswith("# Breadcrumb:")
    ]
    assert len(breadcrumb_lines) == 1
    assert "os.system" in breadcrumb_lines[0]
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        assert "os.system" not in stripped, f"os.system leaked into runnable line: {line!r}"


def test_generate_notebook_sanitizes_unicode_line_separator(tmp_path):
    """U+2028 (line separator) is also a line terminator in some contexts."""
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/copyclip/foo.py", name="bar"),
        suggested_inputs=[1],
        breadcrumb="atlas import os",
    )
    nb = generate_marimo_notebook(req, str(tmp_path), _make_resolved(), temp_dir=str(tmp_path))
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    assert " " not in content


def test_generate_notebook_truncates_excessive_breadcrumb(tmp_path):
    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/copyclip/foo.py", name="bar"),
        suggested_inputs=[1],
        breadcrumb="x" * 2000,
    )
    nb = generate_marimo_notebook(req, str(tmp_path), _make_resolved(), temp_dir=str(tmp_path))
    content = Path(nb).read_text(encoding="utf-8")
    ast.parse(content)
    # Long enough to verify the sanitiser engaged without hard-coding the cap.
    assert content.count("x") < 1000
    assert "..." in content


def test_resolve_function_ref_rejects_non_importable_module():
    """Files like 2legit.py or foo-bar.py would otherwise produce an import
    statement that fails at runtime with a confusing marimo_spawn_failed."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(
        conn, pid, name="bar", kind="function", file_path="src/foo-bar.py", module=None
    )
    with pytest.raises(FunctionNotFoundError) as exc:
        resolve_function_ref(conn, pid, FunctionRef(file="src/foo-bar.py", name="bar"))
    assert "importable" in str(exc.value).lower()


def test_resolve_function_ref_uses_db_file_for_module_fallback():
    """When the symbols.module column is NULL, the resolver derives the module
    from the analyzer's canonical file path, not the user-supplied path."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(
        conn, pid, name="bar", kind="function", file_path="src/copyclip/foo.py", module=None
    )
    resolved = resolve_function_ref(
        conn, pid, FunctionRef(file="src/copyclip/foo.py", name="bar")
    )
    assert resolved.module == "copyclip.foo"


def test_resolve_function_ref_overrides_slash_style_db_module():
    """The analyzer stores `symbols.module` in slash-style for the architecture
    graph (e.g. 'copyclip/intelligence'). Trusting that value here would
    produce a `from copyclip/intelligence import …` line that fails the
    dotted-identifier check and surfaces to the user as the misleading
    'function not found in the index' dialog. The resolver must derive the
    dotted module from the canonical file path instead of using the DB
    column."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(
        conn,
        pid,
        name="AgentTool",
        kind="class",
        file_path="src/copyclip/intelligence/agents.py",
        module="copyclip/intelligence",  # slash-style as the analyzer stores it
    )
    resolved = resolve_function_ref(
        conn, pid, FunctionRef(file="src/copyclip/intelligence/agents.py", name="AgentTool")
    )
    assert resolved.module == "copyclip.intelligence.agents"


def test_launch_playground_cleans_temp_dir_on_runner_failure(tmp_path):
    """Failed runner.launch must not leak per-request temp dirs."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_project(conn)
    _seed_symbol(conn, pid, name="bar", kind="function", file_path="src/foo.py", module="foo")

    mock_runner = Mock()
    mock_runner.launch.side_effect = MarimoSpawnError("boom")

    req = PlaygroundLaunchRequest(
        source="atlas",
        function_ref=FunctionRef(file="src/foo.py", name="bar"),
        suggested_inputs=[1],
        breadcrumb="test",
    )
    with pytest.raises(MarimoSpawnError):
        launch_playground(req, str(tmp_path), conn, pid, mock_runner)

    notebook_path = mock_runner.launch.call_args[0][0]
    assert not Path(notebook_path).exists(), "temp notebook should be cleaned up"
    assert not Path(notebook_path).parent.exists(), "temp dir should be cleaned up"


def test_launch_endpoint_rejects_malformed_json():
    """A POST with a non-JSON body must surface as 400 invalid_request, not
    bubble up as an HTTP 500."""
    _, port = _start_server_with_runner(Mock())

    body = b"not json at all {{{{"
    req = request.Request(
        f"http://127.0.0.1:{port}/api/playground/launch",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=3) as r:
            status, payload = r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8")
        status, payload = exc.code, json.loads(body_text) if body_text else {}
    assert status == 400
    assert payload["error"] == "invalid_request"


def test_launch_endpoint_rejects_qualname_injection():
    _, port = _start_server_with_runner(Mock())

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "atlas",
            "function_ref": {
                "file": "src/copyclip/intelligence/reacquaintance.py",
                "name": "build_reacquaintance_briefing",
                "qualname": "x;import os;y.build_reacquaintance_briefing",
            },
            "breadcrumb": "test",
        },
    )
    assert status == 400
    assert body["error"] == "invalid_function_ref"


def test_launch_endpoint_rejects_path_traversal():
    _, port = _start_server_with_runner(Mock())

    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/playground/launch",
        {
            "source": "atlas",
            "function_ref": {"file": "../../../etc/passwd.py", "name": "bar"},
            "breadcrumb": "test",
        },
    )
    assert status == 400
    assert body["error"] == "invalid_function_ref"
