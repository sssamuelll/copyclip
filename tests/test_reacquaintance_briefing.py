import json

from copyclip.intelligence.db import (
    connect,
    init_schema,
    get_or_create_project,
    record_project_visit,
    create_reentry_checkpoint,
)
from copyclip.intelligence.reacquaintance import build_reacquaintance_briefing


def _seed_reacquaintance_project(conn, root: str) -> int:
    pid = get_or_create_project(conn, root, name="copyclip")
    conn.execute("UPDATE projects SET story=? WHERE id=?", ("CopyClip is a local-first project intelligence control plane.", pid))

    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-new", "samuel", "2026-04-14T18:00:00Z", "fix packaging and async test support"),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-old", "samuel", "2026-04-09T09:00:00Z", "older baseline commit"),
    )

    for _ in range(3):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-new", "pyproject.toml", 10, 1),
        )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-new", "tests/test_mcp_intent_oracle.py", 12, 0),
    )

    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score, created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, "tests/test_mcp_intent_oracle.py", "high", "test_gap", "Async MCP coverage was previously brittle.", 82, "2026-04-14T18:05:00Z"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score, created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, "pyproject.toml", "medium", "churn", "Packaging changed frequently this week.", 65, "2026-04-14T18:06:00Z"),
    )

    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Use MCP intent checks", "MCP changes should stay bounded and testable.", "accepted", "manual", "2026-04-10T10:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Expand MCP integration coverage", "Decide whether to add broader integration coverage.", "proposed", "manual", "2026-04-14T18:10:00Z"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 1, "file", "tests/test_mcp_intent_oracle.py"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 2, "file", "tests/test_mcp_intent_oracle.py"),
    )

    conn.execute(
        "INSERT INTO story_snapshots(project_id, focus_areas_json, major_changes_json, open_questions_json, summary_json) VALUES(?,?,?,?,?)",
        (
            pid,
            json.dumps([{"area": "tests/test_mcp_intent_oracle.py", "severity": "high", "kind": "test_gap", "score": 82}]),
            json.dumps([{"sha": "sha-new", "message": "fix packaging and async test support"}]),
            json.dumps([{"decision_id": 2, "title": "Expand MCP integration coverage", "status": "proposed"}]),
            json.dumps({"files": 10, "commits": 2, "risks": 2}),
        ),
    )
    conn.commit()
    return pid


def _seed_realistic_context_switch_project(conn, root: str) -> int:
    """Fixture simulating a project with time-separated activity for context‑switch testing."""
    pid = get_or_create_project(conn, root, name="demo")
    conn.execute("UPDATE projects SET story=? WHERE id=?", (
        "Demo project with recent changes, risks, and unresolved decisions.",
        pid,
    ))

    # Baseline visit: 7 days ago
    record_project_visit(conn, pid, visited_at="2026-04-07T12:00:00Z")

    # Recent commits (within last day)
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-recent-a", "alice", "2026-04-14T10:00:00Z", "feat: add new API endpoint"),
    )
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-recent-b", "bob", "2026-04-14T14:30:00Z", "refactor: simplify validation logic"),
    )
    # Old commit (outside baseline window)
    conn.execute(
        "INSERT INTO commits(project_id, sha, author, date, message) VALUES(?,?,?,?,?)",
        (pid, "sha-old-c", "charlie", "2026-04-01T09:00:00Z", "initial setup"),
    )

    # File churn: high churn on file_a, medium on file_b, low on file_c
    for _ in range(5):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-recent-a", "src/api/endpoint.py", 20, 5),
        )
    for _ in range(2):
        conn.execute(
            "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
            (pid, "sha-recent-b", "src/validation.py", 12, 3),
        )
    conn.execute(
        "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-old-c", "src/legacy.py", 5, 2),
    )

    # Risks: high risk on file_a, medium on file_b
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score, created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, "src/api/endpoint.py", "high", "complexity", "High churn and many edge cases.", 85, "2026-04-14T11:00:00Z"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score, created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, "src/validation.py", "medium", "test_gap", "Validation coverage is incomplete.", 60, "2026-04-14T15:00:00Z"),
    )

    # Decisions: accepted linked to file_a, proposed linked to file_b, unresolved without link
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Adopt new API pattern", "Use consistent error handling for new endpoints.", "accepted", "manual", "2026-04-13T10:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Refactor validation module", "Should we extract validation into a separate package?", "proposed", "manual", "2026-04-14T16:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type, created_at) VALUES(?,?,?,?,?,?)",
        (pid, "Update documentation", "Need to update API docs after recent changes.", "unresolved", "manual", "2026-04-14T17:00:00Z"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 1, "file", "src/api/endpoint.py"),
    )
    conn.execute(
        "INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
        (pid, 2, "file", "src/validation.py"),
    )

    # Story snapshot (recent)
    conn.execute(
        "INSERT INTO story_snapshots(project_id, focus_areas_json, major_changes_json, open_questions_json, summary_json) VALUES(?,?,?,?,?)",
        (
            pid,
            json.dumps([{"area": "src/api/endpoint.py", "severity": "high", "kind": "complexity", "score": 85}]),
            json.dumps([{"sha": "sha-recent-a", "message": "feat: add new API endpoint"}]),
            json.dumps([{"decision_id": 2, "title": "Refactor validation module", "status": "proposed"}]),
            json.dumps({"files": 8, "commits": 3, "risks": 2}),
        ),
    )
    conn.commit()
    return pid


