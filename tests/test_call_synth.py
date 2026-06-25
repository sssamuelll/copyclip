import ast
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
    _import_bindings,
    _Binding,
    _dotted_name,
    _import_module_matches,
    _function_call_confirms,
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


# ---------------------------------------------------------------------------
# Task 3: _import_module_matches + _function_call_confirms
# ---------------------------------------------------------------------------

def _resolved(file, name, module, kind="function", parent=None, line_start=1):
    return ResolvedFunction(
        file=file, name=name,
        qualname=(f"{parent}.{name}" if parent else name),
        kind=kind, module=module, line_start=line_start, parent_class=parent,
    )


def test_import_module_matches_tolerates_src_root():
    assert _import_module_matches("src.pkg.lib", "pkg.lib") is True
    assert _import_module_matches("pkg.lib", "pkg.lib") is True
    assert _import_module_matches("copyclip.intelligence.analyzer", "copyclip.intelligence.analyzer") is True
    assert _import_module_matches("src.pkg.other", "pkg.lib") is False
    assert _import_module_matches("", "pkg.lib") is False


def _one_call(src: str) -> ast.Call:
    """Return the single ast.Call in the last statement of a snippet."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            return node
    raise AssertionError("no call")


def test_function_call_confirms_from_import():
    src = "from src.pkg.lib import target\ndef test_t():\n    target('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True


def test_function_call_confirms_same_file_bare_name():
    src = "def helper():\n    return target(1)\ndef target(x):\n    return x\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "src/pkg/lib.py", resolved) is True


def test_function_call_confirms_module_attribute():
    src = "import src.pkg.lib as lib\ndef test_t():\n    lib.target('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True


def test_function_call_rejects_same_name_other_module():
    # The caller imports `process` from zzz; the resolved target is aaa.process.
    # The 'calls' edge may (wrongly) point here, but the binding must be rejected.
    src = "from src.pkg.zzz import process\ndef test_p():\n    process('x')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved_aaa = _resolved("src/pkg/aaa.py", "process", "pkg.aaa")
    assert _function_call_confirms(call, b, "tests/test_z.py", resolved_aaa) is False
    # ...but it DOES confirm for the correctly-bound target.
    resolved_zzz = _resolved("src/pkg/zzz.py", "process", "pkg.zzz")
    assert _function_call_confirms(call, b, "tests/test_z.py", resolved_zzz) is True


def test_function_call_confirms_aliased_import():
    # `from m import target as tgt; tgt(...)` must confirm via the alias binding —
    # the call name is `tgt`, but its original imported name is the target.
    src = "from src.pkg.lib import target as tgt\ndef test_t():\n    tgt('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True


def test_function_call_same_file_local_def_wins_over_import():
    # The target's own file both imports a same-named symbol AND defines the target.
    # Python binds the module-level def (it shadows the import), and the analyzer's
    # same-file edge points at the local def — so a bare call confirms to THIS symbol.
    src = (
        "from src.pkg.other import target\n"
        "def target(x):\n    return x\n"
        "def helper():\n    return target(1)\n"
    )
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = [n for n in ast.walk(tree) if isinstance(n, ast.Call)][0]
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib", line_start=2)
    assert _function_call_confirms(call, b, "src/pkg/lib.py", resolved) is True


def test_function_call_confirms_unaliased_dotted_module_import():
    # `import src.pkg.lib; src.pkg.lib.target(...)` — the receiver is the full
    # dotted module, keyed under "src.pkg.lib"; _dotted_name(func.value) returns
    # the same string, so the attribute call confirms.
    src = "import src.pkg.lib\ndef test_t():\n    src.pkg.lib.target('abc')\n"
    tree = ast.parse(src)
    b = _import_bindings(tree)
    call = _one_call(src)
    resolved = _resolved("src/pkg/lib.py", "target", "pkg.lib")
    assert _function_call_confirms(call, b, "tests/test_lib.py", resolved) is True
