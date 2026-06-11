"""Pulso PR-P2: the "Last contact" atom.

days since a human last touched a file AFTER the most recent AI-attributed
(Co-Authored-By) commit. Silent (None, not 0) when there is no AI burst, or when
the human has already returned since the last burst. Recency only — never a
comprehension claim.
"""
import sqlite3
from datetime import datetime, timezone

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.pulso import build_last_contact

NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def _seed(conn):
    conn.execute("INSERT INTO projects(id, root_path, name) VALUES(1,'/p','P')")


def _commit(conn, sha, date_iso, ai, path):
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message, ai_attributed) VALUES(1,?,?,?,?,?)",
        (sha, "Samuel", date_iso, "msg", 1 if ai else 0),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(1,?,?,0,0)",
        (sha, path),
    )


def _conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    _seed(c)
    return c


def test_no_ai_burst_is_silent():
    c = _conn()
    _commit(c, "h1", "2026-06-01 10:00:00 +0000", False, "src/a.py")
    assert build_last_contact(c, 1, "src/a.py", now=NOW) is None


def test_human_returned_after_burst_is_silent():
    # AI burst on the 1st, human came back on the 10th -> current, nothing to track.
    c = _conn()
    _commit(c, "ai1", "2026-06-01 10:00:00 +0000", True, "src/a.py")
    _commit(c, "h1", "2026-06-10 10:00:00 +0000", False, "src/a.py")
    assert build_last_contact(c, 1, "src/a.py", now=NOW) is None


def test_burst_after_last_human_touch_reports_gap():
    # Human touched on the 1st, AI burst on the 20th, human hasn't returned.
    c = _conn()
    _commit(c, "h1", "2026-06-01 12:00:00 +0000", False, "src/a.py")
    _commit(c, "ai1", "2026-06-20 12:00:00 +0000", True, "src/a.py")
    res = build_last_contact(c, 1, "src/a.py", now=NOW)
    assert res is not None
    assert res["last_contact_days"] == 29  # since 2026-06-01
    assert res["ai_burst_days"] == 10      # since 2026-06-20
    assert res["never_human_touched"] is False


def test_never_human_touched_file_reports_since_burst():
    # Only AI ever touched it -> the strongest leak; contact measured since burst.
    c = _conn()
    _commit(c, "ai1", "2026-06-20 12:00:00 +0000", True, "src/gen.py")
    res = build_last_contact(c, 1, "src/gen.py", now=NOW)
    assert res is not None
    assert res["never_human_touched"] is True
    assert res["last_contact_days"] == 10
    assert res["ai_burst_days"] == 10


def test_persist_writes_nullable_column():
    from copyclip.intelligence.analyzer import _persist_last_contact

    c = _conn()
    # one file with an open burst-gap, one with no burst (must persist NULL).
    for p in ("src/a.py", "src/b.py"):
        c.execute("INSERT INTO analysis_file_insights(project_id, path, module) VALUES(1,?,?)", (p, "m"))
    _commit(c, "h1", "2024-01-01 12:00:00 +0000", False, "src/a.py")
    _commit(c, "ai1", "2024-02-01 12:00:00 +0000", True, "src/a.py")
    _commit(c, "h2", "2024-01-01 12:00:00 +0000", False, "src/b.py")  # no burst on b
    _persist_last_contact(c, 1)
    a = c.execute("SELECT pulso_last_contact_days FROM analysis_file_insights WHERE path='src/a.py'").fetchone()[0]
    b = c.execute("SELECT pulso_last_contact_days FROM analysis_file_insights WHERE path='src/b.py'").fetchone()[0]
    assert a is not None and a > 0   # open gap recorded
    assert b is None                 # absence persists as NULL, never 0
