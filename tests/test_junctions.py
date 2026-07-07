from copyclip.intelligence.cuaderno.junctions import compute_junctions

SRC_IF_ELSE = (
    "\n"
    "def f(x):\n"          # line 2
    "    if x > 0:\n"      # line 3
    "        a = 1\n"      # line 4
    "        b = 2\n"      # line 5
    "    else:\n"          # line 6
    "        a = -1\n"     # line 7
    "    return a\n"       # line 8
)

SRC_LADDER = (
    "\n"
    "def g(x):\n"          # 2
    "    if x == 1:\n"     # 3
    "        r = 'a'\n"    # 4
    "    elif x == 2:\n"   # 5
    "        r = 'b'\n"    # 6
    "    else:\n"          # 7
    "        r = 'c'\n"    # 8
    "    return r\n"       # 9
)

SRC_BARE_IF = (
    "\n"
    "def h(x):\n"          # 2
    "    y = 0\n"          # 3
    "    if x:\n"          # 4
    "        y = 1\n"      # 5
    "    return y\n"       # 6
)

SRC_NESTED = (
    "\n"
    "def n(x):\n"          # 2
    "    if x > 0:\n"      # 3
    "        if x > 10:\n" # 4
    "            a = 2\n"  # 5
    "        else:\n"      # 6
    "            a = 1\n"  # 7
    "    else:\n"          # 8
    "        a = 0\n"      # 9
    "    return a\n"       # 10
)

SRC_NESTED_DEF = (
    "\n"
    "def outer(x):\n"          # 2
    "    def inner(y):\n"      # 3
    "        if y:\n"          # 4
    "            return 1\n"   # 5
    "        return 0\n"       # 6
    "    if x:\n"              # 7
    "        return inner(x)\n"# 8
    "    return -1\n"          # 9
)


def test_if_else_took_if():
    j = compute_junctions(SRC_IF_ELSE, 2, "f", {3, 4, 5, 8}, False)
    assert j == [{"test_line": 3, "arms": [
        {"kind": "if", "lines": [4, 5], "taken": True},
        {"kind": "else", "lines": [7, 7], "taken": False},
    ]}]


def test_if_else_took_else():
    j = compute_junctions(SRC_IF_ELSE, 2, "f", {3, 7, 8}, False)
    arms = j[0]["arms"]
    assert arms[0]["taken"] is False
    assert arms[1]["taken"] is True


def test_ladder_took_elif():
    j = compute_junctions(SRC_LADDER, 2, "g", {3, 5, 6, 9}, False)
    assert j == [{"test_line": 3, "arms": [
        {"kind": "if", "lines": [4, 4], "taken": False},
        {"kind": "elif", "lines": [6, 6], "taken": True},
        {"kind": "else", "lines": [8, 8], "taken": False},
    ]}]


def test_bare_if_no_else():
    j = compute_junctions(SRC_BARE_IF, 2, "h", {3, 4, 6}, False)
    assert j == [{"test_line": 4, "arms": [
        {"kind": "if", "lines": [5, 5], "taken": False},
    ]}]


def test_truncated_yields_unknown_not_false():
    # only the test line was reached before the cap
    j = compute_junctions(SRC_IF_ELSE, 2, "f", {3}, True)
    arms = j[0]["arms"]
    assert arms[0]["taken"] is None
    assert arms[1]["taken"] is None


def test_nested_if_inside_taken_arm():
    # outer took the if-arm; inner took its else-arm
    j = compute_junctions(SRC_NESTED, 2, "n", {3, 4, 7, 10}, False)
    outer = next(x for x in j if x["test_line"] == 3)
    inner = next(x for x in j if x["test_line"] == 4)
    assert outer["arms"][0]["taken"] is True     # if-arm (lines 4..7)
    assert outer["arms"][1]["taken"] is False    # else-arm (line 9)
    assert inner["arms"][0]["taken"] is False    # inner if (line 5)
    assert inner["arms"][1]["taken"] is True     # inner else (line 7)


def test_if_in_nested_def_excluded():
    # inner()'s `if y:` must NOT appear — nested defs are not traced
    j = compute_junctions(SRC_NESTED_DEF, 2, "outer", {7, 8}, False)
    assert all(x["test_line"] != 4 for x in j)
    assert [x["test_line"] for x in j] == [7]


def test_no_if_returns_empty():
    src = "\ndef p(x):\n    return x + 1\n"
    assert compute_junctions(src, 2, "p", {3}, False) == []


def test_syntax_error_returns_empty():
    assert compute_junctions("def broken(:\n", 1, "broken", set(), False) == []


def test_target_not_found_returns_empty():
    assert compute_junctions(SRC_IF_ELSE, 999, "missing", {3}, False) == []
