from copyclip.intelligence.db import connect, init_schema, get_or_create_project
from copyclip.intelligence.handoff import build_handoff_packet, build_handoff_review_summary


def _seed_project(conn, root: str) -> int:
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
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Frontend must stay evidence-first", "Ask UI must preserve evidence-first rendering.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (2, "file", "frontend/src/pages/AskPage.tsx"),
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
        (pid, "src/copyclip/analytics/hotspot.py", "python", 900, 1.0, "h-hotspot"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "frontend/src/pages/AskPage.tsx", "tsx", 4800, 1.0, "h-ask"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery can bypass bounded delegation.", 93),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/analytics/hotspot.py", "high", "complexity", "Hot area with high churn.", 99),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/intelligence/server.py", "copyclip.intelligence", "[]", 22, 55.0),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/analytics/hotspot.py", "copyclip.analytics", "[]", 33, 88.0),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "frontend/src/pages/AskPage.tsx", "frontend.pages", "[]", 9, 30.0),
    )
    conn.commit()
    return pid


def _build_packet(conn, pid, **overrides):
    return build_handoff_packet(
        conn,
        pid,
        task_prompt=overrides.get("task_prompt", "Tighten bounded MCP delegation."),
        declared_files=overrides.get("declared_files", ["src/copyclip/mcp_server.py"]),
        declared_modules=overrides.get("declared_modules", []),
        do_not_touch=overrides.get("do_not_touch", [
            {"target": "frontend/src/pages/AskPage.tsx", "reason": "Ask UI is excluded.", "severity": "hard_boundary"},
        ]),
        acceptance_criteria=overrides.get("acceptance_criteria", ["Delegation stays bounded."]),
        generated_at="2026-04-20T10:00:00Z",
    )


def test_review_summary_clean_when_touches_stay_in_scope(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
        generated_at="2026-04-20T11:00:00Z",
    )
    conn.close()

    assert summary["meta"]["packet_id"] == packet["meta"]["packet_id"]
    assert summary["meta"]["review_state"] == "generated"
    assert summary["meta"]["generated_at"] == "2026-04-20T11:00:00Z"
    assert summary["scope_check"]["declared_scope"] == ["src/copyclip/mcp_server.py"]
    assert summary["scope_check"]["touched_files"] == ["src/copyclip/mcp_server.py"]
    assert summary["scope_check"]["out_of_scope_touches"] == []
    assert summary["scope_check"]["boundary_violations"] == []
    assert summary["result"]["verdict"] == "accepted"
    assert summary["result"]["confidence"] in {"medium", "high"}
    # touching declared scope that's also in packet.risk_dark_zones is an acknowledged dark zone, not an unexpected entry
    assert all(entry.get("expected") is True for entry in summary["dark_zone_entry"])


def test_review_summary_flags_out_of_scope_touches(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={
            "touched_files": [
                "src/copyclip/mcp_server.py",
                "src/copyclip/intelligence/server.py",  # out of declared scope
            ]
        },
    )
    conn.close()

    assert "src/copyclip/intelligence/server.py" in summary["scope_check"]["out_of_scope_touches"]
    assert "src/copyclip/mcp_server.py" not in summary["scope_check"]["out_of_scope_touches"]
    assert summary["result"]["verdict"] == "changes_requested"
    assert summary["result"]["confidence"] == "high"
    assert "out of declared scope" in summary["scope_check"]["summary"].lower() or "out-of-scope" in summary["scope_check"]["summary"].lower()


def test_review_summary_flags_do_not_touch_boundary_as_violation(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={
            "touched_files": [
                "src/copyclip/mcp_server.py",
                "frontend/src/pages/AskPage.tsx",  # hard boundary
            ]
        },
    )
    conn.close()

    violations = summary["scope_check"]["boundary_violations"]
    assert any(v["target"] == "frontend/src/pages/AskPage.tsx" for v in violations)
    assert summary["result"]["verdict"] == "changes_requested"
    assert summary["result"]["confidence"] == "high"


