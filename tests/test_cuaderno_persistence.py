import sqlite3
from copyclip.intelligence.db import init_cuaderno_schema


def test_init_cuaderno_schema_creates_tables():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)

    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "cuaderno_sessions" in tables
    assert "cuaderno_questions" in tables


def test_init_cuaderno_schema_is_idempotent():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)
    init_cuaderno_schema(conn)  # second call must not raise

    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "cuaderno_sessions" in tables


def test_cuaderno_questions_links_to_session():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)

    conn.execute(
        "INSERT INTO cuaderno_sessions(id, project_root, created_at) VALUES(?,?,?)",
        ("s1", "/tmp/proj", "2026-05-28T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO cuaderno_questions"
        "(session_id, position, question, frame_json, bookmarked, got_it, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("s1", 1, "what?", '{"question":"what?","blocks":[]}', 0, None, "2026-05-28T00:00:01Z"),
    )
    conn.commit()

    row = conn.execute(
        "SELECT session_id, position FROM cuaderno_questions WHERE session_id=?", ("s1",)
    ).fetchone()
    assert row == ("s1", 1)
