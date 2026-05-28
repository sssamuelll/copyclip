import sqlite3
import tempfile
from pathlib import Path

from copyclip.intelligence.cuaderno.anchor import grep_symbols, read_file
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
