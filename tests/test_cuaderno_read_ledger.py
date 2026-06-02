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
