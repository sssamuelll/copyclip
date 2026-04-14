import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request

from copyclip.intelligence.cli import _maybe_handle_internal
from copyclip.intelligence.db import connect, init_schema, get_or_create_project, record_project_visit
from copyclip.intelligence.server import run_server


def _count_visits(root_path: str) -> int:
    conn = connect(root_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM project_visits").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


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


def _seed_project(conn, root_path: str) -> int:
    pid = get_or_create_project(conn, root_path, name="tmp")
    conn.execute("UPDATE projects SET story=? WHERE id=?", ("CopyClip is a local-first project intelligence control plane.", pid))
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-1", "samuel", "2026-04-14T18:00:00Z", "fix packaging and async test support"),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-1", "pyproject.toml", 10, 1),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "pyproject.toml", "high", "churn", "Packaging changed recently.", 80),
    )
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status) VALUES(?,?,?,?)",
        (pid, "Use bounded MCP handoffs", "Keep MCP changes bounded and testable.", "accepted"),
    )
    record_project_visit(conn, pid, visited_at="2026-04-13T12:00:00Z")
    conn.commit()
    return pid


def _seed_realistic_context_switch_project(conn, root_path: str) -> int:
    """Fixture simulating a project with time-separated activity for context‑switch testing."""
    pid = get_or_create_project(conn, root_path, name="demo")
    conn.execute("UPDATE projects SET story=? WHERE id=?", (
        "Demo project with recent changes, risks, and unresolved decisions.",
        pid,
    ))

    # Baseline visit: 7 days ago
    record_project_visit(conn, pid, visited_at="2026-04-07T12:00:00Z")

    # Recent commits (within last day)
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-recent-a", "alice", "2026-04-14T10:00:00Z", "feat: add new API endpoint"),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-recent-b", "bob", "2026-04-14T14:30:00Z", "refactor: simplify validation logic"),
    )
    # Old commit (outside baseline window)
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-old-c", "charlie", "2026-04-01T09:00:00Z", "initial setup"),
    )

    # File churn: high churn on file_a, medium on file_b, low on file_c
    for _ in range(5):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-recent-a", "src/api/endpoint.py", 20, 5),
        )
    for _ in range(2):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-recent-b", "src/validation.py", 12, 3),
        )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-old-c", "src/legacy.py", 5, 2),
    )

    # Risks: high risk on file_a, medium on file_b
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score, created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, "src/api/endpoint.py", "high", "complexity", "High churn and many edge cases.", 85, "2026-04-14T11:00:00Z"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score, created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, "src/validation.py", "medium", "test_gap", "Validation coverage is incomplete.", 60, "2026-04-14T15:00:00Z"),
    )

    # Decisions: accepted linked to file_a, proposed linked to file_b, unresolved without link
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Adopt new API pattern", "Use consistent error handling for new endpoints.", "accepted", "manual", "2026-04-13T10:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Refactor validation module", "Should we extract validation into a separate package?", "proposed", "manual", "2026-04-14T16:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Update documentation", "Need to update API docs after recent changes.", "unresolved", "manual", "2026-04-14T17:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 1, "file", "src/api/endpoint.py"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 2, "file", "src/validation.py"),
    )

    # Story snapshot (recent)
    import json as json_module
    conn.execute(
        "INSERT INTO story_snapshots(project_id, focus_areas_json, major_changes_json, open_questions_json, summary_json) VALUES(?,?,?,?,?)",
        (
            pid,
            json_module.dumps([{"area": "src/api/endpoint.py", "severity": "high", "kind": "complexity", "score": 85}]),
            json_module.dumps([{"sha": "sha-recent-a", "message": "feat: add new API endpoint"}]),
            json_module.dumps([{"decision_id": 2, "title": "Refactor validation module", "status": "proposed"}]),
            json_module.dumps({"files": 8, "commits": 3, "risks": 2}),
        ),
    )
    conn.commit()
    return pid



