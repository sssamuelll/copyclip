import os
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from copyclip.intelligence.db import db_path, connect, init_schema, get_active_decisions
from copyclip.intelligence.analyzer import _module_from_relpath, _analyze_git_folder
from copyclip.intelligence.server import _project_id

def test_db_isolation(tmp_path):
    """Verify that different project roots create separate isolated DBs."""
    proj1 = tmp_path / "project1"
    proj2 = tmp_path / "project2"
    proj1.mkdir()
    proj2.mkdir()
    
    path1 = db_path(str(proj1))
    path2 = db_path(str(proj2))
    
    assert ".copyclip" in path1
    assert str(proj1) in path1
    assert str(proj2) in path2
    assert path1 != path2

def test_module_extraction():
    """Verify how we categorize files into modules."""
    assert _module_from_relpath("src/api/auth.py") == "api"
    assert _module_from_relpath("lib/utils/helper.js") == "utils"
    assert _module_from_relpath("README.md") == "root"
    assert _module_from_relpath("app/main.py") == "main.py"

def test_git_folder_analysis(tmp_path):
    """Test git stats gathering without real git."""
    proj = tmp_path / "git_proj"
    proj.mkdir()
    git_dir = proj / ".git"
    git_dir.mkdir()
    (git_dir / "some_pack").write_text("dummy data")
    
    # Mock _safe_git to return dummy branch/tag info
    with patch("copyclip.intelligence.analyzer._safe_git") as mock_git:
        mock_git.side_effect = lambda root, args: "  main\n* dev" if "branch" in args[0] else "v1.0"
        
        conn = sqlite3.connect(":memory:")
        stats = _analyze_git_folder(str(proj), 1, conn)
        
        assert stats["branches_count"] == 2
        assert stats["tags_count"] == 1
        assert stats["git_size_kb"] >= 0

def test_get_active_decisions(tmp_path):
    """Verify we only fetch accepted or resolved decisions."""
    root = str(tmp_path)
    conn = connect(root)
    init_schema(conn)
    
    pid = 1
    conn.execute("INSERT INTO projects (id, root_path, name) VALUES (?,?,?)", (pid, root, "test"))
    conn.execute(
        "INSERT INTO decisions (project_id, title, summary, status) VALUES (?,?,?,?)",
        (pid, "D1", "Accepted Rule", "accepted")
    )
    conn.execute(
        "INSERT INTO decisions (project_id, title, summary, status) VALUES (?,?,?,?)",
        (pid, "D2", "Proposed Rule", "proposed")
    )
    conn.execute(
        "INSERT INTO decisions (project_id, title, summary, status) VALUES (?,?,?,?)",
        (pid, "D3", "Resolved Rule", "resolved")
    )
    conn.commit()
    conn.close()
    
    decisions = get_active_decisions(root)
    titles = [d["title"] for d in decisions]
    
    assert "D1" in titles
    assert "D3" in titles
    assert "D2" not in titles
