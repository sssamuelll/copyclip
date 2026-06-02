import json
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
        "status": "answer",
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


def test_final_round_forces_an_answer(tmp_path: Path):
    """A model that keeps researching gets one forced closing round: the last
    round is offered ONLY the answer tools (emit_block/finish) plus a directive,
    so it must compose an answer instead of exhausting the budget with reads."""
    read_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    closing_turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "it does X"}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "it does X"}),
            _content("f", "finish", {}),
        ]),
    ]
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream([read_turn, closing_turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None, max_tool_rounds=2,
    ))

    # A real answer, not the budget-exhausted fallback.
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["blocks"] == [{"kind": "lead", "text": "it does X"}]

    # The closing (2nd) round was offered ONLY the answer tools...
    closing_call = client.calls[1]
    closing_tool_names = {t["name"] for t in closing_call["tools"]}
    assert closing_tool_names == {"emit_block", "finish"}

    # ...and carried a directive telling the model to answer now.
    flat = json.dumps(closing_call["messages"])
    assert "emit_block" in flat and ("answer" in flat.lower() or "compose" in flat.lower())


def test_non_final_rounds_keep_research_tools(tmp_path: Path):
    """Only the LAST round is restricted; earlier rounds keep the full toolset
    (including list_dir / read_file) so evidence-gathering still works."""
    read_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    closing_turn = [
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [_content("f", "finish", {})]),
    ]
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream([read_turn, closing_turn])
    list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None, max_tool_rounds=2,
    ))
    first_call = client.calls[0]
    first_tool_names = {t["name"] for t in first_call["tools"]}
    assert "read_file" in first_tool_names and "list_dir" in first_tool_names


def test_emit_block_across_two_turns_emits_once(tmp_path: Path):
    """A turn emits a valid block but does NOT finish (stop_reason tool_use); a
    second turn finishes. The block must be emitted exactly once (during the
    first stream), acked in between, and appear once in the final frame. This is
    the non-terminal emit_block continue/ack path (spec line 69)."""
    turns = [
        [
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "hi"}),
            _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "hi"})]),
        ],
        [
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [_content("f", "finish", {})]),
        ],
    ]
    client = StubStream(turns)
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    block_events = [e for e in events if e["type"] == "block"]
    assert len(block_events) == 1
    assert block_events[0]["block"] == {"kind": "lead", "text": "hi"}
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["blocks"] == [{"kind": "lead", "text": "hi"}]
    # The second turn must have been driven (ack fed back) → two stream calls.
    assert len(client.calls) == 2
