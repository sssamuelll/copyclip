from copyclip.intelligence.db import connect, init_schema, get_or_create_project
from copyclip.intelligence.cognitive_debt import (
    CONTRACT_VERSION,
    COGNITIVE_DEBT_FACTORS,
    build_debt_breakdown,
    breakdown_fingerprint,
)


def _seed(conn, root: str, *, with_blame: bool = True) -> int:
    pid = get_or_create_project(conn, root, name="copyclip")
    # files
    for rel, lang in [
        ("src/copyclip/mcp_server.py", "python"),
        ("src/copyclip/intelligence/server.py", "python"),
        ("tests/test_mcp.py", "python"),
        ("frontend/src/pages/AskPage.tsx", "tsx"),
    ]:
        conn.execute(
            "INSERT INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
            (pid, rel, lang, 1200, 1.0, f"h-{rel}"),
        )
    # analysis_file_insights
    insights = [
        ("src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0, 0.72 if with_blame else None, 1_600_000_000.0 if with_blame else None),
        ("src/copyclip/intelligence/server.py", "copyclip.intelligence", "[]", 22, 40.0, None, None),
        ("tests/test_mcp.py", "tests", "[]", 3, 2.0, 0.0 if with_blame else None, 1_700_000_000.0 if with_blame else None),
        ("frontend/src/pages/AskPage.tsx", "frontend.pages", "[]", 9, 30.0, None, None),
    ]
    for path, module, imports_json, complexity, debt, ratio, last_human in insights:
        conn.execute(
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,agent_line_ratio,last_human_ts) VALUES(?,?,?,?,?,?,?,?)",
            (pid, path, module, imports_json, complexity, debt, ratio, last_human),
        )
    # commits + file_changes (churn signal for mcp_server)
    for sha, author, date in [
        ("sha-1", "samuel", "2026-04-10T10:00:00+00:00"),
        ("sha-2", "claude-bot", "2026-04-15T12:00:00+00:00"),
        ("sha-3", "samuel", "2026-04-18T09:00:00+00:00"),
    ]:
        conn.execute("INSERT INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)", (pid, sha, author, date, f"msg-{sha}"))
    for sha in ["sha-1", "sha-2", "sha-3"]:
        conn.execute("INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)", (pid, sha, "src/copyclip/mcp_server.py", 20, 5))
    # decisions
    conn.execute("INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)", (pid, "Use bounded MCP handoff packets", "Bounded delegation.", "accepted", "manual"))
    conn.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)", (1, "file", "src/copyclip/mcp_server.py"))
    conn.commit()
    return pid


_NOW_TS = 1_713_600_000.0  # 2026-04-20T10:40:00Z  (well after the seeded blame ts)


def test_file_breakdown_contains_all_contract_factors(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)
    conn.close()

    assert breakdown["meta"]["contract_version"] == CONTRACT_VERSION
    assert breakdown["meta"]["scope_kind"] == "file"
    factor_ids = [f["factor_id"] for f in breakdown["factor_breakdown"]]
    assert factor_ids == [f["id"] for f in COGNITIVE_DEBT_FACTORS]
    assert breakdown["score"]["severity"] in {"low", "medium", "high", "critical"}
    assert 0 <= breakdown["score"]["value"] <= 100
    assert breakdown["score"]["confidence"] in {"low", "medium", "high"}


def test_missing_blame_signals_lower_confidence_but_keep_score_bounded(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path), with_blame=False)

    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)
    conn.close()

    # agent_authored_ratio and review_staleness should be unavailable without blame
    unavailable = {f["factor_id"] for f in breakdown["factor_breakdown"] if not f["signal_available"]}
    assert "agent_authored_ratio" in unavailable
    assert "review_staleness" in unavailable
    # signal_coverage must be strictly below 1.0 and confidence not 'high'
    assert breakdown["score"]["signal_coverage"] < 1.0
    assert breakdown["score"]["confidence"] in {"low", "medium"}
    # score stays in bounds
    assert 0 <= breakdown["score"]["value"] <= 100


