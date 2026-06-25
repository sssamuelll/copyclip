from __future__ import annotations

import sys
import pytest
from textwrap import dedent

from copyclip.intelligence.playground import FunctionRef
from copyclip.intelligence.capture import (
    CallDescriptor,
    FreeTextCall,
    InvalidCallDescriptorError,
)


def test_call_descriptor_minimal_no_args():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/foo.py", "name": "bar"}})
    assert isinstance(cd.function_ref, FunctionRef)
    assert cd.args == []
    assert cd.kwargs == {}
    assert cd.ctor is None


def test_call_descriptor_args_kwargs_ctor():
    cd = CallDescriptor.from_dict({
        "function_ref": {"file": "src/foo.py", "name": "method_name", "qualname": "Foo.method_name"},
        "args": [1, "x"],
        "kwargs": {"flag": True},
        "ctor": {"args": [42], "kwargs": {"name": "n"}},
    })
    assert cd.args == [1, "x"]
    assert cd.kwargs == {"flag": True}
    assert cd.ctor == {"args": [42], "kwargs": {"name": "n"}}


def test_call_descriptor_rejects_non_json_serializable():
    with pytest.raises(InvalidCallDescriptorError):
        CallDescriptor.from_dict({
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "args": [object()],  # not JSON-serializable
        })


def test_call_descriptor_rejects_non_list_args():
    with pytest.raises(InvalidCallDescriptorError):
        CallDescriptor.from_dict({
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "args": {"not": "a list"},
        })


def test_call_descriptor_rejects_non_string_kwarg_keys():
    with pytest.raises(InvalidCallDescriptorError):
        CallDescriptor.from_dict({
            "function_ref": {"file": "src/foo.py", "name": "bar"},
            "kwargs": {"ok": 1, "bad key with space": 2},  # not an identifier
        })


def test_free_text_call_carries_user_expression_verbatim():
    # The USER's edited free text is THEIR own code (spec §10 path 2). It is NOT
    # repr-guarded — it is exec'd in the module namespace on explicit confirm.
    ft = FreeTextCall.from_text("addup(3 + 4)")
    assert ft.text == "addup(3 + 4)"


def test_free_text_call_rejects_blank():
    with pytest.raises(InvalidCallDescriptorError):
        FreeTextCall.from_text("   ")


def test_free_text_call_rejects_multiple_statements():
    # A single expression, not a script: reject semicolons / newlines so the
    # confirm gesture stays "run THIS call", not "run an arbitrary program".
    with pytest.raises(InvalidCallDescriptorError):
        FreeTextCall.from_text("import os; os.system('x')")


from copyclip.intelligence.capture import (
    Step,
    Var,
    normalize_trace,
    StepThroughResponse,
    FallbackResponse,
)


def _raw(events):
    # The driver pre-flattens each event's in-scope vars into the Var shape but
    # NEVER emits `changed` — the normalizer derives it (spec §9).
    return {"trace": events}


def test_normalize_derives_changed_vars_between_steps():
    raw = _raw([
        {"line": 1, "event": "line", "scope": [{"name": "x", "kind": "scalar", "text": "1"}]},
        {"line": 2, "event": "line", "scope": [
            {"name": "x", "kind": "scalar", "text": "1"},
            {"name": "y", "kind": "scalar", "text": "2"},
        ]},
        {"line": 3, "event": "line", "scope": [
            {"name": "x", "kind": "scalar", "text": "9"},
            {"name": "y", "kind": "scalar", "text": "2"},
        ]},
    ])
    steps = normalize_trace(raw)
    assert [s.changed for s in steps] == [["x"], ["y"], ["x"]]
    # scope completeness is the DRIVER's contract (spec §9): the driver emits the
    # full in-scope snapshot at every step, so every var appears at every step.
    # The normalizer passes scope straight through without accumulation.
    assert [v.name for v in steps[2].scope] == ["x", "y"]


def test_normalize_changed_matches_handoff_for_canonical_resolve_trace():
    """Spec §9 hard requirement: the DERIVED `changed` must match the handoff's
    hand-authored `changed` for the canonical resolve-trace so capture and the
    React renderer never silently diverge. The driver emits line/event/scope
    only; this proves the normalizer reproduces the handoff's per-step deltas."""
    # Driver-shape input (no `changed`): a tiny slice of the handoff's
    # resolve_function_ref trace — bind `row`, then `resolved`, then return.
    raw = _raw([
        {"line": 255, "event": "call", "scope": [
            {"name": "conn", "kind": "opaque", "label": "sqlite3.Connection"},
            {"name": "project_id", "kind": "scalar", "text": "42"},
        ]},
        {"line": 256, "event": "line", "scope": [
            {"name": "conn", "kind": "opaque", "label": "sqlite3.Connection"},
            {"name": "project_id", "kind": "scalar", "text": "42"},
            {"name": "row", "kind": "large", "summary": "tuple", "meta": "6 items"},
        ]},
        {"line": 257, "event": "line", "scope": [
            {"name": "conn", "kind": "opaque", "label": "sqlite3.Connection"},
            {"name": "project_id", "kind": "scalar", "text": "42"},
            {"name": "row", "kind": "large", "summary": "tuple", "meta": "6 items"},
            {"name": "resolved", "kind": "object", "text": "ResolvedFunction(name='bar')"},
        ]},
    ])
    # Hand-authored `changed`, copied from the handoff's Component fixture:
    handoff_changed = [[], ["row"], ["resolved"]]
    # `conn`/`project_id` are call-frame args present from step 0; the handoff
    # counts neither the opaque `conn` nor unchanged args as moved.
    steps = normalize_trace(raw)
    assert [s.changed for s in steps] == handoff_changed


def test_normalize_emits_raise_terminal_step():
    raw = _raw([
        {"line": 1, "event": "line", "scope": []},
        {"line": 2, "event": "raise", "scope": [],
         "raised": {"type": "KeyError", "message": "'x'"}},
    ])
    steps = normalize_trace(raw)
    assert steps[-1].event == "raise"
    assert steps[-1].raised == {"type": "KeyError", "message": "'x'"}


def test_step_and_var_to_dict_shape():
    s = Step(line=10, event="line", changed=["a"],
             scope=[Var(name="a", kind="large", summary="dict", meta="3 keys",
                        children=[{"name": "k", "text": "1"}])])
    d = s.to_dict()
    assert d == {
        "line": 10, "event": "line", "changed": ["a"],
        "scope": [{"name": "a", "kind": "large", "summary": "dict",
                   "meta": "3 keys", "children": [{"name": "k", "text": "1"}]}],
    }


def test_opaque_var_carries_label_not_text():
    v = Var(name="f", kind="opaque", label="TextIOWrapper")
    assert v.to_dict() == {"name": "f", "kind": "opaque", "label": "TextIOWrapper"}


def test_responses_to_dict():
    st = StepThroughResponse(
        trace=[Step(line=1, event="line", changed=[], scope=[])],
        source_lines=[{"num": 1, "text": "def f():"}],
        func_name="f", file_line="src/foo.py:1", truncated=False)
    assert st.to_dict()["kind"] == "trace"
    assert st.to_dict()["truncated"] is False
    fb = FallbackResponse(reason="async function", iframe_url="http://127.0.0.1:5000/",
                          playground_id="pgid-test")
    assert fb.to_dict() == {"kind": "fallback", "reason": "async function",
                            "iframe_url": "http://127.0.0.1:5000/",
                            "playground_id": "pgid-test"}


# ---------------------------------------------------------------------------
# Task 3: Eligibility gate
# ---------------------------------------------------------------------------

from copyclip.intelligence.playground import ResolvedFunction
from copyclip.intelligence.capture import eligibility_reason


def _resolved(kind="function", parent=None, name="bar"):
    return ResolvedFunction(file="src/copyclip/foo.py", name=name,
                            qualname=(f"{parent}.{name}" if parent else name),
                            kind=kind, module="copyclip.foo",
                            line_start=10, parent_class=parent)


def test_eligible_plain_function_with_no_args_required():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    assert eligibility_reason(cd, _resolved(), is_async=False, is_generator=False) is None


def test_async_function_declines():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=True, is_generator=False)
    assert reason and "async" in reason.lower()


def test_async_generator_declines_with_async_reason():
    # detect_kind reports is_async for an async generator (Task 4); the gate must
    # surface the 'async' reason, not the 'generator' one (spec §7 decline copy).
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=True, is_generator=False)
    assert reason and "async" in reason.lower()


def test_generator_function_declines():
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=False, is_generator=True)
    assert reason and "generator" in reason.lower()


def test_method_without_ctor_declines():
    cd = CallDescriptor.from_dict({
        "function_ref": {"file": "src/copyclip/foo.py", "name": "m", "qualname": "Foo.m"},
    })
    reason = eligibility_reason(cd, _resolved(kind="method", parent="Foo", name="m"),
                               is_async=False, is_generator=False)
    assert reason and "constructor" in reason.lower()


