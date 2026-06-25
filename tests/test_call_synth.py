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
    _lift_literal_args,
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


# ---------------------------------------------------------------------------
# Task 4: _lift_literal_args
# ---------------------------------------------------------------------------

def test_lift_literal_args_pure_literals():
    call = _one_call("f(1, 'two', [3, 4], k=True, j=None)")
    out = _lift_literal_args(call)
    assert out == ([1, "two", [3, 4]], {"k": True, "j": None})


def test_lift_literal_args_rejects_free_name():
    assert _lift_literal_args(_one_call("f(conn, 1)")) is None


def test_lift_literal_args_rejects_call_arg():
    assert _lift_literal_args(_one_call("f(Foo(), 1)")) is None


def test_lift_literal_args_rejects_splat():
    assert _lift_literal_args(_one_call("f(*xs)")) is None
    assert _lift_literal_args(_one_call("f(**kw)")) is None


def test_lift_literal_args_rejects_non_json_float():
    assert _lift_literal_args(_one_call("f(float('nan'))")) is None  # not a literal anyway
    # a literal that json rejects:
    assert _lift_literal_args(_one_call("f(1e400)")) is None  # inf literal -> rejected


# ---------------------------------------------------------------------------
# Task 5: synthesize_call
# ---------------------------------------------------------------------------

def test_synthesize_call_lifts_literal_test_call(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    out = synthesize_call_for_test = call_synth.synthesize_call(resolved, conn, pid, root)
    assert out is not None
    assert out.args == ["abc"]
    assert out.kwargs == {}
    assert out.ctor is None
    assert out.arg_source == "tests"


def test_synthesize_call_returns_none_for_fixture_args(tmp_path):
    files = {
        "src/pkg/lib.py": "def needs_conn(conn, n):\n    return n\n",
        "tests/test_lib.py": (
            "from src.pkg.lib import needs_conn\n\n"
            "def test_it(db):\n"
            "    assert needs_conn(db, 3) == 3\n"   # `db` is a fixture (free name)
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="needs_conn"))
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_returns_none_with_no_call_site(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": "def lonely(x):\n    return x\n"}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="lonely"))
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_does_not_lift_same_name_other_module(tmp_path):
    # The spec §8 re-verification BLOCKER: two same-named `process` functions in
    # DIFFERENT modules; the test imports zzz.process with a literal arg. The
    # analyzer's name-based edge binds test_p -> aaa.process (first-match-wins), so a
    # request for aaa.process must NOT lift zzz's call-site (binding mismatch).
    files = {
        "src/pkg/aaa.py": "def process(rel):\n    return 'AAA'\n",
        "src/pkg/zzz.py": "def process(rel):\n    return 'ZZZ'\n",
        "tests/test_z.py": (
            "from src.pkg.zzz import process\n\n"
            "def test_p():\n"
            "    assert process('x') == 'ZZZ'\n"
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    # aaa: the (wrong) edge points here, but the caller imports zzz -> rejected -> None.
    resolved_aaa = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/aaa.py", name="process"))
    assert call_synth.synthesize_call(resolved_aaa, conn, pid, root) is None
    # zzz: the correctly-bound target has NO inbound edge (the analyzer wrote only the
    # single first-match edge to aaa), so there is nothing to lift -> None. Re-verification
    # PREVENTS the wrong lift; it does not RECOVER the right one (honest v1 boundary).
    resolved_zzz = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/zzz.py", name="process"))
    assert call_synth.synthesize_call(resolved_zzz, conn, pid, root) is None


def test_synthesize_call_refuses_ambiguous_module_collision(tmp_path):
    # False-confirm guard: two DISTINCT files collapse to the same _module_from_file
    # module ('pkg.lib') — src/pkg/lib.py (src-stripped) and pkg/lib.py (already pkg.lib).
    # A module-string match is then not a unique-file match, so synthesis must refuse
    # rather than risk lifting the wrong file's call and stamping it 'tests'.
    files = {
        "src/pkg/lib.py": "def target(rel):\n    return rel.upper()\n",
        "pkg/lib.py": "def target(rel):\n    return rel.lower()\n",
        "tests/test_lib.py": (
            "from pkg.lib import target\n\n"
            "def test_t():\n"
            "    assert target('abc') in ('ABC', 'abc')\n"
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    for f in ("src/pkg/lib.py", "pkg/lib.py"):
        resolved = resolve_function_ref(conn, pid, FunctionRef(file=f, name="target"))
        assert resolved.module == "pkg.lib"  # confirms the collision
        assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_returns_none_for_class_target(tmp_path):
    files = {
        "src/pkg/greet.py": (
            "class Greeter:\n"
            "    def __init__(self, prefix):\n"
            "        self.prefix = prefix\n"
        ),
        "tests/test_greet.py": (
            "from src.pkg.greet import Greeter\n\n"
            "def test_make():\n"
            "    assert Greeter('hi').prefix == 'hi'\n"
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/greet.py", name="Greeter"))
    assert resolved.kind == "class"
    assert call_synth.synthesize_call(resolved, conn, pid, root) is None


def test_synthesize_call_prefers_tests_and_richest(tmp_path):
    files = {
        "src/pkg/lib.py": "def target(a, b=0):\n    return a\n",
        "src/pkg/use.py": (
            "from src.pkg.lib import target\n\n"
            "def use():\n"
            "    return target(1)\n"            # non-test, fewer args
        ),
        "tests/test_lib.py": (
            "from src.pkg.lib import target\n\n"
            "def test_a():\n"
            "    target(7, b=9)\n"              # test, richer
        ),
    }
    conn, pid, root = analyzed_project(tmp_path, files)
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    out = call_synth.synthesize_call(resolved, conn, pid, root)
    assert out is not None
    assert out.args == [7] and out.kwargs == {"b": 9}


def test_synthesize_call_returns_none_without_project_root(tmp_path):
    conn, pid, root = analyzed_project(
        tmp_path, {"src/pkg/lib.py": _LIB, "tests/test_lib.py": _TEST}
    )
    resolved = resolve_function_ref(conn, pid, FunctionRef(file="src/pkg/lib.py", name="target"))
    assert call_synth.synthesize_call(resolved, conn, pid, None) is None
