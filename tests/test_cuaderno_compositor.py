import json
from pathlib import Path
from unittest.mock import patch

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
        project_id=1, conn=None, max_tool_rounds=1,
    ))
    kinds = [e["type"] for e in events]
    assert kinds == ["block", "block", "frame"]
    assert events[0]["block"] == {"kind": "lead", "text": "hi"}
    assert events[1]["block"] == {"kind": "paragraph", "text": "body"}
    frame = events[2]["frame"]
    assert frame["question"] == "q"
    assert frame["blocks"] == [{"kind": "lead", "text": "hi"},
                                {"kind": "paragraph", "text": "body"}]
    assert frame["status"] == "ungrounded"
    assert frame["verdict"]["source"] == "cheap"
    assert frame["verdict"]["grounded"] is False


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


def test_graph_view_fog_is_stamped_authoritative(tmp_path: Path):
    """End-to-end honesty: the model calls get_module_graph (evidence gains the
    computed debt), then emits a graph_view LYING about both the fog number and
    the cited file. The emitted block must carry the SERVER's score and citation
    — fog crosses computed, never uttered."""
    import sqlite3
    from copyclip.intelligence.db import init_schema

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path) VALUES(?)", (str(tmp_path),))
    pid = conn.execute("SELECT id FROM projects").fetchone()[0]

    def _sym(name, module, fp):
        cur = conn.execute(
            "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,"
            "parent_symbol_id,module) VALUES(?,?,?,?,?,?,?,?)",
            (pid, name, "function", fp, 1, 5, None, module))
        return cur.lastrowid

    a = _sym("fn_a", "pkg/a", "pkg/a.py")
    b = _sym("fn_b", "pkg/b", "pkg/b.py")
    conn.execute("INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
                 "VALUES(?,?,?,?)", (pid, a, b, "calls"))
    conn.execute("INSERT INTO analysis_file_insights(project_id,path,module,cognitive_debt) "
                 "VALUES(?,?,?,?)", (pid, "pkg/a.py", "pkg/a", 88.0))
    conn.commit()

    gv = {"kind": "widget", "widget": {
        "kind": "graph_view",
        "nodes": [{"id": "pkg/a", "label": "a",
                   "citation": {"kind": "path", "path": "LIES.py"},   # wrong file
                   "cognitive_debt_score": 3.0}],                      # wrong number
        "edges": []}}
    turns = [
        [
            _tool_stop("t1", "get_module_graph", {}),
            _msg_stop("tool_use", [_content("t1", "get_module_graph", {})]),
        ],
        [
            _tool_stop("b1", "emit_block", gv),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [_content("b1", "emit_block", gv),
                                   _content("f", "finish", {})]),
        ],
    ]
    client = StubStream(turns)
    events = list(iter_compose_events(
        client=client, question="show me the architecture",
        project_root=str(tmp_path), project_id=pid, conn=conn,
    ))
    blocks = [e["block"] for e in events if e["type"] == "block"]
    assert blocks, "graph_view block was not emitted"
    node = blocks[0]["widget"]["nodes"][0]
    assert node["cognitive_debt_score"] == 88.0                       # server truth, not 3.0
    assert node["citation"] == {"kind": "path", "path": "pkg/a.py"}   # not LIES.py


def test_implicit_finish_on_end_turn(tmp_path: Path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("end_turn", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None, max_tool_rounds=1,
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
        project_id=1, conn=None, max_tool_rounds=1,
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
        project_id=1, conn=None, max_tool_rounds=1,
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
        project_id=1, conn=None, max_tool_rounds=2,
    ))
    block_events = [e for e in events if e["type"] == "block"]
    assert len(block_events) == 1
    assert block_events[0]["block"] == {"kind": "lead", "text": "hi"}
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["blocks"] == [{"kind": "lead", "text": "hi"}]
    # The second turn must have been driven (ack fed back) → two stream calls.
    assert len(client.calls) == 2


