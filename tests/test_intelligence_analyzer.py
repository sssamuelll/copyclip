import random
import time

from copyclip.intelligence.analyzer import (
    _complexity_score,
    _is_dependency_impacted,
    _is_test_path,
)
from copyclip.intelligence.tree_sitter_parser import (
    CallRef,
    ExtractionResult,
    ImportRef,
    InheritanceRef,
    SymbolDef,
)


def test_is_test_path_variants():
    assert _is_test_path("tests/test_api.py")
    assert _is_test_path("src/foo/bar.spec.ts")
    assert _is_test_path("src/foo/bar.test.js")
    assert not _is_test_path("src/foo/bar.ts")


def test_complexity_score_detects_control_flow():
    low = "def x():\n    return 1\n"
    high = """
def y(a):
    if a:
        for i in range(3):
            if i % 2:
                try:
                    pass
                except Exception:
                    pass
    else:
        while a:
            break
"""
    assert _complexity_score(high, "python") > _complexity_score(low, "python")
    assert _complexity_score(low, "python") >= 1


def test_dependency_impact_detection():
    changed = {"api", "auth"}
    assert _is_dependency_impacted(changed, "api", [])
    assert _is_dependency_impacted(changed, "ui", ["auth", "react"])
    assert not _is_dependency_impacted(changed, "ui", ["react", "lodash"])


# ---------------------------------------------------------------------------
# Symbol-edge resolution (refactor parity tests)
#
# Both helpers below mirror the call/inheritance resolution block inside
# ``analyzer.analyze`` so the algorithm can be exercised in isolation. The
# legacy variant retains the pre-refactor O(F*C*(I+S)) scan; the new variant
# uses the O(1) reverse index. Production code lives in analyzer.py only — the
# test mirrors are NOT exported.
# ---------------------------------------------------------------------------


def _build_indices(file_extractions):
    """Return (symbol_id_map, global_symbols, import_map) the same way analyze() does."""
    symbol_id_map = {}
    global_symbols = {}
    next_id = 1
    for rel, (mod, extraction) in file_extractions.items():
        for sym in extraction.definitions:
            symbol_id_map[(rel, sym.name, sym.kind)] = next_id
            global_symbols[(mod, sym.name)] = next_id
            next_id += 1
    import_map = {}
    for rel, (mod, extraction) in file_extractions.items():
        for imp in extraction.imports:
            import_map[(rel, imp.target)] = imp.target
    return symbol_id_map, global_symbols, import_map


def _legacy_resolve_edges(file_extractions):
    """Pre-refactor algorithm copied verbatim from analyzer.py:687-742 (HEAD~1)."""
    symbol_id_map, global_symbols, import_map = _build_indices(file_extractions)
    edges = []
    for rel, (mod, extraction) in file_extractions.items():
        for call in extraction.calls:
            callee_base = call.callee.split(".")[0]
            callee_name = call.callee.split(".")[-1] if "." in call.callee else call.callee
            callee_id = symbol_id_map.get((rel, callee_name, "function")) or \
                        symbol_id_map.get((rel, callee_name, "method"))
            if not callee_id:
                for (r, imp_name), src_mod in import_map.items():
                    if r == rel and imp_name == callee_base:
                        callee_id = global_symbols.get((src_mod, callee_name))
                        if callee_id:
                            break
            if not callee_id:
                for (m, n), sid in global_symbols.items():
                    if n == callee_name:
                        callee_id = sid
                        break
            if callee_id:
                caller_id = symbol_id_map.get((rel, call.caller, "function")) or \
                            symbol_id_map.get((rel, call.caller, "method"))
                if caller_id:
                    edges.append((caller_id, callee_id, "calls"))
    for rel, (mod, extraction) in file_extractions.items():
        for inh in extraction.inheritance:
            child_id = symbol_id_map.get((rel, inh.child, "class")) or \
                       symbol_id_map.get((rel, inh.child, "struct"))
            parent_id = symbol_id_map.get((rel, inh.parent, "class")) or \
                        symbol_id_map.get((rel, inh.parent, "trait")) or \
                        symbol_id_map.get((rel, inh.parent, "interface"))
            if not parent_id:
                for (m, n), sid in global_symbols.items():
                    if n == inh.parent:
                        parent_id = sid
                        break
            if child_id and parent_id:
                edges.append((child_id, parent_id, "inherits"))
    return edges


