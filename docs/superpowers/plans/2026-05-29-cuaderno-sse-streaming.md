# Cuaderno SSE Streaming Implementation Plan (Task 32 / v1.1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /api/cuaderno/ask` stream its answer live — the user watches the tutor read evidence (tool-call rows), then watches the answer compose itself block by block — replacing the Phase-1 one-shot JSON response.

**Architecture:** The agentic loop becomes a two-phase generator: an *evidence* phase (read tools, emitting `tool` events) and a *composition* phase where the model delivers the answer by calling `emit_block` once per block then `finish` (each completed `emit_block` emits a `block` event). The backend streams these as Server-Sent Events over `text/event-stream`; the frontend consumes them via `fetch` + `ReadableStream` and renders a growing frame. Every block still carries verifiable citations — the anti-invention invariant is unchanged.

**Tech Stack:** Python 3.10+, `anthropic` SDK streaming API (`client.messages.stream`), stdlib `BaseHTTPRequestHandler`/`ThreadingHTTPServer`, `sqlite3`, `pytest` (backend). React 18 + TypeScript + Vite (frontend; type-checked via `tsc -b`, no unit-test harness — matches the Phase-1 frontend).

**Design spec:** [`../specs/2026-05-29-cuaderno-sse-streaming-design.md`](../specs/2026-05-29-cuaderno-sse-streaming-design.md). Read it before starting.

---

## File structure

### Backend — new files

- `src/copyclip/intelligence/cuaderno/ask_stream.py` — HTTP-facing wrapper: prepends the `meta` event, persists on the terminal `frame` (attaching `position`), persists a partial frame on error/disconnect.

### Backend — modified files

- `src/copyclip/intelligence/cuaderno/schema.py` — add `KNOWN_BLOCK_KINDS` + `validate_block_dict`.
- `src/copyclip/intelligence/cuaderno/tool_catalog.py` — add `emit_block` + `finish` tool definitions and the `ANSWER_TOOLS` set.
- `src/copyclip/intelligence/cuaderno/prompts.py` — change the output contract to the `emit_block`/`finish` protocol.
- `src/copyclip/intelligence/cuaderno/compositor.py` — add `iter_compose_events` generator; rewrite `compose_frame` as a thin wrapper draining it.
- `src/copyclip/intelligence/cuaderno/anthropic_client.py` — add `messages_stream` + module-level `_normalize_block`.
- `src/copyclip/intelligence/server_helpers.py` — add `sse_response` writer.
- `src/copyclip/intelligence/server.py` — switch the `/api/cuaderno/ask` handler (lines 2506-2545) to SSE.

### Frontend — modified files

- `frontend/src/types/api.ts` — add `ToolRow` + `CuadernoStreamEvent` (after the Cuaderno block, ~line 849).
- `frontend/src/api/cuaderno.ts` — add `askStream`; remove the dead `ask`/`postJson` in PR4.
- `frontend/src/pages/CuadernoPage.tsx` — rework `onAsk` to consume the stream; add streaming state + abort.
- `frontend/src/components/cuaderno/Cuaderno.tsx` — two-act scene gate; shared `ToolRow`.
- `frontend/src/components/cuaderno/frames/FrameMidStream.tsx` — shared `ToolRow`, render `error` state.

### Tests — modified files

- `tests/test_cuaderno_compositor.py` — rewrite for the streaming generator + `emit_block` protocol.
- `tests/test_cuaderno_tool_catalog.py` — update the tool-name assertion.
- `tests/test_cuaderno_e2e.py` — the pre-existing full-stack HTTP test mocks the old `messages_create` + single-JSON-response contract; it is skipped during PR1 (so the suite stays green) and rewritten against the SSE route in PR2 (Task 9).
- `tests/test_cuaderno_endpoint.py` — its 3 ask-route tests assert the old single-JSON `/ask` contract; they are migrated to the SSE contract in PR2 (Task 9), stubbing `ask_stream.iter_compose_events` and reading the event stream. The 400/503 error guards still emit plain JSON and keep their assertions. (Discovered during execution; not in the original file map.)

### Tests — new files

- `tests/test_cuaderno_anthropic_stream.py` — `messages_stream` normalization against a fake raw client.
- `tests/test_cuaderno_ask_stream.py` — `iter_ask_events` meta/persist/partial behavior.
- `tests/test_cuaderno_sse_response.py` — `sse_response` writer against a fake handler.

---

## PR1 — Backend core (generator + protocol, no HTTP, no real SDK streaming)

PR1 defines the new protocol and the streaming generator, tested entirely against a stub that implements `messages_stream`. The real adapter method lands in PR2.

---

### Task 1: Block-kind validation helper

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/schema.py`
- Test: `tests/test_cuaderno_schema.py` (append)

- [ ] **Step 1: Append the failing test**

Append to `tests/test_cuaderno_schema.py`:

```python
from copyclip.intelligence.cuaderno.schema import (
    KNOWN_BLOCK_KINDS, validate_block_dict,
)


def test_validate_block_dict_accepts_known_kind():
    assert validate_block_dict({"kind": "lead", "text": "hi"}) is None
    assert validate_block_dict({"kind": "paragraph", "text": "x"}) is None


def test_validate_block_dict_rejects_unknown_kind():
    reason = validate_block_dict({"kind": "bogus", "text": "x"})
    assert reason is not None and "bogus" in reason


def test_validate_block_dict_rejects_non_object():
    assert validate_block_dict("nope") is not None
    assert validate_block_dict({"text": "no kind"}) is not None