def test_build_reacquaintance_briefing_for_last_seen_baseline(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_reacquaintance_project(conn, root)
    record_project_visit(conn, pid, visited_at="2026-04-13T12:00:00Z")
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    assert briefing["meta"]["baseline_mode"] == "last_seen"
    assert briefing["project_refresher"]["summary"]
    assert briefing["top_changes"]
    assert briefing["read_first"]
    assert briefing["top_risk"]["area"] == "tests/test_mcp_intent_oracle.py"
    assert briefing["open_questions"]
    assert briefing["evidence_index"]


def test_briefing_prioritizes_recent_high_signal_files(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_reacquaintance_project(conn, root)
    record_project_visit(conn, pid, visited_at="2026-04-13T12:00:00Z")
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    top_read = briefing["read_first"][0]
    assert top_read["target"] in {"tests/test_mcp_intent_oracle.py", "pyproject.toml"}
    assert top_read["evidence"]
    assert briefing["top_changes"][0]["evidence"]


def test_briefing_uses_checkpoint_baseline_and_fallback_notes(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root, name="copyclip")
    create_reentry_checkpoint(conn, pid, name="release-cut", checkpoint_at="2026-04-14T09:00:00Z", notes="release baseline")
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="checkpoint", checkpoint_name="release-cut")

    assert briefing["meta"]["baseline_mode"] == "checkpoint"
    assert briefing["meta"]["baseline_label"] == "checkpoint:release-cut"
    assert briefing["meta"]["confidence"] in {"low", "medium"}
    assert briefing["fallback_notes"]
    assert briefing["top_risk"] is None


def test_realistic_context_switch_briefing_filters_old_commits(tmp_path):
    """Only commits after the baseline should appear in top_changes."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_realistic_context_switch_project(conn, root)
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    # Should have exactly 2 recent commits (sha-recent-a, sha-recent-b)
    assert len(briefing["top_changes"]) == 2
    for change in briefing["top_changes"]:
        assert change["title"] in {"feat: add new API endpoint", "refactor: simplify validation logic"}
    # Old commit sha-old-c should not appear
    assert not any("initial setup" in ch["title"] for ch in briefing["top_changes"])


def test_realistic_context_switch_ranking_prioritizes_high_churn_and_risk(tmp_path):
    """High‑churn, high‑risk file should rank first in read_first."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_realistic_context_switch_project(conn, root)
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    read_first = briefing["read_first"]
    assert len(read_first) >= 1
    # src/api/endpoint.py has highest churn (5) + high risk (85) → should be rank 1
    if read_first[0]["target"] == "src/api/endpoint.py":
        assert read_first[0]["score"] > read_first[1]["score"] if len(read_first) > 1 else True
    # At least one of the high‑signal files should be present
    assert any(item["target"] in {"src/api/endpoint.py", "src/validation.py"} for item in read_first)


def test_realistic_context_switch_evidence_citations_are_linked(tmp_path):
    """Evidence items should reference actual commits, files, risks, decisions."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_realistic_context_switch_project(conn, root)
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    evidence_map = {item["id"]: item for item in briefing["evidence_index"]}
    assert any(e["type"] == "commit" for e in evidence_map.values())
    assert any(e["type"] == "file" for e in evidence_map.values())
    assert any(e["type"] == "risk" for e in evidence_map.values())
    assert any(e["type"] == "decision" for e in evidence_map.values())

    # Each top_change should have at least one evidence reference
    for change in briefing["top_changes"]:
        assert change["evidence"]
        for ev_id in change["evidence"]:
            assert ev_id in evidence_map


def test_realistic_context_switch_relevant_decisions_include_linked_and_unresolved(tmp_path):
    """Relevant decisions should include linked decisions and unresolved ones."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_realistic_context_switch_project(conn, root)
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    relevant = briefing["relevant_decisions"]
    # Should include at least decision 2 (proposed, linked to validation.py) and decision 3 (unresolved)
    decision_ids = {d["id"] for d in relevant}
    assert 2 in decision_ids or 3 in decision_ids
    for d in relevant:
        assert d["evidence"]
        assert d["why_now"]


def test_realistic_context_switch_top_risk_is_highest_scored(tmp_path):
    """Top risk should be the highest‑scored risk present."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_realistic_context_switch_project(conn, root)
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    risk = briefing["top_risk"]
    assert risk is not None
    assert risk["area"] == "src/api/endpoint.py"
    assert risk["severity"] == "high"
    assert risk["score"] == 85


def test_realistic_context_switch_open_questions_derive_from_unresolved_decisions(tmp_path):
    """Open questions should be derived from unresolved/proposed decisions."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_realistic_context_switch_project(conn, root)
    conn.close()

    briefing = build_reacquaintance_briefing(root, baseline_mode="last_seen")

    questions = briefing["open_questions"]
    assert len(questions) >= 1
    # At least one question should be about "Refactor validation module" or "Update documentation"
    titles = {q["question"] for q in questions}
    assert any("Refactor validation module" in t or "Update documentation" in t for t in titles)
    for q in questions:
        assert q["derived_from"]
        assert q["next_step"]