def test_method_with_ctor_is_eligible():
    cd = CallDescriptor.from_dict({
        "function_ref": {"file": "src/copyclip/foo.py", "name": "m", "qualname": "Foo.m"},
        "ctor": {"args": [1]},
    })
    assert eligibility_reason(cd, _resolved(kind="method", parent="Foo", name="m"),
                              is_async=False, is_generator=False) is None


def test_decorated_target_declines_with_honest_reason():
    """Fix 2: a decorated target makes own_file the wrapper's file, so the real
    body is never anchored. The gate must decline with an honest reason rather
    than ship an empty stepper."""
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    reason = eligibility_reason(cd, _resolved(), is_async=False, is_generator=False,
                                is_decorated=True)
    assert reason and "decorat" in reason.lower(), (
        f"a decorated target must decline with a 'decorated' reason; got {reason!r}"
    )


def test_undecorated_target_is_eligible_with_decorated_kwarg():
    """is_decorated=False (the default) must not change eligibility."""
    cd = CallDescriptor.from_dict({"function_ref": {"file": "src/copyclip/foo.py", "name": "bar"}})
    assert eligibility_reason(cd, _resolved(), is_async=False, is_generator=False,
                              is_decorated=False) is None


# ---------------------------------------------------------------------------
# Task 4: In-subprocess capture driver (bounded settrace; every cap proven)
# ---------------------------------------------------------------------------

import importlib

driver = importlib.import_module("copyclip.intelligence._capture_driver")


def test_bounded_repr_summarizes_large_collection():
    v = driver.var_for("xs", list(range(5000)))
    assert v["kind"] == "large"
    assert v["summary"] == "list"
    assert "5,000" in v["meta"] or "5000" in v["meta"]
    assert len(v["children"]) <= driver.LARGE_CHILDREN_CAP


def test_bounded_repr_scalar_is_capped_text():
    v = driver.var_for("n", 42)
    assert v["kind"] == "scalar"
    assert v["text"] == "42"


def test_repr_size_cap_demotes_huge_string_to_large():
    # A scalar whose repr exceeds REPR_SIZE_CAP must surface as kind:"large",
    # never inlined whole (spec §5 cap 2 fires).
    v = driver.var_for("s", "x" * (driver.REPR_SIZE_CAP + 500))
    assert v["kind"] == "large"


def test_opaque_skip_list_for_file_handle(tmp_path):
    f = open(tmp_path / "x.txt", "w")
    try:
        v = driver.var_for("fh", f)
        assert v["kind"] == "opaque"
        assert "TextIOWrapper" in v["label"]
        assert "text" not in v  # never repr'd (spec §5 cap 4 fires)
    finally:
        f.close()


def test_repr_that_raises_is_opaque_not_crash():
    class Boom:
        def __repr__(self):
            raise RuntimeError("nope")
    v = driver.var_for("b", Boom())
    assert v["kind"] == "opaque"  # repr failure → opaque, never propagates


def test_repr_time_budget_cap_fires(monkeypatch):
    # spec §5 cap 3: a __repr__ that BLOCKS must not hang the serializer — the
    # per-value time budget aborts it and the value renders opaque.
    monkeypatch.setattr(driver, "REPR_TIME_BUDGET_S", 0.01)

    class Slow:
        def __repr__(self):
            import time as _t
            _t.sleep(0.2)  # blows the 0.01s budget
            return "slow"
    v = driver.var_for("s", Slow())
    assert v["kind"] == "opaque"  # overran the time budget → opaque, not the repr


def test_trace_function_records_steps_and_scope():
    def sample(a):
        b = a + 1
        c = b * 2
        return c
    raw = driver.trace_call(sample, args=[3], kwargs={})
    assert raw["trace"][-1]["event"] == "return"
    assert not raw.get("truncated")
    names = {v["name"] for ev in raw["trace"] for v in ev["scope"]}
    assert {"a", "b", "c"} <= names
    # The driver does NOT emit `changed` — that is the normalizer's job (spec §9).
    assert all("changed" not in ev for ev in raw["trace"])


def test_trace_records_raise_terminal_step():
    def boom(x):
        return {}[x]
    raw = driver.trace_call(boom, args=["k"], kwargs={})
    last = raw["trace"][-1]
    assert last["event"] == "raise"
    assert last["raised"]["type"] == "KeyError"


def test_max_steps_cap_fires(monkeypatch):
    # spec §5 cap 1: a runaway loop truncates, never hangs.
    monkeypatch.setattr(driver, "MAX_STEPS", 20)
    def loopy(n):
        total = 0
        while True:
            total += 1
    raw = driver.trace_call(loopy, args=[0], kwargs={})
    assert raw["truncated"] is True
    assert len(raw["trace"]) <= 25  # MAX_STEPS + a small terminal slack


def test_wall_clock_cap_fires(monkeypatch):
    # spec §5 cap 5: a long-running capture aborts on the wall-clock guard even
    # if it stays under MAX_STEPS (e.g. a slow body per line).
    monkeypatch.setattr(driver, "WALL_CLOCK_BUDGET_S", 0.05)
    monkeypatch.setattr(driver, "MAX_STEPS", 10_000_000)
    def slow_loop(n):
        import time as _t
        total = 0
        for _ in range(10_000_000):
            _t.sleep(0.001)  # each line burns time → trips the 0.05s guard
            total += 1
    raw = driver.trace_call(slow_loop, args=[0], kwargs={})
    assert raw["truncated"] is True


# ---------------------------------------------------------------------------
# Task 4 (code-quality fix): _trace_free_text — USER free-text path coverage
# ---------------------------------------------------------------------------
# The MODEL path (trace_call) is tested above; the USER path (_trace_free_text)
# shares the same bounds logic but differs in two key details:
#   1. raise-step line = events[-1]["line"] if events else 0  (no last_line dict)
#   2. no last_line tracking at all
# Each test here targets a specific behavior or cap of _trace_free_text.
# ---------------------------------------------------------------------------

import importlib.util as _ilu


def _make_free_text_mod(tmp_path, name: str, source: str):
    """Write source to a temp .py file, import it, register in sys.modules.

    Returns the module name string (suitable for spec["module"]). The caller is
    responsible for removing it from sys.modules when done (use the fixture).
    """
    p = tmp_path / f"{name}.py"
    p.write_text(source, encoding="utf-8")
    spec_obj = _ilu.spec_from_file_location(name, str(p))
    mod = _ilu.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(mod)
    sys.modules[name] = mod
    return name


def test_free_text_happy_path_records_steps_and_scope(tmp_path):
    """_trace_free_text produces call/line/return events and captures scope vars."""
    mod_name = _make_free_text_mod(tmp_path, "_ft_happy", dedent("""\
        def addup(a, b):
            total = a + b
            return total
    """))
    try:
        spec = {"module": mod_name, "name": "addup", "call_text": "addup(2, 3)"}
        raw = driver._trace_free_text(spec)
        assert raw["trace"][-1]["event"] == "return"
        assert not raw["truncated"]
        names = {v["name"] for ev in raw["trace"] for v in ev["scope"]}
        assert {"a", "b", "total"} <= names
    finally:
        sys.modules.pop(mod_name, None)


def test_free_text_no_changed_key_emitted(tmp_path):
    """_trace_free_text never emits 'changed' — that is the normalizer's job (spec §9)."""
    mod_name = _make_free_text_mod(tmp_path, "_ft_nochanged", dedent("""\
        def addup(a, b):
            total = a + b
            return total
    """))
    try:
        spec = {"module": mod_name, "name": "addup", "call_text": "addup(1, 2)"}
        raw = driver._trace_free_text(spec)
        assert all("changed" not in ev for ev in raw["trace"])
    finally:
        sys.modules.pop(mod_name, None)


def test_free_text_raise_step_line_comes_from_last_traced_event(tmp_path):
    """Raise-step line = events[-1]["line"] before the raise, not a last_line dict.

    This verifies the specific implementation detail that distinguishes
    _trace_free_text from trace_call: there is no last_line tracking, so the
    raise event's line is taken from the final captured trace event.

    The assertion uses a CONCRETE expected line number derived from the module
    source written below:
      line 1:  def boom(x):
      line 2:      return {}[x]     <-- last executed line before KeyError

    If line-tracking ever regressed (e.g. the raise step always used line 0
    or the call-frame entry line), this test would fail.
    """
    source = dedent("""\
        def boom(x):
            return {}[x]
    """)
    mod_name = _make_free_text_mod(tmp_path, "_ft_raise", source)
    # The last statement executed inside boom before the KeyError is the
    # "return {}[x]" expression, which is line 2 of the module source above.
    EXPECTED_RAISE_LINE = 2
    try:
        spec = {"module": mod_name, "name": "boom", "call_text": 'boom("k")'}
        raw = driver._trace_free_text(spec)
        last = raw["trace"][-1]
        assert last["event"] == "raise"
        assert last["raised"]["type"] == "KeyError"
        # The raise-step line must equal the concrete source line of the last
        # statement executed before the exception propagated. If line tracking
        # were broken (e.g. always returning 0 or the def-line), this fails.
        assert last["line"] == EXPECTED_RAISE_LINE, (
            f"raise step line was {last['line']}, expected {EXPECTED_RAISE_LINE} "
            f"(line of 'return {{}}[x]' in the test module); "
            f"line-tracking may have regressed in _trace_free_text"
        )
    finally:
        sys.modules.pop(mod_name, None)


