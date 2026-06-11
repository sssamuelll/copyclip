"""Pulso PR-P4: the honest surface — the get_last_contact tutor tool.

Lists files an AI burst last shaped that the human has not returned to, longest
gap first. Reads the persisted column (never blame). Silent files are absent,
not zero. Each row is citable by file_path. Recency only.
"""
import sqlite3

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.cuaderno.anchor import get_last_contact
from copyclip.intelligence.cuaderno.tool_catalog import dispatch_tool, build_tool_definitions


def _conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    c.execute("INSERT INTO projects(id, root_path, name) VALUES(1,'/p','P')")
    return c


def _file(c, path, last_contact_days):
    c.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, pulso_last_contact_days) VALUES(1,?,?,?)",
        (path, "m", last_contact_days),
    )


def _commit(c, sha, date_iso, ai, path):
    c.execute(
        "INSERT INTO commits(project_id, sha, author, date, message, ai_attributed) VALUES(1,?,?,?,?,?)",
        (sha, "Samuel", date_iso, "m", 1 if ai else 0),
    )
    c.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(1,?,?,0,0)",
        (sha, path),
    )


def test_lists_open_gaps_longest_first_and_excludes_silent():
    c = _conn()
    _file(c, "src/cold.py", 40)
    _file(c, "src/warm.py", 6)
    _file(c, "src/current.py", None)  # silent -> must NOT appear
    for p in ("src/cold.py", "src/warm.py"):
        _commit(c, f"h-{p}", "2026-01-01 10:00:00 +0000", False, p)
        _commit(c, f"ai-{p}", "2026-02-01 10:00:00 +0000", True, p)

    res = get_last_contact(c, 1, limit=10)
    items = res["last_contact"]

    paths = [it["file_path"] for it in items]
    assert paths == ["src/cold.py", "src/warm.py"]   # longest gap first, NULL excluded
    assert items[0]["last_contact_days"] == 40
    # the full honest detail is recomputed for the listed rows
    assert items[0]["ai_burst_days"] is not None
    assert items[0]["never_human_touched"] is False


def test_empty_when_nothing_to_report():
    c = _conn()
    _file(c, "src/current.py", None)
    assert get_last_contact(c, 1)["last_contact"] == []


def test_tool_is_registered_and_dispatches():
    names = {t["name"] for t in build_tool_definitions()}
    assert "get_last_contact" in names

    c = _conn()
    _file(c, "src/a.py", 12)
    _commit(c, "h", "2026-01-01 10:00:00 +0000", False, "src/a.py")
    _commit(c, "ai", "2026-02-01 10:00:00 +0000", True, "src/a.py")
    out = dispatch_tool("get_last_contact", {"limit": 5}, project_root="/p", conn=c, project_id=1)
    assert out["last_contact"][0]["file_path"] == "src/a.py"