def test_pyrrhic_answer_is_sealed_ungrounded(tmp_path: Path):
    """Zero reads + a confident code answer -> status ungrounded (the incident).
    With max_tool_rounds=1 there is no budget for a retry, so the verdict seals
    immediately — confirming the gate fires even when the retry cannot."""
    turn = [
        _tool_stop("b1", "emit_block",
                   {"kind": "lead", "text": "CopyClip is a local-first CLI."}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block",
                     {"kind": "lead", "text": "CopyClip is a local-first CLI."}),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="how does it work?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=1,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "ungrounded"


def test_grounded_answer_is_sealed_answer(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    turns = [
        [
            _tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
        ],
        [
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "It does X per README.md."}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b1", "emit_block", {"kind": "lead", "text": "It does X per README.md."}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    client = StubStream(turns)
    events = list(iter_compose_events(
        client=client, question="how does it work?",
        project_root=str(tmp_path), project_id=1, conn=None,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "answer"


def test_fallback_frames_are_status_fallback(tmp_path: Path):
    turn = [
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [_content("f", "finish", {})]),
    ]
    client = StubStream([turn])
    events = list(iter_compose_events(
        client=client, question="q", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "fallback"


def test_ungrounded_finish_triggers_one_grounding_retry(tmp_path: Path):
    """Turn 1: ungrounded finish (no reads). The gate must NOT seal; it injects
    a grounding directive and grants another round. Turn 2 reads. Turn 3 answers
    grounded -> status answer. Exactly one retry, research tools kept on retry."""
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    ungrounded_turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
            _content("f", "finish", {}),
        ]),
    ]
    grounded_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    final_turn = [
        _tool_stop("b2", "emit_block", {"kind": "lead", "text": "It does X per README.md."}),
        _tool_stop("f2", "finish", {}),
        _msg_stop("tool_use", [
            _content("b2", "emit_block", {"kind": "lead", "text": "It does X per README.md."}),
            _content("f2", "finish", {}),
        ]),
    ]
    client = StubStream([ungrounded_turn, grounded_turn, final_turn])
    events = list(iter_compose_events(
        client=client, question="how does it work?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "answer"
    retry_call = client.calls[1]
    retry_names = {t["name"] for t in retry_call["tools"]}
    assert "read_file" in retry_names
    # The corrected answer REPLACES the ungrounded one — the hallucinated block
    # must not survive inside a frame sealed as a confident answer.
    texts = " ".join(b.get("text", "") for b in frame["frame"]["blocks"])
    assert "It does X per README.md." in texts
    assert "It is a CLI." not in texts


def test_grounding_retry_suppressed_when_next_round_is_closing(tmp_path: Path):
    """With a tiny budget, an ungrounded finish whose retry round would BE the
    closing round (research tools stripped) must NOT retry — it seals ungrounded
    directly in a single stream call, avoiding the closing-round collision."""
    ungrounded_turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([ungrounded_turn, ungrounded_turn])
    events = list(iter_compose_events(
        client=client, question="how does it work?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=2,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "ungrounded"
    assert len(client.calls) == 1


def test_grounding_retry_fires_at_most_once(tmp_path: Path):
    """Model stays ungrounded across the original finish AND the retry ->
    sealed ungrounded, no infinite loop, exactly one retry (2 stream calls)."""
    ungrounded_turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([ungrounded_turn, ungrounded_turn, ungrounded_turn])
    events = list(iter_compose_events(
        client=client, question="how does it work?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8,
    ))
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "ungrounded"
    assert len(client.calls) == 2


def test_retry_emits_reset_event(tmp_path: Path):
    """The grounding retry emits a `reset` so downstream consumers drop the
    discarded provisional blocks; the corrected answer seals `answer`."""
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    ungrounded_turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
            _content("f", "finish", {}),
        ]),
    ]
    read_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    final_turn = [
        _tool_stop("b2", "emit_block", {"kind": "lead", "text": "It does X per README.md."}),
        _tool_stop("f2", "finish", {}),
        _msg_stop("tool_use", [
            _content("b2", "emit_block", {"kind": "lead", "text": "It does X per README.md."}),
            _content("f2", "finish", {}),
        ]),
    ]
    client = StubStream([ungrounded_turn, read_turn, final_turn])
    events = list(iter_compose_events(
        client=client, question="how does it work?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8,
    ))
    assert any(e["type"] == "reset" for e in events)
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "answer"


def test_language_mismatch_triggers_retry(tmp_path: Path):
    """A GROUNDED answer in the wrong language fires the one retry (with a
    reset); the corrected Spanish answer seals `answer`."""
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    read_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    english_answer = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "It walks the syntax tree."}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": "It walks the syntax tree."}),
            _content("f", "finish", {}),
        ]),
    ]
    spanish_answer = [
        _tool_stop("b2", "emit_block", {"kind": "lead", "text": "El sistema recorre la sintaxis del proyecto."}),
        _tool_stop("f2", "finish", {}),
        _msg_stop("tool_use", [
            _content("b2", "emit_block", {"kind": "lead", "text": "El sistema recorre la sintaxis del proyecto."}),
            _content("f2", "finish", {}),
        ]),
    ]
    client = StubStream([read_turn, english_answer, spanish_answer])
    events = list(iter_compose_events(
        client=client, question="como funciona el analizador",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8,
    ))
    assert any(e["type"] == "reset" for e in events)
    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["status"] == "answer"
    texts = " ".join(b.get("text", "") for b in frame["frame"]["blocks"])
    assert "sistema" in texts and "It walks" not in texts