def test_free_text_raise_with_no_prior_events_line_is_zero(tmp_path):
    """When the expression raises before any frame anchored to own_file fires,
    events is empty → the raise step gets line=0 (the 'else 0' branch)."""
    mod_name = _make_free_text_mod(tmp_path, "_ft_zero_events", dedent("""\
        def dummy():
            pass
    """))
    try:
        # call_text raises directly without ever entering dummy()'s file-anchored frame
        spec = {"module": mod_name, "name": "dummy", "call_text": "1/0"}
        raw = driver._trace_free_text(spec)
        last = raw["trace"][-1]
        assert last["event"] == "raise"
        assert last["raised"]["type"] == "ZeroDivisionError"
        assert last["line"] == 0  # events was empty → else 0 branch
    finally:
        sys.modules.pop(mod_name, None)


def test_free_text_max_steps_cap_fires(tmp_path, monkeypatch):
    """spec §5 cap 1 also applies to the USER path: a runaway loop truncates."""
    mod_name = _make_free_text_mod(tmp_path, "_ft_loopy", dedent("""\
        def loopy():
            total = 0
            while True:
                total += 1
    """))
    try:
        monkeypatch.setattr(driver, "MAX_STEPS", 20)
        spec = {"module": mod_name, "name": "loopy", "call_text": "loopy()"}
        raw = driver._trace_free_text(spec)
        assert raw["truncated"] is True
        assert len(raw["trace"]) <= 25  # MAX_STEPS + small terminal slack
    finally:
        sys.modules.pop(mod_name, None)


def test_free_text_wall_clock_cap_fires(tmp_path, monkeypatch):
    """spec §5 cap 5 also applies to the USER path: wall-clock guard aborts capture."""
    mod_name = _make_free_text_mod(tmp_path, "_ft_slowloop", dedent("""\
        def slow_loop():
            import time as _t
            total = 0
            for _ in range(10_000_000):
                _t.sleep(0.001)
                total += 1
    """))
    try:
        monkeypatch.setattr(driver, "WALL_CLOCK_BUDGET_S", 0.05)
        monkeypatch.setattr(driver, "MAX_STEPS", 10_000_000)
        spec = {"module": mod_name, "name": "slow_loop", "call_text": "slow_loop()"}
        raw = driver._trace_free_text(spec)
        assert raw["truncated"] is True
    finally:
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Task 5: Subprocess orchestration — run_capture, run_free_text_capture, probe_target
# ---------------------------------------------------------------------------

import textwrap
from copyclip.intelligence.capture import run_capture, run_free_text_capture, probe_target


def _write_user_module(tmp_path, body):
    (tmp_path / "usermod.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


def test_run_capture_traces_a_real_function(tmp_path):
    root = _write_user_module(tmp_path, """
        def addup(a):
            b = a + 1
            return b * 2
    """)
    resolved = ResolvedFunction(file="usermod.py", name="addup", qualname="addup",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    cd = CallDescriptor.from_dict({"function_ref": {"file": "usermod.py", "name": "addup"},
                                   "args": [3]})
    steps, truncated, truncated_reason = run_capture(cd, resolved, project_root=str(root))
    assert truncated is False
    assert truncated_reason is None
    assert steps[-1].event == "return"
    names = {v.name for s in steps for v in s.scope}
    assert {"a", "b"} <= names


def test_run_free_text_capture_executes_user_expression(tmp_path):
    root = _write_user_module(tmp_path, """
        def addup(a):
            b = a + 1
            return b * 2
    """)
    resolved = ResolvedFunction(file="usermod.py", name="addup", qualname="addup",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    ft = FreeTextCall.from_text("addup(3 + 4)")
    steps, truncated, truncated_reason = run_free_text_capture(ft, resolved, project_root=str(root))
    assert steps[-1].event == "return"
    names = {v.name for s in steps for v in s.scope}
    assert {"a", "b"} <= names


def test_probe_detects_async(tmp_path):
    root = _write_user_module(tmp_path, """
        async def fetch(x):
            return x
    """)
    resolved = ResolvedFunction(file="usermod.py", name="fetch", qualname="fetch",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    detect, source_lines = probe_target(resolved, project_root=str(root))
    assert detect["is_async"] is True
    assert any("async def fetch" in sl["text"] for sl in source_lines)


def test_probe_detects_async_generator_as_async(tmp_path):
    root = _write_user_module(tmp_path, """
        async def stream(x):
            yield x
    """)
    resolved = ResolvedFunction(file="usermod.py", name="stream", qualname="stream",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    detect, _ = probe_target(resolved, project_root=str(root))
    assert detect["is_async"] is True  # async-gen → async reason, not generator


def test_run_capture_raise_is_terminal_step(tmp_path):
    root = _write_user_module(tmp_path, """
        def boom(k):
            return {}[k]
    """)
    resolved = ResolvedFunction(file="usermod.py", name="boom", qualname="boom",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    cd = CallDescriptor.from_dict({"function_ref": {"file": "usermod.py", "name": "boom"},
                                   "args": ["x"]})
    steps, truncated, truncated_reason = run_capture(cd, resolved, project_root=str(root))
    assert steps[-1].event == "raise"
    assert steps[-1].raised["type"] == "KeyError"


# ---------------------------------------------------------------------------
# NEW: Critical #3/#5 — FallbackResponse must carry playground_id
# ---------------------------------------------------------------------------

def test_fallback_response_to_dict_includes_playground_id():
    """FallbackResponse must serialize playground_id so the frontend can use it
    for the live-state id, /status poll, and reap — NOT idFromIframeUrl."""
    fb = FallbackResponse(reason="async function", iframe_url="http://127.0.0.1:5000/",
                          playground_id="pgid-abc")
    d = fb.to_dict()
    assert d == {"kind": "fallback", "reason": "async function",
                 "iframe_url": "http://127.0.0.1:5000/", "playground_id": "pgid-abc"}


def test_fallback_response_playground_id_required():
    """playground_id is a required field; omitting it must fail."""
    import inspect as _i
    params = _i.signature(FallbackResponse.__init__).parameters
    # dataclass: check that playground_id has no default (is required)
    assert "playground_id" in params


# ---------------------------------------------------------------------------
# NEW: Critical #2 — empty trace → FallbackResponse (not StepThroughResponse)
# This is tested at the _build_invocation level via capture module seam.
# The launch_playground integration test lives in test_playground_trace.py.
# ---------------------------------------------------------------------------

def test_fallback_response_shape_roundtrip():
    """FallbackResponse.to_dict() produces the exact shape the frontend consumes."""
    fb = FallbackResponse(reason="that call didn't run the function — nothing to step through",
                          iframe_url="http://127.0.0.1:5000/",
                          playground_id="pg-xyz")
    d = fb.to_dict()
    assert d["kind"] == "fallback"
    assert d["reason"] == "that call didn't run the function — nothing to step through"
    assert d["iframe_url"] == "http://127.0.0.1:5000/"
    assert d["playground_id"] == "pg-xyz"


# ---------------------------------------------------------------------------
# NEW: Medium correctness — opaque skip-list tightening
# _is_opaque_type must use module-anchored FQN so a user class named
# ConnectionManager is NOT hidden while a real sqlite3.Connection IS.
# ---------------------------------------------------------------------------

def test_opaque_skips_real_sqlite3_connection():
    """A real sqlite3.Connection must be rendered opaque (dangerous to repr)."""
    import sqlite3 as _sq3
    conn = _sq3.connect(":memory:")
    try:
        v = driver.var_for("conn", conn)
        assert v["kind"] == "opaque", (
            f"sqlite3.Connection should be opaque, got kind={v['kind']!r}"
        )
    finally:
        conn.close()


def test_opaque_does_not_hide_user_class_with_connection_substring():
    """A user-defined class whose name contains 'Connection' must NOT be skipped.
    The skip-list must match module-anchored FQN prefixes, not loose substrings."""
    class ConnectionManager:  # user class — NOT sqlite3/sqlalchemy
        def __repr__(self):
            return "ConnectionManager(host='localhost')"

    v = driver.var_for("mgr", ConnectionManager())
    assert v["kind"] != "opaque", (
        f"A user class named ConnectionManager must NOT be rendered opaque; "
        f"got kind={v['kind']!r}. The opaque skip-list must match module-anchored "
        f"FQN prefixes (e.g. 'sqlite3.'), not loose substrings."
    )
    # Also verify that a class named 'Engine' in __main__ is not skipped
    class Engine:
        def __repr__(self):
            return "Engine(threads=4)"

    ve = driver.var_for("eng", Engine())
    assert ve["kind"] != "opaque", (
        f"A user class named Engine must NOT be rendered opaque; "
        f"got kind={ve['kind']!r}"
    )


def test_opaque_does_not_hide_user_class_named_session():
    """A user class named Session (not sqlalchemy.orm.Session) must not be opaque."""
    class Session:  # user class
        def __repr__(self):
            return "Session(user='alice')"

    v = driver.var_for("s", Session())
    assert v["kind"] != "opaque", (
        f"User class 'Session' should NOT be opaque (no module prefix match); "
        f"got kind={v['kind']!r}"
    )


# ---------------------------------------------------------------------------
# NEW: Critical #1 — emit boundary SEAM: model top-level args/kwargs/ctor
# folded into widget.data.call + call_text computed from _build_invocation logic
# ---------------------------------------------------------------------------

from copyclip.intelligence.cuaderno.emit_fold import fold_playground_widget


def test_emit_fold_plain_function_produces_call_and_call_text():
    """A plain-function emit_block dict with top-level args/kwargs must produce
    widget.data.call and widget.data.call_text."""
    emit_block = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {"file": "src/foo.py", "name": "addup"},
            "breadcrumb": "Step through addup",
            "args": [1, 2],
            "kwargs": {"verbose": True},
        },
    }
    result = fold_playground_widget(emit_block)
    w = result["widget"]
    assert "call" in w, "folded widget must have a 'call' key"
    assert w["call"]["function_ref"] == {"file": "src/foo.py", "name": "addup"}
    assert w["call"]["args"] == [1, 2]
    assert w["call"]["kwargs"] == {"verbose": True}
    assert "call_text" in w, "folded widget must have a 'call_text' key"
    # call_text must be a real invocation, not a placeholder
    assert w["call_text"] == "addup(1, 2, verbose=True)", (
        f"Expected 'addup(1, 2, verbose=True)', got {w['call_text']!r}"
    )
    # Top-level args/kwargs must be removed from widget root (they live in call now)
    assert "args" not in w
    assert "kwargs" not in w


def test_emit_fold_method_with_ctor_produces_call_and_call_text():
    """A method emit_block with ctor must produce call_text of the form
    'Foo(ctor_args).method(args)' with repr-literal args."""
    emit_block = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {
                "file": "src/foo.py",
                "name": "process",
                "qualname": "MyClass.process",
            },
            "breadcrumb": "Step through MyClass.process",
            "args": ["input.txt"],
            "kwargs": {},
            "ctor": {"args": [42], "kwargs": {"mode": "strict"}},
        },
    }
    result = fold_playground_widget(emit_block)
    w = result["widget"]
    assert w["call"]["ctor"] == {"args": [42], "kwargs": {"mode": "strict"}}
    # strings must be repr()'d — 'input.txt' → "'input.txt'"
    assert w["call_text"] == "MyClass(42, mode='strict').process('input.txt')", (
        f"Got {w['call_text']!r}"
    )


def test_emit_fold_string_arg_is_repr_quoted():
    """String args must appear quoted in call_text (repr-literal form, spec §4)."""
    emit_block = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {"file": "src/foo.py", "name": "greet"},
            "breadcrumb": "Step through greet",
            "args": ["hello world"],
            "kwargs": {},
        },
    }
    result = fold_playground_widget(emit_block)
    w = result["widget"]
    assert w["call_text"] == "greet('hello world')", (
        f"String arg must be repr-quoted; got {w['call_text']!r}"
    )


