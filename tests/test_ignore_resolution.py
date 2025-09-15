import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from copyclip.__main__ import _get_copyclip_ignore_file
from copyclip.scanner import scan_files


def test_copyclip_ignore_from_installation(tmp_path, monkeypatch):
    # Mock the module location to return our test directory
    test_module_dir = tmp_path / "src" / "copyclip"
    test_module_dir.mkdir(parents=True)
    
    # Create a fake .copyclipignore in the project root
    project_root = tmp_path
    (project_root / ".copyclipignore").write_text("*.pyc\n__pycache__\n.venv\n")
    
    # Mock __file__ to point to our test module
    monkeypatch.setattr("copyclip.__main__.__file__", str(test_module_dir / "__main__.py"))
    
    # Should find the .copyclipignore in project root
    ignore_file = _get_copyclip_ignore_file()
    assert ignore_file == str(project_root / ".copyclipignore")


def test_scan_with_copyclip_ignore(tmp_path):
    # Setup test directory structure
    project = tmp_path / "project"
    project.mkdir()
    (project / "keep.py").write_text("print('keep')")
    (project / "test.pyc").write_text("compiled")
    
    cache_dir = project / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "cached.py").write_text("cached")
    
    venv_dir = project / ".venv"
    venv_dir.mkdir()
    (venv_dir / "lib.py").write_text("venv file")
    
    # Create ignore file
    (project / ".copyclipignore").write_text("*.pyc\n__pycache__\n.venv\n")
    
    # Scan with the ignore file
    files = scan_files(str(project), ignore_file_path=str(project / ".copyclipignore"))
    basenames = {os.path.basename(p) for p in files}
    
    # Should include only keep.py
    assert "keep.py" in basenames
    assert "test.pyc" not in basenames
    assert "cached.py" not in basenames
    assert "lib.py" not in basenames