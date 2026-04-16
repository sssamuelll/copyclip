import json

from copyclip.intelligence.db import get_or_create_project


REPRESENTATIVE_ASK_EVAL_CASES = [
    {
        "scenario": "base",
        "question": "what did we decide about auth session rollout?",
        "answer_kind": "grounded_answer",
        "grounded": True,
        "confidence": "high",
        "required_citation_types": ["decision", "file", "risk"],
        "required_evidence_groups": ["decisions", "files", "risks"],
        "drill_down_type": "decision",
    },
    {
        "scenario": "base",
        "question": "where is SessionManager defined?",
        "answer_kind": "grounded_answer",
        "grounded": True,
        "confidence": "medium",
        "required_citation_types": ["file"],
        "required_evidence_groups": ["symbols"],
        "drill_down_type": "file",
    },
    {
        "scenario": "contradiction",
        "question": "does auth session drift conflict with the rollout decision?",
        "answer_kind": "contradiction_detected",
        "grounded": False,
        "confidence": "low",
        "required_citation_types": ["decision", "risk", "file"],
        "required_evidence_groups": ["decisions", "files", "risks"],
        "drill_down_type": "decision",
    },
    {
        "scenario": "base",
        "question": "what happened to quantum orchard lattice?",
        "answer_kind": "insufficient_evidence",
        "grounded": False,
        "confidence": "low",
        "required_citation_types": [],
        "required_evidence_groups": [],
        "drill_down_type": "none",
    },
]


def seed_representative_ask_project(conn, root: str, include_contradiction: bool = False) -> int:
    pid = get_or_create_project(conn, root, name="ask-eval")

    decision_id = conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Auth session rollout decision", "Use auth session flow for login continuity and keep rollout stable.", "accepted", "manual"),
    ).lastrowid
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (decision_id, "file", "src/auth/session.ts"),
    )
    billing_decision_id = conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Billing retry guidance", "Retries should stay isolated from auth session behavior.", "accepted", "manual"),
    ).lastrowid
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (billing_decision_id, "file", "src/billing/retries.ts"),
    )

    for path_value, hash_value in [
        ("src/auth/session.ts", "h-auth"),
        ("src/billing/retries.ts", "h-billing"),
        ("src/ui/login.tsx", "h-ui"),
    ]:
        conn.execute(
            "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
            (pid, path_value, "typescript", 1000, 1.0, hash_value),
        )

    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "medium", "test_gap", "Session flow still lacks enough regression coverage.", 78),
    )
    if include_contradiction:
        conn.execute(
            "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
            (pid, "src/auth/session.ts", "high", "intent_drift", "Recent auth changes appear to conflict with the accepted rollout direction.", 96),
        )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/billing/retries.ts", "medium", "complexity", "Billing retry branching is moderately complex.", 61),
    )

    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-auth-rollout", "samuel", "2026-04-15T10:00:00Z", "auth session rollout for login continuity"),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-auth-rewrite", "samuel", "2026-04-16T08:30:00Z", "rewrite auth session behavior"),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-billing", "samuel", "2026-04-14T09:00:00Z", "tighten billing retry conditions"),
    )

    for _ in range(4):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-auth-rollout", "src/auth/session.ts", 18, 4),
        )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-auth-rewrite", "src/auth/session.ts", 34, 12),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-billing", "src/billing/retries.ts", 12, 5),
    )

    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/auth/session.ts", "auth", json.dumps(["src/ui/login.tsx"]), 13, 8.0),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/billing/retries.ts", "billing", json.dumps([]), 8, 5.0),
    )

    conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, module) VALUES(?,?,?,?,?,?,?)",
        (pid, "SessionManager", "class", "src/auth/session.ts", 10, 58, "auth"),
    )
    conn.execute(
        "INSERT INTO symbols(project_id, name, kind, file_path, line_start, line_end, module) VALUES(?,?,?,?,?,?,?)",
        (pid, "loginWithSession", "function", "src/auth/session.ts", 60, 105, "auth"),
    )
    conn.commit()
    return pid
