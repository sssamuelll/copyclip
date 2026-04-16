from copyclip.intelligence.db import connect, init_schema, get_or_create_project
from copyclip.intelligence.handoff import build_handoff_packet


def _seed_handoff_project(conn, root: str) -> int:
    pid = get_or_create_project(conn, root, name="copyclip")
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Use bounded MCP handoff packets", "Delegation should use inspectable bounded packets.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/mcp_server.py"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 1, "file", "src/copyclip/mcp_server.py"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "python", 1200, 1.0, "h-mcp"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/intelligence/server.py", "python", 2400, 1.0, "h-server"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "tests/test_mcp_intent_oracle.py", "python", 900, 1.0, "h-test"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/analytics/hotspot.py", "python", 900, 1.0, "h-hotspot"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery can bypass bounded delegation if widened carelessly.", 93),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-mcp", "src/copyclip/mcp_server.py", 30, 8),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/analytics/hotspot.py", "high", "complexity", "Hot unrelated area with high churn.", 99),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-hot", "src/copyclip/analytics/hotspot.py", 70, 20),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-mcp", "samuel", "2026-04-16T10:00:00Z", "tighten MCP handoff boundaries"),
    )
    conn.commit()
    return pid


def test_build_handoff_packet_includes_scope_decisions_risks_and_projection(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_handoff_project(conn, root)

    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Build a bounded handoff packet generator for MCP delegation.",
        declared_files=["src/copyclip/mcp_server.py"],
        declared_modules=["copyclip.mcp"],
        do_not_touch=[{"target": "frontend", "reason": "UI excluded for backend slice.", "severity": "hard_boundary"}],
        acceptance_criteria=["Packet includes scope, constraints, and review contract."],
    )
    conn.close()

    assert packet["meta"]["state"] == "ready_for_review"
    assert packet["meta"]["created_by"] == "human"
    assert packet["objective"]["task_type"] == "feature"
    assert packet["scope"]["declared_files"] == ["src/copyclip/mcp_server.py"]
    assert "copyclip.mcp" in packet["scope"]["declared_modules"]
    assert packet["relevant_decisions"]
    assert packet["relevant_decisions"][0]["title"] == "Use bounded MCP handoff packets"
    assert packet["constraints"]
    assert any(item["type"] == "architectural_decision" for item in packet["constraints"])
    assert packet["risk_dark_zones"]
    assert any(item["kind"] == "intent_drift" for item in packet["risk_dark_zones"])
    assert any(item["kind"] == "cognitive_debt" for item in packet["risk_dark_zones"])
    assert any(evidence_id.startswith("risk:debt:") for item in packet["risk_dark_zones"] for evidence_id in item["evidence"])
    assert packet["agent_consumable_packet"]["allowed_write_scope"] == ["src/copyclip/mcp_server.py"]
    assert "frontend" in packet["agent_consumable_packet"]["do_not_touch"]
    assert packet["review_contract"]["check_decision_conflicts"] is True
    assert packet["evidence_index"]
    assert any(item["id"] == "file:src/copyclip/mcp_server.py" for item in packet["evidence_index"])


def test_build_handoff_packet_generates_blocking_question_when_scope_is_missing(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_handoff_project(conn, root)

    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Help with safe delegation.",
        declared_files=[],
        declared_modules=[],
    )
    conn.close()

    assert packet["meta"]["state"] == "draft"
    assert packet["questions_to_clarify"]
    assert packet["questions_to_clarify"][0]["blocking"] is True
    assert packet["agent_consumable_packet"]["allowed_write_scope"] == []


def test_build_handoff_packet_expands_module_scope_into_allowed_write_scope(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_handoff_project(conn, root)

    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Tighten MCP delegation boundaries.",
        declared_files=[],
        declared_modules=["copyclip.mcp"],
    )
    conn.close()

    assert packet["meta"]["state"] == "ready_for_review"
    assert "src/copyclip/mcp_server.py" in packet["scope"]["declared_files"]
    assert "src/copyclip/mcp_server.py" in packet["agent_consumable_packet"]["allowed_write_scope"]


def test_build_handoff_packet_blocks_when_declared_module_cannot_resolve_to_files(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_handoff_project(conn, root)

    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Tighten unknown delegation boundaries.",
        declared_files=[],
        declared_modules=["copyclip.unknown"],
    )
    conn.close()

    assert packet["meta"]["state"] == "draft"
    assert packet["agent_consumable_packet"]["allowed_write_scope"] == []
    assert any(item["blocking"] for item in packet["questions_to_clarify"])
    assert any("did not resolve" in item["question"].lower() for item in packet["questions_to_clarify"])


def test_build_handoff_packet_backfills_supporting_files_from_context_and_decision_overlap(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_handoff_project(conn, root)

    packet = build_handoff_packet(
        conn,
        pid,
        task_prompt="Review MCP handoff boundaries and inspect related server paths.",
        declared_files=["src/copyclip/mcp_server.py"],
    )

    assert packet["scope"]["supporting_files"]
    assert "src/copyclip/mcp_server.py" not in packet["scope"]["supporting_files"]
    assert "src/copyclip/analytics/hotspot.py" not in packet["scope"]["supporting_files"]
    assert len(packet["scope"]["supporting_files"]) <= 5
    assert packet["scope"]["supporting_context_rationale"]

    conn.close()


def test_build_handoff_packet_is_deterministic_for_same_inputs_and_has_resolvable_evidence(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_handoff_project(conn, root)
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/intelligence/server.py"),
    )
    conn.commit()

    kwargs = {
        "task_prompt": "Build a bounded handoff packet generator for MCP delegation.",
        "declared_files": ["src/copyclip/mcp_server.py", "src/copyclip/intelligence/server.py"],
        "declared_modules": ["copyclip.mcp"],
        "do_not_touch": [{"target": "frontend", "reason": "UI excluded for backend slice.", "severity": "hard_boundary"}],
        "acceptance_criteria": ["Packet includes scope, constraints, and review contract."],
        "generated_at": "2026-04-16T12:00:00Z",
    }
    packet_a = build_handoff_packet(conn, pid, **kwargs)
    packet_b = build_handoff_packet(conn, pid, **kwargs)

    assert packet_a["meta"]["packet_id"] == packet_b["meta"]["packet_id"]
    assert packet_a["meta"]["created_at"] == packet_b["meta"]["created_at"]
    assert packet_a["meta"]["updated_at"] == packet_b["meta"]["updated_at"]
    assert len(packet_a["relevant_decisions"]) == 1
    assert set(packet_a["relevant_decisions"][0]["linked_targets"]) == {
        "src/copyclip/mcp_server.py",
        "src/copyclip/intelligence/server.py",
    }
    assert len([item for item in packet_a["constraints"] if item["type"] == "architectural_decision"]) == 1
    evidence_ids = {item["id"] for item in packet_a["evidence_index"]}
    for decision in packet_a["relevant_decisions"]:
        for evidence_id in decision["evidence"]:
            assert evidence_id in evidence_ids

    conn.close()