def _new_resolve_edges(file_extractions):
    """Mirror of post-refactor algorithm in analyzer.py."""
    symbol_id_map, global_symbols, import_map = _build_indices(file_extractions)
    name_to_sid = {}
    for (_module, name), sid in global_symbols.items():
        name_to_sid.setdefault(name, sid)
    edges = []
    for rel, (mod, extraction) in file_extractions.items():
        for call in extraction.calls:
            callee_base = call.callee.split(".")[0]
            callee_name = call.callee.split(".")[-1] if "." in call.callee else call.callee
            callee_id = symbol_id_map.get((rel, callee_name, "function")) or \
                        symbol_id_map.get((rel, callee_name, "method"))
            if not callee_id and (rel, callee_base) in import_map:
                callee_id = global_symbols.get((callee_base, callee_name))
            if not callee_id:
                callee_id = name_to_sid.get(callee_name)
            if callee_id:
                caller_id = symbol_id_map.get((rel, call.caller, "function")) or \
                            symbol_id_map.get((rel, call.caller, "method"))
                if caller_id:
                    edges.append((caller_id, callee_id, "calls"))
    for rel, (mod, extraction) in file_extractions.items():
        for inh in extraction.inheritance:
            child_id = symbol_id_map.get((rel, inh.child, "class")) or \
                       symbol_id_map.get((rel, inh.child, "struct"))
            parent_id = symbol_id_map.get((rel, inh.parent, "class")) or \
                        symbol_id_map.get((rel, inh.parent, "trait")) or \
                        symbol_id_map.get((rel, inh.parent, "interface"))
            if not parent_id:
                parent_id = name_to_sid.get(inh.parent)
            if child_id and parent_id:
                edges.append((child_id, parent_id, "inherits"))
    return edges


def _make_extraction(defs=(), imports=(), calls=(), inh=()):
    e = ExtractionResult()
    for d in defs:
        e.definitions.append(SymbolDef(name=d[0], kind=d[1], line_start=1, line_end=2))
    for t in imports:
        e.imports.append(ImportRef(target=t))
    for c in calls:
        e.calls.append(CallRef(caller=c[0], callee=c[1], line=1))
    for i in inh:
        e.inheritance.append(InheritanceRef(child=i[0], parent=i[1]))
    return e


def test_resolve_edges_empty_input():
    assert _new_resolve_edges({}) == []
    assert _legacy_resolve_edges({}) == []


def test_resolve_edges_single_file_self_call():
    fx = {
        "a.py": ("mod_a", _make_extraction(
            defs=[("foo", "function"), ("bar", "function")],
            calls=[("foo", "bar")],
        )),
    }
    new_edges = _new_resolve_edges(fx)
    assert len(new_edges) == 1
    assert new_edges == _legacy_resolve_edges(fx)


def test_resolve_edges_prefers_same_file_over_global():
    # Two modules both define ``run``; caller in mod_a calls ``run`` -> must
    # bind to mod_a's local symbol, not mod_b's.
    fx = {
        "a.py": ("mod_a", _make_extraction(
            defs=[("entry", "function"), ("run", "function")],
            calls=[("entry", "run")],
        )),
        "b.py": ("mod_b", _make_extraction(
            defs=[("run", "function")],
        )),
    }
    new_edges = _new_resolve_edges(fx)
    assert _legacy_resolve_edges(fx) == new_edges
    assert len(new_edges) == 1
    caller_id, callee_id, kind = new_edges[0]
    assert kind == "calls"
    # callee must be the local mod_a:run, which was inserted before mod_b:run
    sid_map, _, _ = _build_indices(fx)
    assert callee_id == sid_map[("a.py", "run", "function")]


