"""Hasn't been back (comprehension strategy ③) — the cuaderno's entry cue.

`build_entry_cue` picks the single most-overdue AI burst the human has NOT
returned to — LIVE-verified (the persisted snapshot only selects candidates; the
live build_last_contact verdict decides), and scoped to the snapshot's age so it
never claims a present-tense gap past what analysis witnessed. Silent when there
is nothing honest to surface. The FILE is stale, never the mind.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.pulso import build_entry_cue

NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def _conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    c.execute("INSERT INTO projects(id, root_path, name) VALUES(1,'/p','P')")
    return c


def _insight(c, path, days, *, updated_at="2026-06-30 11:00:00"):
    c.execute(
        "INSERT INTO analysis_file_insights"
        "(project_id, path, module, pulso_last_contact_days, updated_at) "
        "VALUES(1,?,?,?,?)",
        (path, "m", days, updated_at),
    )


def _commit(c, sha, date_iso, ai, path):
    c.execute(
        "INSERT INTO commits(project_id, sha, author, date, message, ai_attributed) "
        "VALUES(1,?,?,?,?,?)", (sha, "S", date_iso, "m", 1 if ai else 0))
    c.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) "
        "VALUES(1,?,?,0,0)", (sha, path))


def _burst_unreturned(c, path, burst="2026-02-01 10:00:00 +0000"):
    _commit(c, f"h-{path}", "2026-01-01 10:00:00 +0000", False, path)
    _commit(c, f"ai-{path}", burst, True, path)  # AI after human -> hasn't been back


def _burst_returned(c, path):
    _commit(c, f"ai-{path}", "2026-02-01 10:00:00 +0000", True, path)
    _commit(c, f"h2-{path}", "2026-03-01 10:00:00 +0000", False, path)  # human after burst


def test_picks_the_most_overdue_live_candidate():
    c = _conn()
    _insight(c, "src/cold.py", 395)
    _insight(c, "src/warm.py", 60)
    # cold: human long ago, AI burst after -> the human hasn't been back for a year
    _commit(c, "h-cold", "2025-06-01 10:00:00 +0000", False, "src/cold.py")
    _commit(c, "ai-cold", "2026-01-01 10:00:00 +0000", True, "src/cold.py")
    # warm: recent human contact, AI burst after -> a much shorter gap
    _commit(c, "h-warm", "2026-05-01 10:00:00 +0000", False, "src/warm.py")
    _commit(c, "ai-warm", "2026-06-01 10:00:00 +0000", True, "src/warm.py")
    cue = build_entry_cue(c, 1, now=NOW)
    assert cue["file_path"] == "src/cold.py"  # the longest human gap wins
    assert cue["last_contact_days"] > 300


def test_skips_a_file_the_human_returned_to_even_if_snapshot_says_otherwise():
    c = _conn()
    _insight(c, "src/back.py", 50)  # stale snapshot claims a 50-day gap
    _burst_returned(c, "src/back.py")  # but live: the human came back after the burst
    assert build_entry_cue(c, 1, now=NOW) is None


def test_silent_when_no_candidates():
    c = _conn()
    _insight(c, "src/x.py", None)  # NULL snapshot is not a candidate
    assert build_entry_cue(c, 1, now=NOW) is None


def test_carries_age_and_flags_stale_snapshot():
    c = _conn()
    old = (NOW - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    _insight(c, "src/cold.py", 100, updated_at=old)
    _burst_unreturned(c, "src/cold.py")
    cue = build_entry_cue(c, 1, now=NOW, stale_after_days=14)
    assert cue["analyzed_age_days"] >= 29
    assert cue["stale"] is True


def test_fresh_snapshot_is_not_stale():
    c = _conn()
    fresh = (NOW - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    _insight(c, "src/cold.py", 100, updated_at=fresh)
    _burst_unreturned(c, "src/cold.py")
    cue = build_entry_cue(c, 1, now=NOW, stale_after_days=14)
    assert cue["analyzed_age_days"] <= 3
    assert cue["stale"] is False


def test_missing_updated_at_does_not_overclaim_staleness():
    c = _conn()
    c.execute(
        "INSERT INTO analysis_file_insights"
        "(project_id, path, module, pulso_last_contact_days, updated_at) "
        "VALUES(1,?,?,?,NULL)", ("src/n.py", "m", 80))
    _burst_unreturned(c, "src/n.py")
    cue = build_entry_cue(c, 1, now=NOW)
    assert cue["analyzed_age_days"] is None
    assert cue["stale"] is False