def test_emit_fold_no_args_no_call_text_placeholder():
    """When no args/kwargs/ctor are present, call_text is 'name()' (not a placeholder)."""
    emit_block = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {"file": "src/foo.py", "name": "run"},
            "breadcrumb": "Step through run",
        },
    }
    result = fold_playground_widget(emit_block)
    w = result["widget"]
    assert w["call_text"] == "run()"
    assert w["call"]["args"] == []
    assert w["call"]["kwargs"] == {}
    assert w["call"].get("ctor") is None


def test_emit_fold_non_playground_widget_passthrough():
    """A non-playground widget block must pass through unmodified."""
    block = {"kind": "widget", "widget": {"kind": "graph_subset", "nodes": [], "edges": []}}
    assert fold_playground_widget(block) is block


def test_emit_fold_non_widget_block_passthrough():
    """A non-widget block must pass through unmodified."""
    block = {"kind": "paragraph", "text": "hello"}
    assert fold_playground_widget(block) is block


# ===========================================================================
# FINAL-REVIEW BACKEND FIXES — TDD tests (must FAIL before fixes are applied)
# ===========================================================================


# ---------------------------------------------------------------------------
# Fix 1: _Abort must be BaseException so user `except Exception:` loops do not
# swallow it, causing runaway captures to bypass the abort.
# ---------------------------------------------------------------------------

def test_abort_not_caught_by_except_exception(monkeypatch):
    """A function whose loop body swallows Exception must STILL be aborted at
    MAX_STEPS (truncated trace). _Abort must be BaseException, not Exception."""
    monkeypatch.setattr(driver, "MAX_STEPS", 10)

    def runaway_swallow():
        total = 0
        while True:
            try:
                total += 1
            except Exception:  # noqa: BLE001 — deliberately swallows Exception
                continue

    raw = driver.trace_call(runaway_swallow, args=[], kwargs={})
    assert raw["truncated"] is True, (
        "_Abort must be BaseException so it is NOT caught by 'except Exception:'; "
        "if it is only Exception, the loop swallows the abort and this never truncates."
    )


def test_abort_is_base_exception_not_exception():
    """_Abort must be a BaseException subclass (not Exception) so that a loop
    body with 'except Exception: continue' cannot swallow the cap abort.
    A bare 'except:' does catch BaseException in Python; the spec's stated goal
    is specifically that 'except Exception:' (the common defensive pattern)
    cannot intercept the abort — this test pins that contract."""
    assert not issubclass(driver._Abort, Exception), (
        "_Abort must NOT inherit from Exception. "
        "Change 'class _Abort(Exception)' to 'class _Abort(BaseException)' so "
        "that 'except Exception:' guards in user code cannot swallow the abort."
    )
    assert issubclass(driver._Abort, BaseException), (
        "_Abort must be a BaseException subclass."
    )


# ---------------------------------------------------------------------------
# Fix 2: `exception` events are NOT in the schema union — handle inside tracer.
# (a) No step has event outside {call, line, return, raise}
# (b) Uncaught raise terminal step must have non-empty scope + correct raised
# (c) Caught-and-handled exception must NOT emit an 'exception'-typed step
# ---------------------------------------------------------------------------

_VALID_EVENTS = frozenset({"call", "line", "return", "raise"})


def test_no_step_has_event_outside_schema_union(tmp_path):
    """Every step emitted by trace_call/normalize_trace must have event in the
    schema union {call, line, return, raise}. 'exception' is NOT in the union."""
    mod_name = _make_free_text_mod(tmp_path, "_ev_schema", dedent("""\
        def func_with_catch(xs):
            result = []
            for x in xs:
                try:
                    result.append(1 // x)
                except ZeroDivisionError:
                    result.append(0)
            return result
    """))
    try:
        spec = {"module": mod_name, "name": "func_with_catch",
                "call_text": "func_with_catch([1, 0, 2])"}
        raw = driver._trace_free_text(spec)
        bad = [ev for ev in raw["trace"] if ev.get("event") not in _VALID_EVENTS]
        assert not bad, (
            f"Steps with non-schema events: {bad!r}. "
            "'exception' events from sys.settrace must be suppressed inside the tracer."
        )
    finally:
        sys.modules.pop(mod_name, None)


def test_uncaught_raise_terminal_step_has_nonempty_scope_and_raised(tmp_path):
    """A function that raises uncaught must yield a terminal 'raise' step with
    non-empty scope (captured from frame.f_locals) AND a correct raised dict.
    Currently the synthetic raise step in trace_call uses scope:[] — fix that."""
    mod_name = _make_free_text_mod(tmp_path, "_uncaught_raise", dedent("""\
        def boom_with_locals(x):
            msg = 'about to fail'
            raise ValueError(msg)
    """))
    try:
        spec = {"module": mod_name, "name": "boom_with_locals",
                "call_text": "boom_with_locals(42)"}
        raw = driver._trace_free_text(spec)
        last = raw["trace"][-1]
        assert last["event"] == "raise", f"Expected raise, got {last['event']!r}"
        assert last["raised"]["type"] == "ValueError"
        assert last["raised"]["message"] == "about to fail"
        scope_names = {v["name"] for v in last["scope"]}
        assert scope_names, (
            "Terminal raise step must capture scope from frame.f_locals; "
            "got empty scope. Fix: capture scope from the exception frame, "
            "not from a pre-raise snapshot."
        )
        assert "x" in scope_names or "msg" in scope_names, (
            f"Expected local vars 'x' or 'msg' in raise scope; got {scope_names!r}"
        )
    finally:
        sys.modules.pop(mod_name, None)