# ---------------------------------------------------------------------------
# Task 6 — judge integration
# ---------------------------------------------------------------------------

from copyclip.intelligence.cuaderno.judge import JudgeVerdict


def _grounded_answer_turns(text="It walks the AST in analyzer.py."):
    read_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    answer_turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": text}),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "lead", "text": text}),
            _content("f", "finish", {}),
        ]),
    ]
    return [read_turn, answer_turn]


def _judge_returning(verdict):
    def _judge(question, blocks, ledger):
        return verdict
    return _judge


def test_judge_ok_seals_answer_with_judge_verdict(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream(_grounded_answer_turns())
    jv = JudgeVerdict("code_comprehension", True, True, True, "ok", None, None, "good")
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge_returning(jv),
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer"
    assert frame["verdict"]["source"] == "judge" and frame["verdict"]["responsive"] is True


def test_judge_insufficient_consulted_empty_seals_insufficient_evidence(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream(_grounded_answer_turns())
    jv = JudgeVerdict("code_comprehension", False, True, True, "insufficient", "consulted_empty", None, "empty")
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge_returning(jv),
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "insufficient_evidence"


def test_judge_insufficient_not_consulted_seals_ungrounded(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream(_grounded_answer_turns())
    jv = JudgeVerdict("code_comprehension", False, True, True, "insufficient", "not_consulted", None, "lazy")
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge_returning(jv),
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "ungrounded"


def test_no_judge_seals_answer_with_cheap_verdict(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream(_grounded_answer_turns())
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer" and frame["verdict"]["source"] == "cheap"


# ---------------------------------------------------------------------------
# Task 7 — harder paths (retry loops, non-fungibility)
# ---------------------------------------------------------------------------

def test_judge_retry_then_ok_seals_corrected_answer(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    read = [_tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})])]
    bad = [_tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
           _tool_stop("f", "finish", {}),
           _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
                                  _content("f", "finish", {})])]
    good = [_tool_stop("b2", "emit_block", {"kind": "lead", "text": "It walks the AST, dispatching per node."}),
            _tool_stop("f2", "finish", {}),
            _msg_stop("tool_use", [_content("b2", "emit_block", {"kind": "lead", "text": "It walks the AST, dispatching per node."}),
                                   _content("f2", "finish", {})])]
    client = StubStream([read, bad, good])
    verdicts = iter([
        JudgeVerdict("code_comprehension", True, False, True, "retry", None, "explain the mechanism", "what not how"),
        JudgeVerdict("code_comprehension", True, True, True, "ok", None, None, "good now"),
    ])
    def _judge(q, b, l): return next(verdicts)
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge,
    ))
    assert any(e["type"] == "reset" for e in events)
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer"
    assert "It is a CLI." not in " ".join(b.get("text", "") for b in frame["blocks"])


