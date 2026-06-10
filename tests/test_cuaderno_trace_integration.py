import json
import sqlite3
from pathlib import Path

import pytest

from copyclip.intelligence.cuaderno.compositor import iter_compose_events, CLOSING_DIRECTIVE
from copyclip.intelligence.cuaderno.trace import InteractionTrace
from copyclip.intelligence.db import init_cuaderno_schema
from copyclip.intelligence.cuaderno.persistence import create_session
from copyclip.intelligence.cuaderno.ask_stream import iter_ask_events


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


def test_tool_run_traced_with_paths_and_content_bearing(tmp_path):
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
    _, lines = _run(tmp_path, turns, max_tool_rounds=8)
    tools = _by_event(lines, "tool.run")
    assert len(tools) == 1
    t = tools[0]
    assert t["name"] == "read_file" and t["error"] is None
    assert t["content_bearing"] is True
    assert "README.md" in t["result_paths"]
    assert isinstance(t["ms"], int) and t["sse"] is True


def test_grounding_retry_traced_with_reason_and_directive(tmp_path):
    # Two finished answers with ZERO reads: the first triggers the one-shot
    # grounding retry (reset), the second seals `ungrounded`.
    answer_turn = lambda bid: [
        _tool_stop(bid, "emit_block", {"kind": "lead", "text": "claim"}),
        _tool_stop(f"f{bid}", "finish", {}),
        _msg_stop("tool_use", [
            _content(bid, "emit_block", {"kind": "lead", "text": "claim"}),
            _content(f"f{bid}", "finish", {}),
        ]),
    ]
    events, lines = _run(tmp_path, [answer_turn("b1"), answer_turn("b2")], max_tool_rounds=3)
    assert any(e["type"] == "reset" for e in events)
    retries = _by_event(lines, "retry")
    assert len(retries) == 1
    r = retries[0]
    assert r["kind"] == "grounding"
    assert r["reason"]                      # the QualityVerdict's reason, verbatim
    assert r["directive"]                   # the injected corrective text
    assert r["discarded_blocks"] == 1
    assert r["sse"] is True                 # this IS the reset the frontend saw
    cheaps = _by_event(lines, "verdict.cheap")
    assert len(cheaps) == 2                 # one per terminal attempt
    assert cheaps[0]["status"] == "ungrounded"


def test_judge_verdict_traced_including_fail_open(tmp_path):
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")

    def failing_judge(q, blocks, ledger):
        from copyclip.intelligence.cuaderno.judge import _ok_verdict
        return _ok_verdict("judge unavailable: boom")

    turns = [
        [
            _tool_stop("r1", "read_file", {"path": "README.md"}),
            _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
        ],
        [
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "ok"}),
            _tool_stop("f", "finish", {}),
            _msg_stop("tool_use", [
                _content("b1", "emit_block", {"kind": "lead", "text": "ok"}),
                _content("f", "finish", {}),
            ]),
        ],
    ]
    _, lines = _run(tmp_path, turns, max_tool_rounds=8, judge=failing_judge)
    judges = _by_event(lines, "verdict.judge")
    assert len(judges) == 1
    j = judges[0]
    assert j["judged"] is False
    assert j["decision"] == "ok"
    assert "judge unavailable" in j["fail_open_error"]
    assert j["verdict"]["source"] == "unjudged"


def test_floor_decline_traced_for_run_request_fallback(tmp_path):
    # A run-request that produces NO blocks seals `fallback`; the floor is
    # attempted but declines (conn=None resolves nothing) — and says so.
    turn = [
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [_content("f", "finish", {})]),
    ]
    _, lines = _run(tmp_path, [turn], question="run foo now", max_tool_rounds=1)
    floors = _by_event(lines, "floor")
    assert len(floors) == 1
    f = floors[0]
    assert f["attempted"] is True and f["reclassified"] is False
    assert f["symbol"] is None and f["decline_reason"]


