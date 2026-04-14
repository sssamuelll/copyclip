from datetime import datetime, timezone

from copyclip.intelligence.db import (
    connect,
    init_schema,
    get_or_create_project,
    record_project_visit,
    create_reentry_checkpoint,
    get_reentry_baseline,
)


def test_reentry_schema_tables_exist(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)

    visit_cols = {r[1] for r in conn.execute("PRAGMA table_info(project_visits)").fetchall()}
    checkpoint_cols = {r[1] for r in conn.execute("PRAGMA table_info(reentry_checkpoints)").fetchall()}
    conn.close()

    assert {"project_id", "visit_kind", "visited_at"}.issubset(visit_cols)
    assert {"project_id", "name", "checkpoint_at", "notes"}.issubset(checkpoint_cols)


def test_record_project_visit_and_last_seen_baseline(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root)

    record_project_visit(conn, pid, visited_at="2026-04-10T09:00:00Z")
    record_project_visit(conn, pid, visited_at="2026-04-14T18:30:00Z")

    baseline = get_reentry_baseline(conn, pid, mode="last_seen")
    conn.close()

    assert baseline["mode"] == "last_seen"
    assert baseline["available"] is True
    assert baseline["started_at"] == "2026-04-14T18:30:00Z"


def test_last_seen_ignores_recent_reacquaintance_session_marker(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root)

    record_project_visit(conn, pid, visit_kind="dashboard_open", visited_at="2026-04-10T09:00:00Z")
    recent = datetime.now(timezone.utc).isoformat()
    record_project_visit(conn, pid, visit_kind="reacquaintance_api", visited_at=recent)

    baseline = get_reentry_baseline(conn, pid, mode="last_seen")
    conn.close()

    assert baseline["mode"] == "last_seen"
    assert baseline["available"] is True
    assert baseline["started_at"] == "2026-04-10T09:00:00Z"


def test_last_seen_ignores_multiple_recent_reacquaintance_markers(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root)

    record_project_visit(conn, pid, visit_kind="dashboard_open", visited_at="2026-04-10T09:00:00Z")
    recent = datetime.now(timezone.utc).isoformat()
    record_project_visit(conn, pid, visit_kind="reacquaintance_api", visited_at=recent)
    record_project_visit(conn, pid, visit_kind="reacquaintance_cli", visited_at=recent)
    record_project_visit(conn, pid, visit_kind="reacquaintance_open", visited_at=recent)

    baseline = get_reentry_baseline(conn, pid, mode="last_seen")
    conn.close()

    assert baseline["mode"] == "last_seen"
    assert baseline["available"] is True
    assert baseline["started_at"] == "2026-04-10T09:00:00Z"


def test_checkpoint_baseline_returns_named_checkpoint(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root)

    create_reentry_checkpoint(conn, pid, name="post-release", checkpoint_at="2026-04-12T12:00:00Z", notes="after shipping v0.4.0")

    baseline = get_reentry_baseline(conn, pid, mode="checkpoint", checkpoint_name="post-release")
    conn.close()

    assert baseline["mode"] == "checkpoint"
    assert baseline["available"] is True
    assert baseline["label"] == "checkpoint:post-release"
    assert baseline["started_at"] == "2026-04-12T12:00:00Z"


def test_window_baseline_is_synthetic_but_available(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root)

    baseline = get_reentry_baseline(conn, pid, mode="window", window="7d")
    conn.close()

    assert baseline["mode"] == "window"
    assert baseline["available"] is True
    assert baseline["label"] == "window:7d"
    assert baseline["started_at"] is not None


def test_last_seen_falls_back_to_last_analysis_then_window(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root)

    conn.execute(
        "INSERT INTO analysis_jobs(id, project_id, status, phase, started_at, finished_at) VALUES(?,?,?,?,?,?)",
        ("job-1", pid, "completed", "snapshots", "2026-04-13T11:00:00Z", "2026-04-13T11:05:00Z"),
    )
    conn.commit()

    baseline = get_reentry_baseline(conn, pid, mode="last_seen")
    assert baseline["mode"] == "last_analysis"
    assert baseline["available"] is True
    assert baseline["started_at"] == "2026-04-13T11:05:00Z"

    conn.execute("DELETE FROM analysis_jobs WHERE project_id=?", (pid,))
    conn.commit()

    baseline = get_reentry_baseline(conn, pid, mode="last_seen")
    conn.close()

    assert baseline["mode"] == "window"
    assert baseline["available"] is True
    assert baseline["label"] == "window:7d"