def test_judge_retry_still_non_responsive_seals_off_target(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    read = [_tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})])]
    bad = [_tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
           _tool_stop("f", "finish", {}),
           _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
                                  _content("f", "finish", {})])]
    client = StubStream([read, bad, bad])
    jv = JudgeVerdict("code_comprehension", True, False, True, "retry", None, "explain the mechanism", "still what not how")
    def _judge(q, b, l): return jv
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "off_target"
    assert frame["verdict"]["responsive"] is False


def test_judge_failure_fails_open_to_answer(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream(_grounded_answer_turns())
    ok = JudgeVerdict("code_comprehension", True, True, True, "ok", None, None, "judge unavailable: x")
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge_returning(ok),
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer"


def test_grounding_and_responsiveness_retries_are_non_fungible(tmp_path: Path):
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    ungrounded = [_tool_stop("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
                  _tool_stop("f", "finish", {}),
                  _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "It is a CLI."}),
                                         _content("f", "finish", {})])]
    read = [_tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})])]
    grounded_but_off = [_tool_stop("b2", "emit_block", {"kind": "lead", "text": "It is, per README.md, a CLI."}),
                        _tool_stop("f2", "finish", {}),
                        _msg_stop("tool_use", [_content("b2", "emit_block", {"kind": "lead", "text": "It is, per README.md, a CLI."}),
                                               _content("f2", "finish", {})])]
    fixed = [_tool_stop("b3", "emit_block", {"kind": "lead", "text": "It walks the AST node by node."}),
             _tool_stop("f3", "finish", {}),
             _msg_stop("tool_use", [_content("b3", "emit_block", {"kind": "lead", "text": "It walks the AST node by node."}),
                                    _content("f3", "finish", {})])]
    client = StubStream([ungrounded, read, grounded_but_off, fixed])
    verdicts = iter([
        JudgeVerdict("code_comprehension", True, False, True, "retry", None, "mechanism please", "off"),
        JudgeVerdict("code_comprehension", True, True, True, "ok", None, None, "good"),
    ])
    def _judge(q, b, l): return next(verdicts)
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge, max_tool_rounds=8,
    ))
    resets = [e for e in events if e["type"] == "reset"]
    assert len(resets) == 2
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer"


