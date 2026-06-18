"""Pulso v0.2.1 — "Last visit".

A ratified decision touching a file (decision_history action='status_change' via a
DIRECT decision_refs file link) is the strongest witness act the cuaderno records
(an authoring write over the human's own ledger, already timestamped). It counts
as the human RETURNING to a file — a second dated contact clock beside git. It
proves return/review, NEVER comprehension. Silence rules unchanged.
"""
import sqlite3
from datetime import datetime, timezone

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.pulso import build_last_contact, _last_ratified_decision

NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def _conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    c.execute("INSERT INTO projects(id, root_path, name) VALUES(1,'/p','P')")
    return c


def _commit(c, sha, date_iso, ai, path):
    c.execute("INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) VALUES(1,?,?,?,?,?)", (sha, "S", date_iso, "m", 1 if ai else 0))
    c.execute("INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(1,?,?,0,0)", (sha, path))


def _ratify(c, decision_id, path, when, *, action="status_change", with_ref=True):
    c.execute("INSERT OR IGNORE INTO decisions(id,project_id,title,summary,status) VALUES(?,1,'D','x','accepted')", (decision_id,))
    if with_ref:
        c.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,'file',?)", (decision_id, path))
    c.execute("INSERT INTO decision_history(decision_id,action,from_status,to_status,note,created_at) VALUES(?,?,?,?,?,?)", (decision_id, action, "proposed", "accepted", "n", when))


def test_reads_human_status_change_via_direct_ref():
    c = _conn()
    _ratify(c, 1, "src/a.py", "2026-03-01 12:00:00")
    dt = _last_ratified_decision(c, 1, "src/a.py")
    assert dt is not None and (dt.year, dt.month) == (2026, 3)


def test_ignores_system_actions_and_unlinked_decisions():
    c = _conn()
    _ratify(c, 1, "src/a.py", "2026-03-01 12:00:00", action="created")  # system action
    assert _last_ratified_decision(c, 1, "src/a.py") is None
    _ratify(c, 2, "src/a.py", "2026-04-01 12:00:00", with_ref=False)    # no direct file ref
    assert _last_ratified_decision(c, 1, "src/a.py") is None


def test_ratification_after_burst_breaks_the_silence():
    c = _conn()
    _commit(c, "ai", "2026-02-01 10:00:00 +0000", True, "src/a.py")
    _ratify(c, 1, "src/a.py", "2026-03-01 12:00:00")  # reviewed after the burst
    assert build_last_contact(c, 1, "src/a.py", now=NOW) is None  # current via review


def test_ratification_is_the_latest_contact_when_git_is_older():
    c = _conn()
    _commit(c, "h", "2026-01-01 12:00:00 +0000", False, "src/a.py")   # human commit Jan
    _ratify(c, 1, "src/a.py", "2026-02-01 12:00:00")                  # ratified Feb (later)
    _commit(c, "ai", "2026-06-01 12:00:00 +0000", True, "src/a.py")   # AI burst Jun
    res = build_last_contact(c, 1, "src/a.py", now=NOW)
    assert res is not None
    assert res["last_contact_source"] == "decision"
    assert res["last_contact_days"] == 149   # since 2026-02-01
    assert res["reviewed_days"] == 149


def test_git_is_the_source_when_no_review():
    c = _conn()
    _commit(c, "h", "2026-01-01 12:00:00 +0000", False, "src/a.py")
    _commit(c, "ai", "2026-06-01 12:00:00 +0000", True, "src/a.py")
    res = build_last_contact(c, 1, "src/a.py", now=NOW)
    assert res["last_contact_source"] == "git"
    assert res["reviewed_days"] is None
