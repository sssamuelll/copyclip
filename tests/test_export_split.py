"""--split-lines: chunked clipboard export for paste-limited surfaces.

pack_chunks is the pure core: greedy file-boundary packing (a file block never
splits across chunks if it fits whole in one), hard-splitting only blocks that
alone exceed the budget — with an honest '(continued):' header on each slice.
"""
import subprocess
import sys

from copyclip.__main__ import pack_chunks


FILE_A = "a.py:\nline1\nline2\nline3"          # 4 lines
FILE_B = "b.py:\nuno\ndos"                     # 3 lines
FILE_C = "c.md:\nx"                            # 2 lines


def test_everything_fits_in_one_chunk():
    chunks = pack_chunks([FILE_A, FILE_B], max_lines=100)
    assert chunks == [FILE_A + "\n\n" + FILE_B]


def test_packs_at_file_boundaries_never_mid_file():
    # budget of 8: A(4) + joiner(1) + B(3) = 8 fits; C starts chunk 2
    chunks = pack_chunks([FILE_A, FILE_B, FILE_C], max_lines=8)
    assert chunks == [FILE_A + "\n\n" + FILE_B, FILE_C]


def test_file_that_would_overflow_moves_whole_to_next_chunk():
    # budget of 6: A(4) fits; B would need 4+1+3=8 -> B moves whole
    chunks = pack_chunks([FILE_A, FILE_B], max_lines=6)
    assert chunks == [FILE_A, FILE_B]


def test_oversize_single_block_hard_splits_with_continued_header():
    big = "big.py:\n" + "\n".join(f"l{i}" for i in range(1, 10))  # 10 lines
    chunks = pack_chunks([big], max_lines=6)
    # slice 1: header + l1..l5 (6 lines); slice 2: continued header + l6..l9
    assert chunks[0] == "big.py:\nl1\nl2\nl3\nl4\nl5"
    assert chunks[1] == "big.py (continued):\nl6\nl7\nl8\nl9"
    assert all(c.count("\n") + 1 <= 6 for c in chunks)


def test_oversize_block_without_header_colon_gets_generic_continuation():
    blob = "\n".join(f"x{i}" for i in range(1, 8))  # 7 lines, no 'path:' first line
    chunks = pack_chunks([blob], max_lines=4)
    assert chunks[0] == "x1\nx2\nx3\nx4"
    assert chunks[1].startswith("(continued)\n")
    assert all(c.count("\n") + 1 <= 4 for c in chunks)


def test_oversize_block_neighbors_still_pack_around_it():
    big = "big.py:\n" + "\n".join(f"l{i}" for i in range(1, 8))  # 8 lines
    chunks = pack_chunks([FILE_C, big, FILE_B], max_lines=5)
    # C alone (big won't fit after it), big split into 2, B packs after? No —
    # slices of big fill their own chunks; B starts fresh.
    assert chunks[0] == FILE_C
    assert chunks[1] == "big.py:\nl1\nl2\nl3\nl4"
    assert chunks[2] == "big.py (continued):\nl5\nl6\nl7"
    assert chunks[3] == FILE_B


def test_empty_parts_yield_no_chunks():
    assert pack_chunks([], max_lines=10) == []


def test_interactive_loop_copies_each_part_with_markers(tmp_path, monkeypatch):
    # Wiring test: run_export with --split-lines delivers every chunk to the
    # clipboard in order, each with its part marker, waiting for Enter between.
    from copyclip import __main__ as m

    (tmp_path / "one.md").write_text("\n".join(f"a{i}" for i in range(1, 21)), encoding="utf-8")
    (tmp_path / "two.md").write_text("\n".join(f"b{i}" for i in range(1, 21)), encoding="utf-8")

    copied = []

    class FakeClipboard:
        def copy(self, text):
            copied.append(text)
            return True

    enters = iter(["", "", "", ""])
    monkeypatch.setattr(m, "ClipboardManager", FakeClipboard)
    monkeypatch.setattr("builtins.input", lambda *a: next(enters))
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": staticmethod(lambda: True)})())

    m.run_export([str(tmp_path), "--split-lines", "25", "--view", "text", "--no-progress"])

    assert len(copied) >= 2
    for i, payload in enumerate(copied, 1):
        assert payload.startswith(f"--- copyclip part {i}/{len(copied)} ---\n")
    # every content line of both files made it across, in order
    joined = "\n".join(copied)
    for token in ["a1", "a20", "b1", "b20"]:
        assert token in joined


def test_split_lines_flag_in_help():
    out = subprocess.run([sys.executable, "-m", "copyclip", "copy", "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "--split-lines" in out.stdout
