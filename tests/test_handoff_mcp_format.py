from copyclip.intelligence.db import connect, init_schema, get_or_create_project
from copyclip.intelligence.handoff import (
    build_handoff_packet,
    format_handoff_packet_for_mcp,
)


def _seed(conn, root: str) -> int:
    pid = get_or_create_project(conn, root, name="copyclip")
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Use bounded MCP handoff packets", "Delegation should use bounded packets.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/mcp_server.py"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "python", 1200, 1.0, "h-mcp"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery can bypass bounded delegation.", 93),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0),
    )
    conn.commit()
    return pid


def test_format_mcp_packet_exposes_only_bounded_agent_fields(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Build bounded MCP delegation.",
        declared_files=["src/copyclip/mcp_server.py"],
        do_not_touch=[{"target": "frontend", "reason": "UI excluded.", "severity": "hard_boundary"}],
        acceptance_criteria=["Stay bounded."],
        delegation_target="claude-code",
        generated_at="2026-04-20T10:00:00Z",
    )
    # add private-looking data the MCP view must not expose
    packet["notes"] = ["internal reviewer note"]
    packet["meta"]["approved_by"] = "samuel"

    bounded = format_handoff_packet_for_mcp(packet)
    conn.close()

    assert set(bounded["meta"].keys()) <= {"packet_id", "state", "updated_at", "delegation_target", "packet_version"}
    assert "approved_by" not in bounded["meta"]
    assert "evidence_index" not in bounded
    assert "bundle_manifest" not in bounded
    assert "notes" not in bounded

    # agent-facing fields exist
    assert bounded["objective"]["summary"] == "Build bounded MCP delegation."
    assert bounded["agent_consumable_packet"]["allowed_write_scope"] == ["src/copyclip/mcp_server.py"]
    assert "frontend" in bounded["agent_consumable_packet"]["do_not_touch"]
    assert bounded["constraints_summary"]
    assert any("MCP" in line or "bounded" in line.lower() for line in bounded["constraints_summary"])
    assert bounded["risk_summary"]
    assert any("intent_drift" in line for line in bounded["risk_summary"])
    assert isinstance(bounded["questions_to_clarify"], list)
    assert isinstance(bounded["acceptance_criteria"], list)
    assert "Stay bounded." in bounded["acceptance_criteria"]


def test_format_mcp_packet_blocks_consumption_when_packet_not_ready(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Still drafting.",
        declared_files=[],
        declared_modules=[],
    )
    conn.close()
    assert packet["meta"]["state"] == "draft"

    bounded = format_handoff_packet_for_mcp(packet)
    assert bounded["meta"]["state"] == "draft"
    assert bounded["agent_ready"] is False
    assert "not_ready_for_consumption" in bounded["warnings"]


def test_format_mcp_packet_marks_ready_when_approved_or_delegated(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Approved.",
        declared_files=["src/copyclip/mcp_server.py"],
        acceptance_criteria=["OK."],
        generated_at="2026-04-20T10:00:00Z",
    )
    conn.close()

    packet["meta"]["state"] = "approved_for_handoff"
    bounded_approved = format_handoff_packet_for_mcp(packet)
    assert bounded_approved["agent_ready"] is True
    assert bounded_approved["warnings"] == []

    packet["meta"]["state"] = "delegated"
    bounded_delegated = format_handoff_packet_for_mcp(packet)
    assert bounded_delegated["agent_ready"] is True