def test_known_block_kinds_matches_constructors():
    assert KNOWN_BLOCK_KINDS == {
        "lead", "paragraph", "ordered_list", "code_block", "ascii_block",
        "citation", "citation_stack", "callout", "widget", "followups",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_schema.py -v -k validate_block or known_block`
Expected: FAIL with `ImportError: cannot import name 'validate_block_dict'`.

- [ ] **Step 3: Implement the helper**

Append to `src/copyclip/intelligence/cuaderno/schema.py` (after `frame_from_dict`):

```python
KNOWN_BLOCK_KINDS = {
    "lead", "paragraph", "ordered_list", "code_block", "ascii_block",
    "citation", "citation_stack", "callout", "widget", "followups",
}


def validate_block_dict(d: Any) -> Optional[str]:
    """Return None if d is a renderable Block dict, else a short reason string.

    Light validation: the block must be an object with a known `kind`. Per-kind
    field validation is intentionally deferred — Block.from_dict tolerates extra
    or missing fields, and the kind check is what guards the renderer against an
    unknown block type falling through to a null render.
    """
    if not isinstance(d, dict):
        return "block is not an object"
    kind = d.get("kind")
    if kind not in KNOWN_BLOCK_KINDS:
        return f"unknown or missing block kind: {kind!r}"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_schema.py -v`
Expected: PASS (all existing tests plus the 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/schema.py tests/test_cuaderno_schema.py
git commit -m "feat(cuaderno): block-kind validation helper for emit_block"
```

---

### Task 2: emit_block + finish tool definitions

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/tool_catalog.py`
- Test: `tests/test_cuaderno_tool_catalog.py`

- [ ] **Step 1: Update the existing name-set test and add new assertions**

In `tests/test_cuaderno_tool_catalog.py`, replace the body of `test_tool_definitions_include_all_tools` and append two tests:

```python
def test_tool_definitions_include_all_tools():
    tools = build_tool_definitions()
    names = {t["name"] for t in tools}
    assert names == {
        "read_file", "grep_symbols", "get_callers", "get_callees",
        "git_log", "git_blame", "git_diff", "find_tests",
        "emit_block", "finish",
    }


def test_emit_block_requires_kind():
    tools = build_tool_definitions()
    emit = next(t for t in tools if t["name"] == "emit_block")
    assert emit["input_schema"]["required"] == ["kind"]
    assert emit["input_schema"]["additionalProperties"] is True


def test_answer_tools_set():
    from copyclip.intelligence.cuaderno.tool_catalog import ANSWER_TOOLS
    assert ANSWER_TOOLS == {"emit_block", "finish"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_tool_catalog.py -v`
Expected: FAIL — `test_tool_definitions_include_all_tools` assertion mismatch and `ImportError` for `ANSWER_TOOLS`.

- [ ] **Step 3: Add the definitions and the set**

In `src/copyclip/intelligence/cuaderno/tool_catalog.py`, add the module-level constant after the imports (after line 6):

```python
ANSWER_TOOLS = {"emit_block", "finish"}
```

Then, inside `build_tool_definitions`, add these two entries to the returned list, immediately before the closing `]` (after the `find_tests` entry):

```python
        {
            "name": "emit_block",
            "description": (
                "Emit ONE block of your answer. Call once per block, in order. "
                "Each block must conform to the Block schema in the system prompt. "
                "Your answer IS the ordered sequence of emit_block calls."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "lead | paragraph | ordered_list | code_block | ascii_block | citation | citation_stack | callout | widget | followups",
                    },
                },
                "required": ["kind"],
                "additionalProperties": True,
            },
        },
        {
            "name": "finish",
            "description": "Call once, after you have emitted every block of your answer. Takes no arguments. Ends the answer.",
            "input_schema": {"type": "object", "properties": {}},
        },
```

`dispatch_tool` is left unchanged: `emit_block` and `finish` are intercepted by the compositor and never reach `dispatch_tool` (which would return `unknown_tool` for them).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_tool_catalog.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/tool_catalog.py tests/test_cuaderno_tool_catalog.py
git commit -m "feat(cuaderno): emit_block + finish tool definitions"
```

---

### Task 3: Rewrite the system prompt for the emit_block protocol

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/prompts.py`

No test (prompt text). Verified by the compositor tests in Task 4.

- [ ] **Step 1: Replace the output section**

In `src/copyclip/intelligence/cuaderno/prompts.py`, replace the block from `## Your output` through the end of the `### Frame schema` fenced block (current lines 18-30) with:

```
## Your output

When you have gathered enough evidence, deliver your answer by calling the
`emit_block` tool once per block, in order. Each call carries exactly ONE
block conforming to the Block schema below. When you have emitted every block,
call the `finish` tool (it takes no arguments).

Do NOT return the answer as text and do NOT wrap blocks in an array — your
answer IS the ordered sequence of `emit_block` calls. Do not include the
question; it is recorded automatically.
```

Leave the `### Block kinds`, `### Citation shape`, `### Widget kinds`, and `## Tone` sections exactly as they are.

- [ ] **Step 2: Sanity-check the module imports cleanly**

Run: `python -c "from copyclip.intelligence.cuaderno.prompts import SYSTEM_PROMPT; assert 'emit_block' in SYSTEM_PROMPT and 'SINGLE text block' not in SYSTEM_PROMPT; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/prompts.py
git commit -m "feat(cuaderno): system prompt uses emit_block/finish protocol"
```

---

### Task 4: The streaming generator `iter_compose_events`

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`
- Test: `tests/test_cuaderno_compositor.py` (rewritten in Task 5; this task adds the generator + its tests in a temporary test file first, then Task 5 consolidates)

To keep this task self-contained, write the generator tests in `tests/test_cuaderno_compositor.py`, replacing the file's contents.

- [ ] **Step 1: Replace the test file**

Replace the entire contents of `tests/test_cuaderno_compositor.py` with:

```python
from pathlib import Path

from copyclip.intelligence.cuaderno.compositor import (
    iter_compose_events, compose_frame,
)
from copyclip.intelligence.cuaderno.schema import Frame


class StubStream:
    """Stub adapter exposing messages_stream with scripted turns.

    Each scripted turn is a list of normalized streaming events. A turn must
    end with a message_stop event. messages_stream yields the next turn's
    events one at a time, mirroring the real AnthropicAdapter.messages_stream.
    """

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def messages_stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self._turns:
            raise RuntimeError("StubStream ran out of scripted turns")
        for ev in self._turns.pop(0):
            yield ev


def _tool_stop(block_id, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": block_id, "name": name, "input": inp}}


def _content(block_id, name, inp):
    return {"type": "tool_use", "id": block_id, "name": name, "input": inp}


def _msg_stop(stop_reason, content):
    return {"type": "message_stop", "stop_reason": stop_reason, "content": content}


def test_emits_blocks_then_frame_in_one_turn(tmp_path: Path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "hi"}),
        _tool_stop("b2", "emit_block", {"kind": "paragraph", "text": "body"}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "hi"}),
            _content("b2", "emit_block", {"kind": "paragraph", "text": "body"}),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    kinds = [e["type"] for e in events]
    assert kinds == ["block", "block", "frame"]
    assert events[0]["block"] == {"kind": "lead", "text": "hi"}
    assert events[1]["block"] == {"kind": "paragraph", "text": "body"}
    assert events[2]["frame"] == {
        "question": "q",
        "blocks": [{"kind": "lead", "text": "hi"},
                   {"kind": "paragraph", "text": "body"}],
    }