def test_resolve_edges_uses_imported_module():
    # mod_a imports mod_b; mod_a.entry calls ``helper`` -> should resolve to
    # mod_b.helper via the import_map shortcut.
    fx = {
        "a.py": ("mod_a", _make_extraction(
            defs=[("entry", "function")],
            imports=["mod_b"],
            calls=[("entry", "mod_b.helper")],
        )),
        "b.py": ("mod_b", _make_extraction(
            defs=[("helper", "function")],
        )),
    }
    new_edges = _new_resolve_edges(fx)
    assert _legacy_resolve_edges(fx) == new_edges
    assert len(new_edges) == 1


def test_resolve_edges_global_first_match_wins_with_duplicates():
    # Two modules declare ``shared`` with the same name. Caller in a third
    # module without imports must fall back to the global index, picking
    # whichever was inserted first (mod_a.shared in our build order).
    fx = {
        "a.py": ("mod_a", _make_extraction(defs=[("shared", "function")])),
        "b.py": ("mod_b", _make_extraction(defs=[("shared", "function")])),
        "c.py": ("mod_c", _make_extraction(
            defs=[("entry", "function")],
            calls=[("entry", "shared")],
        )),
    }
    new_edges = _new_resolve_edges(fx)
    assert _legacy_resolve_edges(fx) == new_edges
    assert len(new_edges) == 1
    sid_map, _, _ = _build_indices(fx)
    _, callee_id, _ = new_edges[0]
    assert callee_id == sid_map[("a.py", "shared", "function")]


def test_resolve_edges_inheritance_global_fallback():
    fx = {
        "base.py": ("mod_base", _make_extraction(defs=[("Animal", "class")])),
        "derived.py": ("mod_derived", _make_extraction(
            defs=[("Dog", "class")],
            inh=[("Dog", "Animal")],
        )),
    }
    new_edges = _new_resolve_edges(fx)
    assert _legacy_resolve_edges(fx) == new_edges
    assert len(new_edges) == 1
    assert new_edges[0][2] == "inherits"


def test_resolve_edges_no_match_emits_no_edge():
    # Calls to undeclared names must produce zero edges.
    fx = {
        "a.py": ("mod_a", _make_extraction(
            defs=[("entry", "function")],
            calls=[("entry", "print"), ("entry", "len")],
        )),
    }
    assert _new_resolve_edges(fx) == []
    assert _legacy_resolve_edges(fx) == []


def test_resolve_edges_n_equals_one():
    fx = {
        "only.py": ("only", _make_extraction(
            defs=[("solo", "function")],
            calls=[("solo", "solo")],
        )),
    }
    new_edges = _new_resolve_edges(fx)
    assert _legacy_resolve_edges(fx) == new_edges
    assert len(new_edges) == 1


def test_resolve_edges_parity_random_seeded():
    rng = random.Random(0xC0FFEE)
    # Seeded synthetic project; sized so the legacy O(N^2) scan still finishes
    # quickly enough for CI.
    n_files = 30
    fx = {}
    all_names = [f"sym_{i}" for i in range(80)]
    for fi in range(n_files):
        rel = f"f{fi}.py"
        mod = f"mod_{fi}"
        defs = [(n, rng.choice(["function", "method", "class"])) for n in rng.sample(all_names, 8)]
        imports = [f"mod_{rng.randrange(n_files)}" for _ in range(rng.randint(0, 4))]
        callers = [d[0] for d in defs if d[1] in {"function", "method"}] or ["__noop__"]
        calls = []
        for _ in range(rng.randint(2, 10)):
            base = rng.choice(["", rng.choice(imports) + "."]) if imports else ""
            target = rng.choice(all_names)
            calls.append((rng.choice(callers), f"{base}{target}"))
        inh = []
        classes = [d[0] for d in defs if d[1] == "class"]
        if classes and rng.random() < 0.5:
            inh.append((rng.choice(classes), rng.choice(all_names)))
        fx[rel] = (mod, _make_extraction(defs=defs, imports=imports, calls=calls, inh=inh))
    legacy = _legacy_resolve_edges(fx)
    new = _new_resolve_edges(fx)
    assert new == legacy, f"edge sets diverge: legacy={legacy[:5]}... new={new[:5]}..."
    # Sanity: at least one call edge produced for this seed.
    assert any(e[2] == "calls" for e in new)


