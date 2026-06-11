from copyclip.intelligence.cuaderno.read_ledger import (
    is_content_bearing_read, ReadLedger,
)


def test_read_file_with_lines_is_content_bearing():
    assert is_content_bearing_read("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})


def test_read_file_error_is_not_content_bearing():
    assert not is_content_bearing_read("read_file", {"error": "file_not_found", "path": "a.py"})


def test_empty_grep_symbols_is_not_content_bearing():
    assert not is_content_bearing_read("grep_symbols", {"symbols": []})


def test_nonempty_grep_symbols_is_content_bearing():
    assert is_content_bearing_read("grep_symbols", {"symbols": [{"name": "f"}]})


def test_list_dir_with_entries_is_content_bearing():
    assert is_content_bearing_read("list_dir", {"path": ".", "entries": ["a", "b"]})


def test_answer_tools_are_never_content_bearing_reads():
    assert not is_content_bearing_read("emit_block", {"kind": "lead", "text": "x"})
    assert not is_content_bearing_read("finish", {"ok": True})


def test_ledger_counts_and_paths():
    led = ReadLedger()
    led.record("list_dir", {"path": ".", "entries": ["a"]})
    led.record("read_file", {"path": "src/a.py", "lines": [{"n": 1, "text": "x"}]})
    led.record("read_file", {"error": "file_not_found", "path": "missing.py"})
    assert led.content_bearing_count == 2
    assert "src/a.py" in led.read_paths
    assert "missing.py" not in led.read_paths


# ── Wave 4 tools count as real evidence (close the gate's blind spot) ────────

def test_get_risks_is_content_bearing():
    assert is_content_bearing_read("get_risks", {"risks": [{"area": "a.py", "score": 9}]})
    assert not is_content_bearing_read("get_risks", {"risks": []})


def test_get_decisions_is_content_bearing():
    assert is_content_bearing_read("get_decisions", {"decisions": [{"id": 1}]})
    assert not is_content_bearing_read("get_decisions", {"decisions": []})


def test_get_reverse_dependents_is_content_bearing():
    assert is_content_bearing_read(
        "get_reverse_dependents", {"target_module": "core", "impacted_modules": ["api"]}
    )
    assert not is_content_bearing_read(
        "get_reverse_dependents", {"target_module": "unknown", "impacted_modules": []}
    )


def test_get_story_snapshots_is_content_bearing():
    assert is_content_bearing_read("get_story_snapshots", {"snapshots": [{"generated_at": "t"}]})
    assert not is_content_bearing_read("get_story_snapshots", {"snapshots": [], "note": "none"})


def test_reacquaintance_with_changes_is_content_bearing():
    assert is_content_bearing_read(
        "get_reacquaintance_briefing", {"meta": {}, "top_changes": [{"x": 1}], "read_first": []}
    )
    assert not is_content_bearing_read(
        "get_reacquaintance_briefing",
        {"meta": {}, "top_changes": [], "read_first": [], "relevant_decisions": []},
    )


def test_ledger_harvests_risk_area_as_evidence_path():
    """A risk's file is citable: the tutor can cite src/foo.py and the gate must
    recognize it as tool-evidenced, not fabricated."""
    led = ReadLedger()
    led.record("get_risks", {"risks": [{"area": "src/foo.py", "file_path": "src/foo.py", "score": 9}]})
    assert "src/foo.py" in led.evidence_paths