def test_read_tool_then_compose(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    turns = [
        [
            _tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
        ],
        [
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "answer"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b1", "emit_block", {"kind": "lead", "text": "answer"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    client = StubStream(turns)
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    kinds = [e["type"] for e in events]
    assert kinds == ["tool", "tool", "block", "frame"]
    assert events[0]["name"] == "read_file" and events[0]["state"] == "running"
    assert events[1]["name"] == "read_file" and events[1]["state"] == "done"
    assert events[1]["ms"] is not None and events[1]["ms"] >= 0
    assert events[2]["block"] == {"kind": "lead", "text": "answer"}


def test_implicit_finish_on_end_turn(tmp_path: Path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("end_turn", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    assert [e["type"] for e in events] == ["block", "frame"]
    assert events[1]["frame"]["blocks"] == [{"kind": "lead", "text": "x"}]


def test_malformed_block_is_dropped(tmp_path: Path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "good"}),
        _tool_stop("b2", "emit_block", {"kind": "bogus", "text": "bad"}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "good"}),
            _content("b2", "emit_block", {"kind": "bogus", "text": "bad"}),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    block_events = [e for e in events if e["type"] == "block"]
    assert len(block_events) == 1
    assert block_events[0]["block"]["kind"] == "lead"
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["blocks"] == [{"kind": "lead", "text": "good"}]


def test_zero_blocks_yields_fallback_frame(tmp_path: Path):
    turn = [
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [_content("f", "finish", {})]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    assert [e["type"] for e in events] == ["frame"]
    blocks = events[0]["frame"]["blocks"]
    assert len(blocks) == 1 and blocks[0]["kind"] == "paragraph"


def test_budget_exhausted_yields_fallback_frame(tmp_path: Path):
    (tmp_path / "x.py").write_text("pass\n", encoding="utf-8")
    read_turn = [
        _tool_stop("r", "read_file", {"path": "x.py"}),
        _msg_stop("tool_use", [_content("r", "read_file", {"path": "x.py"})]),
    ]
    client = StubStream([read_turn, read_turn, read_turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None, max_tool_rounds=2,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    text = frame["frame"]["blocks"][0]["text"].lower()
    assert "budget" in text or "couldn't finish" in text


def test_stream_exception_yields_error_event(tmp_path: Path):
    class Boom:
        calls = []
        def messages_stream(self, **kwargs):
            raise RuntimeError("api down")
            yield  # pragma: no cover — makes this a generator
    events = list(iter_compose_events(
        client=Boom(), question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    assert events[-1]["type"] == "error"
    assert events[-1]["partial"] is False


def test_compose_frame_wrapper_returns_terminal_frame(tmp_path: Path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "hi"}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "hi"}),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([turn])
    frame = compose_frame(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    )
    assert isinstance(frame, Frame)
    assert frame.question == "q"
    assert frame.blocks[0].kind == "lead"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_compositor.py -v`
Expected: FAIL with `ImportError: cannot import name 'iter_compose_events'`.

- [ ] **Step 3: Rewrite compositor.py**

Replace the entire contents of `src/copyclip/intelligence/cuaderno/compositor.py` with:

```python
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterator, Optional

from .prompts import SYSTEM_PROMPT
from .schema import Block, Frame, frame_from_dict, frame_to_dict, validate_block_dict
from .tool_catalog import build_tool_definitions, dispatch_tool


def _fallback_frame(question: str, reason: str) -> Frame:
    return Frame(
        question=question,
        blocks=[
            Block.paragraph(
                f"I couldn't finish this turn — {reason}. Try rephrasing, or "
                "ask a narrower question (a specific file, function, or commit)."
            ),
        ],
    )


def _ack(tool_use_id: str, payload: dict, *, is_error: bool = False) -> dict[str, Any]:
    r: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(payload),
    }
    if is_error:
        r["is_error"] = True
    return r


def _args_summary(name: str, args: dict[str, Any]) -> str:
    """A short label for the tool-call row (e.g. 'src/foo.py:10-20')."""
    if args.get("path"):
        s = str(args["path"])
        if args.get("line_start"):
            s += f":{args['line_start']}"
            if args.get("line_end"):
                s += f"-{args['line_end']}"
        return s
    for key in ("symbol", "name", "commit_sha", "module"):
        if args.get(key):
            return str(args[key])
    return ""


def iter_compose_events(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    model: str = "claude-sonnet-4-5",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
) -> Iterator[dict[str, Any]]:
    """Run the agentic loop as a generator of events.

    Yields, in order:
      {"type": "tool",  "id", "name", "args", "state": running|done|error, "ms"}
      {"type": "block", "block": <block dict>}
      {"type": "frame", "frame": <frame dict>}              # terminal success/fallback
      {"type": "error", "message": str, "partial": bool}    # terminal failure

    The model delivers its answer by calling emit_block once per block then
    finish. Read tools (read_file, grep_symbols, ...) run during the evidence
    phase and surface as tool events.
    """
    tools = build_tool_definitions()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    emitted: list[Block] = []

    for _ in range(max_tool_rounds):
        turn_content: list[dict[str, Any]] = []
        stop_reason: Optional[str] = None
        finish_seen = False
        emit_status: dict[str, Optional[str]] = {}  # tool_use_id -> reason (None = ok)

        try:
            for sev in client.messages_stream(
                model=model,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
                max_tokens=max_tokens,
            ):
                if sev.get("type") == "block_stop":
                    blk = sev.get("block") or {}
                    if blk.get("type") == "tool_use" and blk.get("name") == "emit_block":
                        inp = blk.get("input") or {}
                        reason = validate_block_dict(inp)
                        emit_status[blk["id"]] = reason
                        if reason is None:
                            b = Block.from_dict(inp)
                            emitted.append(b)
                            yield {"type": "block", "block": b.to_dict()}
                    elif blk.get("type") == "tool_use" and blk.get("name") == "finish":
                        finish_seen = True
                elif sev.get("type") == "message_stop":
                    stop_reason = sev.get("stop_reason")
                    turn_content = sev.get("content", []) or []
        except Exception as exc:  # noqa: BLE001 — surface LLM/stream failure as a terminal error
            yield {
                "type": "error",
                "message": f"stream failed ({exc})",
                "partial": len(emitted) > 0,
            }
            return

        messages.append({"role": "assistant", "content": turn_content})

        # Terminal: explicit finish, or a non-tool stop reason (implicit finish).
        if finish_seen or stop_reason != "tool_use":
            if emitted:
                yield {"type": "frame",
                       "frame": frame_to_dict(Frame(question=question, blocks=emitted))}
            else:
                yield {"type": "frame",
                       "frame": frame_to_dict(
                           _fallback_frame(question, "the model produced no answer blocks"))}
            return

        # Continue: ack every tool_use block. Dispatch read tools (with events);
        # ack emit_block (already emitted/rejected during the stream) and finish.
        tool_results: list[dict[str, Any]] = []
        for blk in turn_content:
            if blk.get("type") != "tool_use":
                continue
            name = blk.get("name")
            tuid = blk["id"]
            if name == "emit_block":
                reason = emit_status.get(tuid)
                if reason is None:
                    tool_results.append(_ack(tuid, {"ok": True}))
                else:
                    tool_results.append(
                        _ack(tuid, {"error": "invalid_block", "detail": reason}, is_error=True))
                continue
            if name == "finish":
                tool_results.append(_ack(tuid, {"ok": True}))
                continue

            args = blk.get("input") or {}
            args_str = _args_summary(name, args)
            yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                   "state": "running", "ms": None}
            t0 = time.perf_counter()
            try:
                result = dispatch_tool(
                    name, args, project_root=project_root,
                    project_id=project_id, conn=conn,
                )
                ms = int((time.perf_counter() - t0) * 1000)
                tool_results.append(_ack(tuid, result))
                yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                       "state": "done", "ms": ms}
            except Exception as exc:  # noqa: BLE001 — surface tool failures to the LLM and the UI
                ms = int((time.perf_counter() - t0) * 1000)
                tool_results.append(
                    _ack(tuid, {"error": "tool_failed", "detail": str(exc)}, is_error=True))
                yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                       "state": "error", "ms": ms}

        messages.append({"role": "user", "content": tool_results})

    # Budget exhausted → fallback frame (terminal; parity with the wrapper below).
    if emitted:
        yield {"type": "frame",
               "frame": frame_to_dict(Frame(question=question, blocks=emitted))}
    else:
        yield {"type": "frame",
               "frame": frame_to_dict(_fallback_frame(question, "tool-call budget exhausted"))}


def compose_frame(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    model: str = "claude-sonnet-4-5",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
) -> Frame:
    """Drain iter_compose_events and return the terminal Frame.

    Non-streaming convenience used by tests and for live-vs-restore parity. On a
    terminal error event it returns a fallback Frame, so this is total.
    """
    last_frame: Optional[Frame] = None
    for ev in iter_compose_events(
        client=client, question=question, project_root=project_root,
        project_id=project_id, conn=conn, model=model,
        max_tool_rounds=max_tool_rounds, max_tokens=max_tokens,
    ):
        if ev["type"] == "frame":
            last_frame = frame_from_dict(ev["frame"])
        elif ev["type"] == "error":
            return _fallback_frame(question, ev["message"])
    if last_frame is not None:
        return last_frame
    return _fallback_frame(question, "no terminal frame produced")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_compositor.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): iter_compose_events generator + emit_block protocol"
```

---

### Task 5: Confirm the full backend suite is green

**Files:** none (verification gate for PR1)

- [ ] **Step 1: Run the whole cuaderno backend suite**

Run: `python -m pytest tests/ -k cuaderno -v`
Expected: PASS. If `test_cuaderno_tool_catalog.py::test_dispatch_unknown_tool_returns_error` fails, confirm `dispatch_tool` was not altered for `emit_block`/`finish` (they must still return `unknown_tool` if dispatched, since they are intercepted upstream).

- [ ] **Step 2: Commit (only if a fix was needed)**

```bash
git add -A
git commit -m "test(cuaderno): PR1 backend suite green"
```

---

## PR2 — Backend streaming SDK + HTTP SSE

---

### Task 6: `messages_stream` on the Anthropic adapter

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/anthropic_client.py`
- Test: `tests/test_cuaderno_anthropic_stream.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_anthropic_stream.py`:

```python
from copyclip.intelligence.cuaderno.anthropic_client import (
    AnthropicAdapter, _normalize_block,
)


class _Blk:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _StopEvent:
    type = "content_block_stop"
    def __init__(self, block):
        self.content_block = block


class _OtherEvent:
    type = "content_block_delta"  # should be ignored by messages_stream


class _FakeStreamCtx:
    def __init__(self, events, final):
        self._events = events
        self._final = final
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def __iter__(self):
        return iter(self._events)
    def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, ctx):
        self._ctx = ctx
    def stream(self, **kwargs):
        return self._ctx


class _FakeRawClient:
    def __init__(self, ctx):
        self.messages = _FakeMessages(ctx)


def test_normalize_block_text_and_tool_use():
    assert _normalize_block(_Blk(type="text", text="hi")) == {"type": "text", "text": "hi"}
    assert _normalize_block(
        _Blk(type="tool_use", id="t1", name="read_file", input={"path": "x"})
    ) == {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}}


def test_messages_stream_yields_block_stops_then_message_stop():
    tool_blk = _Blk(type="tool_use", id="b1", name="emit_block",
                    input={"kind": "lead", "text": "hi"})
    final = _Blk(stop_reason="tool_use", content=[tool_blk])
    ctx = _FakeStreamCtx([_StopEvent(tool_blk), _OtherEvent()], final)
    adapter = AnthropicAdapter(raw_client=_FakeRawClient(ctx))

    events = list(adapter.messages_stream(model="m", messages=[], max_tokens=10))
    assert events[0] == {
        "type": "block_stop",
        "block": {"type": "tool_use", "id": "b1", "name": "emit_block",
                  "input": {"kind": "lead", "text": "hi"}},
    }
    assert events[-1] == {
        "type": "message_stop",
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": "b1", "name": "emit_block",
                     "input": {"kind": "lead", "text": "hi"}}],
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_anthropic_stream.py -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_block'`.

- [ ] **Step 3: Implement `messages_stream` + `_normalize_block`**

In `src/copyclip/intelligence/cuaderno/anthropic_client.py`, add a module-level function after the imports (after line 4) and a method on `AnthropicAdapter` after `messages_create`:

```python
def _normalize_block(blk) -> dict:
    if blk.type == "text":
        return {"type": "text", "text": blk.text}
    if blk.type == "tool_use":
        return {"type": "tool_use", "id": blk.id, "name": blk.name, "input": blk.input or {}}
    return {"type": blk.type}
```

Method (add inside the class, after `messages_create`):

```python
    def messages_stream(self, **kwargs):
        """Yield normalized streaming events from the Anthropic streaming API:

          {"type": "block_stop", "block": <normalized block>}      # per content block
          {"type": "message_stop", "stop_reason": str, "content": [<normalized blocks>]}

        Reacting at content_block_stop is what lets the compositor emit a block
        event the moment each emit_block tool call completes.
        """
        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_stop":
                    yield {"type": "block_stop",
                           "block": _normalize_block(event.content_block)}
            final = stream.get_final_message()
            yield {
                "type": "message_stop",
                "stop_reason": final.stop_reason,
                "content": [_normalize_block(b) for b in final.content],
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_anthropic_stream.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anthropic_client.py tests/test_cuaderno_anthropic_stream.py
git commit -m "feat(cuaderno): AnthropicAdapter.messages_stream normalized events"
```

---

### Task 7: `iter_ask_events` — HTTP-facing wrapper with persistence

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/ask_stream.py`
- Test: `tests/test_cuaderno_ask_stream.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_ask_stream.py`:

```python
import sqlite3
from pathlib import Path

from copyclip.intelligence.db import init_cuaderno_schema
from copyclip.intelligence.cuaderno.persistence import create_session, list_questions
from copyclip.intelligence.cuaderno.ask_stream import iter_ask_events


class StubStream:
    def __init__(self, turns):
        self._turns = list(turns)
    def messages_stream(self, **kwargs):
        for ev in self._turns.pop(0):
            yield ev


def _tool_stop(bid, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": bid, "name": name, "input": inp}}


def _content(bid, name, inp):
    return {"type": "tool_use", "id": bid, "name": name, "input": inp}


def _msg_stop(reason, content):
    return {"type": "message_stop", "stop_reason": reason, "content": content}


def _conn():
    c = sqlite3.connect(":memory:")
    init_cuaderno_schema(c)
    return c


def _one_block_finish():
    return [[
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "hi"}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "hi"}),
            _content("f", "finish", {}),
        ]),
    ]]


