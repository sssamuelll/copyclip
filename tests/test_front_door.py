"""Front door: bare copyclip = the shell; export is an explicit subcommand."""
import subprocess
import sys

from copyclip.__main__ import classify_bare_invocation


def test_bare_invocation_routes_to_start():
    assert classify_bare_invocation(["copyclip"]) == ("start", ".")


def test_positional_folder_routes_to_start_with_path():
    assert classify_bare_invocation(["copyclip", "./myapp"]) == ("start", "./myapp")


def test_export_flag_on_bare_invocation_is_an_error():
    kind, detail = classify_bare_invocation(["copyclip", ".", "--minimize", "basic"])
    assert kind == "error"
    assert "--minimize" in detail


def test_export_flag_with_equals_detected():
    kind, detail = classify_bare_invocation(["copyclip", "--minimize=basic"])
    assert kind == "error"


def test_export_subcommand_help_smoke():
    out = subprocess.run([sys.executable, "-m", "copyclip", "export", "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "--minimize" in out.stdout


def test_bare_help_carries_the_claim():
    out = subprocess.run([sys.executable, "-m", "copyclip", "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "understanding your own codebase" in out.stdout
    assert "Intent Authority" not in out.stdout


def test_export_flag_bare_invocation_exits_2():
    out = subprocess.run([sys.executable, "-m", "copyclip", ".", "--minimize", "basic"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 2
    assert "copyclip export" in out.stderr
