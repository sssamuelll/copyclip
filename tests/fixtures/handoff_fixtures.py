"""Shared fixtures for handoff packet / review tests.

Two scenarios are exposed:

- ``seed_bounded_delegation_project``: a realistic project with an MCP delegation
  decision, a frontend evidence-first decision, a do-not-touch frontend boundary,
  and a high-risk analytics hotspot that is NOT in declared scope. Built to cover
  the common "safe delegation" narrative.
- ``seed_minimal_project``: an empty project with only a project row, to exercise
  edge cases (missing scope, missing decisions, etc.).

Plus helpers to build packets in each canonical lifecycle state.
"""

from __future__ import annotations

from typing import Any

from copyclip.intelligence.db import get_or_create_project
from copyclip.intelligence.handoff import build_handoff_packet, save_handoff_packet, update_handoff_packet


def seed_bounded_delegation_project(conn, root: str) -> int:
    """Seed a realistic handoff scenario.

    - decision #1: "Use bounded MCP handoff packets" (accepted) linked to src/copyclip/mcp_server.py
    - decision #2: "Frontend must stay evidence-first" (accepted) linked to frontend/src/pages/AskPage.tsx
    - files: mcp_server.py, intelligence/server.py, analytics/hotspot.py (out of scope + high risk), AskPage.tsx
    - risks: intent_drift on mcp_server (high), complexity on hotspot (high)
    - analysis_file_insights with modules and cognitive_debt signals
    """
    pid = get_or_create_project(conn, root, name="copyclip")
    rows: list[tuple[str, tuple[Any, ...]]] = [
        ("INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
            (pid, "Use bounded MCP handoff packets", "Delegation should use inspectable bounded packets.", "accepted", "manual")),
        ("INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
            (1, "file", "src/copyclip/mcp_server.py")),
        ("INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
            (pid, "Frontend must stay evidence-first", "AskPage must preserve evidence-first rendering.", "accepted", "manual")),
        ("INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
            (2, "file", "frontend/src/pages/AskPage.tsx")),
        ("INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/mcp_server.py", "python", 1200, 1.0, "h-mcp")),
        ("INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/intelligence/server.py", "python", 2400, 1.0, "h-server")),
        ("INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/analytics/hotspot.py", "python", 900, 1.0, "h-hotspot")),
        ("INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
            (pid, "frontend/src/pages/AskPage.tsx", "tsx", 4800, 1.0, "h-ask")),
        ("INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery can bypass bounded delegation.", 93)),
        ("INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/analytics/hotspot.py", "high", "complexity", "Hot area with high churn.", 99)),
        ("INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0)),
        ("INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/intelligence/server.py", "copyclip.intelligence", "[]", 22, 55.0)),
        ("INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
            (pid, "src/copyclip/analytics/hotspot.py", "copyclip.analytics", "[]", 33, 88.0)),
        ("INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
            (pid, "frontend/src/pages/AskPage.tsx", "frontend.pages", "[]", 9, 30.0)),
    ]
    for sql, args in rows:
        conn.execute(sql, args)
    conn.commit()
    return pid


def seed_minimal_project(conn, root: str) -> int:
    return get_or_create_project(conn, root, name="copyclip-minimal")


def build_standard_bounded_packet(
    conn,
    pid: int,
    *,
    declared_files: list[str] | None = None,
    do_not_touch: list[dict[str, Any]] | None = None,
    acceptance_criteria: list[str] | None = None,
    generated_at: str = "2026-04-20T10:00:00Z",
) -> dict[str, Any]:
    """Standard scenario packet: bounded MCP work with AskPage excluded."""
    return build_handoff_packet(
        conn,
        pid,
        task_prompt="Tighten bounded MCP delegation without touching the evidence-first Ask UI.",
        declared_files=declared_files if declared_files is not None else ["src/copyclip/mcp_server.py"],
        do_not_touch=do_not_touch if do_not_touch is not None else [
            {"target": "frontend/src/pages/AskPage.tsx", "reason": "Ask UI is excluded.", "severity": "hard_boundary"},
        ],
        acceptance_criteria=acceptance_criteria if acceptance_criteria is not None else ["Delegation stays bounded."],
        generated_at=generated_at,
    )


def advance_packet_to(conn, pid: int, packet: dict[str, Any], target_state: str) -> dict[str, Any]:
    """Persist the packet then walk it through the allowed lifecycle sequence to reach target_state."""
    save_handoff_packet(conn, pid, packet)
    packet_id = packet["meta"]["packet_id"]
    sequence: list[tuple[str, dict[str, Any]]] = []
    path_to = {
        "draft": [],
        "ready_for_review": [],
        "approved_for_handoff": [("approved_for_handoff", {"approved_by": "samuel", "delegation_target": "claude-code"})],
        "delegated": [
            ("approved_for_handoff", {"approved_by": "samuel", "delegation_target": "claude-code"}),
            ("delegated", {}),
        ],
        "change_received": [
            ("approved_for_handoff", {"approved_by": "samuel", "delegation_target": "claude-code"}),
            ("delegated", {}),
            ("change_received", {}),
        ],
    }
    if target_state not in path_to:
        raise ValueError(f"unsupported target state: {target_state}")
    sequence = path_to[target_state]
    for state, extras in sequence:
        update_handoff_packet(conn, pid, packet_id, {"state": state, **extras})
    conn.commit()
    return packet
