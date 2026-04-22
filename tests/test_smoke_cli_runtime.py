import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import request


ROOT_DIR = Path(__file__).resolve().parents[1]


def _make_minimal_project(tmp_path: Path) -> Path:
    root = tmp_path / "demo_project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "demo.py").write_text('def add(a, b):\n    return a + b\n', encoding="utf-8")
    return root


def test_copyclip_analyze_cli_smoke(tmp_path):
    root = _make_minimal_project(tmp_path)

    result = subprocess.run(
        ["copyclip", "analyze", "--path", str(root)],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, output
    assert "Indexed" in output
    assert (root / ".copyclip" / "intelligence.db").exists()


def test_copyclip_mcp_cli_smoke_exits_cleanly_when_stdin_is_closed(tmp_path):
    root = _make_minimal_project(tmp_path)

    result = subprocess.run(
        ["copyclip", "mcp"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, output
    assert "Traceback" not in output


def test_copyclip_start_cli_smoke_serves_health_and_overview(tmp_path):
    root = _make_minimal_project(tmp_path)
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "copyclip", "start", "--no-open", "--path", str(root), "--port", "0"],
        cwd=ROOT_DIR,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_lines: list[str] = []
    dash_url = None
    deadline = time.time() + 30
    try:
        while time.time() < deadline:
            line = process.stdout.readline()
            if line:
                output_lines.append(line)
                if "CopyClip Intelligence running at" in line:
                    dash_url = line.split("CopyClip Intelligence running at", 1)[1].strip()
                    break
            elif process.poll() is not None:
                break
            else:
                time.sleep(0.1)

        output = "".join(output_lines)
        assert dash_url, output or "copyclip start exited before reporting dashboard URL"

        health = json.loads(request.urlopen(f"{dash_url}/api/health", timeout=10).read().decode("utf-8"))
        overview = json.loads(request.urlopen(f"{dash_url}/api/overview", timeout=10).read().decode("utf-8"))

        assert health["ok"] is True
        assert overview["files"] >= 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
