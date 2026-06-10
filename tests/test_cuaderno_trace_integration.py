import json
from pathlib import Path

from copyclip.intelligence.cuaderno.compositor import iter_compose_events
from copyclip.intelligence.cuaderno.trace import InteractionTrace


class StubStream:
    def __init__(self, turns):
        self._turns = list(turns)

    def messages_stream(self, **kwargs):
        if not self._turns:
            raise RuntimeError("StubStream ran out of scripted turns")
        for ev in self._turns.pop(0):
            yield ev


def _tool_stop(bid, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": bid, "name": name, "input": inp}}


def _content(bid, name, inp):
    return {"type": "tool_use", "id": bid, "name": name, "input": inp}


def _msg_stop(reason, content):
    return {"type": "message_stop", "stop_reason": reason, "content": content}


def _run(tmp_path, turns, question="q", max_tool_rounds=1, conn=None, judge=None):
    trace = InteractionTrace.start("ask", tmp_path / "logs", {"question": question})
    events = list(iter_compose_events(
        client=StubStream(turns), question=question, project_root=str(tmp_path),
        project_id=1, conn=conn, max_tool_rounds=max_tool_rounds, judge=judge,
        trace=trace,
    ))
    trace.close()
    lines = [json.loads(l) for l in trace.path.read_text(encoding="utf-8").splitlines()]
    return events, lines


def _by_event(lines, name):
    return [l for l in lines if l["event"] == name]


def test_block_accept_and_reject_traced_with_reason(tmp_path):
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
    _, lines = _run(tmp_path, [turn])
    acc = _by_event(lines, "block.accept")
    rej = _by_event(lines, "block.reject")
    assert len(acc) == 1 and acc[0]["block"]["kind"] == "lead" and acc[0]["sse"] is True
    assert len(rej) == 1 and rej[0]["block"]["kind"] == "bogus"
    assert rej[0]["reason"]          # the gate's reason string, verbatim
    assert rej[0]["recovery"]        # the recovery text sent back to the model


def test_llm_round_traced_with_ms_and_stop_reason(tmp_path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("end_turn", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    _, lines = _run(tmp_path, [turn])
    rounds = _by_event(lines, "llm.round")
    assert len(rounds) == 1
    r = rounds[0]
    assert r["round_i"] == 0 and r["closing"] is True   # max_tool_rounds=1: round 0 IS closing
    assert r["stop_reason"] == "end_turn"
    assert isinstance(r["ms"], int) and r["ms"] >= 0
    assert r["usage"] is None  # adapters don't report usage today; field stays honest


def test_recovery_directive_traced_when_all_blocks_rejected(tmp_path):
    turns = [
        [   # round 0: only a rejected block -> widget-fixation backstop fires
            _tool_stop("b1", "emit_block", {"kind": "bogus", "text": "bad"}),
            _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "bogus", "text": "bad"})]),
        ],
        [   # round 1: a clean close
            _tool_stop("b2", "emit_block", {"kind": "lead", "text": "ok"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b2", "emit_block", {"kind": "lead", "text": "ok"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    _, lines = _run(tmp_path, turns, max_tool_rounds=3)
    recs = _by_event(lines, "recovery.directive")
    assert len(recs) == 1 and recs[0]["variant"] == "generic"


def test_stream_failure_traces_error_event(tmp_path):
    turns = [
        [   # round 0 continues (tool_use, no finish) so round 1 is attempted...
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
            _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
        ],
        # ...and StubStream raises (no turns left) -> compositor error terminal
    ]
    events, lines = _run(tmp_path, turns, max_tool_rounds=3)
    assert events[-1]["type"] == "error"
    errs = _by_event(lines, "error")
    assert len(errs) == 1
    assert "stream failed" in errs[0]["message"] and errs[0]["partial"] is True
    assert errs[0]["sse"] is True
