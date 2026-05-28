import sqlite3
import subprocess
import tempfile
from pathlib import Path

from copyclip.intelligence.cuaderno.anchor import (
    git_blame,
    git_diff,
    git_log,
    grep_symbols,
    read_file,
)
from copyclip.intelligence.db import init_schema


def test_read_file_returns_lines_with_numbers(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = read_file(str(tmp_path), "src/foo.py")
    assert out["path"] == "src/foo.py"
    assert out["lines"] == [
        {"n": 1, "text": "a"},
        {"n": 2, "text": "b"},
        {"n": 3, "text": "c"},
        {"n": 4, "text": "d"},
        {"n": 5, "text": "e"},
    ]


def test_read_file_with_line_range_slices(tmp_path: Path):
    (tmp_path / "x.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = read_file(str(tmp_path), "x.py", line_start=2, line_end=4)
    assert [r["n"] for r in out["lines"]] == [2, 3, 4]
    assert [r["text"] for r in out["lines"]] == ["b", "c", "d"]


def test_read_file_rejects_path_escaping_root(tmp_path: Path):
    (tmp_path / "x.py").write_text("hi", encoding="utf-8")
    out = read_file(str(tmp_path), "../etc/passwd")
    assert out == {"error": "path_outside_root"}


def test_read_file_missing(tmp_path: Path):
    out = read_file(str(tmp_path), "nope.py")
    assert out == {"error": "file_not_found", "path": "nope.py"}


def _seed_symbols(conn, project_id, rows):
    for r in rows:
        conn.execute(
            "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (project_id, r["name"], r["kind"], r["file_path"],
             r.get("line_start", 1), r.get("line_end", 10),
             None, r.get("module", "x")),
        )
    conn.commit()


def test_grep_symbols_by_name(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_symbols(conn, pid, [
        {"name": "foo", "kind": "function", "file_path": "src/a.py"},
        {"name": "foo", "kind": "method", "file_path": "src/b.py"},
        {"name": "bar", "kind": "function", "file_path": "src/c.py"},
    ])

    out = grep_symbols(conn, pid, name="foo")
    assert sorted(r["file_path"] for r in out["symbols"]) == ["src/a.py", "src/b.py"]


def test_grep_symbols_by_kind(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_symbols(conn, pid, [
        {"name": "x", "kind": "class", "file_path": "src/a.py"},
        {"name": "y", "kind": "function", "file_path": "src/b.py"},
    ])

    out = grep_symbols(conn, pid, kind="class")
    assert [r["name"] for r in out["symbols"]] == ["x"]


def test_grep_symbols_limit(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_symbols(conn, pid, [
        {"name": f"sym{i}", "kind": "function", "file_path": f"src/{i}.py"} for i in range(20)
    ])

    out = grep_symbols(conn, pid, limit=5)
    assert len(out["symbols"]) == 5


from copyclip.intelligence.cuaderno.anchor import get_callers, get_callees


def _seed_edges(conn, pid, edges):
    """edges: list of (caller_name, callee_name, kind)"""
    name_to_id = {}
    for name, kind in {(e[0], "function") for e in edges} | {(e[1], "function") for e in edges}:
        if name not in name_to_id:
            cur = conn.execute(
                "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (pid, name, kind, f"src/{name}.py", 1, 5, None, "x"),
            )
            name_to_id[name] = cur.lastrowid
    for caller, callee, edge_kind in edges:
        conn.execute(
            "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
            "VALUES(?,?,?,?)",
            (pid, name_to_id[caller], name_to_id[callee], edge_kind),
        )
    conn.commit()
    return name_to_id


def test_get_callers_returns_call_sites(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_edges(conn, pid, [("foo", "bar", "calls"), ("baz", "bar", "calls")])

    out = get_callers(conn, pid, "bar")
    assert sorted(c["name"] for c in out["callers"]) == ["baz", "foo"]


def test_get_callees_returns_outgoing_calls(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_edges(conn, pid, [("foo", "bar", "calls"), ("foo", "baz", "calls")])

    out = get_callees(conn, pid, "foo")
    assert sorted(c["name"] for c in out["callees"]) == ["bar", "baz"]


def _git(cwd: Path, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_git_log_returns_commits(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name",  "t")
    (tmp_path / "a.txt").write_text("1")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    (tmp_path / "a.txt").write_text("2")
    _git(tmp_path, "commit", "-am", "second")

    out = git_log(str(tmp_path), limit=10)
    msgs = [c["message"] for c in out["commits"]]
    assert "first" in msgs and "second" in msgs


def test_git_blame_returns_sha_for_lines(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name",  "t")
    (tmp_path / "a.txt").write_text("line1\nline2\nline3\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "init")

    out = git_blame(str(tmp_path), "a.txt", line_start=1, line_end=3)
    assert all(len(b["commit"]) >= 7 for b in out["blame"])
    assert len(out["blame"]) == 3