def test_meta_is_first_and_frame_carries_position(tmp_path: Path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    events = list(iter_ask_events(
        client=StubStream(_one_block_finish()), question="q",
        project_root=str(tmp_path), project_id=1, conn=conn, session_id=sid,
    ))
    assert events[0] == {"type": "meta", "session_id": sid}
    frame_ev = next(e for e in events if e["type"] == "frame")
    assert frame_ev["position"] == 1
    rows = list_questions(conn, sid)
    assert len(rows) == 1 and rows[0]["frame"]["blocks"][0]["kind"] == "lead"


def test_blocks_are_forwarded(tmp_path: Path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    events = list(iter_ask_events(
        client=StubStream(_one_block_finish()), question="q",
        project_root=str(tmp_path), project_id=1, conn=conn, session_id=sid,
    ))
    assert any(e["type"] == "block" and e["block"]["kind"] == "lead" for e in events)


def test_disconnect_persists_partial(tmp_path: Path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    gen = iter_ask_events(
        client=StubStream(_one_block_finish()), question="q",
        project_root=str(tmp_path), project_id=1, conn=conn, session_id=sid,
    )
    assert next(gen)["type"] == "meta"
    assert next(gen)["type"] == "block"   # the lead block
    gen.close()                            # simulate client disconnect mid-stream
    rows = list_questions(conn, sid)
    assert len(rows) == 1
    assert rows[0]["frame"]["blocks"][0]["kind"] == "lead"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_ask_stream.py -v`
Expected: FAIL with `ModuleNotFoundError: ... cuaderno.ask_stream`.

- [ ] **Step 3: Implement ask_stream.py**

Create `src/copyclip/intelligence/cuaderno/ask_stream.py`:

```python
from __future__ import annotations

import sqlite3
from typing import Any, Iterator, Optional

from .compositor import iter_compose_events
from .persistence import save_question
from .schema import Block, Frame, frame_from_dict


def _persist_partial(conn, session_id: str, question: str, emitted: list[dict]) -> None:
    pframe = Frame(question=question, blocks=[Block.from_dict(b) for b in emitted])
    save_question(conn, session_id, question, pframe)


def iter_ask_events(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    session_id: str,
    model: str = "claude-sonnet-4-5",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
) -> Iterator[dict[str, Any]]:
    """Wrap iter_compose_events for the HTTP layer.

    - Prepends a `meta` event carrying session_id.
    - On the terminal `frame`, persists the Frame and attaches its `position`.
    - On a terminal `error` with partial=True (or on client disconnect, which
      arrives as GeneratorExit in the finally), persists the partial Frame from
      the blocks already emitted.
    """
    yield {"type": "meta", "session_id": session_id}
    emitted: list[dict] = []
    persisted = False
    try:
        for ev in iter_compose_events(
            client=client, question=question, project_root=project_root,
            project_id=project_id, conn=conn, model=model,
            max_tool_rounds=max_tool_rounds, max_tokens=max_tokens,
        ):
            if ev["type"] == "block":
                emitted.append(ev["block"])
                yield ev
            elif ev["type"] == "tool":
                yield ev
            elif ev["type"] == "frame":
                frame = frame_from_dict(ev["frame"])
                position = save_question(conn, session_id, question, frame)
                persisted = True
                yield {"type": "frame", "position": position, "frame": ev["frame"]}
            elif ev["type"] == "error":
                if ev.get("partial") and emitted:
                    _persist_partial(conn, session_id, question, emitted)
                    persisted = True
                yield ev
    finally:
        # Client disconnect (GeneratorExit) or abnormal stop: persist partial once.
        if not persisted and emitted:
            try:
                _persist_partial(conn, session_id, question, emitted)
            except Exception:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_ask_stream.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/ask_stream.py tests/test_cuaderno_ask_stream.py
git commit -m "feat(cuaderno): iter_ask_events wrapper with meta + persist + partial"
```

---

### Task 8: `sse_response` writer

**Files:**
- Modify: `src/copyclip/intelligence/server_helpers.py`
- Test: `tests/test_cuaderno_sse_response.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_sse_response.py`:

```python
import io
import json

from copyclip.intelligence.server_helpers import sse_response


class FakeHandler:
    def __init__(self, fail_after=None):
        self.wfile = io.BytesIO()
        self.headers_sent = []
        self.status = None
        self._writes = 0
        self._fail_after = fail_after

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.headers_sent.append((k, v))

    def end_headers(self):
        self.headers_sent.append(("__end__", ""))


def _records(handler):
    text = handler.wfile.getvalue().decode("utf-8")
    return [r for r in text.split("\n\n") if r.strip()]


def test_sse_response_writes_headers_and_data_records():
    h = FakeHandler()
    ok = sse_response(h, iter([{"type": "meta", "session_id": "s1"},
                               {"type": "block", "block": {"kind": "lead"}}]))
    assert ok is True
    assert h.status == 200
    assert ("Content-Type", "text/event-stream") in h.headers_sent
    recs = _records(h)
    assert recs[0] == 'data: {"type": "meta", "session_id": "s1"}'
    assert json.loads(recs[1][len("data: "):])["type"] == "block"


def test_sse_response_returns_false_on_broken_pipe():
    class Boom(io.BytesIO):
        def write(self, b):
            raise BrokenPipeError("client gone")

    closed = {"v": False}

    def events():
        try:
            yield {"type": "meta", "session_id": "s1"}
            yield {"type": "block", "block": {}}
        finally:
            closed["v"] = True

    h = FakeHandler()
    h.wfile = Boom()
    ok = sse_response(h, events())
    assert ok is False
    assert closed["v"] is True  # generator was closed so its finally ran
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_sse_response.py -v`
Expected: FAIL with `ImportError: cannot import name 'sse_response'`.

- [ ] **Step 3: Implement sse_response**

Append to `src/copyclip/intelligence/server_helpers.py`:

```python
def sse_response(handler, events) -> bool:
    """Stream JSON event dicts as text/event-stream.

    Writes SSE headers, then one `data: <json>\\n\\n` record per event with an
    explicit flush. Returns True if the stream completed, False if the client
    disconnected (in which case the events generator is closed so its finally
    can run — e.g. to persist a partial frame).
    """
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()
    for ev in events:
        try:
            handler.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            close = getattr(events, "close", None)
            if close is not None:
                close()
            return False
    return True
```

Note: `io.BytesIO` has no `flush` side effects but does define `flush()`, so the test's `FakeHandler.wfile` works. The `Boom` subclass raises on `write`, exercising the disconnect path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_sse_response.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/server_helpers.py tests/test_cuaderno_sse_response.py
git commit -m "feat(server): sse_response writer with disconnect handling"
```

---

### Task 9: Switch the `/api/cuaderno/ask` handler to SSE

**Files:**
- Modify: `src/copyclip/intelligence/server.py` (lines 2506-2545 and the imports near 2522-2527)

- [ ] **Step 1: Confirm the import of `sse_response`**

At the top of `src/copyclip/intelligence/server.py`, find the existing import of helpers from `server_helpers` (search for `from .server_helpers import`). Add `sse_response` to that import list. If helpers are imported individually, add:

```python
from .server_helpers import sse_response
```

Verify with: `python -c "import ast,sys; ast.parse(open(r'src/copyclip/intelligence/server.py',encoding='utf-8').read()); print('parse ok')"`
Expected: `parse ok`.

- [ ] **Step 2: Replace the ask-handler body**

In `src/copyclip/intelligence/server.py`, replace lines 2522-2545 (the block from `from .cuaderno import compositor as _compositor` through the `return` after `self._json({...})`) with:

```python
                    from .cuaderno.anthropic_client import AnthropicAdapter
                    from .cuaderno.ask_stream import iter_ask_events
                    from .cuaderno.persistence import create_session
                    if not session_id:
                        session_id = create_session(conn, project_root=ctx.root)
                    try:
                        client = AnthropicAdapter()
                    except RuntimeError as exc:
                        self._json({"error": "llm_not_configured", "detail": str(exc)}, 503)
                        return
                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id,
                    )
                    sse_response(self, events)
                    return
```

This keeps the `conn` open for the full stream (the `do_POST` `finally` at lines 2548-2552 closes it only after `sse_response` returns), and persistence happens inside `iter_ask_events` on the terminal frame.

- [ ] **Step 3: Verify the module parses and the cuaderno suite still passes**

Run: `python -c "import ast; ast.parse(open(r'src/copyclip/intelligence/server.py',encoding='utf-8').read()); print('parse ok')"`
Expected: `parse ok`.

Run: `python -m pytest tests/ -k cuaderno -v`
Expected: PASS (the handler change has no dedicated unit test; it is exercised manually in Step 4 and by the frontend e2e in PR4).

- [ ] **Step 4: Rewrite the full-stack e2e test for SSE**

`tests/test_cuaderno_e2e.py` was skipped in PR1 (it mocked the old `messages_create` + single-JSON contract). Now that the route is SSE, replace the ENTIRE file contents with:

```python
import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib import request

from copyclip.intelligence.db import connect, init_schema, init_cuaderno_schema
from copyclip.intelligence.server import run_server


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _wait_port(port, timeout_s=3.0):
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


def _post_sse(url, body, timeout=15):
    """POST and parse a text/event-stream response into a list of event dicts."""
    data = json.dumps(body).encode("utf-8")
    req = request.Request(url, method="POST", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as r:
        status = r.status
        ctype = r.headers.get("Content-Type", "")
        raw = r.read().decode("utf-8")
    events = []
    for record in raw.split("\n\n"):
        record = record.strip()
        if not record:
            continue
        for line in record.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return status, ctype, events


def _stop(bid, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": bid, "name": name, "input": inp}}


def _content(bid, name, inp):
    return {"type": "tool_use", "id": bid, "name": name, "input": inp}


def _msg(reason, content):
    return {"type": "message_stop", "stop_reason": reason, "content": content}


def test_e2e_example_A_streams_frame_over_sse():
    """Full-stack: POST /api/cuaderno/ask drives the streaming compositor
    (messages_stream + emit_block) and returns an SSE stream whose terminal
    frame event carries the composed blocks."""
    td = tempfile.mkdtemp(prefix="cuaderno-e2e-")
    root = str(Path(td).absolute())
    (Path(td) / "README.md").write_text("# CopyClip", encoding="utf-8")
    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    conn.commit()
    conn.close()

    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start()
    _wait_port(port)

    lead = {"kind": "lead", "text": "CopyClip is a personal tool."}
    cite = {"kind": "citation",
            "citation": {"kind": "path", "path": "README.md", "line_start": 1, "line_end": 1}}
    turns = [
        [
            _stop("t1", "read_file", {"path": "README.md"}),
            _msg("tool_use", [_content("t1", "read_file", {"path": "README.md"})]),
        ],
        [
            _stop("b1", "emit_block", lead),
            _stop("b2", "emit_block", cite),
            _stop("f", "finish", {}),
            _msg("tool_use", [
                _content("b1", "emit_block", lead),
                _content("b2", "emit_block", cite),
                _content("f", "finish", {}),
            ]),
        ],
    ]

    def _stream(**kwargs):
        for ev in turns.pop(0):
            yield ev

    with patch(
        "copyclip.intelligence.cuaderno.anthropic_client.AnthropicAdapter"
    ) as MockAdapter:
        MockAdapter.return_value.messages_stream.side_effect = _stream
        status, ctype, events = _post_sse(
            f"http://127.0.0.1:{port}/api/cuaderno/ask",
            {"question": "what does this project do?"},
        )

    assert status == 200
    assert "text/event-stream" in ctype
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert "tool" in types
    assert "block" in types
    frame_ev = next(e for e in events if e["type"] == "frame")
    kinds = [b["kind"] for b in frame_ev["frame"]["blocks"]]
    assert "lead" in kinds
    assert "citation" in kinds
    assert frame_ev["position"] == 1
```

Run: `python -m pytest tests/test_cuaderno_e2e.py -v`
Expected: PASS, 1 test.

NOTE on connection close: `_post_sse` uses `r.read()`, which blocks until the server closes the socket at stream end. This works because `BaseHTTPRequestHandler`'s default `protocol_version` is HTTP/1.0, so the connection closes when the handler returns. If this test hangs, it means the handler is keeping the connection open after the stream — verify the handler returns promptly after `sse_response` and does not set HTTP/1.1 keep-alive that outlives the response. If it proves flaky in CI, the manual smoke (Step 6) is the fallback verification and the test may be `@pytest.mark.skip`-ed with a recorded reason rather than left failing.

- [ ] **Step 5: Run the full cuaderno suite and commit**

Run: `python -m pytest tests/ -k cuaderno -q`
Expected: PASS (the e2e test now runs and passes; nothing skipped for the streaming path).

```bash
git add src/copyclip/intelligence/server.py tests/test_cuaderno_e2e.py
git commit -m "feat(cuaderno): /api/cuaderno/ask streams SSE events"
```

- [ ] **Step 6: Manual smoke test (requires ANTHROPIC_API_KEY + an analyzed project)**

Start the server on this repo and curl the stream:

```bash
# In one shell, with the project analyzed and the API key set:
python -m copyclip start   # or however the server is normally started
# In another shell:
curl -N -X POST http://127.0.0.1:4310/api/cuaderno/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"what does this project do?"}'
```

Expected: a `text/event-stream` where you see `data: {"type": "meta", ...}` first, then `data: {"type": "tool", ...}` rows, then `data: {"type": "block", ...}` lines appearing progressively, then a final `data: {"type": "frame", "position": N, ...}`.

---

## PR3 — Frontend transport (types + askStream)

Frontend tasks are verified by `npm run build` (which runs `tsc -b`, the project's type-safety net) and, for behavior, by the manual e2e in PR4. The project has no frontend unit-test harness; this plan does not add one.

---

### Task 10: Stream event types

**Files:**
- Modify: `frontend/src/types/api.ts` (after the Cuaderno block, ~line 849)

- [ ] **Step 1: Add the types**

Append to `frontend/src/types/api.ts`, after the `CuadernoSession` type (line 849):

```typescript
export type ToolRow = {
  state: 'queued' | 'running' | 'done' | 'error'
  name: string
  args: string
  ms: number | null
}

export type CuadernoStreamEvent =
  | { type: 'meta'; session_id: string }
  | {
      type: 'tool'
      id: string
      name: string
      args: string
      state: 'running' | 'done' | 'error'
      ms: number | null
    }
  | { type: 'block'; block: Block }
  | { type: 'frame'; position: number; frame: Frame }
  | { type: 'error'; message: string; partial: boolean }
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npm run build`
Expected: build succeeds (no `tsc` errors). If `vite build` is slow or unwanted, `npx tsc -b` alone also suffices for the type check.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno): ToolRow + CuadernoStreamEvent types"
```

---

### Task 11: `askStream` client

**Files:**
- Modify: `frontend/src/api/cuaderno.ts`

- [ ] **Step 1: Add the streaming function**

In `frontend/src/api/cuaderno.ts`, update the import on line 1, then add an exported `askStream` after the `cuadernoApi` object (after line 60).

Replace line 1 with (this keeps the existing `ask` method compiling — `CuadernoAskResponse` is removed in Task 14 once `ask` is deleted):

```typescript
import type {
  CuadernoAskResponse,
  CuadernoSession,
  CuadernoStreamEvent,
} from '../types/api'
```

Append after the `cuadernoApi` object:

```typescript
// Streams POST /api/cuaderno/ask as text/event-stream. EventSource cannot be
// used because it is GET-only and this endpoint needs a JSON POST body, so we
// read the response body with fetch + a ReadableStream reader and parse SSE
// records ("data: <json>\n\n") ourselves, buffering across chunk boundaries.
export async function askStream(
  question: string,
  sessionId: string | undefined,
  opts: { onEvent: (e: CuadernoStreamEvent) => void; signal?: AbortSignal },
): Promise<void> {
  const r = await fetch('/api/cuaderno/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
    signal: opts.signal,
  })
  if (!r.ok || !r.body) {
    const text = r.body ? await r.text() : ''
    throw new Error(`POST /api/cuaderno/ask → ${r.status}: ${text}`)
  }
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const record = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      const dataLine = record
        .split('\n')
        .find((l) => l.startsWith('data:'))
      if (!dataLine) continue
      const json = dataLine.slice(5).trim()
      if (!json) continue
      opts.onEvent(JSON.parse(json) as CuadernoStreamEvent)
    }
  }
}
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/cuaderno.ts
git commit -m "feat(cuaderno): askStream fetch-stream client"
```

---

## PR4 — Frontend wiring (consume the stream)

---

### Task 12: FrameMidStream uses the shared ToolRow and renders the error state

**Files:**
- Modify: `frontend/src/components/cuaderno/frames/FrameMidStream.tsx`

- [ ] **Step 1: Replace the local types and add the error glyph**

Replace lines 1-16 of `frontend/src/components/cuaderno/frames/FrameMidStream.tsx` with:

```typescript
import type { ToolRow } from '../../../types/api'

