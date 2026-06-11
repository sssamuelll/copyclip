"""The persisted cognitive_debt column must hold the LIVE 8-factor composite
(build_debt_breakdown), not the dead single-factor scalar. This collapses the
two debt lineages: the fog, the MCP map, and handoff risks all read this column,
so feeding it from the live engine fixes all three at once."""
import sqlite3

from copyclip.intelligence.db import init_schema
from copyclip.intelligence.cognitive_debt import build_debt_breakdown
from copyclip.intelligence.analyzer import _persist_composite_scores
from tests.fixtures.cog_debt_fixtures import seed_mixed_debt_project


def test_persist_composite_overwrites_column_with_live_engine(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))

    # the fixture seeds the DEAD single-factor value for mcp_server.py
    before = conn.execute(
        "SELECT cognitive_debt FROM analysis_file_insights WHERE project_id=? AND path=?",
        (pid, "src/copyclip/mcp_server.py"),
    ).fetchone()[0]
    assert before == 86.0

    _persist_composite_scores(conn, pid)

    # after: EVERY file's column equals its live composite score
    for path in (
        "src/copyclip/mcp_server.py",
        "src/copyclip/ask/answer.py",
        "src/copyclip/new_module.py",
    ):
        col = conn.execute(
            "SELECT cognitive_debt FROM analysis_file_insights WHERE project_id=? AND path=?",
            (pid, path),
        ).fetchone()[0]
        live = round(float(build_debt_breakdown(conn, pid, "file", path)["score"]["value"] or 0.0), 2)
        assert col == live, f"{path}: column {col} != live composite {live}"

    # and the dead single-factor value is gone (the column actually changed)
    after_mcp = conn.execute(
        "SELECT cognitive_debt FROM analysis_file_insights WHERE project_id=? AND path=?",
        (pid, "src/copyclip/mcp_server.py"),
    ).fetchone()[0]
    assert after_mcp != 86.0
