import asyncio
from pathlib import Path

from copyclip.intelligence.analyzer import analyze
from copyclip.intelligence.db import connect
from copyclip.intelligence.playground import ResolvedFunction, resolve_function_ref, FunctionRef
from copyclip.intelligence.cuaderno import call_synth
from copyclip.intelligence.cuaderno.call_synth import (
    SynthesizedCall,
    _resolve_target_symbol_id,
    _candidate_callers,
)


def analyzed_project(tmp_path: Path, files: dict[str, str]):
    """Write source, run the REAL analyzer, return (conn, project_id, root).

    analyze() opens its OWN connection and closes it, so we REOPEN the on-disk
    db with connect(). ':memory:' cannot be used (analyze builds its own conn).
    """
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    asyncio.run(analyze(str(tmp_path)))
    conn = connect(str(tmp_path))
    pid = conn.execute(
        "SELECT id FROM projects WHERE root_path=?", (str(tmp_path),)
    ).fetchone()[0]
    return conn, int(pid), str(tmp_path)


_LIB = "def target(rel):\n    return rel.upper()\n"
_TEST = (
    "from src.pkg.lib import target\n\n"
    "def test_target():\n"
    "    assert target('abc') == 'ABC'\n"
)


def test_resolve_target_symbol_id_matches_the_symbols_row(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    sid = _resolve_target_symbol_id(conn, pid, resolved)
    expected = conn.execute(
        "SELECT id FROM symbols WHERE project_id=? AND file_path=? AND name=? AND kind=? AND line_start=?",
        (pid, "src/pkg/lib.py", "target", "function", 1),
    ).fetchone()[0]
    assert sid == expected


def test_candidate_callers_finds_the_test_function(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    sid = _resolve_target_symbol_id(conn, pid, resolved)
    assert sid is not None
    callers = _candidate_callers(conn, pid, sid)
    assert any(c.name == "test_target" and c.file_path == "tests/test_lib.py" for c in callers)
