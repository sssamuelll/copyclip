"""End-to-end delegation narratives that exercise the full handoff pipeline.

Each test composes a packet, walks the lifecycle, generates a review summary via
``build_handoff_review_summary``, and asserts the verdict + key signals against
a realistic scenario drawn from docs/HANDOFF_PACKET_CONTRACT.md.
"""

from copyclip.intelligence.db import connect, init_schema
from copyclip.intelligence.handoff import (
    build_handoff_review_summary,
    save_handoff_packet,
    save_handoff_review_summary,
    update_handoff_packet,
)

from tests.fixtures.handoff_fixtures import (
    build_standard_bounded_packet,
    seed_bounded_delegation_project,
)


def test_happy_path_clean_change_is_accepted(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)
    save_handoff_packet(conn, pid, packet)
    packet_id = packet["meta"]["packet_id"]

    update_handoff_packet(conn, pid, packet_id, {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"})
    update_handoff_packet(conn, pid, packet_id, {"state": "delegated"})
    update_handoff_packet(conn, pid, packet_id, {"state": "change_received"})
    conn.commit()

    summary = build_handoff_review_summary(
        conn, pid, packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
        generated_at="2026-04-20T11:00:00Z",
    )
    save_handoff_review_summary(conn, pid, packet_id, summary)
    final = update_handoff_packet(conn, pid, packet_id, {"state": "reviewed"})
    conn.close()

    assert summary["result"]["verdict"] == "accepted"
    assert summary["scope_check"]["out_of_scope_touches"] == []
    assert summary["scope_check"]["boundary_violations"] == []
    assert summary["decision_conflicts"] == []
    assert final["meta"]["state"] == "reviewed"


def test_boundary_violation_requires_changes(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)
    conn.close()
    conn = connect(str(tmp_path))
    init_schema(conn)

    summary = build_handoff_review_summary(
        conn, pid, packet,
        proposed_changes={"touched_files": [
            "src/copyclip/mcp_server.py",
            "frontend/src/pages/AskPage.tsx",
        ]},
    )
    conn.close()

    assert summary["result"]["verdict"] == "changes_requested"
    assert any(v["target"] == "frontend/src/pages/AskPage.tsx" for v in summary["scope_check"]["boundary_violations"])
    # decision #2 (Frontend evidence-first) touches the same boundary target and must appear in conflicts
    assert any(c["decision_id"] == 2 for c in summary["decision_conflicts"])


def test_unexpected_dark_zone_excursion_requires_changes(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn, pid, packet,
        proposed_changes={"touched_files": [
            "src/copyclip/mcp_server.py",
            "src/copyclip/analytics/hotspot.py",  # high risk + high debt, NOT in declared scope
        ]},
    )
    conn.close()

    assert summary["result"]["verdict"] == "changes_requested"
    unexpected = [entry for entry in summary["dark_zone_entry"] if not entry.get("expected")]
    assert any(entry["area"] == "src/copyclip/analytics/hotspot.py" for entry in unexpected)
    assert "src/copyclip/analytics/hotspot.py" in summary["scope_check"]["out_of_scope_touches"]


def test_unresolved_questions_push_verdict_to_human_review(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid, acceptance_criteria=[])

    # The packet generator surfaces a non-blocking question when acceptance_criteria is empty
    assert any(q.get("question") for q in packet["questions_to_clarify"])

    summary = build_handoff_review_summary(
        conn, pid, packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
    )
    conn.close()

    assert summary["result"]["verdict"] == "needs_human_review"
    assert summary["result"]["confidence"] == "medium"
    assert summary["unresolved_questions"]


def test_scenario_pipeline_survives_resumed_review(tmp_path):
    """Running the review twice for the same packet + inputs should be idempotent by design."""
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)
    save_handoff_packet(conn, pid, packet)
    packet_id = packet["meta"]["packet_id"]
    update_handoff_packet(conn, pid, packet_id, {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"})
    update_handoff_packet(conn, pid, packet_id, {"state": "delegated"})
    update_handoff_packet(conn, pid, packet_id, {"state": "change_received"})
    conn.commit()

    proposed = {"touched_files": ["src/copyclip/mcp_server.py"]}
    first = build_handoff_review_summary(conn, pid, packet, proposed, generated_at="2026-04-20T11:00:00Z")
    save_handoff_review_summary(conn, pid, packet_id, first)
    update_handoff_packet(conn, pid, packet_id, {"state": "reviewed"})

    # re-run review with the same inputs; persist again (valid: reviewed can be overwritten when the review summary mutates)
    second = build_handoff_review_summary(conn, pid, packet, proposed, generated_at="2026-04-20T11:00:00Z")
    save_handoff_review_summary(conn, pid, packet_id, second)
    conn.close()

    assert first == second
    assert first["meta"]["review_id"] == second["meta"]["review_id"]