def test_budget_tail_would_be_answer_is_judged(tmp_path: Path):
    """A would-be-answer reached via budget exhaustion is STILL judged (Option A):
    a judge retry there cannot retry (loop is over) -> off_target."""
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    read = [_tool_stop("r", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r", "read_file", {"path": "README.md"})])]
    emit_no_finish = [
        _tool_stop("b", "emit_block", {"kind": "lead", "text": "It walks the AST."}),
        _msg_stop("tool_use", [_content("b", "emit_block", {"kind": "lead", "text": "It walks the AST."})]),
    ]
    client = StubStream([read, emit_no_finish, emit_no_finish])
    jv = JudgeVerdict("code_comprehension", True, False, True, "retry", None, "redo", "off")
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None, judge=_judge_returning(jv), max_tool_rounds=3,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "off_target"
    assert frame["verdict"]["source"] == "judge"


# ---------------------------------------------------------------------------
# Task 4 — emit-time verification: graph subset + playground recipe validation
# ---------------------------------------------------------------------------

def test_invented_graph_edge_yields_invalid_block_ack(tmp_path: Path):
    """Turn 1: model calls get_module_graph (returns nodes pkg/a, pkg/b and one
    directed edge a->b).  Turn 2: model emits a graph_view widget with an INVENTED
    reversed edge (b->a) then finishes.  The compositor must reject the block with
    invalid_block — matching the existing malformed-block behaviour — and the
    frame must contain NO blocks (the rejected widget is never emitted)."""
    _MODULE_GRAPH_RESULT = {
        "modules": [
            {"name": "pkg/a", "file_path": "src/pkg/a.py"},
            {"name": "pkg/b", "file_path": "src/pkg/b.py"},
        ],
        "edges": [{"from": "pkg/a", "to": "pkg/b", "weight": 1}],
        "truncated": False,
    }

    widget_block = {
        "kind": "widget",
        "widget": {
            "kind": "graph_view",
            "nodes": [{"id": "pkg/a", "label": "a", "citation": {"kind": "path", "path": "src/pkg/a.py"}},
                      {"id": "pkg/b", "label": "b", "citation": {"kind": "path", "path": "src/pkg/b.py"}}],
            "edges": [{"from": "pkg/b", "to": "pkg/a"}],  # reversed — not in evidence
        },
    }

    turns = [
        # Turn 1: model calls get_module_graph
        [
            _tool_stop("g1", "get_module_graph", {"scope": ""}),
            _msg_stop("tool_use", [_content("g1", "get_module_graph", {"scope": ""})]),
        ],
        # Turn 2: model emits a widget with an invented edge, then finishes
        [
            _tool_stop("b1", "emit_block", widget_block),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b1", "emit_block", widget_block),
                _content("f", "finish", {}),
            ]),
        ],
    ]

    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _MODULE_GRAPH_RESULT,
    ):
        events = list(iter_compose_events(
            client=client, question="q", project_root=str(tmp_path),
            project_id=1, conn=None, max_tool_rounds=8,
        ))

    # The widget block must have been REJECTED (invalid_block path mirrors
    # test_malformed_block_is_dropped: no block events, fallback frame).
    block_events = [e for e in events if e["type"] == "block"]
    assert len(block_events) == 0, "invented-edge widget must not be emitted as a block"

    frame = next(e for e in events if e["type"] == "frame")
    assert frame["frame"]["blocks"] == [] or frame["frame"]["status"] in (
        "fallback", "ungrounded"
    ), "frame must reflect rejection of the invalid widget"


def test_graph_evidence_survives_across_rounds(tmp_path: Path):
    """Round 1 returns a get_module_graph tool result (nodes pkg/a + pkg/b, edge
    a->b); round 2 emits a VALID graph_view widget whose edges match that
    evidence, then finishes.  The compositor must ACCEPT the block — evidence
    accumulated at turn level, not per-round, so the cross-round emission is
    valid."""
    _MODULE_GRAPH_RESULT = {
        "modules": [
            {"name": "pkg/a", "file_path": "src/pkg/a.py"},
            {"name": "pkg/b", "file_path": "src/pkg/b.py"},
        ],
        "edges": [{"from": "pkg/a", "to": "pkg/b", "weight": 1}],
        "truncated": False,
    }

    valid_widget_block = {
        "kind": "widget",
        "widget": {
            "kind": "graph_view",
            "nodes": [{"id": "pkg/a", "label": "a", "citation": {"kind": "path", "path": "src/pkg/a.py"}},
                      {"id": "pkg/b", "label": "b", "citation": {"kind": "path", "path": "src/pkg/b.py"}}],
            "edges": [{"from": "pkg/a", "to": "pkg/b"}],  # matches evidence exactly
        },
    }

    turns = [
        # Round 1: model calls get_module_graph
        [
            _tool_stop("g1", "get_module_graph", {"scope": ""}),
            _msg_stop("tool_use", [_content("g1", "get_module_graph", {"scope": ""})]),
        ],
        # Round 2: model emits a widget whose edges ARE in the evidence, then finishes
        [
            _tool_stop("b1", "emit_block", valid_widget_block),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b1", "emit_block", valid_widget_block),
                _content("f", "finish", {}),
            ]),
        ],
    ]

    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _MODULE_GRAPH_RESULT,
    ):
        events = list(iter_compose_events(
            client=client, question="q", project_root=str(tmp_path),
            project_id=1, conn=None, max_tool_rounds=8,
        ))

    # The widget block must have been ACCEPTED: a block event must exist and the
    # frame must contain the widget (no invalid_block rejection).
    block_events = [e for e in events if e["type"] == "block"]
    assert len(block_events) == 1, (
        "cross-round graph_view with valid edges must be accepted as a block"
    )
    assert block_events[0]["block"]["kind"] == "widget"

    frame = next(e for e in events if e["type"] == "frame")
    assert len(frame["frame"]["blocks"]) == 1, (
        "valid cross-round widget must appear in the sealed frame"
    )


