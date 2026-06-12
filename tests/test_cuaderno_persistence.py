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
        "(session_id, position, question, frame_json, bookmarked, answer_check, created_at) "
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
    set_bookmark, set_answer_check,
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


def test_set_bookmark_and_answer_check():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[]))
    set_bookmark(conn, sid, 1, True)
    set_answer_check(conn, sid, 1, "answers")
    q = get_question_by_position(conn, sid, 1)
    assert q["bookmarked"] is True
    assert q["answer_check"] == "answers"


def test_answer_check_judges_the_artifact_not_the_mind():
    """The mark judges whether the ANSWER addressed the question ('answers' |
    'not_yet'), never a mind-state. The old mind-verdicts ('got'/'didnt') are
    rejected — they were the W4-3-class comprehension claim Axiom-0 forbade."""
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[]))
    for ok in ("answers", "not_yet", None):
        set_answer_check(conn, sid, 1, ok)
    for bad in ("got", "didnt", "understood"):
        try:
            set_answer_check(conn, sid, 1, bad)
            assert False, f"{bad!r} must be rejected"
        except ValueError:
            pass


def test_migration_renames_got_it_and_translates_values():
    """An existing DB carrying the old mind-scoped got_it column migrates to
    answer_check, translating 'got'->'answers' and 'didnt'->'not_yet' so no
    human's marks are lost when the doctrine breach is repaired."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE cuaderno_sessions(id TEXT PRIMARY KEY, project_root TEXT NOT NULL,"
        " created_at TEXT NOT NULL, last_seen_at TEXT);"
        "CREATE TABLE cuaderno_questions(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,"
        " position INTEGER NOT NULL, question TEXT NOT NULL, frame_json TEXT NOT NULL,"
        " bookmarked INTEGER NOT NULL DEFAULT 0, got_it TEXT, created_at TEXT NOT NULL,"
        " UNIQUE(session_id, position));"
    )
    conn.execute("INSERT INTO cuaderno_sessions(id,project_root,created_at) VALUES('s','/p','t')")
    conn.execute("INSERT INTO cuaderno_questions(session_id,position,question,frame_json,"
                 "bookmarked,got_it,created_at) VALUES('s',1,'q','{}',0,'got','t')")
    conn.execute("INSERT INTO cuaderno_questions(session_id,position,question,frame_json,"
                 "bookmarked,got_it,created_at) VALUES('s',2,'q','{}',0,'didnt','t')")
    conn.execute("INSERT INTO cuaderno_questions(session_id,position,question,frame_json,"
                 "bookmarked,got_it,created_at) VALUES('s',3,'q','{}',0,NULL,'t')")
    conn.commit()

    init_cuaderno_schema(conn)  # must migrate in place

    cols = {r[1] for r in conn.execute("PRAGMA table_info(cuaderno_questions)").fetchall()}
    assert "answer_check" in cols and "got_it" not in cols
    vals = [r[0] for r in conn.execute(
        "SELECT answer_check FROM cuaderno_questions ORDER BY position").fetchall()]
    assert vals == ["answers", "not_yet", None]
