import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError

from copyclip.intelligence.db import connect, init_schema
from copyclip.intelligence.server import run_server


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(port: int, timeout_s: float = 3.0):
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start in time")


def _get_json(url: str):
    with request.urlopen(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _seed(conn, root: str) -> int:
    conn.execute("INSERT INTO projects(root_path,name,story) VALUES(?,?,?)", (root, "copyclip", "bounded delegation"))
    pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0]
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,agent_line_ratio,last_human_ts) VALUES(?,?,?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0, 0.72, 1_700_000_000.0),
    )
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Use bounded MCP handoff packets", "Bounded delegation.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/mcp_server.py"),
    )
    conn.commit()
    return pid


def test_breakdown_endpoint_returns_file_breakdown():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        resp = _get_json(
            f"http://127.0.0.1:{port}/api/cognitive-debt/breakdown?scope=file&id=src/copyclip/mcp_server.py"
        )
        breakdown = resp["breakdown"]
        assert breakdown["meta"]["scope_kind"] == "file"
        assert breakdown["meta"]["scope_id"] == "src/copyclip/mcp_server.py"
        assert breakdown["meta"]["contract_version"] == "v1"
        factor_ids = [f["factor_id"] for f in breakdown["factor_breakdown"]]
        assert "agent_authored_ratio" in factor_ids
        assert "decision_gap" in factor_ids


def test_breakdown_endpoint_rejects_invalid_scope():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        try:
            _get_json(f"http://127.0.0.1:{port}/api/cognitive-debt/breakdown?scope=cluster&id=foo")
            raise AssertionError("expected invalid scope to 400")
        except HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read().decode("utf-8"))
            assert body["error"] == "invalid_scope_kind"

        try:
            _get_json(f"http://127.0.0.1:{port}/api/cognitive-debt/breakdown?scope=module&id=does.not.exist")
            raise AssertionError("expected missing module to 404")
        except HTTPError as e:
            assert e.code == 404
            body = json.loads(e.read().decode("utf-8"))
            assert body["error"] == "module_not_found"


def test_breakdown_endpoint_requires_scope_id_for_file_and_module():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        try:
            _get_json(f"http://127.0.0.1:{port}/api/cognitive-debt/breakdown?scope=file")
            raise AssertionError("expected missing scope_id to 400")
        except HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read().decode("utf-8"))
            assert body["error"] == "scope_id_required"
