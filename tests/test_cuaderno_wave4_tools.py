"""Wave 4 (PR-W4-1) — tutor tools that absorb the dashboard's question-classes
without fabrication. Every test seeds real data (sqlite :memory:, real git
repos) and asserts the tool's output comes from that data, never the model.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from copyclip.intelligence.db import init_schema


def _project(conn: sqlite3.Connection, root: str = "/tmp/proj") -> int:
    cur = conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    return int(cur.lastrowid)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ── get_decisions ──────────────────────────────────────────────────────────

def test_get_decisions_returns_ledger_rows():
    from copyclip.intelligence.cuaderno.anchor import get_decisions
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Use marimo", "reactive notebook", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id,title,status,source_type) VALUES(?,?,?,?)",
        (pid, "Drop Jupyter", "proposed", "agent"),
    )
    conn.commit()

    out = get_decisions(conn, pid)
    by_title = {d["title"]: d for d in out["decisions"]}
    assert set(by_title) == {"Use marimo", "Drop Jupyter"}
    assert by_title["Use marimo"]["status"] == "accepted"
    assert by_title["Use marimo"]["summary"] == "reactive notebook"
    assert by_title["Use marimo"]["source_type"] == "manual"


def test_get_decisions_filters_by_status():
    from copyclip.intelligence.cuaderno.anchor import get_decisions
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    conn.execute("INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (pid, "A", "accepted"))
    conn.execute("INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (pid, "B", "proposed"))
    conn.commit()

    out = get_decisions(conn, pid, status="proposed")
    assert [d["title"] for d in out["decisions"]] == ["B"]


def test_get_decisions_scopes_to_project():
    from copyclip.intelligence.cuaderno.anchor import get_decisions
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn, "/tmp/a")
    other = _project(conn, "/tmp/b")
    conn.execute("INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (pid, "mine", "accepted"))
    conn.execute("INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (other, "theirs", "accepted"))
    conn.commit()

    out = get_decisions(conn, pid)
    assert [d["title"] for d in out["decisions"]] == ["mine"]


# ── get_story_snapshots ────────────────────────────────────────────────────

def test_get_story_snapshots_returns_parsed_snapshots():
    from copyclip.intelligence.cuaderno.anchor import get_story_snapshots
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    conn.execute(
        "INSERT INTO story_snapshots(project_id,generated_at,focus_areas_json,"
        "major_changes_json,open_questions_json,summary_json) VALUES(?,?,?,?,?,?)",
        (pid, "2026-06-01T00:00:00", json.dumps(["analyzer"]),
         json.dumps([{"area": "cuaderno"}]), json.dumps(["why?"]),
         json.dumps({"text": "shift"})),
    )
    conn.commit()

    out = get_story_snapshots(conn, pid)
    snap = out["snapshots"][0]
    assert snap["generated_at"] == "2026-06-01T00:00:00"
    assert snap["focus_areas"] == ["analyzer"]
    assert snap["major_changes"] == [{"area": "cuaderno"}]
    assert snap["open_questions"] == ["why?"]
    assert snap["summary"] == {"text": "shift"}


def test_get_story_snapshots_newest_first():
    from copyclip.intelligence.cuaderno.anchor import get_story_snapshots
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    for ts in ("2026-06-01T00:00:00", "2026-06-05T00:00:00"):
        conn.execute(
            "INSERT INTO story_snapshots(project_id,generated_at,summary_json) VALUES(?,?,?)",
            (pid, ts, json.dumps({"t": ts})),
        )
    conn.commit()

    out = get_story_snapshots(conn, pid)
    assert [s["generated_at"] for s in out["snapshots"]] == [
        "2026-06-05T00:00:00", "2026-06-01T00:00:00",
    ]


def test_get_story_snapshots_empty_degrades_explicitly():
    """Decision G: no analysis → say so, never invent a narrative."""
    from copyclip.intelligence.cuaderno.anchor import get_story_snapshots
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)

    out = get_story_snapshots(conn, pid)
    assert out["snapshots"] == []
    assert "note" in out and out["note"]


# ── get_reverse_dependents ─────────────────────────────────────────────────

def _seed_module(conn, pid, name, path_prefix):
    conn.execute(
        "INSERT INTO modules(project_id,name,path_prefix) VALUES(?,?,?)",
        (pid, name, path_prefix),
    )


def _seed_dep(conn, pid, frm, to):
    conn.execute(
        "INSERT INTO dependencies(project_id,from_module,to_module,edge_type) VALUES(?,?,?,?)",
        (pid, frm, to, "import"),
    )


def test_get_reverse_dependents_walks_transitively():
    from copyclip.intelligence.cuaderno.anchor import get_reverse_dependents
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    _seed_module(conn, pid, "core", "src/core/")
    _seed_module(conn, pid, "api", "src/api/")
    _seed_module(conn, pid, "cli", "src/cli/")
    _seed_dep(conn, pid, "api", "core")   # api depends on core
    _seed_dep(conn, pid, "cli", "api")    # cli depends on api
    conn.commit()

    out = get_reverse_dependents(conn, pid, "src/core/engine.py")
    assert out["target_module"] == "core"
    assert set(out["impacted_modules"]) == {"api", "cli"}


def test_get_reverse_dependents_unknown_path():
    from copyclip.intelligence.cuaderno.anchor import get_reverse_dependents
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    _seed_module(conn, pid, "core", "src/core/")
    conn.commit()

    out = get_reverse_dependents(conn, pid, "nowhere/x.py")
    assert out["target_module"] == "unknown"
    assert out["impacted_modules"] == []


def test_get_reverse_dependents_excludes_target_and_survives_cycles():
    from copyclip.intelligence.cuaderno.anchor import get_reverse_dependents
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn)
    _seed_module(conn, pid, "a", "src/a/")
    _seed_module(conn, pid, "b", "src/b/")
    _seed_dep(conn, pid, "a", "b")  # a -> b
    _seed_dep(conn, pid, "b", "a")  # b -> a (cycle)
    conn.commit()

    out = get_reverse_dependents(conn, pid, "src/a/x.py")
    assert out["target_module"] == "a"
    # b depends on a; a depends on b — cycle must not hang. b is impacted.
    assert set(out["impacted_modules"]) == {"b"}


# ── git_archaeology ────────────────────────────────────────────────────────

def _init_repo(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")


def test_git_archaeology_returns_commits_and_file_linked_decisions(tmp_path: Path):
    from copyclip.intelligence.cuaderno.anchor import git_archaeology
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("v1\n", encoding="utf-8")
    _git(tmp_path, "add", "src/foo.py")
    _git(tmp_path, "commit", "-m", "add foo")
    (tmp_path / "src" / "foo.py").write_text("v2\n", encoding="utf-8")
    _git(tmp_path, "commit", "-am", "change foo")

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn, str(tmp_path))
    cur = conn.execute(
        "INSERT INTO decisions(project_id,title,status,source_type) VALUES(?,?,?,?)",
        (pid, "Foo shape", "accepted", "manual"),
    )
    did = cur.lastrowid
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (did, "file", "src/foo.py"),
    )
    conn.commit()

    out = git_archaeology(str(tmp_path), conn, pid, "src/foo.py")
    assert out["file"] == "src/foo.py"
    assert [c["message"] for c in out["commits"]][:2] == ["change foo", "add foo"]
    titles = [d["title"] for d in out["related_decisions"]]
    assert "Foo shape" in titles
    d = next(d for d in out["related_decisions"] if d["title"] == "Foo shape")
    assert d["matched_refs"][0]["ref_type"] == "file"


def test_git_archaeology_matches_commit_ref(tmp_path: Path):
    from copyclip.intelligence.cuaderno.anchor import git_archaeology
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-m", "init a")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout.strip()

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn, str(tmp_path))
    cur = conn.execute(
        "INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (pid, "From commit", "accepted")
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (cur.lastrowid, "commit", sha[:8]),
    )
    conn.commit()

    out = git_archaeology(str(tmp_path), conn, pid, "a.py")
    assert [d["title"] for d in out["related_decisions"]] == ["From commit"]


def test_git_archaeology_ignores_unrelated_decisions(tmp_path: Path):
    from copyclip.intelligence.cuaderno.anchor import git_archaeology
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-m", "init")

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _project(conn, str(tmp_path))
    cur = conn.execute(
        "INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (pid, "Other file", "accepted")
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (cur.lastrowid, "file", "totally/other.py"),
    )
    conn.commit()

    out = git_archaeology(str(tmp_path), conn, pid, "a.py")
    assert out["related_decisions"] == []


# ── get_reacquaintance_briefing ────────────────────────────────────────────

def test_get_reacquaintance_briefing_runs_engine_and_keeps_burst_essentials(tmp_path: Path):
    """Wraps the real reacquaintance engine (no mock). With no analysis the
    engine returns its empty-but-valid shape; the tool keeps the re-entry
    essentials that reconnect the human across bursts."""
    from copyclip.intelligence.cuaderno.anchor import get_reacquaintance_briefing

    out = get_reacquaintance_briefing(str(tmp_path))
    assert {"meta", "top_changes", "read_first", "relevant_decisions"} <= set(out)
    assert isinstance(out["top_changes"], list)
    assert isinstance(out["read_first"], list)
    assert "project" in out["meta"]


def test_get_reacquaintance_briefing_trims_heavy_evidence_index(tmp_path: Path):
    """The evidence_index can be large; the tool trims it so the briefing fits
    the tutor's context window (decision A2)."""
    from copyclip.intelligence.cuaderno.anchor import get_reacquaintance_briefing

    out = get_reacquaintance_briefing(str(tmp_path))
    assert "evidence_index" not in out