type Props = {
  question: string
  tools: ToolRow[]
  partial: string
}

export function FrameMidStream({ question, tools, partial }: Props) {
```

Then update the glyph and meta expressions inside the `tools.map` (current lines 26-37) to handle `error`:

```typescript
            <span className="tag">
              {t.state === 'done'
                ? '✓'
                : t.state === 'error'
                ? '⨯'
                : t.state === 'running'
                ? '◐'
                : '·'}
            </span>
            <span className="name">{t.name}</span>
            <span className="args">{t.args}</span>
            <span className="meta">
              {t.state === 'done'
                ? `${t.ms ?? 0} ms`
                : t.state === 'error'
                ? 'failed'
                : t.state === 'running'
                ? 'running…'
                : 'queued'}
            </span>
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/frames/FrameMidStream.tsx
git commit -m "feat(cuaderno): FrameMidStream shares ToolRow + renders error state"
```

---

### Task 13: Two-act scene gate in Cuaderno

**Files:**
- Modify: `frontend/src/components/cuaderno/Cuaderno.tsx`

- [ ] **Step 1: Update imports and props**

In `frontend/src/components/cuaderno/Cuaderno.tsx`, replace the type import on line 2 and the `Props` type (lines 11-22):

```typescript
import type { Block, Citation, CuadernoQuestion, ToolRow } from '../../types/api'
```

```typescript
type Props = {
  sessionLabel: string
  questionNumber: string
  questions: CuadernoQuestion[]
  activeQuestion: CuadernoQuestion | null
  isLoading: boolean
  streamingQuestion?: string
  partialBlocks?: Block[]
  toolCalls?: ToolRow[]
  onAsk: (question: string) => void
  onSelectFromHistory: (position: number) => void
  onSetGotIt: (position: number, value: 'got' | 'didnt') => void
}
```

- [ ] **Step 2: Update the destructure and the scene logic**

Replace the destructure defaults (lines 24-35) and the scene computation (lines 39-40):

```typescript
export function Cuaderno({
  sessionLabel,
  questionNumber,
  questions,
  activeQuestion,
  isLoading,
  streamingQuestion = '',
  partialBlocks = [],
  toolCalls = [],
  onAsk,
  onSelectFromHistory,
  onSetGotIt,
}: Props) {
  const [sidePanelFor, setSidePanelFor] = useState<Citation | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const scene: 'empty' | 'midstream' | 'writing' | 'frame' = !isLoading
    ? activeQuestion
      ? 'frame'
      : 'empty'
    : partialBlocks.length > 0
    ? 'writing'
    : 'midstream'
```

- [ ] **Step 3: Render the writing act**

Replace the `midstream` render branch (current lines 69-75) with both the `midstream` and the new `writing` branches:

```typescript
            {scene === 'midstream' && (
              <FrameMidStream
                question={streamingQuestion || questions[questions.length - 1]?.question || '…'}
                tools={toolCalls}
                partial=""
              />
            )}
            {scene === 'writing' && (
              <FrameDynamic
                frame={{ question: streamingQuestion, blocks: partialBlocks }}
                onOpenCitation={setSidePanelFor}
                onAsk={onAsk}
              />
            )}
```

- [ ] **Step 4: Type-check**

Run (from `frontend/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cuaderno/Cuaderno.tsx
git commit -m "feat(cuaderno): two-act scene gate (evidence -> writing -> settled)"
```

---

### Task 14: CuadernoPage consumes the stream

**Files:**
- Modify: `frontend/src/pages/CuadernoPage.tsx`
- Modify: `frontend/src/api/cuaderno.ts` (remove the now-dead `ask`/`postJson`)

- [ ] **Step 1: Rework CuadernoPage**

Replace lines 1-4 of `frontend/src/pages/CuadernoPage.tsx`:

```typescript
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Block, CuadernoQuestion, ToolRow } from '../types/api'
import { Cuaderno } from '../components/cuaderno/Cuaderno'
import { askStream, cuadernoApi } from '../api/cuaderno'
```

Add streaming state after line 15 (`const [error, setError] = useState...`):

```typescript
  const [streamingQuestion, setStreamingQuestion] = useState('')
  const [partialBlocks, setPartialBlocks] = useState<Block[]>([])
  const [toolCalls, setToolCalls] = useState<ToolRow[]>([])
  const abortRef = useRef<AbortController | null>(null)

  // Abort an in-flight stream on unmount.
  useEffect(() => () => abortRef.current?.abort(), [])
```

Replace the entire `onAsk` function (lines 40-63) with:

```typescript
  const onAsk = (question: string) => {
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac

    setError(null)
    setIsLoading(true)
    setStreamingQuestion(question)
    setPartialBlocks([])
    setToolCalls([])

    let capturedSession = sessionId

    askStream(question, sessionId ?? undefined, {
      signal: ac.signal,
      onEvent: (e) => {
        switch (e.type) {
          case 'meta':
            if (!capturedSession) {
              capturedSession = e.session_id
              setSessionId(e.session_id)
              localStorage.setItem(SESSION_STORAGE_KEY, e.session_id)
            }
            break
          case 'tool':
            setToolCalls((prev) => {
              const next = prev.filter((t) => t.name + t.args !== e.name + e.args)
              return [
                ...next,
                { state: e.state, name: e.name, args: e.args, ms: e.ms },
              ]
            })
            break
          case 'block':
            setPartialBlocks((prev) => [...prev, e.block])
            break
          case 'frame': {
            const newQ: CuadernoQuestion = {
              position: e.position,
              question,
              frame: e.frame,
              bookmarked: false,
              got_it: null,
              created_at: new Date().toISOString(),
            }
            setQuestions((prev) => [...prev, newQ])
            setActivePosition(e.position)
            break
          }
          case 'error':
            setError(e.partial ? `${e.message} (partial answer saved)` : e.message)
            break
        }
      },
    })
      .catch((err) => {
        if (ac.signal.aborted) return
        setError(String(err))
      })
      .finally(() => {
        if (ac.signal.aborted) return
        setIsLoading(false)
        setPartialBlocks([])
        setToolCalls([])
      })
  }
```

Update the `<Cuaderno>` props (lines 99-108) to pass the streaming state:

```typescript
      <Cuaderno
        sessionLabel={sessionLabel}
        questionNumber={questionNumber}
        questions={questions}
        activeQuestion={activeQuestion}
        isLoading={isLoading}
        streamingQuestion={streamingQuestion}
        partialBlocks={partialBlocks}
        toolCalls={toolCalls}
        onAsk={onAsk}
        onSelectFromHistory={onSelectFromHistory}
        onSetGotIt={onSetGotIt}
      />
```

- [ ] **Step 2: Remove the dead one-shot client**

In `frontend/src/api/cuaderno.ts`, remove the now-unused `postJson` helper (lines 3-14) and the `ask` method from `cuadernoApi` (lines 39-44). Update the import on line 1 to drop `CuadernoAskResponse`:

```typescript
import type { CuadernoSession, CuadernoStreamEvent } from '../types/api'
```

The `cuadernoApi` object retains only `session` and `patchQuestion`:

```typescript
export const cuadernoApi = {
  session(sessionId: string) {
    return getJson<CuadernoSession>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}`,
    )
  },
  patchQuestion(
    sessionId: string,
    position: number,
    fields: { bookmarked?: boolean; got_it?: 'got' | 'didnt' | null },
  ) {
    return patchJson<{ ok: boolean }>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}/questions/${position}`,
      fields,
    )
  },
}
```

- [ ] **Step 3: Type-check**

Run (from `frontend/`): `npm run build`
Expected: build succeeds. (If `tsc` flags `CuadernoAskResponse` as unused anywhere else, remove those references — it should now be referenced nowhere.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CuadernoPage.tsx frontend/src/api/cuaderno.ts
git commit -m "feat(cuaderno): CuadernoPage consumes the SSE stream (revives mid-stream UI)"
```