def test_decision_gap_reflects_linked_decisions(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    linked = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)
    unlinked = build_debt_breakdown(conn, pid, "file", "src/copyclip/intelligence/server.py", now_ts=_NOW_TS)
    conn.close()

    linked_factor = next(f for f in linked["factor_breakdown"] if f["factor_id"] == "decision_gap")
    unlinked_factor = next(f for f in unlinked["factor_breakdown"] if f["factor_id"] == "decision_gap")
    assert linked_factor["normalized_contribution"] == 0.0  # fully linked
    assert unlinked_factor["normalized_contribution"] == 100.0  # no decision linkage
    assert any(ev.startswith("decision:") for ev in linked_factor["evidence"])


def test_test_evidence_gap_detects_module_with_tests(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    tested_file = build_debt_breakdown(conn, pid, "file", "tests/test_mcp.py", now_ts=_NOW_TS)
    untested = build_debt_breakdown(conn, pid, "file", "src/copyclip/intelligence/server.py", now_ts=_NOW_TS)
    conn.close()

    tested_factor = next(f for f in tested_file["factor_breakdown"] if f["factor_id"] == "test_evidence_gap")
    untested_factor = next(f for f in untested["factor_breakdown"] if f["factor_id"] == "test_evidence_gap")
    assert tested_factor["normalized_contribution"] == 0.0
    assert untested_factor["normalized_contribution"] == 100.0


def test_churn_pressure_scales_with_change_count(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    hot = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)
    cold = build_debt_breakdown(conn, pid, "file", "frontend/src/pages/AskPage.tsx", now_ts=_NOW_TS)
    conn.close()

    hot_factor = next(f for f in hot["factor_breakdown"] if f["factor_id"] == "churn_pressure")
    cold_factor = next(f for f in cold["factor_breakdown"] if f["factor_id"] == "churn_pressure")
    assert hot_factor["raw_signal"]["changes"] == 3
    assert cold_factor["raw_signal"]["changes"] == 0
    assert hot_factor["normalized_contribution"] > cold_factor["normalized_contribution"]


def test_ownership_ambiguity_uses_distinct_authors(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)
    conn.close()

    ownership = next(f for f in breakdown["factor_breakdown"] if f["factor_id"] == "ownership_ambiguity")
    # seeded 2 distinct authors (samuel + claude-bot)
    assert ownership["signal_available"] is True
    assert ownership["raw_signal"]["distinct_authors"] == 2


def test_severity_thresholds_are_applied(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS)
    conn.close()

    severity = breakdown["score"]["severity"]
    value = breakdown["score"]["value"]
    if value >= 75:
        assert severity == "critical"
    elif value >= 50:
        assert severity == "high"
    elif value >= 25:
        assert severity == "medium"
    else:
        assert severity == "low"


def test_module_breakdown_aggregates_member_files(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    breakdown = build_debt_breakdown(conn, pid, "module", "copyclip.mcp", now_ts=_NOW_TS)
    conn.close()

    assert breakdown["meta"]["scope_kind"] == "module"
    assert breakdown["meta"]["scope_id"] == "copyclip.mcp"
    assert breakdown["notes"]
    assert breakdown["notes"][0]["kind"] == "module_file_scores"
    assert any(item["path"] == "src/copyclip/mcp_server.py" for item in breakdown["notes"][0]["items"])


def test_project_breakdown_enumerates_modules(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    breakdown = build_debt_breakdown(conn, pid, "project", "copyclip", now_ts=_NOW_TS)
    conn.close()

    assert breakdown["meta"]["scope_kind"] == "project"
    module_scores = breakdown["notes"][0]["items"]
    assert {"copyclip.mcp", "copyclip.intelligence", "tests", "frontend.pages"} <= {row["module"] for row in module_scores}


def test_unknown_scope_raises(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))
    import pytest
    with pytest.raises(ValueError):
        build_debt_breakdown(conn, pid, "cluster", "foo", now_ts=_NOW_TS)
    with pytest.raises(ValueError):
        build_debt_breakdown(conn, pid, "module", "does.not.exist", now_ts=_NOW_TS)
    conn.close()


def test_breakdown_fingerprint_is_deterministic(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed(conn, str(tmp_path))

    a = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS, generated_at="2026-04-20T10:00:00Z")
    b = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=_NOW_TS, generated_at="2026-04-20T10:00:00Z")
    conn.close()

    assert breakdown_fingerprint(a) == breakdown_fingerprint(b)
