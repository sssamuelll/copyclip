from copyclip.intelligence.ask_project import build_ask_response
from copyclip.intelligence.db import connect, init_schema, get_or_create_project


def _seed_ranked_project(conn, root: str) -> int:
    pid = get_or_create_project(conn, root, name="ranked")

    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Auth rollout decision", "Use the new auth session flow in auth module.", "accepted", "manual"),
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
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/billing/invoice.ts", "typescript", 1000, 1.0, "h-billing"),
    )

    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "high", "test_gap", "Auth session flow lacks enough regression coverage.", 92),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/billing/invoice.ts", "medium", "complexity", "Invoice generation has moderate branching.", 60),
    )

    for _ in range(5):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-auth", "src/auth/session.ts", 12, 3),
        )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-auth", "samuel", "2026-04-14T12:00:00Z", "auth session rollout for login flow"),
    )

    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "auth", "[]", 12, 8.0),
    )
    conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, module) VALUES(?,?,?,?,?,?,?)",
        (pid, "SessionManager", "class", "src/auth/session.ts", 10, 60, "auth"),
    )
    conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, module) VALUES(?,?,?,?,?,?,?)",
        (pid, "loginWithSession", "function", "src/auth/session.ts", 70, 100, "auth"),
    )

    conn.commit()
    return pid


def test_build_ask_response_prefers_decision_and_risk_aligned_auth_evidence(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_ranked_project(conn, root)

    response = build_ask_response(conn, pid, "what did we decide about auth session rollout?")
    conn.close()

    assert response["grounded"] is True
    assert response["answer_kind"] == "grounded_answer"
    assert response["evidence"]["decisions"]
    assert response["evidence"]["risks"]
    assert response["evidence"]["files"]
    assert response["evidence"]["files"][0]["id"] == "src/auth/session.ts"
    assert any("question terms" in item.lower() for item in response["evidence_selection_rationale"])
    assert response["next_drill_down"]["target"] in {1, "src/auth/session.ts"}


def test_build_ask_response_returns_symbol_evidence_for_symbol_query(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_ranked_project(conn, root)

    response = build_ask_response(conn, pid, "where is SessionManager defined?")
    conn.close()

    assert response["grounded"] is True
    assert response["evidence"]["symbols"]
    assert response["evidence"]["symbols"][0]["label"] == "SessionManager"
    assert response["next_drill_down"]["target"] in {"src/auth/session.ts", "SessionManager"}


def test_build_ask_response_does_not_prefer_unrelated_hot_file_when_decision_ref_exists(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_ranked_project(conn, root)

    for _ in range(15):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-billing", "src/billing/invoice.ts", 20, 10),
        )
    conn.commit()

    response = build_ask_response(conn, pid, "what changed in auth session flow?")
    conn.close()

    assert response["grounded"] is True
    assert response["evidence"]["files"]
    assert response["evidence"]["files"][0]["id"] == "src/auth/session.ts"