def test_caught_exception_does_not_emit_exception_event(tmp_path):
    """When an exception is caught inside the function, no 'exception'-typed
    step must appear in the trace — 'exception' is not in the schema union."""
    mod_name = _make_free_text_mod(tmp_path, "_caught_exc", dedent("""\
        def safe(x):
            try:
                return 1 // x
            except ZeroDivisionError:
                return -1
    """))
    try:
        spec = {"module": mod_name, "name": "safe", "call_text": "safe(0)"}
        raw = driver._trace_free_text(spec)
        exc_steps = [ev for ev in raw["trace"] if ev.get("event") == "exception"]
        assert not exc_steps, (
            f"Caught exceptions must NOT emit 'exception' steps; got {exc_steps!r}"
        )
    finally:
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Fix 3a: SUBPROCESS kill path coverage — a pathological (slow) capture trips
# communicate(timeout=...) → _kill_group → CaptureError.
# ---------------------------------------------------------------------------

import textwrap as _tw


def test_subprocess_kill_group_on_timeout(tmp_path, monkeypatch):
    """A capture that hangs must trip proc.communicate(timeout=...) → _kill_group
    → CaptureError. Tests the OUTER subprocess kill path in _run_driver by
    mocking communicate() to raise TimeoutExpired (safe, no real subprocess needed)."""
    from copyclip.intelligence.capture import CaptureError, _run_driver, _kill_group
    import copyclip.intelligence.capture as _cap_mod
    import unittest.mock as _mock

    kill_called = {"n": 0}

    def fake_kill_group(proc):
        kill_called["n"] += 1
        # Don't actually kill anything — just record the call
        pass

    monkeypatch.setattr(_cap_mod, "_kill_group", fake_kill_group)

    # Build a spec for a module that genuinely exists so Popen starts OK,
    # but mock communicate() to immediately raise TimeoutExpired.
    (tmp_path / "slow.py").write_text(_tw.dedent("""\
        def noop():
            pass
    """), encoding="utf-8")

    spec = {
        "module": "slow",
        "name": "noop",
        "parent_class": None,
        "args": [],
        "kwargs": {},
        "probe": False,
    }

    original_popen = _cap_mod.subprocess.Popen

    class _FakePopen:
        def __init__(self, *a, **kw):
            self.returncode = 0
            self.pid = 99999

        def communicate(self, timeout=None):
            raise _cap_mod.subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    monkeypatch.setattr(_cap_mod.subprocess, "Popen", _FakePopen)

    with pytest.raises(CaptureError, match="wall-clock"):
        _run_driver(spec, str(tmp_path))

    assert kill_called["n"] == 1, (
        "_kill_group must be called exactly once when communicate() times out; "
        f"was called {kill_called['n']} times"
    )


# ---------------------------------------------------------------------------
# Fix 3b: Tighten test_fallback_response_playground_id_required to actually
# assert the parameter has NO default (inspect.Parameter.empty).
# ---------------------------------------------------------------------------

def test_fallback_response_playground_id_has_no_default():
    """Regression guard: FallbackResponse.playground_id must remain a required field
    with NO default (inspect.Parameter.empty). The field was previously optional with
    an empty-string default; this test ensures it is never silently made optional
    again — omitting it must raise TypeError."""
    import inspect as _i
    sig = _i.signature(FallbackResponse)
    param = sig.parameters.get("playground_id")
    assert param is not None, "FallbackResponse must have a playground_id parameter"
    assert param.default is _i.Parameter.empty, (
        f"FallbackResponse.playground_id must be a required field (no default), "
        f"but it defaults to {param.default!r}. "
        "Remove the default so omitting it raises TypeError."
    )


# ---------------------------------------------------------------------------
# Fix 4: var_for calls repr twice for _LARGE_BY_LEN objects — double budget.
# After the fix, _too_big_repr + _safe_repr must call repr at most once total
# for the same object (inline to a single _safe_repr call).
# ---------------------------------------------------------------------------

def test_var_for_calls_repr_at_most_once_for_large_by_len(monkeypatch):
    """For a _LARGE_BY_LEN object, var_for must call repr at most once.
    Currently it calls _too_big_repr (which calls repr via _safe_repr), then
    if that returns False, calls _safe_repr again — doubling the budget."""
    repr_count = {"n": 0}

    class CountedList(list):
        def __repr__(self):
            repr_count["n"] += 1
            return f"[{len(self)} items]"

    # A small list (3 items) that is NOT too big — exercises the path through
    # _too_big_repr (returns False) then into _safe_repr.
    obj = CountedList([1, 2, 3])
    repr_count["n"] = 0  # reset after construction
    driver.var_for("xs", obj)
    assert repr_count["n"] <= 1, (
        f"var_for called repr {repr_count['n']} times on a small list; "
        "must call it at most once (inline _too_big_repr + _safe_repr into one call)."
    )


# ---------------------------------------------------------------------------
# Fix 5: _assert_json_serializable must use allow_nan=False so NaN/Inf are
# rejected (they break browser JSON.parse).
# ---------------------------------------------------------------------------

def test_assert_json_serializable_rejects_nan():
    """float('nan') must be rejected by _assert_json_serializable (browser
    JSON.parse cannot handle NaN serialized as 'NaN')."""
    from copyclip.intelligence.capture import _assert_json_serializable, InvalidCallDescriptorError
    with pytest.raises(InvalidCallDescriptorError):
        _assert_json_serializable(float("nan"), "test")


def test_assert_json_serializable_rejects_inf():
    """float('inf') must be rejected by _assert_json_serializable."""
    from copyclip.intelligence.capture import _assert_json_serializable, InvalidCallDescriptorError
    with pytest.raises(InvalidCallDescriptorError):
        _assert_json_serializable(float("inf"), "test")


def test_assert_json_serializable_rejects_neg_inf():
    """float('-inf') must be rejected by _assert_json_serializable."""
    from copyclip.intelligence.capture import _assert_json_serializable, InvalidCallDescriptorError
    with pytest.raises(InvalidCallDescriptorError):
        _assert_json_serializable(float("-inf"), "test")


def test_assert_json_serializable_accepts_normal_float():
    """Normal floats like 3.14 must still pass."""
    from copyclip.intelligence.capture import _assert_json_serializable
    _assert_json_serializable(3.14, "test")  # must not raise


# ---------------------------------------------------------------------------
# Fix 6: emit_fold qualname parser drops ctor for nested-class methods.
# Outer.Inner.method → must render Inner(ctor).method(args), NOT method(args).
# ---------------------------------------------------------------------------

def test_emit_fold_nested_class_qualname_falls_back_to_plain_call():
    """FunctionRef (the v1 gate) rejects qualnames with >2 segments, so emit_fold
    must NOT emit a nested-class ctor form that the validator would 400.  A
    3-segment qualname like 'Outer.Inner.method' must produce a plain call (no
    ctor prefix) so the fold output is always valid at the v1 gate."""
    emit_block = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {
                "file": "src/foo.py",
                "name": "method",
                "qualname": "Outer.Inner.method",
            },
            "breadcrumb": "Step through Outer.Inner.method",
            "args": [1],
            "kwargs": {},
            "ctor": {"args": [99], "kwargs": {}},
        },
    }
    result = fold_playground_widget(emit_block)
    w = result["widget"]
    # 3-segment qualname → no parent_class → plain call, never the validator-400 form
    assert w["call_text"] == "method(1)", (
        f"A 3-segment qualname must fall back to a plain call (no ctor prefix), "
        f"not the nested-class form that FunctionRef would 400; got {w['call_text']!r}."
    )


def test_emit_fold_two_level_qualname_still_works():
    """A two-part qualname like 'MyClass.method' must still produce MyClass(...)."""
    emit_block = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {
                "file": "src/foo.py",
                "name": "method",
                "qualname": "MyClass.method",
            },
            "breadcrumb": "Step",
            "args": [],
            "kwargs": {},
            "ctor": {"args": [1], "kwargs": {}},
        },
    }
    result = fold_playground_widget(emit_block)
    w = result["widget"]
    assert w["call_text"] == "MyClass(1).method()", (
        f"Two-level qualname must use MyClass; got {w['call_text']!r}"
    )


# ---------------------------------------------------------------------------
# Fix 7a: FreeTextCall must reject NEWLINE injection (not just ';')
# ---------------------------------------------------------------------------

def test_free_text_call_rejects_newline_injection():
    """FreeTextCall.from_text must reject text containing a newline character
    (multi-line injection like 'foo()\\nimport os')."""
    with pytest.raises(InvalidCallDescriptorError):
        FreeTextCall.from_text("foo()\nimport os")


def test_free_text_call_rejects_escaped_newline():
    """FreeTextCall.from_text must also reject \\n when the string truly contains
    a newline (not just a backslash-n in a literal)."""
    with pytest.raises(InvalidCallDescriptorError):
        FreeTextCall.from_text("foo()\nimport sys")


# ---------------------------------------------------------------------------
# Fix 7b: capture spec module-name traversal rejection
# ---------------------------------------------------------------------------

def test_call_descriptor_rejects_traversal_module_name():
    """A capture spec with a module name like '../x' must be rejected before
    importlib sees it — currently no validation exists for module traversal."""
    from copyclip.intelligence.capture import InvalidCallDescriptorError
    # We test via the validate path on FunctionRef (file field) — and also add
    # a direct module-name check if that path is exercised. At minimum, the
    # FunctionRef file path must reject path traversal.
    from copyclip.intelligence.playground import FunctionRef
    with pytest.raises(Exception):  # PlaygroundError or ValueError
        FunctionRef.from_dict({"file": "../../../etc/passwd", "name": "foo"})