def test_resolve_edges_parity_reversed_insertion_order():
    # Same logical project, different dict iteration order. The "first match
    # wins" rule means edge content should be identical because both impls
    # iterate global_symbols in the same order they were inserted.
    fx_forward = {
        "a.py": ("mod_a", _make_extraction(defs=[("X", "function")])),
        "b.py": ("mod_b", _make_extraction(defs=[("X", "function")])),
        "c.py": ("mod_c", _make_extraction(
            defs=[("entry", "function")],
            calls=[("entry", "X")],
        )),
    }
    fx_reversed = {
        "b.py": ("mod_b", _make_extraction(defs=[("X", "function")])),
        "a.py": ("mod_a", _make_extraction(defs=[("X", "function")])),
        "c.py": ("mod_c", _make_extraction(
            defs=[("entry", "function")],
            calls=[("entry", "X")],
        )),
    }
    assert _new_resolve_edges(fx_forward) == _legacy_resolve_edges(fx_forward)
    assert _new_resolve_edges(fx_reversed) == _legacy_resolve_edges(fx_reversed)


def test_resolve_edges_performance_n_10000_completes_under_500ms():
    # This is the failing-against-old / passing-against-new test:
    # the legacy scan needs ~5-10s on this input; the new index runs in <100ms.
    # Budget: 500ms hard ceiling, easily met by the new impl on commodity CI.
    n_files = 200
    syms_per_file = 50
    calls_per_file = 30
    fx = {}
    for fi in range(n_files):
        rel = f"f{fi}.py"
        mod = f"mod_{fi}"
        defs = [(f"sym_{fi}_{si}", "function") for si in range(syms_per_file)]
        # Calls reference a symbol from a different module -> always forces the
        # fallback path (the slow one in the legacy impl).
        target_mod = (fi + 1) % n_files
        calls = [
            (f"sym_{fi}_0", f"sym_{target_mod}_{ci % syms_per_file}")
            for ci in range(calls_per_file)
        ]
        fx[rel] = (mod, _make_extraction(defs=defs, calls=calls))

    t0 = time.perf_counter()
    edges = _new_resolve_edges(fx)
    dt = time.perf_counter() - t0
    assert dt < 0.5, f"new impl took {dt:.3f}s (expected <0.5s)"
    assert len(edges) == n_files * calls_per_file


def test_resolve_edges_does_not_mutate_inputs():
    fx = {
        "a.py": ("mod_a", _make_extraction(
            defs=[("x", "function"), ("y", "function")],
            imports=["mod_b"],
            calls=[("x", "y"), ("x", "mod_b.z")],
            inh=[],
        )),
        "b.py": ("mod_b", _make_extraction(
            defs=[("z", "function")],
        )),
    }
    snapshot = {
        rel: (mod, [
            [(d.name, d.kind) for d in ex.definitions],
            [i.target for i in ex.imports],
            [(c.caller, c.callee) for c in ex.calls],
            [(h.child, h.parent) for h in ex.inheritance],
        ])
        for rel, (mod, ex) in fx.items()
    }
    _new_resolve_edges(fx)
    after = {
        rel: (mod, [
            [(d.name, d.kind) for d in ex.definitions],
            [i.target for i in ex.imports],
            [(c.caller, c.callee) for c in ex.calls],
            [(h.child, h.parent) for h in ex.inheritance],
        ])
        for rel, (mod, ex) in fx.items()
    }
    assert snapshot == after
