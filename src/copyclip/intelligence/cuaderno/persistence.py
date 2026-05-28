from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from .schema import Frame, frame_to_dict, frame_from_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_session(conn: sqlite3.Connection, *, project_root: str) -> str:
    sid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO cuaderno_sessions(id, project_root, created_at, last_seen_at) "
        "VALUES(?,?,?,?)",
        (sid, project_root, _now(), _now()),
    )
    conn.commit()
    return sid


def save_question(
    conn: sqlite3.Connection, session_id: str, question: str, frame: Frame
) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(position), 0) FROM cuaderno_questions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    next_pos = int(row[0]) + 1
    conn.execute(
        "INSERT INTO cuaderno_questions"
        "(session_id, position, question, frame_json, bookmarked, got_it, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (session_id, next_pos, question, json.dumps(frame_to_dict(frame)), 0, None, _now()),
    )
    conn.execute(
        "UPDATE cuaderno_sessions SET last_seen_at=? WHERE id=?", (_now(), session_id)
    )
    conn.commit()
    return next_pos


def list_questions(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT position, question, frame_json, bookmarked, got_it, created_at "
        "FROM cuaderno_questions WHERE session_id=? ORDER BY position",
        (session_id,),
    ).fetchall()
    return [
        {
            "position": r[0],
            "question": r[1],
            "frame": json.loads(r[2]),
            "bookmarked": bool(r[3]),
            "got_it": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def get_question_by_position(
    conn: sqlite3.Connection, session_id: str, position: int
) -> Optional[dict]:
    row = conn.execute(
        "SELECT question, frame_json, bookmarked, got_it, created_at "
        "FROM cuaderno_questions WHERE session_id=? AND position=?",
        (session_id, position),
    ).fetchone()
    if not row:
        return None
    return {
        "position": position,
        "question": row[0],
        "frame": json.loads(row[1]),
        "bookmarked": bool(row[2]),
        "got_it": row[3],
        "created_at": row[4],
    }


def set_bookmark(
    conn: sqlite3.Connection, session_id: str, position: int, bookmarked: bool
) -> None:
    conn.execute(
        "UPDATE cuaderno_questions SET bookmarked=? WHERE session_id=? AND position=?",
        (1 if bookmarked else 0, session_id, position),
    )
    conn.commit()


def set_got_it(
    conn: sqlite3.Connection, session_id: str, position: int, value: Optional[str]
) -> None:
    """value: 'got' | 'didnt' | None to clear."""
    if value is not None and value not in {"got", "didnt"}:
        raise ValueError(f"got_it must be 'got', 'didnt', or None; got {value!r}")
    conn.execute(
        "UPDATE cuaderno_questions SET got_it=? WHERE session_id=? AND position=?",
        (value, session_id, position),
    )
    conn.commit()
