import json
import sqlite3
from unittest.mock import patch

import pytest

from copyclip.intelligence.db import init_schema
from copyclip.mcp_server import handle_call_tool, handle_list_tools


def _seed_project(db_file, root: str) -> int:
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path, name, story) VALUES(?,?,?)", (root, "copyclip", "bounded delegation"))
    pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0]
    conn.execute(
        "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
        (pid, "Use bounded MCP handoff packets", "Delegation should use bounded packets.", "accepted", "manual"),
    )
    conn.execute(
        "INSERT INTO decision_refs(decision_id, ref_type, ref_value) VALUES(?,?,?)",
        (1, "file", "src/copyclip/mcp_server.py"),
    )
    conn.execute(
        "INSERT INTO files(project_id, path, language, size_bytes, mtime, hash) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "python", 1200, 1.0, "h-mcp"),
    )
    conn.execute(
        "INSERT INTO risks(project_id, area, severity, kind, rationale, score) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "high", "intent_drift", "MCP delivery can bypass bounded delegation.", 93),
    )
    conn.execute(
        "INSERT INTO analysis_file_insights(project_id, path, module, imports_json, complexity, cognitive_debt) VALUES(?,?,?,?,?,?)",
        (pid, "src/copyclip/mcp_server.py", "copyclip.mcp", "[]", 14, 82.0),
    )
    conn.commit()
    conn.close()
    return pid


@pytest.fixture
def temp_project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".copyclip").mkdir()
    db_file = root / ".copyclip" / "intelligence.db"
    _seed_project(db_file, str(root))
    return root


@pytest.mark.asyncio
async def test_list_tools_includes_handoff_tools():
    tools = await handle_list_tools()
    names = [t.name for t in tools]
    assert "list_handoff_packets" in names
    assert "get_handoff_packet" in names
    assert "submit_handoff_review" in names


@pytest.mark.asyncio
async def test_list_handoff_packets_returns_only_consumable_states_by_default(temp_project):
    db_file = temp_project / ".copyclip" / "intelligence.db"
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        # create a draft packet (blocks consumption) and a ready_for_review packet via create endpoint path
        from copyclip.intelligence.db import connect as _connect
        from copyclip.intelligence.handoff import build_handoff_packet, save_handoff_packet, update_handoff_packet

        conn = _connect(str(temp_project))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (str(temp_project),)).fetchone()[0]

        draft = build_handoff_packet(conn, pid, task_prompt="Help", declared_files=[], declared_modules=[], generated_at="2026-04-20T10:00:00Z")
        save_handoff_packet(conn, pid, draft)  # state=draft

        ready = build_handoff_packet(conn, pid, task_prompt="Bounded MCP", declared_files=["src/copyclip/mcp_server.py"], acceptance_criteria=["ok"], generated_at="2026-04-20T10:05:00Z")
        save_handoff_packet(conn, pid, ready)  # state=ready_for_review

        approved = build_handoff_packet(conn, pid, task_prompt="Approved work", declared_files=["src/copyclip/mcp_server.py"], acceptance_criteria=["ok"], generated_at="2026-04-20T10:10:00Z")
        save_handoff_packet(conn, pid, approved)
        update_handoff_packet(conn, pid, approved["meta"]["packet_id"], {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"})
        conn.commit()
        conn.close()

        res = await handle_call_tool("list_handoff_packets", {"path": str(temp_project)})
        text = res[0].text
        assert "approved_for_handoff" in text
        # default filter excludes draft and ready_for_review
        assert "draft" not in text.lower() or "draft_packets=0" in text.lower() or "- state: draft" not in text

        res_all = await handle_call_tool("list_handoff_packets", {"path": str(temp_project), "state": "all"})
        text_all = res_all[0].text
        assert "draft" in text_all.lower()


@pytest.mark.asyncio
async def test_get_handoff_packet_returns_bounded_projection(temp_project):
    db_file = temp_project / ".copyclip" / "intelligence.db"
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        from copyclip.intelligence.db import connect as _connect
        from copyclip.intelligence.handoff import build_handoff_packet, save_handoff_packet, update_handoff_packet

        conn = _connect(str(temp_project))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (str(temp_project),)).fetchone()[0]
        packet = build_handoff_packet(
            conn, pid,
            task_prompt="Bounded MCP delegation.",
            declared_files=["src/copyclip/mcp_server.py"],
            do_not_touch=[{"target": "frontend", "reason": "UI excluded.", "severity": "hard_boundary"}],
            acceptance_criteria=["Delegation stays bounded."],
            generated_at="2026-04-20T10:00:00Z",
        )
        save_handoff_packet(conn, pid, packet)
        update_handoff_packet(conn, pid, packet["meta"]["packet_id"], {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"})
        conn.commit()
        packet_id = packet["meta"]["packet_id"]
        conn.close()

        res = await handle_call_tool("get_handoff_packet", {"path": str(temp_project), "packet_id": packet_id})
        text = res[0].text
        assert packet_id in text
        assert "allowed_write_scope" in text
        assert "src/copyclip/mcp_server.py" in text
        assert "frontend" in text
        # bounded: must not leak internal fields
        assert "evidence_index" not in text
        assert "bundle_manifest" not in text
        assert "approved_by" not in text


@pytest.mark.asyncio
async def test_submit_handoff_review_generates_and_persists_review(temp_project):
    db_file = temp_project / ".copyclip" / "intelligence.db"
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        from copyclip.intelligence.db import connect as _connect
        from copyclip.intelligence.handoff import (
            build_handoff_packet,
            get_handoff_review_summary,
            save_handoff_packet,
            update_handoff_packet,
        )

        conn = _connect(str(temp_project))
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (str(temp_project),)).fetchone()[0]
        packet = build_handoff_packet(
            conn, pid,
            task_prompt="Bounded MCP delegation.",
            declared_files=["src/copyclip/mcp_server.py"],
            acceptance_criteria=["OK"],
            generated_at="2026-04-20T10:00:00Z",
        )
        save_handoff_packet(conn, pid, packet)
        pid_str = packet["meta"]["packet_id"]
        update_handoff_packet(conn, pid, pid_str, {"state": "approved_for_handoff", "approved_by": "samuel", "delegation_target": "claude-code"})
        update_handoff_packet(conn, pid, pid_str, {"state": "delegated"})
        update_handoff_packet(conn, pid, pid_str, {"state": "change_received"})
        conn.commit()
        conn.close()

        res = await handle_call_tool(
            "submit_handoff_review",
            {"path": str(temp_project), "packet_id": pid_str, "touched_files": ["src/copyclip/mcp_server.py"]},
        )
        text = res[0].text
        assert "verdict" in text.lower()
        assert "accepted" in text.lower()

        # persisted
        conn = _connect(str(temp_project))
        summary = get_handoff_review_summary(conn, pid, pid_str)
        conn.close()
        assert summary is not None
        assert summary["meta"]["packet_id"] == pid_str
