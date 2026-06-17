from __future__ import annotations

import pytest

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