def test_run_driver_spec_rejects_semicolon_in_module(tmp_path):
    """_run_driver / _build_invocation must reject a module name containing ';'
    (command injection attempt) before importlib.import_module is called."""
    from copyclip.intelligence.capture import CaptureError, _run_driver

    spec = {
        "module": "os;import sys",  # injection attempt
        "name": "getpid",
        "parent_class": None,
        "args": [],
        "kwargs": {},
        "probe": False,
    }
    # This should either raise CaptureError (driver subprocess reports error)
    # or raise some validation error — it must NOT silently succeed.
    with pytest.raises((CaptureError, Exception)):
        _run_driver(spec, str(tmp_path))


# ---------------------------------------------------------------------------
# Fix 7c: Prompt schema test — embedded JSON schema must match CallDescriptor
# wire shape (args/kwargs/ctor), not just substring presence.
# ---------------------------------------------------------------------------

def test_system_prompt_playground_schema_matches_call_descriptor_shape():
    """The playground widget shape in SYSTEM_PROMPT must document the exact
    CallDescriptor fields (args, kwargs, ctor) so the model emits them correctly.
    Test that 'args', 'kwargs', and 'ctor' all appear in the playground widget
    description AND that 'function_ref' appears (the required anchor field)."""
    from copyclip.intelligence.cuaderno.prompts import SYSTEM_PROMPT

    # Find the playground widget section
    assert "playground" in SYSTEM_PROMPT, "SYSTEM_PROMPT must mention 'playground'"

    # The schema must document all three CallDescriptor fields
    playground_section_start = SYSTEM_PROMPT.find('"kind": "playground"')
    assert playground_section_start >= 0, (
        "SYSTEM_PROMPT must contain the playground widget schema "
        "('{\"kind\": \"playground\", ...}')"
    )

    # Extract a reasonable window around the playground widget doc
    window = SYSTEM_PROMPT[playground_section_start: playground_section_start + 500]

    for field in ("args", "kwargs", "ctor", "function_ref"):
        assert field in window, (
            f"Playground widget schema in SYSTEM_PROMPT must document field '{field}'. "
            f"Window: {window!r}"
        )


def test_widget_recovery_directive_run_documents_call_descriptor_fields():
    """WIDGET_RECOVERY_DIRECTIVE_RUN must name all three CallDescriptor invocation
    fields (args, kwargs, ctor) so the model knows what to emit on recovery."""
    from copyclip.intelligence.cuaderno.prompts import WIDGET_RECOVERY_DIRECTIVE_RUN

    for field in ("args", "kwargs", "ctor"):
        assert field in WIDGET_RECOVERY_DIRECTIVE_RUN, (
            f"WIDGET_RECOVERY_DIRECTIVE_RUN must mention '{field}' so the model "
            f"knows to include it. Got: {WIDGET_RECOVERY_DIRECTIVE_RUN!r}"
        )


# ===========================================================================
# TRACER-CORRECTNESS — PR #177 staff review (5 fixes), TDD (fail-first)
# ===========================================================================


# ---------------------------------------------------------------------------
# Fix 1: frame-scoping — anchor on the TARGET's CODE OBJECT, not its filename.
# Other pure-Python functions in the SAME file must NOT interleave their lines
# into the flat Step[] (spec §5 + §7 "library calls appear as one step").
# ---------------------------------------------------------------------------

def test_sibling_function_in_same_file_is_not_traced(tmp_path):
    """A helper defined in the SAME module file as the target must appear as one
    opaque step (no per-line interleaving). Anchoring on co_filename alone would
    trace the helper's body and mis-anchor it on the target's source pane."""
    mod_name = _make_free_text_mod(tmp_path, "_fs_sibling", dedent("""\
        def helper(z):
            a = z + 1
            b = a + 1
            return b

        def target(n):
            result = helper(n)
            return result + 100
    """))
    try:
        spec = {"module": mod_name, "name": "target", "call_text": "target(5)"}
        raw = driver._trace_free_text(spec)
        # The helper's body lines (2,3,4) must NOT appear as steps — only the
        # target's own lines (the def-line and lines 7,8).
        lines = [ev["line"] for ev in raw["trace"]]
        # helper's interior lines (2 'a = z + 1', 3 'b = a + 1', 4 'return b')
        for helper_line in (2, 3, 4):
            assert helper_line not in lines, (
                f"helper interior line {helper_line} leaked into the target trace: {lines!r}. "
                "Frame-scoping must anchor on the target's CODE OBJECT, not co_filename."
            )
    finally:
        sys.modules.pop(mod_name, None)


def test_sibling_function_not_traced_model_path():
    """Same guard for trace_call (the MODEL path): a sibling helper in the same
    file as the target must not interleave its lines."""
    src = dedent("""\
        def _helper(z):
            inner_a = z * 2
            inner_b = inner_a * 2
            return inner_b

        def model_target(n):
            mt_x = _helper(n)
            return mt_x + 1
    """)
    ns: dict = {}
    exec(compile(src, "<model_target_mod>", "exec"), ns, ns)
    fn = ns["model_target"]
    raw = driver.trace_call(fn, args=[3], kwargs={})
    # No step's scope should ever contain the helper's locals (inner_a/inner_b).
    leaked = {v["name"] for ev in raw["trace"] for v in ev["scope"]
              if v["name"] in {"inner_a", "inner_b", "z"}}
    assert not leaked, (
        f"helper locals leaked into the target trace: {leaked!r}. "
        "trace_call must anchor on func.__code__, not on the shared filename."
    )


def test_recursion_within_target_is_still_traced():
    """Recursion re-enters the SAME code object, so it must STILL be traced
    (frame-scoping anchors on the code object, which recursion shares)."""
    src = dedent("""\
        def fact(n):
            if n <= 1:
                return 1
            return n * fact(n - 1)
    """)
    ns: dict = {}
    exec(compile(src, "<fact_mod>", "exec"), ns, ns)
    raw = driver.trace_call(ns["fact"], args=[3], kwargs={})
    # Multiple 'call' events prove the recursive frames were traced (same code obj).
    call_events = [ev for ev in raw["trace"] if ev["event"] == "call"]
    assert len(call_events) >= 3, (
        f"recursive calls into the SAME code object must be traced; "
        f"got {len(call_events)} call events: {[e['line'] for e in raw['trace']]!r}"
    )


# ---------------------------------------------------------------------------
# Fix 1 (defense-in-depth): normalize_trace must DROP/mark any step whose `line`
# falls outside the captured source_lines range, so a foreign frame can never
# null the slab.
# ---------------------------------------------------------------------------

def test_normalize_drops_steps_outside_source_line_range():
    """normalize_trace, given source_lines, must drop steps whose line is outside
    the captured [min,max] range (a foreign frame leaking through)."""
    raw = _raw([
        {"line": 10, "event": "call", "scope": [{"name": "a", "kind": "scalar", "text": "1"}]},
        {"line": 999, "event": "line", "scope": [{"name": "b", "kind": "scalar", "text": "2"}]},
        {"line": 11, "event": "return", "scope": [{"name": "a", "kind": "scalar", "text": "1"}]},
    ])
    source_lines = [{"num": 10, "text": "def f(a):"}, {"num": 11, "text": "    return a"}]
    steps = normalize_trace(raw, source_lines=source_lines)
    lines = [s.line for s in steps]
    assert 999 not in lines, (
        f"step on line 999 (outside source range 10-11) must be dropped; got {lines!r}"
    )
    assert lines == [10, 11]


def test_normalize_without_source_lines_keeps_all_steps():
    """When source_lines is not supplied (back-compat), normalize_trace must not
    drop anything — the defense-in-depth filter only engages with a known range."""
    raw = _raw([
        {"line": 10, "event": "line", "scope": []},
        {"line": 999, "event": "line", "scope": []},
    ])
    steps = normalize_trace(raw)
    assert [s.line for s in steps] == [10, 999]


# ---------------------------------------------------------------------------
# Fix 3: raise-line — trace_call and _trace_free_text must use the SAME source
# for the terminal raise step's line (the last line the target frame executed).
# ---------------------------------------------------------------------------

def test_trace_call_raise_line_matches_last_executed_line():
    """trace_call's terminal raise step line must be the last line the target
    frame executed before the exception (unified with _trace_free_text)."""
    src = dedent("""\
        def boom_locals(x):
            y = x + 1
            raise ValueError('nope')
    """)
    ns: dict = {}
    exec(compile(src, "<boom_mod>", "exec"), ns, ns)
    raw = driver.trace_call(ns["boom_locals"], args=[7], kwargs={})
    last = raw["trace"][-1]
    assert last["event"] == "raise"
    # The 'raise ValueError' statement is line 3 of the source above.
    assert last["line"] == 3, (
        f"raise step line was {last['line']}, expected 3 (the 'raise' statement line)"
    )