# ---------------------------------------------------------------------------
# Widget-fixation backstop — an ungroundable widget must offer a prose off-ramp
# instead of silently draining the round budget into a blank frame.
# ---------------------------------------------------------------------------

_GRAPH_RESULT = {
    "modules": [
        {"name": "pkg/a", "file_path": "src/pkg/a.py"},
        {"name": "pkg/b", "file_path": "src/pkg/b.py"},
    ],
    "edges": [{"from": "pkg/a", "to": "pkg/b", "weight": 1}],
    "truncated": False,
}

# A graph_view with a reversed edge (b->a) — not in the evidence, so it is
# rejected at emit time and never becomes a block.
_BAD_WIDGET = {
    "kind": "widget",
    "widget": {
        "kind": "graph_view",
        "nodes": [
            {"id": "pkg/a", "label": "a", "citation": {"kind": "path", "path": "src/pkg/a.py"}},
            {"id": "pkg/b", "label": "b", "citation": {"kind": "path", "path": "src/pkg/b.py"}},
        ],
        "edges": [{"from": "pkg/b", "to": "pkg/a"}],
    },
}


def _graph_turn():
    return [
        _tool_stop("g1", "get_module_graph", {"scope": "pkg"}),
        _msg_stop("tool_use", [_content("g1", "get_module_graph", {"scope": "pkg"})]),
    ]


def _bad_widget_turn(bid="w1"):
    # Emits the ungroundable widget WITHOUT finish — stays in tool_use, so the
    # round is non-terminal and the loop continues (the fixation pattern).
    return [
        _tool_stop(bid, "emit_block", _BAD_WIDGET),
        _msg_stop("tool_use", [_content(bid, "emit_block", _BAD_WIDGET)]),
    ]


