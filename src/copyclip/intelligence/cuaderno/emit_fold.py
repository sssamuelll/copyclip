"""Emit-boundary fold: promote model-emitted top-level args/kwargs/ctor on a
playground widget into a nested ``call`` object and pre-render ``call_text``.

The prompt (prompts.py §playground widget shape) instructs the model to emit
``args``, ``kwargs``, and ``ctor`` at the TOP LEVEL of the widget dict.  The
wire contract that the frontend consumes (spec §4) requires these to live
INSIDE a nested ``call`` object alongside a pre-rendered ``call_text`` string
that is the authoritative invocation the user sees before confirming a step-through.

This module owns the SEAM between the model's emission and the wire shape:
  - accept an ``emit_block`` dict (the raw ``emit_block`` tool call input)
  - if it is a playground widget with top-level args/kwargs/ctor, FOLD them
    into ``call = {function_ref, args, kwargs, ctor?}``
  - PRE-RENDER ``call_text`` using repr()-literal args (spec §4 / §10):
      plain function  →  ``fn(1, 'x', flag=True)``
      method          →  ``Foo(42, mode='strict').method('input.txt')``
  - remove the top-level ``args``/``kwargs``/``ctor`` from the widget root
  - all other block kinds pass through unmodified

call_text uses repr() on every arg/kwarg value so strings are quoted:
  ``"hello"`` becomes ``"'hello'"`` in the rendered call — matching the
  spec's "repr-literal" discipline that guards against raw-code injection
  from a garbled model proposal (spec §4 / §10 path 1).
"""
from __future__ import annotations

from typing import Any


def _render_args(args: list, kwargs: dict, ctor: dict | None,
                 func_name: str, parent_class: str | None) -> str:
    """Build the authoritative call_text string from the descriptor fields.

    - plain function:  ``func_name(repr(a0), repr(a1), k=repr(v))``
    - method:          ``ParentClass(repr(ctor_a0), ck=repr(cv)).func_name(repr(a0))``

    All values are repr()'d — strings get quoted, numbers stay bare, etc.
    """
    def _repr_arg(v: Any) -> str:
        return repr(v)

    def _args_str(a: list, kw: dict) -> str:
        parts: list[str] = [_repr_arg(v) for v in a]
        parts += [f"{k}={_repr_arg(v)}" for k, v in kw.items()]
        return ", ".join(parts)

    call_args = _args_str(args, kwargs)

    if parent_class and ctor is not None:
        ctor_args = _args_str(ctor.get("args") or [], ctor.get("kwargs") or {})
        return f"{parent_class}({ctor_args}).{func_name}({call_args})"
    return f"{func_name}({call_args})"


def fold_playground_widget(block: dict) -> dict:
    """Fold the model's top-level args/kwargs/ctor on a playground widget into
    ``call`` + ``call_text``.  Non-playground and non-widget blocks pass through
    unmodified (the same dict object is returned — no copy).

    Called at the emit boundary (block_stop handler in compositor.py) BEFORE
    validate_widget_payload so widget_checks see the final wire shape.
    """
    if not isinstance(block, dict) or block.get("kind") != "widget":
        return block
    w = block.get("widget")
    if not isinstance(w, dict) or w.get("kind") != "playground":
        return block

    fr = w.get("function_ref") or {}
    func_name: str = fr.get("name") or ""
    qualname: str | None = fr.get("qualname")
    # Derive parent_class from qualname (e.g. "MyClass.process" → "MyClass")
    parent_class: str | None = None
    if qualname and "." in qualname:
        head, _, tail = qualname.partition(".")
        if head and tail and "." not in tail:
            parent_class = head

    # Extract top-level args/kwargs/ctor — may be absent (None means empty)
    args: list = list(w.get("args") or [])
    kwargs: dict = dict(w.get("kwargs") or {})
    ctor_raw = w.get("ctor")
    ctor: dict | None = None
    if ctor_raw is not None:
        ctor = {
            "args": list(ctor_raw.get("args") or []),
            "kwargs": dict(ctor_raw.get("kwargs") or {}),
        }

    # Build the nested call object
    call: dict[str, Any] = {
        "function_ref": fr,
        "args": args,
        "kwargs": kwargs,
    }
    if ctor is not None:
        call["ctor"] = ctor

    # Pre-render call_text — repr-literal, authoritative
    call_text = _render_args(args, kwargs, ctor, func_name, parent_class)

    # Build the new widget dict: drop top-level args/kwargs/ctor, add call + call_text
    new_w: dict[str, Any] = {k: v for k, v in w.items()
                              if k not in ("args", "kwargs", "ctor")}
    new_w["call"] = call
    new_w["call_text"] = call_text

    # Return a new block dict with the updated widget
    new_block = {k: v for k, v in block.items() if k != "widget"}
    new_block["widget"] = new_w
    return new_block
