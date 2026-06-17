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
    fb = FallbackResponse(reason="async function", iframe_url="http://127.0.0.1:5000/")
    assert fb.to_dict() == {"kind": "fallback", "reason": "async function",
                            "iframe_url": "http://127.0.0.1:5000/"}


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
    """
    mod_name = _make_free_text_mod(tmp_path, "_ft_raise", dedent("""\
        def boom(x):
            return {}[x]
    """))
    try:
        spec = {"module": mod_name, "name": "boom", "call_text": 'boom("k")'}
        raw = driver._trace_free_text(spec)
        last = raw["trace"][-1]
        assert last["event"] == "raise"
        assert last["raised"]["type"] == "KeyError"
        # The raise-step line must equal the line of the last traced event
        # (events[-2] before the raise was appended), not 0 or an arbitrary value.
        pre_raise_line = raw["trace"][-2]["line"]
        assert last["line"] == pre_raise_line
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