def test_responsiveness_retry_traced(tmp_path):
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    from copyclip.intelligence.cuaderno.judge import JudgeVerdict

    calls = {"n": 0}

    def retry_then_ok(q, blocks, ledger):
        calls["n"] += 1
        if calls["n"] == 1:
            return JudgeVerdict(question_kind="code_comprehension", grounded=True,
                                responsive=False, language_ok=True, decision="retry",
                                world=None, retry_directive="answer HOW, not WHAT",
                                reason="describes instead of explaining")
        return JudgeVerdict(question_kind="code_comprehension", grounded=True,
                            responsive=True, language_ok=True, decision="ok",
                            world=None, retry_directive=None, reason="fine")

    read_turn = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    answer_turn = lambda bid: [
        _tool_stop(bid, "emit_block", {"kind": "lead", "text": "x"}),
        _tool_stop(f"f{bid}", "finish", {}),
        _msg_stop("tool_use", [
            _content(bid, "emit_block", {"kind": "lead", "text": "x"}),
            _content(f"f{bid}", "finish", {}),
        ]),
    ]
    _, lines = _run(tmp_path, [read_turn, answer_turn("b1"), answer_turn("b2")],
                    max_tool_rounds=8, judge=retry_then_ok)
    retries = [l for l in lines if l["event"] == "retry"]
    assert len(retries) == 1
    r = retries[0]
    assert r["kind"] == "responsiveness"
    assert r["directive"] == "answer HOW, not WHAT"
    assert r["discarded_blocks"] == 1 and r["sse"] is True
    judges = [l for l in lines if l["event"] == "verdict.judge"]
    assert len(judges) == 2 and judges[0]["decision"] == "retry" and judges[1]["decision"] == "ok"


