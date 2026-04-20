"""Integration tests for cognitive debt signals flowing into Reacquaintance and Ask Project.

These cover the #51 acceptance criterion: debt should influence re-entry prioritization
and Ask Project's evidence presentation without siloing it in its own dashboard.
"""

from copyclip.intelligence.cognitive_debt import quick_debt_signal
from copyclip.intelligence.db import connect, init_schema, get_or_create_project
from copyclip.intelligence.reacquaintance import build_reacquaintance_briefing, record_reacquaintance_visit
from copyclip.intelligence.ask_project import build_ask_response


def _seed_debt_project(conn, root: str, *, debt_for_server: float = 82.0, debt_for_ask: float = 10.0) -> int:
    pid = get_or_create_project(conn, root, name="copyclip")
    files = [
        ("src/copyclip/intelligence/server.py", "copyclip.intelligence", debt_for_server, 0.72, 1_600_000_000.0),
        ("src/copyclip/ask/answer.py", "copyclip.ask", debt_for_ask, 0.05, 1_700_000_000.0),
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
    # Seed churn and risk so both files surface as read_first candidates
    for i, (sha, author, date) in enumerate([
        ("sha-a", "samuel", "2026-04-10T10:00:00+00:00"),
        ("sha-b", "claude-bot", "2026-04-18T12:00:00+00:00"),
    ]):
        conn.execute("INSERT INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)", (pid, sha, author, date, f"m-{sha}"))
    for sha, path in [("sha-a", "src/copyclip/intelligence/server.py"), ("sha-b", "src/copyclip/ask/answer.py")]:
        conn.execute(
            "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)",
            (pid, sha, path, 20, 5),
        )
    # Risk on both so ranking isn't purely from churn
    conn.execute(
        "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/intelligence/server.py", "high", "intent_drift", "...", 88),
    )
    conn.execute(
        "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/ask/answer.py", "high", "intent_drift", "...", 88),
    )
    # Decision pointing at the Ask file so it surfaces in ask evidence
    conn.execute(
        "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
        (pid, "Use evidence-first Ask responses", "Answers must be grounded.", "accepted", "manual"),
    )
    conn.execute("INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)", (1, "file", "src/copyclip/ask/answer.py"))
    conn.commit()
    return pid


def test_quick_debt_signal_returns_severity_and_primary_signal(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_debt_project(conn, str(tmp_path))

    signal = quick_debt_signal(conn, pid, "src/copyclip/intelligence/server.py")
    conn.close()

    assert signal is not None
    assert signal["value"] >= 75
    assert signal["severity"] == "critical"
    assert signal["primary_signal"] == "agent_authored_ratio"


def test_quick_debt_signal_returns_none_for_unknown_path(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = _seed_debt_project(conn, str(tmp_path))

    assert quick_debt_signal(conn, pid, "does/not/exist.py") is None
    conn.close()


def test_reacquaintance_read_first_carries_debt_signal(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    _seed_debt_project(conn, root)
    conn.close()
    record_reacquaintance_visit(root)

    briefing = build_reacquaintance_briefing(root, baseline_mode="window", window="7d")
    for item in briefing["read_first"]:
        assert "debt_signal" in item
    # the high-debt file should surface as read_first with a debt_signal
    entry = next((i for i in briefing["read_first"] if i["target"] == "src/copyclip/intelligence/server.py"), None)
    assert entry is not None
    assert entry["debt_signal"]["severity"] in {"critical", "high"}
    assert "Dark zone" in entry["reason"]


def test_reacquaintance_prioritizes_high_debt_over_equal_signal_low_debt(tmp_path):
    """Ties on change/risk/decision should break toward the darker file."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    _seed_debt_project(conn, root, debt_for_server=90.0, debt_for_ask=5.0)
    conn.close()
    record_reacquaintance_visit(root)

    briefing = build_reacquaintance_briefing(root, baseline_mode="window", window="7d")
    ordered = briefing["read_first"]
    if len(ordered) >= 2:
        assert ordered[0]["target"] == "src/copyclip/intelligence/server.py"


def test_ask_response_exposes_debt_hints_for_touched_files(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_debt_project(conn, root)

    response = build_ask_response(conn, pid, "what is happening in the intelligence server")
    conn.close()

    assert "debt_hints" in response
    # server.py has debt 82 → must surface at least one debt hint when it appears in evidence
    if response.get("grounded"):
        hinted_targets = {hint["target"] for hint in response["debt_hints"]}
        # intelligence/server is high debt; if it's in evidence, it should appear
        file_ids = {item["id"] for item in response["evidence"]["files"]}
        if "src/copyclip/intelligence/server.py" in file_ids:
            assert "src/copyclip/intelligence/server.py" in hinted_targets


def test_ask_response_biases_drill_down_to_critical_debt_file(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_debt_project(conn, root)

    response = build_ask_response(conn, pid, "look at the intelligence server implementation")
    conn.close()

    if response.get("grounded"):
        file_ids = {item["id"] for item in response["evidence"]["files"]}
        if "src/copyclip/intelligence/server.py" in file_ids:
            assert response["next_drill_down"]["type"] == "file"
            assert response["next_drill_down"]["target"] == "src/copyclip/intelligence/server.py"


def test_ask_response_low_debt_file_does_not_appear_in_debt_hints(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = _seed_debt_project(conn, root, debt_for_server=10.0, debt_for_ask=5.0)

    response = build_ask_response(conn, pid, "evidence first ask implementation")
    conn.close()

    # All files below the medium threshold: no debt_hints entries expected
    assert response.get("debt_hints") == []


def test_ask_insufficient_response_still_returns_debt_hints_field(tmp_path):
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    pid = get_or_create_project(conn, root, name="copyclip-minimal")

    response = build_ask_response(conn, pid, "zzz nonsense question with no evidence")
    conn.close()

    assert "debt_hints" in response
    assert response["debt_hints"] == []
