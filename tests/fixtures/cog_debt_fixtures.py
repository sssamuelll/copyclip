"""Shared fixtures for cognitive debt tests.

Three scenarios cover the realistic shapes a debt breakdown has to handle:

- ``seed_mixed_debt_project``: one critical dark file (mcp_server with high agent
  ratio + stale human review + churn), one healthy file (ask answer with low
  agent ratio + recent human review + decision link + tests), one greenfield
  file with no blame data (forces signal_coverage to drop).
- ``seed_clean_project``: a small project where no file reaches activation
  floors; used to verify remediation returns a ``no_action_needed`` note.
- ``seed_greenfield_project``: persisted rows without blame so
  ``agent_authored_ratio`` and ``review_staleness`` are unavailable and
  confidence must fall to ``low`` or ``medium``.
"""

from __future__ import annotations

from typing import Any

from copyclip.intelligence.db import get_or_create_project


_MCP_COMMITS = [
    ("sha-mcp-1", "samuel", "2026-04-05T10:00:00+00:00", "first refactor"),
    ("sha-mcp-2", "claude-bot", "2026-04-15T12:00:00+00:00", "agent tighten"),
    ("sha-mcp-3", "claude-bot", "2026-04-18T09:00:00+00:00", "agent polish"),
]


def seed_mixed_debt_project(conn, root: str) -> int:
    """Three contrasting files: critical-dark, healthy, greenfield."""
    pid = get_or_create_project(conn, root, name="copyclip")
    files: list[tuple[str, str, float, float | None, float | None]] = [
        ("src/copyclip/mcp_server.py", "copyclip.mcp", 86.0, 0.72, 1_600_000_000.0),
        ("src/copyclip/ask/answer.py", "copyclip.ask", 8.0, 0.05, 1_712_000_000.0),
        ("src/copyclip/new_module.py", "copyclip.new", 22.0, None, None),
        ("tests/test_ask.py", "tests", 1.0, 0.0, 1_712_000_000.0),
    ]
    for path, module, debt, ratio, last_human in files:
        conn.execute(
            "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
            (pid, path, "python", 1000, 1.0, f"h-{path}"),
        )
        conn.execute(
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,agent_line_ratio,last_human_ts) VALUES(?,?,?,?,?,?,?,?)",
            (pid, path, module, "[]", 14 if "mcp_server" in path else 6, debt, ratio, last_human),
        )
    # mcp_server has churn + mixed authors
    for sha, author, date, message in _MCP_COMMITS:
        conn.execute(
            "INSERT INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)",
            (pid, sha, author, date, message),
        )
        conn.execute(
            "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)",
            (pid, sha, "src/copyclip/mcp_server.py", 20, 5),
        )
    # ask/answer has a single recent human touch
    conn.execute(
        "INSERT INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)",
        (pid, "sha-ask-1", "samuel", "2026-04-17T12:00:00+00:00", "recent ask refactor"),
    )
    conn.execute(
        "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)",
        (pid, "sha-ask-1", "src/copyclip/ask/answer.py", 12, 2),
    )
    # decision anchored on ask/answer and mcp_server
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Evidence-first Ask responses", "Answers must be grounded.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/ask/answer.py"),
    )
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Use bounded MCP handoff packets", "Bounded delegation.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
        (2, "file", "src/copyclip/mcp_server.py"),
    )
    # risk on mcp to align with the dark narrative
    conn.execute(
        "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery drift.", 93),
    )
    conn.commit()
    return pid


def seed_clean_project(conn, root: str) -> int:
    """A project where every file is healthy and below activation floors."""
    pid = get_or_create_project(conn, root, name="copyclip-clean")
    # Very recent human review so review_staleness stays below its activation floor.
    _recent_human = 1_714_400_000.0
    files = [
        ("src/copyclip/ok/one.py", "copyclip.ok", 4.0, 0.0, _recent_human),
        ("src/copyclip/ok/two.py", "copyclip.ok", 2.0, 0.0, _recent_human),
        ("tests/copyclip/ok/test_one.py", "tests", 1.0, 0.0, _recent_human),
        ("tests/copyclip/ok/test_two.py", "tests", 1.0, 0.0, _recent_human),
    ]
    for path, module, debt, ratio, last_human in files:
        conn.execute(
            "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
            (pid, path, "python", 600, 1.0, f"h-{path}"),
        )
        conn.execute(
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,agent_line_ratio,last_human_ts) VALUES(?,?,?,?,?,?,?,?)",
            (pid, path, module, "[]", 4, debt, ratio, last_human),
        )
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Keep ok module simple", "Simplicity is the point.", "accepted", "manual"),
    )
    conn.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)", (1, "file", "src/copyclip/ok/one.py"))
    conn.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)", (1, "file", "src/copyclip/ok/two.py"))
    conn.commit()
    return pid


def seed_greenfield_project(conn, root: str) -> int:
    """A new project with no blame data — factors that need blame go unavailable."""
    pid = get_or_create_project(conn, root, name="copyclip-greenfield")
    for path in ["src/copyclip/new/alpha.py", "src/copyclip/new/beta.py"]:
        conn.execute(
            "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
            (pid, path, "python", 400, 1.0, f"h-{path}"),
        )
        conn.execute(
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,agent_line_ratio,last_human_ts) VALUES(?,?,?,?,?,?,?,?)",
            (pid, path, "copyclip.new", "[]", 3, 0.0, None, None),
        )
    conn.commit()
    return pid


STABLE_NOW_TS: float = 1_714_500_000.0  # ~2026-04-30 UTC for deterministic age computations


def debt_counts_by_severity(factor_list: list[dict[str, Any]]) -> dict[str, int]:
    """Handy helper for tests asserting how many factors landed in each severity bucket."""
    counts = {"low": 0, "medium": 0, "high": 0, "critical": 0, "unavailable": 0}
    for factor in factor_list:
        if not factor.get("signal_available"):
            counts["unavailable"] += 1
            continue
        value = factor.get("normalized_contribution") or 0
        if value >= 75:
            counts["critical"] += 1
        elif value >= 50:
            counts["high"] += 1
        elif value >= 25:
            counts["medium"] += 1
        else:
            counts["low"] += 1
    return counts
