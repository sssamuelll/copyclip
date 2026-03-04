import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request

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


def _patch_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="PATCH", data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="POST", data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def test_decisions_pagination_and_meta():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        for i in range(5):
            conn.execute(
                "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
                (pid, f"d{i}", "s", "proposed", "manual"),
            )
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/decisions?limit=2&offset=1")
        assert len(res["items"]) == 2
        assert res["total"] == 5
        assert res["limit"] == 2
        assert res["offset"] == 1
        assert "meta" in res and "generated_at" in res["meta"]


def test_decision_history_endpoint():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
            (pid, "d", "s", "proposed", "manual"),
        )
        decision_id = cur.lastrowid
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        _patch_json(f"http://127.0.0.1:{port}/api/decisions/{decision_id}", {"status": "accepted"})
        hist = _get_json(f"http://127.0.0.1:{port}/api/decisions/{decision_id}/history")
        assert hist["total"] >= 1
        assert any(item["action"] == "status_change" for item in hist["items"])


def test_ask_endpoint_returns_grounded_answer_with_citations():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        conn.execute(
            "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
            (pid, "Adopt WebGPU pipeline", "Use GPU as default simulation backend", "accepted", "manual"),
        )
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _post_json(f"http://127.0.0.1:{port}/api/ask", {"question": "what did we decide about webgpu?"})
        assert res["grounded"] is True
        assert len(res["citations"]) >= 1
        assert any(c["type"] == "decision" for c in res["citations"])
