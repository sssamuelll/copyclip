"""Lifecycle transition coverage for handoff packets and review summaries.

PACKET_TRANSITIONS and REVIEW_STATES are the authoritative definitions; these
tests enumerate every allowed transition and a representative set of disallowed
ones so regressions in the lifecycle machine surface immediately.
"""

import pytest

from copyclip.intelligence.db import connect, init_schema
from copyclip.intelligence.handoff import (
    PACKET_TRANSITIONS,
    REVIEW_STATES,
    save_handoff_packet,
    save_handoff_review_summary,
    update_handoff_packet,
)

from tests.fixtures.handoff_fixtures import (
    build_standard_bounded_packet,
    seed_bounded_delegation_project,
)


ALLOWED_PACKET_TRANSITIONS = [
    (src, dst)
    for src, destinations in PACKET_TRANSITIONS.items()
    for dst in destinations
]

ALL_PACKET_STATES = set(PACKET_TRANSITIONS.keys())
DISALLOWED_PACKET_TRANSITIONS = [
    (src, dst)
    for src in PACKET_TRANSITIONS
    for dst in ALL_PACKET_STATES
    if dst not in PACKET_TRANSITIONS[src] and dst != src
]


def _prime_packet(conn, pid: int, state: str) -> str:
    packet = build_standard_bounded_packet(conn, pid, generated_at=f"2026-04-20T10:{hash(state) % 60:02d}:00Z")
    save_handoff_packet(conn, pid, packet)
    packet_id = packet["meta"]["packet_id"]
    # walk the packet from ready_for_review to the requested start state using allowed transitions
    path = {
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
        "reviewed": [
            ("approved_for_handoff", {"approved_by": "samuel", "delegation_target": "claude-code"}),
            ("delegated", {}),
            ("change_received", {}),
            ("reviewed", {}),
        ],
        "superseded": [("superseded", {})],
        "cancelled": [
            ("approved_for_handoff", {"approved_by": "samuel", "delegation_target": "claude-code"}),
            ("cancelled", {}),
        ],
    }
    if state == "draft":
        # packet was built with a scope, so it's ready_for_review; demote to draft explicitly
        update_handoff_packet(conn, pid, packet_id, {"state": "draft"})
    for target, extras in path.get(state, []):
        update_handoff_packet(conn, pid, packet_id, {"state": target, **extras})
    conn.commit()
    return packet_id


@pytest.mark.parametrize("src_state,dst_state", ALLOWED_PACKET_TRANSITIONS)
def test_allowed_packet_transition(tmp_path, src_state, dst_state):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet_id = _prime_packet(conn, pid, src_state)

    # reviewed requires a persisted review summary to transition into it
    if dst_state == "reviewed":
        review_stub = {
            "meta": {"review_id": f"review_{packet_id}_stub", "packet_id": packet_id, "review_state": "generated", "generated_at": "2026-04-20T11:00:00Z"},
            "result": {"summary": "stub", "verdict": "accepted", "confidence": "medium"},
            "scope_check": {"declared_scope": [], "touched_files": [], "out_of_scope_touches": [], "boundary_violations": [], "summary": "noop"},
            "decision_conflicts": [],
            "blast_radius": {"impacted_modules": [], "touched_file_count": 0, "estimated_size": "small", "impact_summary": "stub"},
            "dark_zone_entry": [],
            "unresolved_questions": [],
            "review_evidence": [],
        }
        save_handoff_review_summary(conn, pid, packet_id, review_stub)

    extras = {}
    if dst_state == "approved_for_handoff":
        extras = {"approved_by": "samuel", "delegation_target": "claude-code"}
    updated = update_handoff_packet(conn, pid, packet_id, {"state": dst_state, **extras})
    conn.close()
    assert updated["meta"]["state"] == dst_state


@pytest.mark.parametrize("src_state,dst_state", DISALLOWED_PACKET_TRANSITIONS)
def test_disallowed_packet_transition_raises(tmp_path, src_state, dst_state):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet_id = _prime_packet(conn, pid, src_state)
    with pytest.raises(ValueError) as exc:
        update_handoff_packet(conn, pid, packet_id, {"state": dst_state})
    conn.close()
    assert str(exc.value).startswith("invalid_state_transition:")
    assert f"{src_state}->{dst_state}" in str(exc.value)


@pytest.mark.parametrize("review_state", sorted(REVIEW_STATES))
def test_all_review_states_are_persistable(tmp_path, review_state):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet_id = _prime_packet(conn, pid, "change_received")

    review = {
        "meta": {"review_id": f"review_{packet_id}_{review_state}", "packet_id": packet_id, "review_state": review_state, "generated_at": "2026-04-20T12:00:00Z"},
        "result": {"summary": "stub", "verdict": "accepted", "confidence": "medium"},
        "scope_check": {"declared_scope": [], "touched_files": [], "out_of_scope_touches": [], "boundary_violations": [], "summary": "noop"},
        "decision_conflicts": [],
        "blast_radius": {"impacted_modules": [], "touched_file_count": 0, "estimated_size": "small", "impact_summary": "stub"},
        "dark_zone_entry": [],
        "unresolved_questions": [],
        "review_evidence": [],
    }
    save_handoff_review_summary(conn, pid, packet_id, review)
    row = conn.execute(
        "SELECT review_state FROM handoff_review_summaries WHERE project_id=? AND packet_id=?",
        (pid, packet_id),
    ).fetchone()
    conn.close()
    assert row[0] == review_state


def test_invalid_review_state_rejected(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_bounded_delegation_project(conn, str(tmp_path))
    packet_id = _prime_packet(conn, pid, "change_received")
    review = {
        "meta": {"review_id": f"review_{packet_id}_bad", "packet_id": packet_id, "review_state": "bogus_state", "generated_at": "2026-04-20T12:00:00Z"},
        "result": {}, "scope_check": {}, "decision_conflicts": [], "blast_radius": {}, "dark_zone_entry": [], "unresolved_questions": [], "review_evidence": [],
    }
    with pytest.raises(ValueError) as exc:
        save_handoff_review_summary(conn, pid, packet_id, review)
    conn.close()
    assert str(exc.value) == "invalid_review_state"