def test_budget_exhausted_tail_traces_single_cheap_verdict(tmp_path):
    # Rounds never reach an explicit terminal: every round keeps stop_reason
    # "tool_use" without finish. The budget tail seals via _sealed_frame, which
    # must trace exactly ONE verdict.cheap (no double-fire with the loop's).
    keep_going = lambda bid: [
        _tool_stop(bid, "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("tool_use", [_content(bid, "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    _, lines = _run(tmp_path, [keep_going("b1"), keep_going("b2")], max_tool_rounds=2)
    cheaps = [l for l in lines if l["event"] == "verdict.cheap"]
    assert len(cheaps) == 1


def test_wire_events_only_under_flag(tmp_path, monkeypatch):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("end_turn", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    # without the flag: no wire events
    monkeypatch.delenv("COPYCLIP_TRACE_WIRE", raising=False)
    _, lines = _run(tmp_path / "off", [list(turn)])
    assert not _by_event(lines, "wire.request") and not _by_event(lines, "wire.response")
    # with the flag: full request + response per round. max_tool_rounds=2 so
    # round 0 is NOT the closing round and no directive is injected.
    monkeypatch.setenv("COPYCLIP_TRACE_WIRE", "1")
    _, lines = _run(tmp_path / "on", [list(turn)], max_tool_rounds=2)
    reqs = _by_event(lines, "wire.request")
    resps = _by_event(lines, "wire.response")
    assert len(reqs) == 1 and len(resps) == 1
    assert reqs[0]["model"] and reqs[0]["system"]
    assert reqs[0]["messages"][0] == {"role": "user", "content": "q"}
    assert isinstance(reqs[0]["tools"], list) and "emit_block" in reqs[0]["tools"]
    assert resps[0]["stop_reason"] == "end_turn"
    assert resps[0]["content"][0]["name"] == "emit_block"


def test_wire_request_captures_messages_as_sent_to_the_llm(tmp_path, monkeypatch):
    # On the CLOSING round the system injects CLOSING_DIRECTIVE into the
    # trailing user turn before calling the LLM. The wire capture must show
    # the request AS SENT — directive included — or the trace lies.
    monkeypatch.setenv("COPYCLIP_TRACE_WIRE", "1")
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("end_turn", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    _, lines = _run(tmp_path, [turn], max_tool_rounds=1)  # round 0 IS closing
    req = _by_event(lines, "wire.request")[0]
    serialized = json.dumps(req["messages"], ensure_ascii=False)
    assert CLOSING_DIRECTIVE in serialized  # the closing directive, as sent
    # tools were clamped to the answer set for the closing round
    assert set(req["tools"]) == {"emit_block", "finish"}


def _conn():
    c = sqlite3.connect(":memory:")
    init_cuaderno_schema(c)
    return c


def _ask_trace_lines(tmp_path):
    files = sorted((tmp_path / ".copyclip" / "logs" / "cuaderno").glob("ask_*.jsonl"))
    assert files, "no trace file written"
    return [json.loads(l) for l in files[-1].read_text(encoding="utf-8").splitlines()]


def test_ask_stream_writes_full_trace_lifecycle(tmp_path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    turns = [
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
    events = list(iter_ask_events(
        client=StubStream(turns), question="q", project_root=str(tmp_path),
        project_id=1, conn=conn, session_id=sid,
        provider="anthropic", judge_model="judge-m",
    ))
    assert events[0]["type"] == "meta"
    lines = _ask_trace_lines(tmp_path)
    names = [l["event"] for l in lines]
    assert names[0] == "ask.start" and names[-1] == "ask.end"
    start = lines[0]
    assert start["question"] == "q" and start["session_id"] == sid
    assert start["provider"] == "anthropic" and start["judge_model"] == "judge-m"
    assert start["model"] and start["max_tool_rounds"] == 8
    seal = next(l for l in lines if l["event"] == "seal")
    assert seal["status"] == "answer" and seal["position"] == 1
    assert seal["blocks"] == 1 and seal["sse"] is True and seal["verdict"]
    persist = next(l for l in lines if l["event"] == "persist")
    assert persist["outcome"] == "ok" and persist["error"] is None
    assert lines[-1]["outcome"] == "answer"


def test_ask_stream_traces_partial_persist_on_stream_error(tmp_path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    turns = [
        [   # round 0 continues; round 1 raises (StubStream exhausted)
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
            _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
        ],
    ]
    events = list(iter_ask_events(
        client=StubStream(turns), question="q", project_root=str(tmp_path),
        project_id=1, conn=conn, session_id=sid,
    ))
    assert events[-1]["type"] == "error"
    lines = _ask_trace_lines(tmp_path)
    names = [l["event"] for l in lines]
    assert "error" in names                          # traced by the compositor
    persist = next(l for l in lines if l["event"] == "persist")
    assert persist["outcome"] == "partial"
    assert lines[-1]["event"] == "ask.end" and lines[-1]["outcome"] == "error"


def test_ask_stream_disconnect_traces_footer(tmp_path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    turns = [
        [   # non-terminal round: generator stays suspended after the block yield
            _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
            _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
        ],
    ]
    gen = iter_ask_events(
        client=StubStream(turns), question="q", project_root=str(tmp_path),
        project_id=1, conn=conn, session_id=sid,
    )
    assert next(gen)["type"] == "meta"
    assert next(gen)["type"] == "block"
    gen.close()  # client disconnect (GeneratorExit at the suspended yield)
    lines = _ask_trace_lines(tmp_path)
    assert lines[-1]["event"] == "ask.end" and lines[-1]["outcome"] == "disconnect"
    persist = next(l for l in lines if l["event"] == "persist")
    assert persist["outcome"] == "partial" and persist["error"] == "client disconnect"


def test_ask_stream_crash_traces_honest_outcome(tmp_path):
    conn = _conn()
    sid = create_session(conn, project_root=str(tmp_path))
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")

    def exploding_judge(q, blocks, ledger):
        raise RuntimeError("judge exploded")

    turns = [
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
    with pytest.raises(RuntimeError, match="judge exploded"):
        list(iter_ask_events(
            client=StubStream(turns), question="q", project_root=str(tmp_path),
            project_id=1, conn=conn, session_id=sid, judge=exploding_judge,
        ))
    lines = _ask_trace_lines(tmp_path)
    assert lines[-1]["event"] == "ask.end" and lines[-1]["outcome"] == "crash"
    persist = next(l for l in lines if l["event"] == "persist")
    assert persist["outcome"] == "partial" and "judge exploded" in persist["error"]
