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


def _patch_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="PATCH", data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _patch_json_expect_error(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="PATCH", data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


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


def test_risk_trends_endpoint_works_with_snapshot_breakdown():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        conn.execute("INSERT INTO snapshots(project_id, summary_json) VALUES(?,?)", (pid, json.dumps({"risk_breakdown": {"churn": 2, "test_gap": 1}})))
        conn.execute("INSERT INTO snapshots(project_id, summary_json) VALUES(?,?)", (pid, json.dumps({"risk_breakdown": {"churn": 4, "complexity": 3}})))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/risks/trends")
        assert res["has_previous"] is True
        assert res["latest"]["churn"] == 4
        assert res["delta"]["churn"] == 2
        assert res["delta"]["test_gap"] == -1


def test_quality_gate_blocks_resolve_without_evidence():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
            (pid, "d", "s", "accepted", "manual"),
        )
        decision_id = cur.lastrowid
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        code, err = _patch_json_expect_error(
            f"http://127.0.0.1:{port}/api/decisions/{decision_id}",
            {"status": "resolved"},
        )
        assert code == 409
        assert err["error"] == "quality_gate_blocked"


def test_quality_gate_allows_resolve_with_ref_or_note():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
            (pid, "d", "s", "accepted", "manual"),
        )
        decision_id = cur.lastrowid
        conn.execute(
            "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
            (decision_id, "file", "src/core.ts"),
        )
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        ok = _patch_json(f"http://127.0.0.1:{port}/api/decisions/{decision_id}", {"status": "resolved"})
        assert ok["ok"] is True
        assert ok["status"] == "resolved"


def test_pulls_endpoint_pagination():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        for i in range(3):
            conn.execute(
                "INSERT INTO pulls(project_id,external_id,title,body,status,merged,labels,author,url,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, str(i+1), f"PR {i+1}", "", "OPEN", 0, "", "dev", f"https://x/pr/{i+1}", "github", "2026-01-01", "2026-01-01"),
            )
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/pulls?limit=2&offset=1")
        assert res["total"] == 3
        assert res["limit"] == 2
        assert res["offset"] == 1
        assert len(res["items"]) == 2