# ---------------------------------------------------------------------------
# Fix 5: truncated reason — split MAX_STEPS overflow ('steps') from WALL_CLOCK
# overrun ('time'). The driver must carry a `truncated_reason` on the payload.
# ---------------------------------------------------------------------------

def test_truncated_reason_steps_on_max_steps(monkeypatch):
    """A MAX_STEPS overflow must carry truncated_reason='steps'."""
    monkeypatch.setattr(driver, "MAX_STEPS", 20)
    def loopy(n):
        total = 0
        while True:
            total += 1
    raw = driver.trace_call(loopy, args=[0], kwargs={})
    assert raw["truncated"] is True
    assert raw["truncated_reason"] == "steps", (
        f"MAX_STEPS overflow must report reason 'steps'; got {raw.get('truncated_reason')!r}"
    )


def test_truncated_reason_time_on_wall_clock(monkeypatch):
    """A WALL_CLOCK overrun must carry truncated_reason='time'."""
    monkeypatch.setattr(driver, "WALL_CLOCK_BUDGET_S", 0.05)
    monkeypatch.setattr(driver, "MAX_STEPS", 10_000_000)
    def slow_loop(n):
        import time as _t
        total = 0
        for _ in range(10_000_000):
            _t.sleep(0.001)
            total += 1
    raw = driver.trace_call(slow_loop, args=[0], kwargs={})
    assert raw["truncated"] is True
    assert raw["truncated_reason"] == "time", (
        f"WALL_CLOCK overrun must report reason 'time'; got {raw.get('truncated_reason')!r}"
    )


def test_truncated_reason_none_when_not_truncated():
    """A clean run carries truncated_reason=None (no conflation with a raise)."""
    def ok(a):
        b = a + 1
        return b
    raw = driver.trace_call(ok, args=[1], kwargs={})
    assert raw["truncated"] is False
    assert raw.get("truncated_reason") is None


def test_truncated_reason_steps_free_text(tmp_path, monkeypatch):
    """The USER free-text path must also carry truncated_reason='steps'."""
    mod_name = _make_free_text_mod(tmp_path, "_tr_loopy", dedent("""\
        def loopy():
            total = 0
            while True:
                total += 1
    """))
    try:
        monkeypatch.setattr(driver, "MAX_STEPS", 20)
        spec = {"module": mod_name, "name": "loopy", "call_text": "loopy()"}
        raw = driver._trace_free_text(spec)
        assert raw["truncated"] is True
        assert raw["truncated_reason"] == "steps"
    finally:
        sys.modules.pop(mod_name, None)


def test_change_signature_flags_inplace_mutation_with_stable_summary():
    """Fix 4: an in-place mutation of a large value with a STABLE (summary, meta)
    must still flag as changed — fold a length/identity component into the
    large-var change signature."""
    # Same summary+meta both steps, but the list contents changed in place.
    raw = _raw([
        {"line": 1, "event": "line", "scope": [
            {"name": "xs", "kind": "large", "summary": "list", "meta": "30 items",
             "children": [{"name": "0", "text": "1"}]},
        ]},
        {"line": 2, "event": "line", "scope": [
            {"name": "xs", "kind": "large", "summary": "list", "meta": "30 items",
             "children": [{"name": "0", "text": "999"}]},
        ]},
    ])
    steps = normalize_trace(raw)
    assert "xs" in steps[1].changed, (
        "an in-place mutation with stable summary/meta but changed children must "
        f"still flag; got changed={steps[1].changed!r}"
    )


# ---------------------------------------------------------------------------
# Fix 2: decorated-target honesty — detect_kind must report a decorated target
# so the eligibility gate can decline with an honest reason (the decorator makes
# own_file the wrapper's file; the real body is never anchored).
# ---------------------------------------------------------------------------

def test_detect_kind_flags_decorated_target(tmp_path):
    """A decorated target (functools.wraps so __wrapped__ is set, but co_name of
    the visible function differs from name OR __wrapped__ exists) must report
    is_decorated=True so the gate can decline honestly."""
    mod_name = _make_free_text_mod(tmp_path, "_dec_target", dedent("""\
        import functools

        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*a, **kw):
                return fn(*a, **kw)
            return wrapper

        @deco
        def work(x):
            return x + 1
    """))
    try:
        spec = {"module": mod_name, "name": "work"}
        detect = driver.detect_kind(spec)
        assert detect.get("is_decorated") is True, (
            f"decorated target must report is_decorated=True; got {detect!r}"
        )
    finally:
        sys.modules.pop(mod_name, None)


def test_detect_kind_undecorated_target_is_not_flagged(tmp_path):
    """An ordinary function must report is_decorated=False."""
    mod_name = _make_free_text_mod(tmp_path, "_undec_target", dedent("""\
        def plain(x):
            return x + 1
    """))
    try:
        detect = driver.detect_kind({"module": mod_name, "name": "plain"})
        assert detect.get("is_decorated") is False
    finally:
        sys.modules.pop(mod_name, None)


# ===========================================================================
# ORCHESTRATION / SAFETY — PR #177 staff review, TDD (fail-first)
# ===========================================================================


# ---------------------------------------------------------------------------
# SAFETY Fix 2: capture.py must cap concurrent captures (mirror marimo_runner's
# MAX_CONCURRENT_PLAYGROUNDS=5). A saturated capture pool returns a stable
# error_code, not an unbounded fan-out of subprocesses.
# ---------------------------------------------------------------------------

import copyclip.intelligence.capture as _cap


def test_capture_concurrency_cap_constant_mirrors_runner():
    """capture.py must expose a concurrency ceiling equal to the runner's."""
    from copyclip.intelligence.marimo_runner import MAX_CONCURRENT_PLAYGROUNDS
    assert _cap.MAX_CONCURRENT_CAPTURES == MAX_CONCURRENT_PLAYGROUNDS


def test_capture_saturation_returns_stable_error_code(tmp_path, monkeypatch):
    """When the capture semaphore is saturated, _run_driver must raise a
    PlaygroundError subclass with a STABLE error_code (HTTP 503), never spawn an
    unbounded number of subprocesses or block forever."""
    from copyclip.intelligence.capture import CaptureBusyError, _run_driver

    # Drain every permit so the next acquire fails immediately.
    sem = _cap._CAPTURE_SEMAPHORE
    acquired = 0
    while sem.acquire(blocking=False):
        acquired += 1
    try:
        spec = {"module": "os", "name": "getpid", "parent_class": None,
                "args": [], "kwargs": {}, "probe": False}
        with pytest.raises(CaptureBusyError) as ei:
            _run_driver(spec, str(tmp_path))
        assert ei.value.error_code == "capture_busy"
        assert ei.value.http_status == 503
    finally:
        for _ in range(acquired):
            sem.release()


def test_capture_busy_error_is_playground_error():
    """CaptureBusyError must be a PlaygroundError so the endpoint catches it and
    emits stable JSON instead of a traceback."""
    from copyclip.intelligence.capture import CaptureBusyError
    from copyclip.intelligence.playground import PlaygroundError
    assert issubclass(CaptureBusyError, PlaygroundError)


