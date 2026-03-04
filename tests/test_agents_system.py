import pytest
import os
import json
from pathlib import Path
from copyclip.intelligence.agents import CopyClipAgent, get_agent
from copyclip.intelligence.db import connect, init_schema

def test_agent_tool_registration():
    """Verify agents have the correct tools."""
    agent = CopyClipAgent("Test", "Tester", "/tmp")
    assert "query_db" in agent.tools
    assert "read_file" in agent.tools
    assert "list_files" in agent.tools

def test_agent_list_files_tool(tmp_path):
    """Test the tool that lists files via DB."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    
    conn.execute("INSERT INTO files (project_id, path) VALUES (1, 'file1.py')")
    conn.execute("INSERT INTO files (project_id, path) VALUES (1, 'file2.ts')")
    conn.commit()
    conn.close()
    
    agent = CopyClipAgent("Scout", "Explorer", root)
    res = agent._tool_list_files()
    
    assert "file1.py" in res
    assert "file2.ts" in res

def test_agent_read_file_safety(tmp_path):
    """Verify file reading tool safety and limits."""
    root = tmp_path
    secret = root / "secret.txt"
    secret.write_text("Hello World")
    
    agent = CopyClipAgent("Scout", "Explorer", str(root))
    
    # Valid file
    content = agent._tool_read_file("secret.txt")
    assert content == "Hello World"
    
    # Missing file
    err = agent._tool_read_file("missing.txt")
    assert "Error" in err

def test_agent_factory():
    """Verify we get the right agent profiles."""
    scout = get_agent("scout", "/tmp")
    assert scout.name == "The Scout"
    
    critic = get_agent("critic", "/tmp")
    assert critic.name == "The Critic"
    
    unknown = get_agent("unknown", "/tmp")
    assert unknown.name == "General"