def test_review_summary_flags_decision_conflicts_for_touched_decision_targets(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    # packet declares scope on mcp_server only; do_not_touch includes AskPage (linked to decision 2)
    packet = _build_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={
            "touched_files": [
                "src/copyclip/mcp_server.py",
                "frontend/src/pages/AskPage.tsx",
            ]
        },
    )
    conn.close()

    conflicts = summary["decision_conflicts"]
    assert any(item["decision_id"] == 2 for item in conflicts)
    askpage_conflict = next(item for item in conflicts if item["decision_id"] == 2)
    assert askpage_conflict["severity"] in {"high", "medium"}
    assert any(ev.startswith("file:frontend/src/pages/AskPage.tsx") for ev in askpage_conflict["evidence"])
    assert any(ev == "decision:2" for ev in askpage_conflict["evidence"])


def test_review_summary_blast_radius_groups_touched_modules(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid, declared_files=[
        "src/copyclip/mcp_server.py",
        "src/copyclip/intelligence/server.py",
        "src/copyclip/analytics/hotspot.py",
    ])

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={
            "touched_files": [
                "src/copyclip/mcp_server.py",
                "src/copyclip/intelligence/server.py",
                "src/copyclip/analytics/hotspot.py",
            ]
        },
    )
    conn.close()

    modules = set(summary["blast_radius"]["impacted_modules"])
    assert {"copyclip.mcp", "copyclip.intelligence", "copyclip.analytics"} <= modules
    assert summary["blast_radius"]["estimated_size"] in {"small", "medium", "large"}
    assert summary["blast_radius"]["touched_file_count"] == 3


def test_review_summary_flags_unexpected_dark_zone_entry(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    # declared scope is only mcp_server.py; hotspot is high-risk + high cognitive_debt but NOT declared
    packet = _build_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={
            "touched_files": [
                "src/copyclip/mcp_server.py",
                "src/copyclip/analytics/hotspot.py",  # unexpected dark zone entry
            ]
        },
    )
    conn.close()

    unexpected = [entry for entry in summary["dark_zone_entry"] if not entry.get("expected")]
    assert any(entry["area"] == "src/copyclip/analytics/hotspot.py" for entry in unexpected)
    assert summary["result"]["verdict"] == "changes_requested"


def test_review_summary_surfaces_unresolved_blocking_questions(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid, declared_files=[], declared_modules=[])
    # this packet will be in draft state with blocking questions
    assert any(q.get("blocking") for q in packet["questions_to_clarify"])

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
    )
    conn.close()

    # When declared scope is empty but the agent still touched files, everything is out-of-scope
    assert summary["scope_check"]["out_of_scope_touches"] == ["src/copyclip/mcp_server.py"]
    assert summary["unresolved_questions"]
    assert all(item.get("priority") in {"low", "medium", "high"} for item in summary["unresolved_questions"])


def test_review_summary_verdict_is_human_review_when_only_questions_remain(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid, acceptance_criteria=[])
    # no acceptance_criteria triggers a non-blocking question in the packet generator
    assert packet["questions_to_clarify"]

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
    )
    conn.close()

    # touched only declared file, no boundary hit, no unexpected dark zone → verdict should reflect the remaining questions
    assert summary["result"]["verdict"] in {"accepted", "needs_human_review"}
    if summary["unresolved_questions"]:
        assert summary["result"]["verdict"] == "needs_human_review"


def test_review_summary_is_deterministic_and_includes_evidence(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_project(conn, str(tmp_path))
    packet = _build_packet(conn, pid)
    proposed = {"touched_files": ["src/copyclip/mcp_server.py", "frontend/src/pages/AskPage.tsx"]}

    summary_a = build_handoff_review_summary(conn, pid, packet, proposed, generated_at="2026-04-20T11:00:00Z")
    summary_b = build_handoff_review_summary(conn, pid, packet, proposed, generated_at="2026-04-20T11:00:00Z")
    conn.close()

    assert summary_a == summary_b
    assert summary_a["meta"]["review_id"].startswith("review_")
    # every piece of review_evidence should resolve to a normalized id
    evidence_ids = {item["id"] for item in summary_a["review_evidence"]}
    assert any(ev_id.startswith("file:") for ev_id in evidence_ids)
    assert any(ev_id.startswith("decision:") for ev_id in evidence_ids)
