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
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0, 0.72, 1_600_000_000.0),
    )
    for sha, author in [("sha-1", "samuel"), ("sha-2", "claude-bot"), ("sha-3", "claude-bot")]:
        conn.execute("INSERT INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)", (pid, sha, author, "2026-04-15T10:00:00+00:00", f"m-{sha}"))
        conn.execute("INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)", (pid, sha, "src/copyclip/mcp_server.py", 10, 2))
    conn.commit()
    return pid


def test_remediation_endpoint_returns_breakdown_and_plan():
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
            f"http://127.0.0.1:{port}/api/cognitive-debt/remediation?scope=file&id=src/copyclip/mcp_server.py"
        )
        assert "breakdown" in resp
        assert "plan" in resp
        plan = resp["plan"]
        assert plan["meta"]["scope_id"] == "src/copyclip/mcp_server.py"
        assert plan["remediation_candidates"]
        action_types = {c["action_type"] for c in plan["remediation_candidates"]}
        assert "review_this_recent_change" in action_types
        assert plan["read_first"]


def test_remediation_endpoint_rejects_invalid_scope():
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
            _get_json(f"http://127.0.0.1:{port}/api/cognitive-debt/remediation?scope=cluster&id=x")
            raise AssertionError("expected 400")
        except HTTPError as e:
            assert e.code == 400
            assert json.loads(e.read().decode("utf-8"))["error"] == "invalid_scope_kind"
