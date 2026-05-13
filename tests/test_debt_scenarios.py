"""End-to-end debt scenarios across scoring, recommendations, and integrations.

Each test runs ``build_debt_breakdown`` followed by ``build_remediation_plan`` on a
realistic fixture and asserts the verdict + recommendation mapping against the
narrative we expect from the contract.
"""

from copyclip.intelligence.cognitive_debt import build_debt_breakdown, quick_debt_signal
from copyclip.intelligence.debt_remediation import REMEDIATION_ACTION_TYPES, build_remediation_plan
from copyclip.intelligence.db import connect, init_schema

from tests.fixtures.cog_debt_fixtures import (
    STABLE_NOW_TS,
    seed_clean_project,
    seed_greenfield_project,
    seed_mixed_debt_project,
)


def test_critical_dark_file_produces_high_severity_and_multiple_remediations(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=STABLE_NOW_TS)
    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert breakdown["score"]["severity"] in {"high", "critical"}
    assert len(plan["remediation_candidates"]) >= 2
    action_types = {c["action_type"] for c in plan["remediation_candidates"]}
    assert "review_this_recent_change" in action_types
    # scope is in declared decision link; decision_gap factor should be suppressed → no link candidate
    assert "link_or_resolve_decision" not in action_types


def test_healthy_file_in_mixed_project_returns_no_action_needed(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_clean_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/ok/one.py", now_ts=STABLE_NOW_TS)
    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert breakdown["score"]["severity"] == "low"
    assert plan["remediation_candidates"] == []
    assert any(note.get("kind") == "no_action_needed" for note in plan["notes"])


def test_greenfield_file_lowers_confidence_without_zeroing_score(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_greenfield_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/new/alpha.py", now_ts=STABLE_NOW_TS)
    conn.close()

    # blame-dependent factors unavailable
    unavailable = {f["factor_id"] for f in breakdown["factor_breakdown"] if not f["signal_available"]}
    assert "agent_authored_ratio" in unavailable
    assert "review_staleness" in unavailable
    # confidence must drop below "high"
    assert breakdown["score"]["confidence"] in {"low", "medium"}
    # score still bounded and defined
    assert 0.0 <= breakdown["score"]["value"] <= 100.0


def test_module_breakdown_severity_tracks_worst_file_when_relevant(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    module_breakdown = build_debt_breakdown(conn, pid, "module", "copyclip.mcp", now_ts=STABLE_NOW_TS)
    file_breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=STABLE_NOW_TS)
    conn.close()

    # mcp module only contains mcp_server; module score should be close to file score
    assert abs(module_breakdown["score"]["value"] - file_breakdown["score"]["value"]) < 5.0
    assert module_breakdown["meta"]["scope_kind"] == "module"


def test_remediation_action_types_are_valid_for_mixed_scope(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    for scope_id in ["src/copyclip/mcp_server.py", "src/copyclip/ask/answer.py", "src/copyclip/new_module.py"]:
        breakdown = build_debt_breakdown(conn, pid, "file", scope_id, now_ts=STABLE_NOW_TS)
        plan = build_remediation_plan(conn, pid, breakdown)
        for candidate in plan["remediation_candidates"]:
            assert candidate["action_type"] in REMEDIATION_ACTION_TYPES
            assert candidate["expected_impact"]["score_delta"] <= 0
    conn.close()


def test_quick_debt_signal_matches_full_breakdown_severity(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    # quick_debt_signal uses datetime.now() internally; share that reference by
    # also letting full default to datetime.now() so the two calls agree.
    for path in ["src/copyclip/mcp_server.py", "src/copyclip/ask/answer.py", "src/copyclip/new_module.py"]:
        quick = quick_debt_signal(conn, pid, path)
        full = build_debt_breakdown(conn, pid, "file", path)
        assert quick is not None
        assert quick["severity"] == full["score"]["severity"]
        assert quick["value"] == round(float(full["score"]["value"]), 2)
    conn.close()


def test_quick_debt_signal_primary_signal_matches_top_weighted_factor(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    for path in ["src/copyclip/mcp_server.py", "src/copyclip/ask/answer.py", "src/copyclip/new_module.py"]:
        quick = quick_debt_signal(conn, pid, path)
        full = build_debt_breakdown(conn, pid, "file", path)
        available = [f for f in full["factor_breakdown"] if f["signal_available"]]
        if not available:
            assert quick["primary_signal"] is None
            continue
        top = max(available, key=lambda f: f["weighted_contribution"])
        assert quick["primary_signal"] == top["factor_id"]
    conn.close()


def test_quick_debt_signal_for_greenfield_path_avoids_unavailable_blame_factors(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_greenfield_project(conn, str(tmp_path))
    quick = quick_debt_signal(conn, pid, "src/copyclip/new/alpha.py")
    assert quick is not None
    # blame-dependent factors are unavailable; primary_signal must not be one of them.
    assert quick["primary_signal"] not in {"agent_authored_ratio", "review_staleness"}
    conn.close()


def test_quick_debt_signal_returns_none_for_path_missing_from_insights(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    assert quick_debt_signal(conn, pid, "src/does/not/exist.py") is None
    conn.close()


def test_read_first_anchor_prefers_human_commit(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=STABLE_NOW_TS)
    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    if plan["read_first"]:
        first = plan["read_first"][0]
        if first["kind"] == "commit":
            # when read_first leads with a commit, it should be the human anchor
            assert first.get("author_kind") == "human"


def test_low_debt_project_surfaces_empty_plan_but_keeps_meta(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_clean_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "project", "copyclip-clean", now_ts=STABLE_NOW_TS)
    plan = build_remediation_plan(conn, pid, breakdown)
    conn.close()

    assert plan["meta"]["scope_kind"] == "project"
    assert plan["remediation_candidates"] == []
    assert any(note.get("kind") == "no_action_needed" for note in plan["notes"])
