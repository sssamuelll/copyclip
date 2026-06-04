from copyclip.intelligence.cuaderno.tool_catalog import build_tool_definitions, dispatch_tool


def test_tool_definitions_include_all_tools():
    tools = build_tool_definitions()
    names = {t["name"] for t in tools}
    assert names == {
        "list_dir", "read_file", "grep_symbols", "get_callers", "get_callees",
        "git_log", "git_blame", "git_diff", "find_tests", "get_module_graph",
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
