import sqlite3

from copyclip.intelligence.cuaderno.tool_catalog import build_tool_definitions, dispatch_tool
from copyclip.intelligence.db import init_schema


def test_tool_definitions_include_all_tools():
    tools = build_tool_definitions()
    names = {t["name"] for t in tools}
    assert names == {
        "list_dir", "read_file", "grep_symbols", "get_callers", "get_callees",
        "git_log", "git_blame", "git_diff", "find_tests", "get_module_graph",
        "get_decisions", "get_reverse_dependents", "git_archaeology",
        "get_story_snapshots", "get_reacquaintance_briefing",
        "emit_block", "finish",
    }


def test_dispatch_list_dir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    out = dispatch_tool("list_dir", {"path": "."}, project_root=str(tmp_path),
                        project_id=1, conn=None)
    names = [e["name"] for e in out["entries"]]
    assert names == ["src", "a.txt"]


def test_dispatch_list_dir_defaults_path(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    out = dispatch_tool("list_dir", {}, project_root=str(tmp_path),
                        project_id=1, conn=None)
    assert {"name": "a.txt", "type": "file"} in out["entries"]


def test_emit_block_requires_kind():
    tools = build_tool_definitions()
    emit = next(t for t in tools if t["name"] == "emit_block")
    assert emit["input_schema"]["required"] == ["kind"]
    assert emit["input_schema"]["additionalProperties"] is True


def test_answer_tools_set():
    from copyclip.intelligence.cuaderno.tool_catalog import ANSWER_TOOLS
    assert ANSWER_TOOLS == {"emit_block", "finish"}


def test_tool_definitions_have_anthropic_shape():
    tools = build_tool_definitions()
    for t in tools:
        assert "name" in t and "description" in t and "input_schema" in t
        assert t["input_schema"]["type"] == "object"
        assert "properties" in t["input_schema"]


def test_dispatch_unknown_tool_returns_error():
    out = dispatch_tool("nope", {}, project_root="/tmp", project_id=1, conn=None)
    assert out == {"error": "unknown_tool", "name": "nope"}


def _conn_with_project(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    cur = conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    return conn, int(cur.lastrowid)


def test_dispatch_get_decisions(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    conn.execute("INSERT INTO decisions(project_id,title,status) VALUES(?,?,?)", (pid, "D", "accepted"))
    conn.commit()
    out = dispatch_tool("get_decisions", {"status": "accepted"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert [d["title"] for d in out["decisions"]] == ["D"]


def test_dispatch_get_reverse_dependents(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    conn.execute("INSERT INTO modules(project_id,name,path_prefix) VALUES(?,?,?)", (pid, "core", "src/core/"))
    conn.execute("INSERT INTO modules(project_id,name,path_prefix) VALUES(?,?,?)", (pid, "api", "src/api/"))
    conn.execute("INSERT INTO dependencies(project_id,from_module,to_module,edge_type) VALUES(?,?,?,?)",
                 (pid, "api", "core", "import"))
    conn.commit()
    out = dispatch_tool("get_reverse_dependents", {"path": "src/core/x.py"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert out["target_module"] == "core"
    assert out["impacted_modules"] == ["api"]


def test_dispatch_get_story_snapshots(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    out = dispatch_tool("get_story_snapshots", {},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert out["snapshots"] == [] and "note" in out


def test_dispatch_git_archaeology(tmp_path):
    import subprocess
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    conn, pid = _conn_with_project(tmp_path)
    out = dispatch_tool("git_archaeology", {"file": "a.py"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert out["file"] == "a.py"
    assert [c["message"] for c in out["commits"]] == ["init"]


def test_dispatch_get_reacquaintance_briefing(tmp_path):
    out = dispatch_tool("get_reacquaintance_briefing", {},
                        project_root=str(tmp_path), project_id=1, conn=None)
    assert {"meta", "top_changes", "read_first"} <= set(out)
