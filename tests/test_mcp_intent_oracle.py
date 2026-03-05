import os
import pytest
import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch
from copyclip.intelligence.db import connect, init_schema
from copyclip.mcp_server import handle_call_tool, handle_list_tools

@pytest.fixture
def temp_project(tmp_path):
    """Setup a temporary project with a copyclip intelligence DB."""
    root = tmp_path / "my_project"
    root.mkdir()
    
    # Pre-create the .copyclip folder so sqlite can open the file
    dot_copyclip = root / ".copyclip"
    dot_copyclip.mkdir()
    db_file = dot_copyclip / "intelligence.db"
    
    # Initialize DB
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        
        # Seed project
        conn.execute("INSERT INTO projects(root_path, name, story) VALUES(?,?,?)", 
                    (str(root), "Test Project", "The soul of testing"))
        
        # Seed an accepted decision
        conn.execute("INSERT INTO decisions(project_id, title, summary, status) VALUES(?,?,?,?)",
                    (1, "No Singletons", "We strictly avoid singletons in this project.", "accepted"))
        
        # Seed cognitive debt data
        conn.execute("INSERT INTO analysis_file_insights(project_id, path, module, cognitive_debt) VALUES(?,?,?,?)",
                    (1, "src/auth.py", "auth", 75.5))
        
        conn.commit()
        conn.close()
        
    return root

@pytest.mark.asyncio
async def test_list_tools():
    """Verify all 5 tools are exposed via MCP."""
    tools = await handle_list_tools()
    names = [t.name for t in tools]
    assert "get_intent_manifesto" in names
    assert "get_context_bundle" in names
    assert "audit_proposal" in names
    assert "log_decision_proposal" in names
    assert "get_cognitive_load" in names

@pytest.mark.asyncio
async def test_get_intent_manifesto(temp_project):
    """Test retrieving the intent manifesto from the DB."""
    db_file = temp_project / ".copyclip" / "intelligence.db"
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        res = await handle_call_tool("get_intent_manifesto", {"path": str(temp_project)})
        content = res[0].text
        
        assert "PROJECT INTENT MANIFESTO" in content
        assert "Test Project" in content
        assert "The soul of testing" in content
        assert "No Singletons" in content

@pytest.mark.asyncio
async def test_log_decision_proposal(temp_project):
    """Test that an agent can propose a new decision via MCP."""
    db_file = temp_project / ".copyclip" / "intelligence.db"
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        args = {
            "path": str(temp_project),
            "title": "Use WebGPU",
            "summary": "Prefer WebGPU over CPU for heavy calculations."
        }
        res = await handle_call_tool("log_decision_proposal", args)
        assert "Success: Decision" in res[0].text
        
        # Verify in DB
        from copyclip.intelligence.db import connect as real_connect
        conn = real_connect(str(temp_project))
        row = conn.execute("SELECT title, status, source_type FROM decisions WHERE title='Use WebGPU'").fetchone()
        assert row["status"] == "proposed"
        assert row["source_type"] == "agent"
        conn.close()

@pytest.mark.asyncio
async def test_get_cognitive_load(temp_project):
    """Test retrieving the 'Fog of War' map via MCP."""
    db_file = temp_project / ".copyclip" / "intelligence.db"
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)):
        res = await handle_call_tool("get_cognitive_load", {"path": str(temp_project)})
        content = res[0].text
        
        assert "FOG OF WAR" in content
        assert "auth" in content
        assert "🔴 HIGH" in content
        assert "Debt: 75.5" in content

@pytest.mark.asyncio
async def test_audit_proposal_semantic(temp_project):
    """Test the semantic audit loop (Phase 2)."""
    db_file = temp_project / ".copyclip" / "intelligence.db"
    
    # We mock the LLM call
    mock_client = AsyncMock()
    mock_client.minimize_code_contextually.return_value = "Status: REJECTED\nScore: 90\nReason: This diff introduces a Singleton pattern."
    
    with patch("copyclip.intelligence.db.db_path", return_value=str(db_file)), \
         patch("copyclip.llm_client.LLMClientFactory.create", return_value=mock_client):
        
        # Link 'src/auth.py' to Decision #1 (No Singletons)
        from copyclip.intelligence.db import connect as real_connect
        conn = real_connect(str(temp_project))
        conn.execute("INSERT INTO decision_links(project_id, decision_id, link_type, target_pattern) VALUES(?,?,?,?)",
                    (1, 1, "file_glob", "src/auth.py"))
        conn.commit()
        conn.close()
        
        diff = """
--- a/src/auth.py
+++ b/src/auth.py
+class AuthManager:
+    _instance = None
+    def __new__(cls):
+        if not cls._instance:
+            cls._instance = super().__new__(cls)
+        return cls._instance
        """
        
        args = {"path": str(temp_project), "proposed_diff": diff}
        res = await handle_call_tool("audit_proposal", args)
        
        assert "INTENT AUDIT REPORT" in res[0].text
        assert "REJECTED" in res[0].text
        assert "Score: 90" in res[0].text