---

### Task 15: Manual end-to-end verification

**Files:** none (verification gate for PR4; requires `ANTHROPIC_API_KEY` and an analyzed project — this repo)

- [ ] **Step 1: Build the frontend bundle**

Run (from `frontend/`): `npm run build`
Expected: build succeeds; the single-file bundle is produced and picked up by the server (same mechanism as Phase 1).

- [ ] **Step 2: Start the server and open the cuaderno**

Start CopyClip the normal way (e.g. `python -m copyclip start`) on this repo, open the cuaderno page in the browser.

- [ ] **Step 3: Ask a broad question and observe the stream**

Ask: `what does this project do?`

Expected, in order:
1. Tool-call rows appear and animate (`◐ running…` → `✓ N ms`) as the tutor reads evidence.
2. The view switches to the growing frame: blocks appear one by one (lead, then paragraphs, code, citations, follow-ups) — each complete when it appears.
3. The frame settles; the "I got this / I didn't" markers appear below it.
4. Citation chips open the side panel; the session history overlay lists the question.

- [ ] **Step 4: Verify cancellation does not crash**

Ask a question, and while it is streaming, navigate away from the cuaderno page (select another sidebar page) and back. Expected: no console errors about setState-after-unmount; the abort fired cleanly.

- [ ] **Step 5: Verify restore parity**

