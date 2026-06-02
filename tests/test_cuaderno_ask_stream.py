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


def _read_then_answer():
    # A grounded turn (a real content-bearing read) followed by an answer turn,
    # so the groundedness gate seals a normal `answer` frame instead of forcing
    # a grounding retry. Requires a README.md in the project_root.
    return [
        [
            _tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
        ],
        [
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "hi"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b1", "emit_block", {"kind": "lead", "text": "hi"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]


def test_meta_is_first_and_frame_carries_position(tmp_path: Path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    events = list(iter_ask_events(
        client=StubStream(_read_then_answer()), question="q",
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


def test_disconnect_persists_partial_with_status_partial(tmp_path: Path):
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
    assert rows[0]["frame"]["status"] == "partial"
