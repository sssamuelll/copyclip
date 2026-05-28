import tempfile
from pathlib import Path

from copyclip.intelligence.cuaderno.anchor import read_file


def test_read_file_returns_lines_with_numbers(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = read_file(str(tmp_path), "src/foo.py")
    assert out["path"] == "src/foo.py"
    assert out["lines"] == [
        {"n": 1, "text": "a"},
        {"n": 2, "text": "b"},
        {"n": 3, "text": "c"},
        {"n": 4, "text": "d"},
        {"n": 5, "text": "e"},
    ]


def test_read_file_with_line_range_slices(tmp_path: Path):
    (tmp_path / "x.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = read_file(str(tmp_path), "x.py", line_start=2, line_end=4)
    assert [r["n"] for r in out["lines"]] == [2, 3, 4]
    assert [r["text"] for r in out["lines"]] == ["b", "c", "d"]


def test_read_file_rejects_path_escaping_root(tmp_path: Path):
    (tmp_path / "x.py").write_text("hi", encoding="utf-8")
    out = read_file(str(tmp_path), "../etc/passwd")
    assert out == {"error": "path_outside_root"}


def test_read_file_missing(tmp_path: Path):
    out = read_file(str(tmp_path), "nope.py")
    assert out == {"error": "file_not_found", "path": "nope.py"}
