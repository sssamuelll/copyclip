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


import json
from copyclip.intelligence.cuaderno.persistence import (
    create_session, save_question, list_questions, get_question_by_position,
    set_bookmark, set_got_it,
)
from copyclip.intelligence.cuaderno.schema import Frame, Block, frame_to_dict


def _conn():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)
    return conn


def test_create_session_returns_id_and_persists():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    assert isinstance(sid, str) and len(sid) > 0
    row = conn.execute(
        "SELECT project_root FROM cuaderno_sessions WHERE id=?", (sid,)
    ).fetchone()
    assert row[0] == "/tmp/proj"


def test_save_question_assigns_position_starting_at_1():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    frame = Frame(question="q1", blocks=[Block.lead("hi")])
    pos1 = save_question(conn, sid, "q1", frame)
    pos2 = save_question(conn, sid, "q2", Frame(question="q2", blocks=[]))
    assert pos1 == 1
    assert pos2 == 2


def test_list_questions_returns_in_order():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[]))
    save_question(conn, sid, "q2", Frame(question="q2", blocks=[]))
    rows = list_questions(conn, sid)
    assert [r["position"] for r in rows] == [1, 2]
    assert [r["question"] for r in rows] == ["q1", "q2"]


def test_get_question_by_position_reconstructs_frame():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[Block.lead("hello")]))
    q = get_question_by_position(conn, sid, 1)
    assert q is not None
    assert q["question"] == "q1"
    assert q["frame"]["blocks"][0]["kind"] == "lead"


def test_set_bookmark_and_got_it():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[]))
    set_bookmark(conn, sid, 1, True)
    set_got_it(conn, sid, 1, "got")
    q = get_question_by_position(conn, sid, 1)
    assert q["bookmarked"] is True
    assert q["got_it"] == "got"
