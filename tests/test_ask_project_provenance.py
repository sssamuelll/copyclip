from copyclip.intelligence.ask_project import build_ask_response
from copyclip.intelligence.db import connect, init_schema, get_or_create_project


def _seed_provenance_project(conn, root: str) -> int:
    pid = get_or_create_project(conn, root, name="prov")

    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Auth session decision", "Use auth session flow for login continuity.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (1, "file", "src/auth/session.ts"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "typescript", 1000, 1.0, "h-auth"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "high", "test_gap", "Session flow lacks regression coverage.", 90),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-auth", "samuel", "2026-04-15T10:00:00Z", "auth session rollout"),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-auth", "src/auth/session.ts", 20, 4),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "auth", "[]", 11, 7.0),
    )
    conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, module) VALUES(?,?,?,?,?,?,?)",
        (pid, "SessionManager", "class", "src/auth/session.ts", 10, 55, "auth"),
    )
    conn.commit()
    return pid


def test_build_ask_response_exposes_traceable_evidence_objects(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_provenance_project(conn, root)

    response = build_ask_response(conn, pid, "what did we decide about auth session?")
    conn.close()

    assert response["grounded"] is True
    assert response["answer_evidence_ids"]
    decision = response["evidence"]["decisions"][0]
    assert decision["ref"] == {"type": "decision", "target": 1}
    assert decision["score"] > 0
    assert decision["why_selected"]
    assert decision["evidence_id"] in response["answer_evidence_ids"]


def test_build_ask_response_includes_file_and_risk_provenance_details(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_provenance_project(conn, root)

    response = build_ask_response(conn, pid, "what changed in auth session?")
    conn.close()

    file_item = response["evidence"]["files"][0]
    risk_item = response["evidence"]["risks"][0]
    assert file_item["ref"] == {"type": "file", "target": "src/auth/session.ts"}
    assert "lexical" in " ".join(file_item["why_selected"]).lower() or "decision" in " ".join(file_item["why_selected"]).lower()
    assert risk_item["ref"] == {"type": "risk", "target": 1}
    assert risk_item["related_file"] == "src/auth/session.ts"
    assert risk_item["why_selected"]
    assert file_item["evidence_id"] in response["answer_evidence_ids"]
    assert risk_item["evidence_id"] in response["answer_evidence_ids"]


def test_build_ask_response_symbol_provenance_points_back_to_file(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_provenance_project(conn, root)

    response = build_ask_response(conn, pid, "where is SessionManager defined?")
    conn.close()

    symbol_item = response["evidence"]["symbols"][0]
    assert symbol_item["ref"] == {"type": "symbol", "target": 1}
    assert symbol_item["related_file"] == "src/auth/session.ts"
    assert symbol_item["why_selected"]
    assert response["next_drill_down"]["target"] == "src/auth/session.ts"


def test_build_ask_response_uses_stable_ids_for_duplicate_symbols_and_risks(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_provenance_project(conn, root)

    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/secondary.ts", "typescript", 1000, 1.0, "h-auth-2"),
    )
    conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, module) VALUES(?,?,?,?,?,?,?)",
        (pid, "SessionManager", "class", "src/auth/secondary.ts", 5, 20, "auth"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "medium", "complexity", "Separate auth complexity signal.", 70),
    )
    conn.commit()

    response = build_ask_response(conn, pid, "where is SessionManager defined and what is the auth session risk?")
    conn.close()

    symbol_targets = {item["ref"]["target"] for item in response["evidence"]["symbols"]}
    risk_targets = {item["ref"]["target"] for item in response["evidence"]["risks"]}
    assert all(isinstance(target, int) for target in symbol_targets)
    assert all(isinstance(target, int) for target in risk_targets)
