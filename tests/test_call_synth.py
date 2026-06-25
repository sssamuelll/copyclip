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


import ast
from copyclip.intelligence.cuaderno.call_synth import _import_bindings, _Binding, _dotted_name


def test_import_bindings_from_import_with_and_without_alias():
    tree = ast.parse(
        "from src.pkg.lib import target\n"
        "from src.pkg.lib import target as tgt\n"
        "import os\n"
        "import a.b.c as abc\n"
    )
    b = _import_bindings(tree)
    assert b["target"] == _Binding(module="src.pkg.lib", orig_name="target")
    assert b["tgt"] == _Binding(module="src.pkg.lib", orig_name="target")
    assert b["os"] == _Binding(module="os", orig_name=None)
    assert b["abc"] == _Binding(module="a.b.c", orig_name=None)


def test_import_bindings_plain_module_import_binds_full_dotted():
    tree = ast.parse("import a.b.c\n")
    b = _import_bindings(tree)
    assert b["a.b.c"] == _Binding(module="a.b.c", orig_name=None)


def test_import_bindings_skips_relative_imports():
    tree = ast.parse("from . import sibling\nfrom .pkg import thing\n")
    b = _import_bindings(tree)
    assert "sibling" not in b
    assert "thing" not in b


def test_dotted_name():
    call = ast.parse("a.b.c.func(1)", mode="eval").body
    assert _dotted_name(call.func.value) == "a.b.c"
    assert _dotted_name(ast.parse("bare", mode="eval").body) == "bare"
    assert _dotted_name(ast.parse("x[0]", mode="eval").body) is None
