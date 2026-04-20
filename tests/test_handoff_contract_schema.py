"""Contract invariants for the handoff packet and review summary shapes.

These tests enforce the schema described in docs/HANDOFF_PACKET_CONTRACT.md so
that packet / review generators cannot silently drop required fields.
"""

from copyclip.intelligence.db import connect, init_schema
from copyclip.intelligence.handoff import (
    PACKET_TRANSITIONS,
    REVIEW_STATES,
    build_handoff_review_summary,
)

from tests.fixtures.handoff_fixtures import (
    build_standard_bounded_packet,
    seed_bounded_delegation_project,
)


REQUIRED_PACKET_KEYS = {
    "meta",
    "objective",
    "scope",
    "constraints",
    "do_not_touch",
    "relevant_decisions",
    "risk_dark_zones",
    "questions_to_clarify",
    "acceptance_criteria",
    "agent_consumable_packet",
    "review_contract",
    "evidence_index",
    "notes",
}

REQUIRED_META_KEYS = {
    "packet_id",
    "packet_version",
    "state",
    "created_at",
    "updated_at",
    "project",
    "created_by",
    "approved_by",
    "delegation_target",
    "source_task",
}

REQUIRED_AGENT_CONSUMABLE_KEYS = {
    "objective",
    "allowed_write_scope",
    "read_scope",
    "constraints",
    "do_not_touch",
    "questions_to_clarify",
    "acceptance_criteria",
}

REQUIRED_REVIEW_CONTRACT_KEYS = {
    "expected_review_type",
    "compare_scope_against_touched_files",
    "check_decision_conflicts",
    "check_dark_zone_entry",
    "check_blast_radius",
    "required_human_questions",
}

REQUIRED_REVIEW_KEYS = {
    "meta",
    "result",
    "scope_check",
    "decision_conflicts",
    "blast_radius",
    "dark_zone_entry",
    "unresolved_questions",
    "review_evidence",
}


def test_packet_has_all_required_top_level_and_meta_keys(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)
    conn.close()

    assert REQUIRED_PACKET_KEYS.issubset(packet.keys())
    assert REQUIRED_META_KEYS.issubset(packet["meta"].keys())
    assert REQUIRED_AGENT_CONSUMABLE_KEYS.issubset(packet["agent_consumable_packet"].keys())
    assert REQUIRED_REVIEW_CONTRACT_KEYS.issubset(packet["review_contract"].keys())


def test_packet_state_is_in_known_lifecycle_set(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)
    conn.close()

    allowed_states = set(PACKET_TRANSITIONS.keys())
    assert packet["meta"]["state"] in allowed_states


def test_review_summary_has_all_required_sections_and_state_is_valid(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
        generated_at="2026-04-20T11:00:00Z",
    )
    conn.close()

    assert REQUIRED_REVIEW_KEYS.issubset(summary.keys())
    assert summary["meta"]["review_state"] in REVIEW_STATES
    assert summary["result"]["verdict"] in {"accepted", "changes_requested", "needs_human_review"}
    assert summary["result"]["confidence"] in {"low", "medium", "high"}


def test_agent_consumable_packet_lists_are_disjoint_projections(tmp_path):
    """allowed_write_scope and do_not_touch should never overlap by construction."""
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)
    conn.close()

    write_scope = set(packet["agent_consumable_packet"]["allowed_write_scope"])
    do_not_touch = set(packet["agent_consumable_packet"]["do_not_touch"])
    assert write_scope.isdisjoint(do_not_touch)


def test_review_contract_fields_drive_review_sections(tmp_path):
    """If the review_contract declares check_decision_conflicts, the review pipeline must populate the section (even if empty)."""
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet = build_standard_bounded_packet(conn, pid)

    assert packet["review_contract"]["check_decision_conflicts"] is True
    assert packet["review_contract"]["check_dark_zone_entry"] is True
    assert packet["review_contract"]["check_blast_radius"] is True

    summary = build_handoff_review_summary(
        conn,
        pid,
        packet,
        proposed_changes={"touched_files": ["src/copyclip/mcp_server.py"]},
        generated_at="2026-04-20T11:00:00Z",
    )
    conn.close()

    assert "decision_conflicts" in summary
    assert "dark_zone_entry" in summary
    assert "blast_radius" in summary
    assert "impacted_modules" in summary["blast_radius"]
    assert "estimated_size" in summary["blast_radius"]
