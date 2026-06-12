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
        "get_story_snapshots", "get_reacquaintance_briefing", "get_risks",
        "get_last_contact", "get_call_path", "get_rationale", "get_entry_cue",
        "get_blast_radius",
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


def test_dispatch_get_call_path(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    a = conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
        "VALUES(?,?,?,?,?,?)", (pid, "a", "function", "src/a.py", 1, 5)).lastrowid
    b = conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
        "VALUES(?,?,?,?,?,?)", (pid, "b", "function", "src/b.py", 1, 5)).lastrowid
    conn.execute(
        "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
        "VALUES(?,?,?,'calls')", (pid, a, b))
    conn.commit()
    out = dispatch_tool("get_call_path", {"symbol": "a"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert [h["symbol"] for h in out["hops"]] == ["a", "b"]
    assert out["kind"] == "static_call_slice"


def test_dispatch_get_blast_radius(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    x = conn.execute("INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
                     "VALUES(?,?,?,?,?,?)", (pid, "x", "function", "src/x.py", 1, 5)).lastrowid
    a = conn.execute("INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
                     "VALUES(?,?,?,?,?,?)", (pid, "a", "function", "src/a.py", 1, 5)).lastrowid
    conn.execute("INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
                 "VALUES(?,?,?,'calls')", (pid, a, x))
    conn.commit()
    out = dispatch_tool("get_blast_radius", {"symbol": "x"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert [c["name"] for c in out["direct_callers"]] == ["a"]
    assert out["kind"] == "static_blast_radius"


def test_dispatch_get_entry_cue(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    conn.execute("INSERT INTO analysis_file_insights"
                 "(project_id,path,module,pulso_last_contact_days) VALUES(?,?,?,?)",
                 (pid, "src/a.py", "m", 30))
    conn.execute("INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) "
                 "VALUES(?,?,?,?,?,0)", (pid, "h", "S", "2026-01-01 10:00:00 +0000", "m"))
    conn.execute("INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) "
                 "VALUES(?,?,?,?,?,1)", (pid, "ai", "S", "2026-02-01 10:00:00 +0000", "m"))
    for sha in ("h", "ai"):
        conn.execute("INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) "
                     "VALUES(?,?,?,0,0)", (pid, sha, "src/a.py"))
    conn.commit()
    out = dispatch_tool("get_entry_cue", {},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert out["entry_cue"]["file_path"] == "src/a.py"


def test_dispatch_get_rationale(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    conn.execute("INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) "
                 "VALUES(?,?,?,?,?,1)", (pid, "ai1", "S", "2026-01-01 00:00:00 +0000", "m"))
    conn.execute("INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) "
                 "VALUES(?,?,?,0,0)", (pid, "ai1", "src/a.py"))
    conn.commit()
    out = dispatch_tool("get_rationale", {"file": "src/a.py"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert out["verdict"] == "accepted_not_decided"
    assert out["ai_shaped"] is True


def test_dispatch_get_risks(tmp_path):
    conn, pid = _conn_with_project(tmp_path)
    conn.execute("INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
                 (pid, "x.py", "high", "churn", "r", 70))
    conn.commit()
    out = dispatch_tool("get_risks", {"kind": "churn"},
                        project_root=str(tmp_path), project_id=pid, conn=conn)
    assert [r["area"] for r in out["risks"]] == ["x.py"]
