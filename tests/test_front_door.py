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


def test_copy_is_an_alias_of_export():
    # `copyclip copy` = the original copy-this-folder muscle memory; same pipeline.
    # Must reach the EXPORT parser (--extension only exists there), not the root help.
    out = subprocess.run([sys.executable, "-m", "copyclip", "copy", "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "--extension" in out.stdout
    assert "(bare)" not in out.stdout  # root-help epilog marker — wrong parser


def test_decisions_probe_never_plants_a_db(tmp_path):
    # The export/copy pipeline probes get_active_decisions on ANY folder. A
    # read-only probe must never create .copyclip/ — otherwise merely copying
    # a folder plants a DB, the folder starts "looking like a project", and a
    # later `copyclip .` there silently boots the full server instead of the
    # helpful not-a-project message.
    from copyclip.intelligence.db import get_active_decisions
    (tmp_path / "notes.md").write_text("hola", encoding="utf-8")
    assert get_active_decisions(str(tmp_path)) == []
    assert not (tmp_path / ".copyclip").exists()


def test_not_a_project_folder_is_not_a_dead_end(tmp_path):
    # A plain folder of notes is not a project — the front door must say what
    # you CAN do there (copy its contents / index it), never just refuse.
    (tmp_path / "brief.md").write_text("hola", encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "copyclip", str(tmp_path)],
                         capture_output=True, text=True, timeout=60)
    combined = out.stdout + out.stderr
    assert "is not a project folder" in combined
    assert "copyclip copy" in combined
    assert "copyclip analyze" in combined