def test_invalid_block_ack_carries_recovery_instruction(tmp_path: Path):
    """When a widget is rejected, its invalid_block ack must carry a `recovery`
    instruction — not just the bare reason — so the model is told what to do."""
    turns = [
        _graph_turn(),
        _bad_widget_turn(),
        [  # the model recovers with prose
            _tool_stop("l1", "emit_block", {"kind": "lead", "text": "ans"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("l1", "emit_block", {"kind": "lead", "text": "ans"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _GRAPH_RESULT,
    ):
        list(iter_compose_events(
            client=client, question="q", project_root=str(tmp_path),
            project_id=1, conn=None, max_tool_rounds=8,
        ))
    # Decode the error acks the model was sent and confirm the rejected widget's
    # ack carries a recovery instruction, not just a bare reason.
    error_acks = []
    for m in client.calls[-1]["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            for blk in m["content"]:
                if isinstance(blk, dict) and blk.get("type") == "tool_result" and blk.get("is_error"):
                    error_acks.append(json.loads(blk["content"]))
    invalid = [a for a in error_acks if a.get("error") == "invalid_block"]
    assert invalid, "the rejected widget must produce an invalid_block ack"
    assert all("recovery" in a for a in invalid), "invalid_block ack must carry a recovery instruction"


def test_all_rejected_round_injects_prose_recovery_directive(tmp_path: Path):
    """After a round whose only emit was a rejected widget, the compositor must
    inject a directive telling the model it may answer in prose."""
    turns = [
        _graph_turn(),
        _bad_widget_turn(),
        [
            _tool_stop("l1", "emit_block", {"kind": "lead", "text": "ans"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("l1", "emit_block", {"kind": "lead", "text": "ans"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _GRAPH_RESULT,
    ):
        list(iter_compose_events(
            client=client, question="q", project_root=str(tmp_path),
            project_id=1, conn=None, max_tool_rounds=8,
        ))
    serialized = json.dumps(client.calls[2]["messages"])
    assert "answer in prose" in serialized, (
        "a stuck-on-widget round must offer the prose off-ramp"
    )


def test_persistent_widget_fixation_keeps_offering_prose_offramp(tmp_path: Path):
    """A model that fixates on an ungroundable widget every round must be offered
    the prose off-ramp (at least once) rather than silently draining the budget."""
    turns = [_graph_turn()] + [_bad_widget_turn(f"w{i}") for i in range(7)]  # 8 rounds
    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _GRAPH_RESULT,
    ):
        events = list(iter_compose_events(
            client=client, question="q", project_root=str(tmp_path),
            project_id=1, conn=None, max_tool_rounds=8,
        ))
    offers = json.dumps(client.calls).count("answer in prose")
    assert offers >= 1, "the prose off-ramp must be offered to a fixating model"
    assert any(e["type"] == "frame" for e in events), "a terminal frame must still be produced"


def test_visual_question_pushes_widget_rebuild_not_prose(tmp_path: Path):
    """For a 'show me the graph' question, a rejected widget must NOT be told to
    answer in prose (that earns off_target) — it must be pushed to rebuild the
    graph_view, since file-granularity evidence makes the widget buildable now."""
    turns = [
        _graph_turn(),
        _bad_widget_turn(),
        [  # a later turn so the loop terminates cleanly
            _tool_stop("l1", "emit_block", {"kind": "lead", "text": "ans"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("l1", "emit_block", {"kind": "lead", "text": "ans"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _GRAPH_RESULT,
    ):
        list(iter_compose_events(
            client=client, question="show me the module graph around the analyzer",
            project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8,
        ))
    # Isolate the injected DIRECTIVE (a user text block) from the ack recovery,
    # which is JSON inside a tool_result.
    directives = []
    for m in client.calls[-1]["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            for blk in m["content"]:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    directives.append(blk["text"])
    joined = " ".join(directives)
    assert "rebuild the graph_view" in joined, "a visual question must be pushed to rebuild the widget"
    # The non-visual directive SELLS prose ("an honest prose answer is better than
    # no answer"); the visual directive must not — that phrase is the distinguisher.
    assert "better than no answer" not in joined, "a visual question must NOT sell the prose off-ramp"


def test_run_question_pushes_playground_emit_not_prose(tmp_path: Path):
    """For a 'dame un ejemplo ejecutable' question, a rejected widget must NOT be
    told to answer in prose (that earns off_target) — it must be pushed to emit a
    playground widget. (Epic #139, Phase 1 — the run-request twin of the graph
    recovery: a SHOW/RUN request is answered by the artifact, not a description.)"""
    turns = [
        _graph_turn(),
        _bad_widget_turn(),
        [  # a later turn so the loop terminates cleanly
            _tool_stop("l1", "emit_block", {"kind": "lead", "text": "ans"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("l1", "emit_block", {"kind": "lead", "text": "ans"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    client = StubStream(turns)
    with patch(
        "copyclip.intelligence.cuaderno.compositor.dispatch_tool",
        side_effect=lambda name, args, **kw: _GRAPH_RESULT,
    ):
        list(iter_compose_events(
            client=client, question="dame un ejemplo ejecutable de _module_from_relpath",
            project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8,
        ))
    directives = []
    for m in client.calls[-1]["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            for blk in m["content"]:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    directives.append(blk["text"])
    joined = " ".join(directives)
    assert "playground" in joined, "a run request must be pushed to emit a playground widget"
    assert "better than no answer" not in joined, "a run request must NOT sell the prose off-ramp"
    assert "rebuild the graph_view" not in joined, "a run request gets the RUN directive, not the graph one"