def test_capture_semaphore_released_after_successful_run(tmp_path):
    """A normal capture must release its permit so the pool does not leak slots."""
    root = _write_user_module(tmp_path, """
        def addup(a):
            return a + 1
    """)
    resolved = ResolvedFunction(file="usermod.py", name="addup", qualname="addup",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    cd = CallDescriptor.from_dict({"function_ref": {"file": "usermod.py", "name": "addup"},
                                   "args": [3]})
    before = _cap._CAPTURE_SEMAPHORE._value
    run_capture(cd, resolved, project_root=str(root))
    assert _cap._CAPTURE_SEMAPHORE._value == before, (
        "the capture semaphore permit must be released after a successful run"
    )


def test_capture_semaphore_released_after_failed_run(tmp_path, monkeypatch):
    """Even when the subprocess times out, the permit must be released (finally)."""
    from copyclip.intelligence.capture import CaptureError, _run_driver
    import copyclip.intelligence.capture as _cap_mod

    monkeypatch.setattr(_cap_mod, "_kill_group", lambda proc: None)

    class _FakePopen:
        def __init__(self, *a, **kw):
            self.returncode = 0
            self.pid = 1

        def communicate(self, timeout=None):
            raise _cap_mod.subprocess.TimeoutExpired(cmd="x", timeout=timeout)

    monkeypatch.setattr(_cap_mod.subprocess, "Popen", _FakePopen)
    spec = {"module": "os", "name": "getpid", "parent_class": None,
            "args": [], "kwargs": {}, "probe": False}
    before = _cap_mod._CAPTURE_SEMAPHORE._value
    with pytest.raises(CaptureError):
        _run_driver(spec, str(tmp_path))
    assert _cap_mod._CAPTURE_SEMAPHORE._value == before, (
        "the permit must be released even when the capture fails"
    )


# ---------------------------------------------------------------------------
# SAFETY Fix 4: stdout demux — the driver shares stdout between the user's real
# code and the trace payload. A user print() must not corrupt the parse.
# ---------------------------------------------------------------------------

def test_traced_function_that_prints_still_yields_clean_trace(tmp_path):
    """A function that prints to stdout must still produce a parseable trace —
    the user's stdout must be redirected away from the trace channel."""
    root = _write_user_module(tmp_path, """
        def chatty(a):
            print("hello from user code")
            print("a second line, with a closing brace } and a [")
            b = a + 1
            return b
    """)
    resolved = ResolvedFunction(file="usermod.py", name="chatty", qualname="chatty",
                                kind="function", module="usermod", line_start=1,
                                parent_class=None)
    cd = CallDescriptor.from_dict({"function_ref": {"file": "usermod.py", "name": "chatty"},
                                   "args": [3]})
    steps, truncated, _reason = run_capture(cd, resolved, project_root=str(root))
    assert steps[-1].event == "return", (
        "a function that prints must still yield a clean return trace; "
        "user stdout must not corrupt the JSON trace payload"
    )
    names = {v.name for s in steps for v in s.scope}
    assert {"a", "b"} <= names


def test_driver_does_not_parse_stdout_when_rc_nonzero(tmp_path, monkeypatch):
    """When the subprocess exits non-zero, _run_driver must NOT attempt to parse
    stdout as a trace payload — a crash with stray stdout must surface as a clean
    CaptureError, not a wrong-cause parse error."""
    from copyclip.intelligence.capture import CaptureError, _run_driver
    import copyclip.intelligence.capture as _cap_mod

    class _FakePopen:
        def __init__(self, *a, **kw):
            self.returncode = 3
            self.pid = 1

        def communicate(self, timeout=None):
            # Non-zero rc but stray stdout present (a user print before a crash).
            return ("hello from user code\nnot json at all", "Traceback: boom")

    monkeypatch.setattr(_cap_mod.subprocess, "Popen", _FakePopen)
    spec = {"module": "os", "name": "getpid", "parent_class": None,
            "args": [], "kwargs": {}, "probe": False}
    with pytest.raises(CaptureError) as ei:
        _run_driver(spec, str(tmp_path))
    # Must be the rc!=0 branch (names the rc / stderr), NOT the "no parseable
    # trace" branch that would mis-attribute the failure to the user's print.
    assert "no parseable trace" not in str(ei.value), (
        "rc!=0 must short-circuit to the subprocess-failed error, not a parse error"
    )


# ---------------------------------------------------------------------------
# SAFETY Fix 6: _kill_group must reclaim the process TREE (grandchildren), not
# just the immediate target. On Windows, CTRL_BREAK must get a grace before the
# tree is reclaimed; TerminateProcess alone leaks grandchildren.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: signal.CTRL_BREAK_EVENT does not exist on POSIX")
def test_kill_group_gives_ctrl_break_grace_before_kill_on_windows(monkeypatch):
    """On Windows, _kill_group must give CTRL_BREAK a grace window (proc.wait)
    before escalating to kill — an immediate proc.kill() leaks grandchildren."""
    import copyclip.intelligence.capture as _cap_mod
    from unittest.mock import MagicMock
    monkeypatch.setattr(_cap_mod.sys, "platform", "win32")

    proc = MagicMock()
    proc.pid = 4321
    # First wait times out (grace expires) → escalate to kill.
    proc.wait.side_effect = [_cap_mod.subprocess.TimeoutExpired("x", 1), None]
    # Avoid touching real psutil in the unit test.
    monkeypatch.setattr(_cap_mod, "_reclaim_tree", lambda pid: None)

    _cap_mod._kill_group(proc)

    proc.send_signal.assert_any_call(_cap_mod.signal.CTRL_BREAK_EVENT)
    assert proc.wait.called, (
        "_kill_group must wait for a CTRL_BREAK grace before escalating to kill"
    )


# ---------------------------------------------------------------------------
# PR #177 staff review — new test 5a: in-driver caps CANNOT fire; outer
# subprocess timeout is the SOLE hard bound.
#
# A single blocking call (threading.Event().wait()) never returns a trace-event
# boundary, so MAX_STEPS / WALL_CLOCK_BUDGET_S (inside the tracer callback)
# never get a chance to fire.  The ONLY thing that can terminate the capture is
# the outer communicate(timeout=WALL_CLOCK_BUDGET_S + 4.0) backstop in
# _run_driver.  We shrink WALL_CLOCK_BUDGET_S via monkeypatch on the _capture_driver
# module (the single owner after item 1) and assert CaptureError arrives before
# the backstop window elapses.
# ---------------------------------------------------------------------------

import time as _time


def test_outer_subprocess_timeout_is_sole_defense_against_blocking_call(
    tmp_path, monkeypatch
):
    """A single blocking C call (threading.Event().wait()) holds the interpreter
    inside one trace-event window: in-driver MAX_STEPS and WALL_CLOCK_BUDGET_S
    never fire (they only check at trace-event boundaries). The OUTER subprocess
    communicate(timeout=...) backstop in _run_driver is the SOLE hard defence.

    Regression guard: if the outer backstop is ever removed or broken, this
    test hangs rather than fails — which is itself a signal.  On a healthy
    implementation it must complete well within the backstop window.
    """
    import copyclip.intelligence.capture as _cap_mod
    import copyclip.intelligence._capture_driver as _drv_mod
    from copyclip.intelligence.capture import CaptureError

    # Shrink the budgets so the test completes quickly.
    # The driver module is the single cap owner (item 1); patching it also
    # updates what capture.py sees (it imported the names from there).
    SHRUNKEN_BUDGET = 1.0  # seconds
    monkeypatch.setattr(_drv_mod, "WALL_CLOCK_BUDGET_S", SHRUNKEN_BUDGET)
    monkeypatch.setattr(_cap_mod, "WALL_CLOCK_BUDGET_S", SHRUNKEN_BUDGET)

    root = _write_user_module(tmp_path, """
        import threading

        def blocker():
            # A single blocking wait: the tracer callback never fires again
            # after the 'call' event, so no in-driver cap can interrupt it.
            threading.Event().wait()
    """)
    resolved = ResolvedFunction(
        file="usermod.py", name="blocker", qualname="blocker",
        kind="function", module="usermod", line_start=1, parent_class=None,
    )
    cd = CallDescriptor.from_dict(
        {"function_ref": {"file": "usermod.py", "name": "blocker"}}
    )

    backstop = SHRUNKEN_BUDGET + 4.0 + 2.0  # generous outer deadline for the test
    t0 = _time.monotonic()
    with pytest.raises(CaptureError, match="wall-clock"):
        run_capture(cd, resolved, project_root=str(tmp_path))
    elapsed = _time.monotonic() - t0

    assert elapsed < backstop, (
        f"CaptureError must arrive before the backstop window ({backstop}s); "
        f"actual elapsed: {elapsed:.2f}s. If this hangs, the outer subprocess "
        "timeout was removed or broken."
    )


# ---------------------------------------------------------------------------
# PR #177 staff review — new test 5b: dedicated test for the 2-second post-kill
# communicate(timeout=2.0) drain in _run_driver.
#
# After _kill_group is called on a timeout, _run_driver calls
# proc.communicate(timeout=2.0) to drain any pipe-holding grandchild.  This
# second communicate must itself timeout gracefully (not hang) when the grandchild
# is still holding the pipe — that timeout is swallowed with a bare `except`.
# ---------------------------------------------------------------------------

def test_post_kill_communicate_drain_timeouts_gracefully(tmp_path, monkeypatch):
    """After the outer communicate(timeout=...) expires and _kill_group is called,
    the post-kill drain communicate(timeout=2.0) must handle TimeoutExpired
    gracefully — a still-running grandchild must not hang the HTTP worker.

    Verifies: the second communicate() call is made with timeout=2.0, and a
    TimeoutExpired from it is swallowed (no exception propagates past _run_driver
    beyond the expected CaptureError for the original timeout)."""
    from copyclip.intelligence.capture import CaptureError, _run_driver
    import copyclip.intelligence.capture as _cap_mod

    communicate_calls: list[dict] = []

    class _FakePopen:
        def __init__(self, *a, **kw):
            self.returncode = 0
            self.pid = 99998

        def communicate(self, timeout=None):
            communicate_calls.append({"timeout": timeout})
            if len(communicate_calls) == 1:
                # First call: simulate the outer backstop firing
                raise _cap_mod.subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
            # Second call (the drain): also times out — must be swallowed
            raise _cap_mod.subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    monkeypatch.setattr(_cap_mod, "_kill_group", lambda proc: None)
    monkeypatch.setattr(_cap_mod.subprocess, "Popen", _FakePopen)

    spec = {
        "module": "os", "name": "getpid", "parent_class": None,
        "args": [], "kwargs": {}, "probe": False,
    }

    with pytest.raises(CaptureError, match="wall-clock"):
        _run_driver(spec, str(tmp_path))

    assert len(communicate_calls) == 2, (
        f"_run_driver must call communicate() exactly twice on timeout "
        f"(outer backstop + post-kill drain); got {len(communicate_calls)} call(s)"
    )
    drain_call = communicate_calls[1]
    assert drain_call["timeout"] == 2.0, (
        f"post-kill drain must use timeout=2.0; got timeout={drain_call['timeout']!r}"
    )