Reload the page. Expected: the session restores via `GET /api/cuaderno/sessions/:id`, and the last answer renders identically to how it appeared live (same blocks, same order).

- [ ] **Step 6: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix(cuaderno): PR4 e2e verification fixes"
```

---

## Self-review notes

- **Spec coverage:** Two-phase loop (Task 4), event protocol incl. layer split — `meta`/`position` owned by the HTTP wrapper (Task 7), `messages.stream` requirement (Task 6), SSE route on the `server_events` pattern (Tasks 8-9), `emit_block`/`finish` protocol + prompt (Tasks 2-3), block validation/rejection (Task 1), error/partial + disconnect persistence (Tasks 7-8), two-act scene gate (Task 13), `askStream` fetch-stream (Task 11), types union (Task 10), dead-code removal (Task 14), live-vs-restore parity verified (Task 15 Step 5). All spec sections map to a task.
- **Streaming/test boundary:** PR1 tests the generator against a `messages_stream` stub; the real adapter method (Task 6) lands in PR2 — so PR1 is fully green without the SDK.
- **Frontend testing:** type-check (`npm run build` → `tsc -b`) + manual e2e, matching the Phase-1 frontend (no unit-test harness). Adding vitest was deliberately not included — flag for the user if desired.
- **Keepalive:** intentionally omitted (localhost same-origin; no proxy) per the spec.
```
