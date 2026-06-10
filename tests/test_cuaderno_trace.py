import json
from pathlib import Path

from copyclip.intelligence.cuaderno.trace import (
    InteractionTrace, NullTrace, NULL_TRACE, trace_logs_dir,
)


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_writes_header_events_and_footer_as_jsonl(tmp_path):
    t = InteractionTrace.start("ask", tmp_path, {"question": "q", "session_id": "s" * 32},
                               tag="deadbeef")
    t.event("block.accept", block={"kind": "lead"}, sse=True)
    t.close(outcome="answer")
    files = list(tmp_path.glob("ask_*.jsonl"))
    assert len(files) == 1
    assert "_deadbeef" in files[0].name
    lines = _read_lines(files[0])
    assert [l["event"] for l in lines] == ["ask.start", "block.accept", "ask.end"]
    assert lines[0]["question"] == "q"
    assert lines[0]["wire"] is False
    assert lines[1]["block"] == {"kind": "lead"} and lines[1]["sse"] is True
    assert lines[2]["outcome"] == "answer"


def test_seq_and_t_ms_are_monotonic(tmp_path):
    t = InteractionTrace.start("ask", tmp_path, {})
    for i in range(5):
        t.event("x", i=i)
    t.close()
    lines = _read_lines(next(tmp_path.glob("*.jsonl")))
    seqs = [l["seq"] for l in lines]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    ts = [l["t_ms"] for l in lines]
    assert ts == sorted(ts)


def test_self_disables_on_write_failure_without_raising(tmp_path):
    t = InteractionTrace.start("ask", tmp_path, {})
    t._fh.close()  # sabotage: the next write raises ValueError internally
    t.event("x")   # must not raise
    assert t.enabled is False
    t.event("y")   # still must not raise
    t.close()      # idempotent, must not raise


def test_start_failure_returns_disabled_instance(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a dir", encoding="utf-8")
    t = InteractionTrace.start("ask", blocker / "sub", {})  # mkdir fails: parent is a file
    assert t.enabled is False
    t.event("x")   # no-op, must not raise
    t.close()


def test_unserializable_payload_does_not_disable(tmp_path):
    t = InteractionTrace.start("ask", tmp_path, {})
    t.event("x", obj=object())   # default=str stringifies it
    assert t.enabled is True
    t.close()
    lines = _read_lines(next(tmp_path.glob("*.jsonl")))
    assert isinstance(lines[1]["obj"], str)


def test_null_trace_is_pure_noop():
    NULL_TRACE.event("x", a=1)
    NULL_TRACE.close()
    assert NULL_TRACE.wire is False
    assert isinstance(NULL_TRACE, NullTrace)


def test_wire_flag_read_from_env_at_start(tmp_path, monkeypatch):
    monkeypatch.setenv("COPYCLIP_TRACE_WIRE", "1")
    t = InteractionTrace.start("ask", tmp_path, {})
    assert t.wire is True
    t.close()
    monkeypatch.setenv("COPYCLIP_TRACE_WIRE", "0")
    t2 = InteractionTrace.start("ask", tmp_path, {})
    assert t2.wire is False
    t2.close()


def test_trace_logs_dir_layout(tmp_path):
    d = trace_logs_dir(str(tmp_path))
    assert d == tmp_path / ".copyclip" / "logs" / "cuaderno"


def test_event_payload_may_contain_name_and_event_keys(tmp_path):
    t = InteractionTrace.start("ask", tmp_path, {})
    t.event("tool.run", name="read_file", event="weird", seq=999)  # must not raise
    assert t.enabled is True
    t.close()
    lines = _read_lines(next(tmp_path.glob("*.jsonl")))
    row = lines[1]
    assert row["event"] == "tool.run"   # fixed field wins
    assert row["seq"] == 1              # fixed field wins
    assert row["name"] == "read_file"   # payload key preserved


def test_disable_survives_broken_stderr(tmp_path, monkeypatch):
    import io
    t = InteractionTrace.start("ask", tmp_path, {})
    t._fh.close()  # next write fails -> _disable -> WARN print
    broken = io.StringIO()
    broken.close()
    monkeypatch.setattr("sys.stderr", broken)
    t.event("x")   # must not raise even though stderr is closed
    assert t.enabled is False
