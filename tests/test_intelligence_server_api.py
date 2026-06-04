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


def _get_text(url: str, timeout: float = 3.0, max_bytes: int | None = None):
    with request.urlopen(url, timeout=timeout) as r:
        data = r.read() if max_bytes is None else r.read(max_bytes)
        return data.decode("utf-8")


def _get_stream_prefix(host: str, port: int, path: str, max_bytes: int = 512, timeout: float = 3.0):
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Accept: text/event-stream\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(req.encode("utf-8"))
        chunks = []
        deadline = time.time() + timeout
        while time.time() < deadline and sum(len(c) for c in chunks) < max_bytes:
            try:
                data = sock.recv(max_bytes)
            except TimeoutError:
                break
            if not data:
                break
            chunks.append(data)
            combined = b"".join(chunks)
            if b"event: connected" in combined:
                break
        return b"".join(chunks).decode("utf-8", errors="replace")


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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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


def test_events_endpoint_starts_with_connected_event():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        body = _get_stream_prefix("127.0.0.1", port, "/api/events?cursor=0")
        assert "event: connected" in body
        assert '"kind": "connected"' in body


def test_health_endpoint_contract():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/health")
        assert res["ok"] is True
        assert res["service"] == "copyclip-intelligence"
        assert res["meta"]["project"] == root.name
        assert res["meta"]["generated_at"]


def test_health_endpoint_survives_sustained_requests():
    # Each handler invocation opens a SQLite conn; if we leak them, the
    # server eventually exhausts fds. Documents the intent that every
    # do_* handler closes its conn on every return path.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        url = f"http://127.0.0.1:{port}/api/health"
        last = None
        for _ in range(50):
            last = _get_json(url)
            assert last["ok"] is True
        assert last is not None
        assert last["service"] == "copyclip-intelligence"
        assert last["meta"]["generated_at"]


def test_context_bundle_endpoint_returns_manifest():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
        conn.execute(
            "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
            (pid, "src/auth/session.ts", "typescript", 1000, 1.0, "h1"),
        )
        conn.execute(
            "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
            (pid, "src/auth/session.ts", "high", "churn", "frequent edits", 90),
        )
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/context-bundle?q=auth+session")
        assert "manifest" in res
        assert len(res["manifest"]) >= 1
        assert res["manifest"][0]["path"] == "src/auth/session.ts"


def test_analyze_cancel_without_running_job_returns_404():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        try:
            _post_json(f"http://127.0.0.1:{port}/api/analyze/cancel", {})
            assert False, "Expected HTTPError"
        except HTTPError as e:
            assert e.code == 404
            payload = json.loads(e.read().decode("utf-8"))
            assert payload.get("error") == "no_running_job"


def test_risk_trends_endpoint_works_with_snapshot_breakdown():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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


def test_settings_alias_get_and_post():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        _post_json(f"http://127.0.0.1:{port}/api/settings", {"COPYCLIP_LLM_PROVIDER": "gemini"})
        res = _get_json(f"http://127.0.0.1:{port}/api/settings")
        assert res.get("COPYCLIP_LLM_PROVIDER") == "gemini"

        _post_json(f"http://127.0.0.1:{port}/api/config", {"COPYCLIP_THEME": "midnight"})
        res2 = _get_json(f"http://127.0.0.1:{port}/api/config")
        assert res2.get("COPYCLIP_THEME") == "midnight"


def test_analyze_job_start_and_status_endpoints():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        root_path = str(root.absolute())
        (root / 'src').mkdir(parents=True, exist_ok=True)
        (root / 'src' / 'a.py').write_text('print(1)\n')

        conn = connect(root_path)
        init_schema(conn)
        conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root_path, "tmp"))
        conn.commit()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        start_res = _post_json(f"http://127.0.0.1:{port}/api/analyze/start", {})
        assert start_res["ok"] is True
        assert "job_id" in start_res

        status = _get_json(f"http://127.0.0.1:{port}/api/analyze/status")
        assert "items" in status
        assert len(status["items"]) >= 1
