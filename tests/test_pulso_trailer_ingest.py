"""Pulso PR-P1: the Co-Authored-By trailer is the ONLY live AI-burst signal.

git-blame author is the dead W4-3 signal (Samuel commits AI work under his own
name -> 0/203). The trailer in the commit body distinguishes an AI burst. The
ingest must capture it; here we pin the detection logic and that the column the
metric will read actually exists.
"""
import sqlite3

from copyclip.intelligence.analyzer import _commit_is_ai_attributed
from copyclip.intelligence.db import init_schema


def test_detects_claude_coauthor_trailer():
    body = (
        "Add the thing.\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
    )
    assert _commit_is_ai_attributed(body) is True


def test_human_coauthor_is_not_ai_attributed():
    body = "Pair session.\n\nCo-authored-by: Jane Dev <jane@example.com>\n"
    assert _commit_is_ai_attributed(body) is False


def test_no_trailer_is_not_ai_attributed():
    assert _commit_is_ai_attributed("Just a plain commit message.") is False
    assert _commit_is_ai_attributed("") is False


def test_trailer_match_is_case_insensitive_and_anchored():
    # Real-world casing variance, and the word "claude" only counts inside a
    # Co-authored-by trailer line — not anywhere in the body.
    assert _commit_is_ai_attributed("x\n\nco-authored-by: CLAUDE <a@anthropic.com>") is True
    assert _commit_is_ai_attributed("I read the Claude docs today.") is False


def test_commits_table_has_ai_attributed_column():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(commits)").fetchall()}
    assert "ai_attributed" in cols
    conn.close()
