"""TDD suite for the cognitive debt remediation engine.

The engine takes a debt breakdown (from build_debt_breakdown) and produces a
prioritized, evidence-backed action plan that agents and humans can consume.
"""

from copyclip.intelligence.db import connect, init_schema, get_or_create_project
from copyclip.intelligence.cognitive_debt import build_debt_breakdown
from copyclip.intelligence.debt_remediation import (
    REMEDIATION_ACTION_TYPES,
    build_remediation_plan,
)


def _seed(conn, root: str) -> int:
    pid = get_or_create_project(conn, root, name="copyclip")
    files = [
        ("src/copyclip/mcp_server.py", "copyclip.mcp", 82.0, 0.72, 1_600_000_000.0),  # high agent ratio, old human review
        ("src/copyclip/intelligence/server.py", "copyclip.intelligence", 40.0, None, None),
        ("tests/test_mcp.py", "tests", 2.0, 0.0, 1_700_000_000.0),
    ]
    for path, module, debt, ratio, last_human in files:
        conn.execute(
            "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
            (pid, path, "python", 1200, 1.0, f"h-{path}"),
        )
        conn.execute(
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,agent_line_ratio,last_human_ts) VALUES(?,?,?,?,?,?,?,?)",
            (pid, path, module, "[]", 10, debt, ratio, last_human),
        )
    # commits + file_changes so the file appears in churn
    for i, (sha, author, date) in enumerate([
        ("sha-a", "samuel", "2026-04-10T10:00:00+00:00"),
        ("sha-b", "claude-bot", "2026-04-15T12:00:00+00:00"),
        ("sha-c", "claude-bot", "2026-04-18T09:00:00+00:00"),
    ]):
        conn.execute("INSERT INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)", (pid, sha, author, date, f"m-{sha}"))
        conn.execute(
            "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)",
            (pid, sha, "src/copyclip/mcp_server.py", 20, 5),
        )
    # decisions (covers mcp_server)
    conn.execute("INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)", (pid, "Use bounded MCP handoff packets", "Bounded delegation.", "accepted", "manual"))
    conn.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)", (1, "file", "src/copyclip/mcp_server.py"))
    conn.commit()
    return pid


_NOW_TS = 1_713_600_000.0


def test_plan_has_meta_and_top_factors_sorted_by_contribution(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert plan["meta"]["scope_kind"] == "file"
    assert plan["meta"]["scope_id"] == "src/copyclip/mcp_server.py"
    assert plan["meta"]["contract_version"] == breakdown["meta"]["contract_version"]
    # top_factors should be factor_ids sorted by weighted_contribution desc
    contributions = [
        (f["factor_id"], f["weighted_contribution"])
        for f in breakdown["factor_breakdown"]
        if f["signal_available"]
    ]
    contributions.sort(key=lambda t: t[1], reverse=True)
    expected_top = [fid for fid, _ in contributions if _ > 0]
    assert plan["top_factors"] == expected_top[: len(plan["top_factors"])]


def test_high_agent_ratio_produces_human_review_candidate(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    action_types = {c["action_type"] for c in plan["remediation_candidates"]}
    assert "review_this_recent_change" in action_types
    review = next(c for c in plan["remediation_candidates"] if c["action_type"] == "review_this_recent_change")
    assert "agent_authored_ratio" in review["reduces_factors"]
    assert review["expected_impact"]["score_delta"] < 0
    # must reference concrete commits in evidence
    assert any(ev.startswith("commit:") for ev in review["evidence"])


def test_high_decision_gap_produces_link_or_propose_decision(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/intelligence/server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    action_types = {c["action_type"] for c in plan["remediation_candidates"]}
    assert "link_or_resolve_decision" in action_types
    link = next(c for c in plan["remediation_candidates"] if c["action_type"] == "link_or_resolve_decision")
    assert "decision_gap" in link["reduces_factors"]


def test_high_test_evidence_gap_produces_add_test(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/intelligence/server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    action_types = {c["action_type"] for c in plan["remediation_candidates"]}
    assert "inspect_tests_or_test_gaps" in action_types


def test_read_first_is_ordered_unique_and_references_targets(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert plan["read_first"]
    ids = [item["id"] for item in plan["read_first"]]
    assert len(ids) == len(set(ids))  # unique
    # should include at least one human-authored commit first (to restore continuity)
    assert any(item["kind"] == "commit" and item.get("author_kind") == "human" for item in plan["read_first"])


def test_expected_total_impact_aggregates_candidates_with_diminishing_returns(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    total = plan["expected_total_impact"]["score_delta"]
    # can't exceed the sum of individual candidate deltas (no negative surplus)
    individual_sum = sum(c["expected_impact"]["score_delta"] for c in plan["remediation_candidates"])
    # diminishing returns: |total| <= |individual_sum|
    assert abs(total) <= abs(individual_sum) + 1e-6
    # but still negative (reducing the score)
    assert total <= 0


def test_low_debt_file_returns_empty_plan_with_explicit_note(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "tests/test_mcp.py", now_ts=_NOW_TS)
    # The tests file has very low agent ratio + module has tests + low churn → low debt

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    # ensure the plan still returns meta and at worst notes
    assert plan["meta"]["scope_id"] == "tests/test_mcp.py"
    if not plan["remediation_candidates"]:
        assert any(note.get("kind") == "no_action_needed" for note in plan["notes"])


def test_action_types_are_a_subset_of_registered_set(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    for candidate in plan["remediation_candidates"]:
        assert candidate["action_type"] in REMEDIATION_ACTION_TYPES


def test_candidates_are_deterministic_for_same_inputs(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS, generated_at="2026-04-20T10:00:00Z")

    plan_a = build_remediation_plan(conn, pid, breakdown)
    plan_b = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert plan_a == plan_b


def test_module_scope_plan_references_module_targets(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "module", "copyclip.mcp", now_ts=_NOW_TS)

    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert plan["meta"]["scope_kind"] == "module"
    # at least one candidate should target the module
    assert any(c["target"].get("kind") == "module" or c["target"].get("module") == "copyclip.mcp" for c in plan["remediation_candidates"])