def test_reacquaintance_api_returns_structured_briefing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/reacquaintance?mode=last_seen")
        assert res["meta"]["baseline_mode"] == "last_seen"
        assert "project_refresher" in res
        assert "top_changes" in res
        assert "read_first" in res
        assert "evidence_index" in res
        assert _count_visits(root_path) == 2


def test_reacquaintance_api_does_not_consume_last_seen_baseline_on_refresh():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        first = _get_json(f"http://127.0.0.1:{port}/api/reacquaintance?mode=last_seen")
        second = _get_json(f"http://127.0.0.1:{port}/api/reacquaintance?mode=last_seen")

        assert [item["title"] for item in first["top_changes"]] == [item["title"] for item in second["top_changes"]]
        assert _count_visits(root_path) == 2


def test_report_reacquaint_outputs_human_readable_summary(capsys, tmp_path):
    root_path = str(tmp_path)
    conn = connect(root_path)
    init_schema(conn)
    _seed_project(conn, root_path)
    conn.close()

    handled = _maybe_handle_internal([
        "copyclip",
        "report",
        "--type",
        "reacquaint",
        "--path",
        root_path,
        "--mode",
        "last_seen",
    ])
    captured = capsys.readouterr()

    assert handled is True
    assert "Catch me up" in captured.out
    assert "Top changes" in captured.out
    assert "Read first" in captured.out
    assert _count_visits(root_path) == 2


def test_cli_report_does_not_create_second_reacquaintance_marker_after_api_visit(capsys, tmp_path):
    root_path = str(tmp_path)
    conn = connect(root_path)
    init_schema(conn)
    _seed_project(conn, root_path)
    conn.close()

    port = _free_port()
    th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
    th.start()
    _wait_port(port)

    _ = _get_json(f"http://127.0.0.1:{port}/api/reacquaintance?mode=last_seen")
    handled = _maybe_handle_internal([
        "copyclip",
        "report",
        "--type",
        "reacquaint",
        "--path",
        root_path,
        "--mode",
        "last_seen",
    ])
    captured = capsys.readouterr()

    assert handled is True
    assert "Catch me up" in captured.out
    assert _count_visits(root_path) == 2

def test_realistic_context_switch_api_end_to_end():
    """End‑to‑end smoke test for reacquaintance briefing with realistic context‑switch data."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        root_path = str(root.absolute())
        conn = connect(root_path)
        init_schema(conn)
        _seed_realistic_context_switch_project(conn, root_path)
        conn.close()

        port = _free_port()
        th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
        th.start()
        _wait_port(port)

        res = _get_json(f"http://127.0.0.1:{port}/api/reacquaintance?mode=last_seen")
        assert res["meta"]["baseline_mode"] == "last_seen"
        assert res["meta"]["confidence"] in {"low", "medium", "high"}
        assert "project_refresher" in res
        assert "top_changes" in res
        assert "read_first" in res
        assert "evidence_index" in res

        # Verify realistic ranking: top risk should be highest scored
        if res["top_risk"]:
            assert res["top_risk"]["area"] == "src/api/endpoint.py"
            assert res["top_risk"]["severity"] == "high"
            assert res["top_risk"]["score"] == 85

        # Verify recent commits appear, old commit does not
        commit_messages = [ch["title"] for ch in res["top_changes"]]
        assert any("add new API endpoint" in msg for msg in commit_messages)
        assert any("simplify validation logic" in msg for msg in commit_messages)
        assert not any("initial setup" in msg for msg in commit_messages)

        # Verify evidence linking
        evidence_map = {item["id"]: item for item in res["evidence_index"]}
        assert any(e["type"] == "commit" for e in evidence_map.values())
        assert any(e["type"] == "risk" for e in evidence_map.values())
        assert any(e["type"] == "decision" for e in evidence_map.values())

        # Verify at least one relevant decision is linked
        assert len(res["relevant_decisions"]) > 0
        for d in res["relevant_decisions"]:
            assert d["evidence"]
            assert d["why_now"]

        # Verify open questions derived from unresolved/proposed decisions
        assert len(res["open_questions"]) > 0
        for q in res["open_questions"]:
            assert q["derived_from"]
            assert q["next_step"]

