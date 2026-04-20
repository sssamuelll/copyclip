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


def _post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="POST", data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _seed_handoff_api_project(conn, root_path: str) -> int:
    conn.execute("INSERT INTO projects(root_path,name,story) VALUES(?,?,?)", (root_path, "copyclip", "local-first control plane"))
    pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root_path,)).fetchone()[0]
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Use bounded MCP handoff packets", "Delegation should use inspectable bounded packets.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/mcp_server.py"),
    )
    conn.execute(
        "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "python", 1200, 1.0, "h-mcp"),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0),
    )
    conn.execute(
        "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery can bypass bounded delegation if widened carelessly.", 93),
    )
    conn.commit()
    return pid


def test_handoff_packets_api_create_list_get_patch_and_review_summary():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_handoff_api_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        created = _post_json(
            f"http://127.0.0.1:{port}/api/handoff-packets",
            {
                "task_prompt": "Build a bounded handoff packet generator for MCP delegation.",
                "declared_files": ["src/copyclip/mcp_server.py"],
                "declared_modules": ["copyclip.mcp"],
                "do_not_touch": [{"target": "frontend", "reason": "UI excluded.", "severity": "hard_boundary"}],
                "acceptance_criteria": ["Packet includes scope and review contract."],
                "generated_at": "2026-04-16T12:00:00Z",
            },
        )
        packet_id = created["packet"]["meta"]["packet_id"]
        assert created["packet"]["meta"]["state"] == "ready_for_review"

        listed = _get_json(f"http://127.0.0.1:{port}/api/handoff-packets")
        assert listed["total"] == 1
        assert listed["items"][0]["packet_id"] == packet_id
        assert listed["items"][0]["state"] == "ready_for_review"

        fetched = _get_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}")
        assert fetched["packet"]["meta"]["packet_id"] == packet_id
        assert fetched["packet"]["agent_consumable_packet"]["allowed_write_scope"] == ["src/copyclip/mcp_server.py"]

        patched = _patch_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
            {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"},
        )
        assert patched["packet"]["meta"]["state"] == "approved_for_handoff"
        assert patched["packet"]["meta"]["approved_by"] == "samuel"
        assert patched["packet"]["meta"]["delegation_target"] == "claude-code"

        patched = _patch_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
            {"state": "delegated"},
        )
        assert patched["packet"]["meta"]["state"] == "delegated"

        patched = _patch_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
            {"state": "change_received"},
        )
        assert patched["packet"]["meta"]["state"] == "change_received"

        review = _post_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}/review-summary",
            {
                "review_state": "generated",
                "result": {"summary": "Change stayed in scope.", "verdict": "accepted", "confidence": "medium"},
                "scope_check": {"declared_scope": ["src/copyclip/mcp_server.py"], "touched_files": ["src/copyclip/mcp_server.py"], "out_of_scope_touches": [], "summary": "All touches stayed in scope."},
            },
        )
        assert review["review_summary"]["meta"]["packet_id"] == packet_id
        assert review["review_summary"]["meta"]["review_state"] == "generated"
        assert review["packet"]["meta"]["state"] == "reviewed"

        fetched = _get_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}")
        assert fetched["packet"]["meta"]["state"] == "reviewed"

        fetched_review = _get_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}/review-summary")
        assert fetched_review["review_summary"]["result"]["verdict"] == "accepted"


def test_handoff_packet_create_blocks_without_scope_or_with_invalid_state_transition():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_handoff_api_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        created = _post_json(
            f"http://127.0.0.1:{port}/api/handoff-packets",
            {"task_prompt": "Help with delegation.", "declared_files": [], "declared_modules": []},
        )
        packet_id = created["packet"]["meta"]["packet_id"]
        assert created["packet"]["meta"]["state"] == "draft"

        try:
            _patch_json(
                f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
                {"state": "delegated"},
            )
            raise AssertionError("expected invalid transition to fail")
        except HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            assert e.code == 409
            assert body["error"] == "invalid_state_transition"

        try:
            _post_json(
                f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}/review-summary",
                {"review_state": "generated", "result": {"summary": "too early"}},
            )
            raise AssertionError("expected premature review creation to fail")
        except HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            assert e.code == 409
            assert body["error"] == "invalid_review_state_for_packet"


def test_handoff_review_summary_can_be_generated_from_proposed_changes():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_handoff_api_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        created = _post_json(
            f"http://127.0.0.1:{port}/api/handoff-packets",
            {
                "task_prompt": "Build a bounded handoff packet generator for MCP delegation.",
                "declared_files": ["src/copyclip/mcp_server.py"],
                "do_not_touch": [{"target": "frontend/src/pages/AskPage.tsx", "reason": "Ask UI excluded.", "severity": "hard_boundary"}],
                "acceptance_criteria": ["Packet includes scope and review contract."],
                "generated_at": "2026-04-20T10:00:00Z",
            },
        )
        packet_id = created["packet"]["meta"]["packet_id"]
        _patch_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}", {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"})
        _patch_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}", {"state": "delegated"})
        _patch_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}", {"state": "change_received"})

        review = _post_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}/review-summary",
            {
                "proposed_changes": {
                    "touched_files": [
                        "src/copyclip/mcp_server.py",
                        "frontend/src/pages/AskPage.tsx",
                    ]
                },
                "generated_at": "2026-04-20T11:00:00Z",
            },
        )
        assert review["review_summary"]["meta"]["packet_id"] == packet_id
        assert review["review_summary"]["result"]["verdict"] == "changes_requested"
        assert any(
            violation["target"] == "frontend/src/pages/AskPage.tsx"
            for violation in review["review_summary"]["scope_check"]["boundary_violations"]
        )
        assert "frontend/src/pages/AskPage.tsx" in review["review_summary"]["scope_check"]["out_of_scope_touches"]
        assert review["packet"]["meta"]["state"] == "reviewed"


def test_handoff_packet_patch_cannot_mark_reviewed_without_review_summary():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_handoff_api_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        created = _post_json(
            f"http://127.0.0.1:{port}/api/handoff-packets",
            {
                "task_prompt": "Build a bounded handoff packet generator for MCP delegation.",
                "declared_files": ["src/copyclip/mcp_server.py"],
                "declared_modules": ["copyclip.mcp"],
            },
        )
        packet_id = created["packet"]["meta"]["packet_id"]

        _patch_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
            {"state": "approved_for_handoff"},
        )
        _patch_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
            {"state": "delegated"},
        )
        _patch_json(
            f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
            {"state": "change_received"},
        )

        try:
            _patch_json(
                f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}",
                {"state": "reviewed"},
            )
            raise AssertionError("expected reviewed patch without summary to fail")
        except HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            assert e.code == 409
            assert body["error"] == "review_summary_required"

        try:
            _get_json(f"http://127.0.0.1:{port}/api/handoff-packets/{packet_id}/review-summary")
            raise AssertionError("expected missing review summary to remain missing")
        except HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            assert e.code == 404
            assert body["error"] == "review_summary_not_found"
