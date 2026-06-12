"""Accepted, not decided (comprehension strategy ②) — deterministic intent recovery.

`get_rationale` recovers the recorded deliberation behind a file (decisions that
reference it, directly or via a commit that touched it) and, when the ledger is
SILENT, returns a deterministic verdict + a constant stamp so a 'why' can never be
invented. Recovering recorded intent is not the human holding it; absence of a
decision over committed code is the signature of accepted-not-decided AI-burst work.
"""
import sqlite3

from copyclip.intelligence.cuaderno.anchor import get_rationale, ACCEPTED_NOT_DECIDED
from copyclip.intelligence.db import init_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    cur = conn.execute("INSERT INTO projects(root_path,name) VALUES('/p','P')")
    return conn, int(cur.lastrowid)


def _commit(conn, pid, sha, path, *, ai=False, msg="m", date="2026-01-01 00:00:00 +0000"):
    conn.execute(
        "INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) "
        "VALUES(?,?,?,?,?,?)", (pid, sha, "S", date, msg, 1 if ai else 0))
    conn.execute(
        "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) "
        "VALUES(?,?,?,0,0)", (pid, sha, path))


def _decision(conn, pid, title, ref_type, ref_value, *, status="accepted"):
    did = conn.execute(
        "INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)",
        (pid, title, status)).lastrowid
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (did, ref_type, ref_value))
    return int(did)


def test_recovers_direct_file_decision():
    conn, pid = _conn()
    _commit(conn, pid, "h1", "src/a.py")
    _decision(conn, pid, "Use X", "file", "src/a.py")
    out = get_rationale(conn, pid, "src/a.py")
    assert out["verdict"] == "recovered"
    assert out["has_recorded_rationale"] is True
    assert [d["title"] for d in out["decisions"]] == ["Use X"]
    assert out["decisions"][0]["matched_via"] == "file"
    assert out["stamp"] is None


def test_recovers_commit_linked_decision():
    conn, pid = _conn()
    _commit(conn, pid, "abc123def456", "src/a.py")
    _decision(conn, pid, "Refactor", "commit", "abc123d")  # short sha prefix
    out = get_rationale(conn, pid, "src/a.py")
    assert out["verdict"] == "recovered"
    assert out["decisions"][0]["matched_via"] == "commit"


def test_accepted_not_decided_when_no_decision():
    conn, pid = _conn()
    _commit(conn, pid, "ai1", "src/a.py", ai=True)
    out = get_rationale(conn, pid, "src/a.py")
    assert out["verdict"] == "accepted_not_decided"
    assert out["has_recorded_rationale"] is False
    assert out["stamp"] == ACCEPTED_NOT_DECIDED
    assert out["ai_shaped"] is True


def test_ai_shaped_is_false_for_human_only_commits():
    conn, pid = _conn()
    _commit(conn, pid, "h1", "src/a.py", ai=False)
    out = get_rationale(conn, pid, "src/a.py")
    assert out["ai_shaped"] is False
    assert out["verdict"] == "accepted_not_decided"


def test_untracked_when_no_history_and_no_decision():
    conn, pid = _conn()
    out = get_rationale(conn, pid, "src/ghost.py")
    assert out["verdict"] == "untracked"
    assert out["stamp"] is None
    assert out["commits"] == [] and out["decisions"] == []


def test_decision_without_commits_is_still_recovered():
    conn, pid = _conn()
    _decision(conn, pid, "Plan Y", "file", "src/new.py")  # decided, not yet committed
    out = get_rationale(conn, pid, "src/new.py")
    assert out["verdict"] == "recovered"


def test_stamp_is_the_exact_benchmark_phrasing():
    # a regression lock: the signature sentence of the product must not drift
    assert ACCEPTED_NOT_DECIDED == "no recorded rationale; this was accepted, not decided."


def test_commits_are_cited_by_sha():
    conn, pid = _conn()
    _commit(conn, pid, "deadbeefcafe", "src/a.py", msg="init")
    out = get_rationale(conn, pid, "src/a.py")
    assert out["commits"][0]["sha"].startswith("deadbeef")
    assert out["commits"][0]["message"] == "init"
