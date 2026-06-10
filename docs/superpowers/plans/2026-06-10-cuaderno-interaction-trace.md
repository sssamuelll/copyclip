# Cuaderno Interaction Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every cuaderno ask and every playground launch writes one append-only JSONL debug timeline to `.copyclip/logs/cuaderno/`, so debug sessions read a file instead of screenshots.

**Architecture:** A new artifact-writer module `cuaderno/trace.py` (`InteractionTrace` / `NullTrace`) is threaded as an optional parameter into the existing pipeline (`ask_stream` → `compositor`, and launch handler → `launch_playground` → `MarimoRunner`). Hooks are one-line `trace.event(...)` calls at decision points that already exist. Full LLM wire capture activates only under `COPYCLIP_TRACE_WIRE=1`. The tracer swallows every failure and self-disables — it can never break the ask path.

**Tech Stack:** Python 3 stdlib only (json, pathlib, time, datetime). Tests with pytest. Spec: `docs/superpowers/specs/2026-06-10-cuaderno-interaction-trace-design.md`.

**Conventions:** Run tests from the repo root: `python -m pytest tests/<file> -q`. All new files use the existing cuaderno style (`from __future__ import annotations`, no logging module). Commit messages follow `feat(cuaderno): ...` / `test(cuaderno): ...` as in `git log`.

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `src/copyclip/intelligence/cuaderno/trace.py` | Create | InteractionTrace/NullTrace, file naming, retention, wire flag. Owns ALL file I/O for traces. |
| `src/copyclip/intelligence/cuaderno/compositor.py` | Modify | `trace` param + hooks: block accept/reject, llm.round, recovery.directive, tool.run, verdict.cheap, retry, verdict.judge, floor, wire events. |
| `src/copyclip/intelligence/cuaderno/judge.py` | Modify | `JudgeVerdict.raw` field (raw judge text for wire-level debugging). |
| `src/copyclip/intelligence/cuaderno/ask_stream.py` | Modify | Trace lifecycle owner for asks: creates, seals, persists, closes. New `provider`/`judge_model` params for the header. |
| `src/copyclip/intelligence/playground.py` | Modify | `launch_playground(trace=...)`: resolve/notebook/spawn/ready/error events. Protocol gains `trace` kwarg. |
| `src/copyclip/intelligence/marimo_runner.py` | Modify | `launch(..., trace=None)` emits `launch.spawn` (cmd, port, pid, mode). |
| `src/copyclip/intelligence/server.py` | Modify | Ask route passes provider/judge_model; launch route creates the launch trace. |
| `tests/test_cuaderno_trace.py` | Create | Unit tests for trace.py. |
| `tests/test_cuaderno_trace_integration.py` | Create | Compositor + ask_stream hooks, asserted against the written file. |
| `tests/test_playground_trace.py` | Create | Launch trace events with a fake runner. |
| `tests/test_cuaderno_judge.py` | Modify | `raw` capture tests. |

Dependency note: `cuaderno/trace.py` imports ONLY stdlib. `playground.py` and `marimo_runner.py` may import `from .cuaderno.trace import NULL_TRACE` safely — `cuaderno/__init__.py` is a docstring, no import cycle.

---

### Task 1: `trace.py` core — write path, self-disable, NullTrace, wire flag

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/trace.py`
- Test: `tests/test_cuaderno_trace.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cuaderno_trace.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_trace.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'copyclip.intelligence.cuaderno.trace'`

- [ ] **Step 3: Write the implementation**

Create `src/copyclip/intelligence/cuaderno/trace.py`:

```python
"""Interaction trace: one append-only JSONL timeline per cuaderno ask / playground launch.

Spec: docs/superpowers/specs/2026-06-10-cuaderno-interaction-trace-design.md

This is an artifact writer, not a logger: the file IS the debugging record of one
interaction, written incrementally (append + flush per event) so a crash leaves a
readable prefix. Golden rule: tracing can NEVER break the ask path — every public
method swallows its own failures, and the tracer self-disables after the first one.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

MAX_TRACE_FILES = 200
WIRE_ENV_VAR = "COPYCLIP_TRACE_WIRE"


def trace_logs_dir(project_root: str) -> Path:
    return Path(project_root) / ".copyclip" / "logs" / "cuaderno"


class NullTrace:
    """No-op stand-in exposing the full InteractionTrace surface."""

    wire = False
    enabled = False
    path: Optional[Path] = None

    def event(self, name: str, **payload: Any) -> None:
        return None

    def close(self, **payload: Any) -> None:
        return None


NULL_TRACE = NullTrace()


class InteractionTrace:
    """Append-only JSONL trace for one interaction. Construct via `start()`."""

    def __init__(self) -> None:
        self.wire = False
        self.enabled = False
        self.path: Optional[Path] = None
        self._fh = None
        self._seq = 0
        self._t0 = time.perf_counter()
        self._kind = "ask"

    @classmethod
    def start(
        cls,
        kind: str,
        logs_dir: Union[str, Path],
        header: Optional[dict] = None,
        tag: Optional[str] = None,
    ) -> "InteractionTrace":
        """Open `<kind>_<UTCstamp>_<tag>.jsonl` and write the `<kind>.start` header
        event. On ANY failure returns a disabled instance (one stderr WARN, no raise)."""
        t = cls()
        t._kind = kind
        t.wire = os.environ.get(WIRE_ENV_VAR, "") not in ("", "0")
        try:
            d = Path(logs_dir)
            d.mkdir(parents=True, exist_ok=True)
            _prune(d)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_tag = tag or uuid.uuid4().hex[:8]
            path = d / f"{kind}_{stamp}_{safe_tag}.jsonl"
            i = 2
            while path.exists():
                path = d / f"{kind}_{stamp}_{safe_tag}-{i}.jsonl"
                i += 1
            t._fh = path.open("x", encoding="utf-8")
            t.path = path
            t.enabled = True
            t.event(f"{kind}.start", **{**(header or {}), "wire": t.wire})
        except Exception as exc:  # noqa: BLE001 — golden rule: never break the pipeline
            t._disable(f"trace start failed: {exc!r}")
        return t

    def event(self, name: str, **payload: Any) -> None:
        if not self.enabled or self._fh is None:
            return
        try:
            line = json.dumps(
                {"seq": self._seq,
                 "t_ms": int((time.perf_counter() - self._t0) * 1000),
                 "event": name,
                 **payload},
                ensure_ascii=False, default=str,
            )
            self._fh.write(line + "\n")
            self._fh.flush()
            self._seq += 1
        except Exception as exc:  # noqa: BLE001 — golden rule
            self._disable(f"trace write failed: {exc!r}")

    def close(self, **payload: Any) -> None:
        if self._fh is None:
            return
        self.event(f"{self._kind}.end", **payload)
        try:
            self._fh.close()
        except Exception:
            pass
        self._fh = None
        self.enabled = False

    def _disable(self, why: str) -> None:
        self.enabled = False
        fh, self._fh = self._fh, None
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
        print(f"WARN trace disabled: {why}", file=sys.stderr)


def _prune(d: Path) -> None:
    """Keep the directory under MAX_TRACE_FILES, oldest-first by name (the UTC
    timestamp prefix makes lexicographic == chronological). Called before each
    new file is created, so we prune to MAX-1 and the new file lands at MAX."""
    files = sorted(p for p in d.glob("*.jsonl") if p.is_file())
    excess = len(files) - (MAX_TRACE_FILES - 1)
    for p in files[: max(0, excess)]:
        try:
            p.unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_trace.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/trace.py tests/test_cuaderno_trace.py
git commit -m "feat(cuaderno): InteractionTrace — JSONL artifact writer that can never break the ask path"
```

---

### Task 2: `trace.py` retention pruning + same-second collision suffix

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/trace.py` (already implemented in Task 1 — this task LOCKS the behavior with tests)
- Test: `tests/test_cuaderno_trace.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cuaderno_trace.py`:

```python
def test_retention_prunes_oldest_beyond_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("copyclip.intelligence.cuaderno.trace.MAX_TRACE_FILES", 5)
    for i in range(7):
        (tmp_path / f"ask_20260101T00000{i}Z_aaaa.jsonl").write_text("{}", encoding="utf-8")
    t = InteractionTrace.start("ask", tmp_path, {})
    t.close()
    files = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert len(files) == 5
    survivors = {f"ask_20260101T00000{i}Z_aaaa.jsonl" for i in (3, 4, 5, 6)}
    assert survivors.issubset(set(files))  # the 3 oldest were pruned, newest 4 + new file remain


def test_same_second_same_tag_does_not_clobber(tmp_path):
    # If both starts land in the same UTC second the second file gets a `-2`
    # suffix; if the clock ticks they differ anyway. Either way: two files.
    t1 = InteractionTrace.start("ask", tmp_path, {}, tag="aaaa")
    t2 = InteractionTrace.start("ask", tmp_path, {}, tag="aaaa")
    t1.close()
    t2.close()
    assert len(list(tmp_path.glob("ask_*.jsonl"))) == 2
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_cuaderno_trace.py -q`
Expected: 10 passed (Task 1's implementation already covers both — if either FAILS, fix `_prune` / the collision loop in `start` until green; the behavior contract is the test).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cuaderno_trace.py
git commit -m "test(cuaderno): lock trace retention and same-second collision behavior"
```

---

### Task 3: Compositor hooks — `trace` param, block accept/reject, llm.round, recovery.directive, stream error

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`
- Test: `tests/test_cuaderno_trace_integration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cuaderno_trace_integration.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py -q`
Expected: FAIL — `iter_compose_events() got an unexpected keyword argument 'trace'`

- [ ] **Step 3: Implement the compositor hooks**

In `src/copyclip/intelligence/cuaderno/compositor.py`:

3a. Add imports (top of file, with the other `.`-relative imports):

```python
from .read_ledger import ReadLedger, is_content_bearing_read
from .trace import NULL_TRACE
```

(`ReadLedger` is already imported — extend that line with `is_content_bearing_read`.)

Also add to the stdlib imports: `from dataclasses import asdict`.

3b. Extend the `iter_compose_events` signature (after `ledger`):

```python
    ledger: Optional[ReadLedger] = None,
    trace: Any = None,
) -> Iterator[dict[str, Any]]:
```

and at the top of the body (next to `ledger = ledger if ...`):

```python
    trace = trace if trace is not None else NULL_TRACE
```

3c. In the round loop, time the call and capture usage. Replace:

```python
        turn_content: list[dict[str, Any]] = []
        stop_reason: Optional[str] = None
        finish_seen = False
        emit_status: dict[str, Optional[str]] = {}  # tool_use_id -> reason (None = ok)

        try:
```

with:

```python
        turn_content: list[dict[str, Any]] = []
        stop_reason: Optional[str] = None
        usage: Any = None
        finish_seen = False
        emit_status: dict[str, Optional[str]] = {}  # tool_use_id -> reason (None = ok)

        round_t0 = time.perf_counter()
        try:
```

3d. Hook block accept/reject. Replace:

```python
                        emit_status[blk["id"]] = reason
                        if reason is None:
                            b = Block.from_dict(inp)
                            emitted.append(b)
                            yield {"type": "block", "block": b.to_dict()}
```

with:

```python
                        emit_status[blk["id"]] = reason
                        if reason is None:
                            b = Block.from_dict(inp)
                            emitted.append(b)
                            trace.event("block.accept", block=b.to_dict(), sse=True)
                            yield {"type": "block", "block": b.to_dict()}
                        else:
                            trace.event("block.reject", block=inp, reason=reason,
                                        recovery=INVALID_BLOCK_RECOVERY)
```

3e. Capture usage in the `message_stop` branch. Replace:

```python
                elif sev.get("type") == "message_stop":
                    stop_reason = sev.get("stop_reason")
                    turn_content = sev.get("content", []) or []
```

with:

```python
                elif sev.get("type") == "message_stop":
                    stop_reason = sev.get("stop_reason")
                    usage = sev.get("usage")
                    turn_content = sev.get("content", []) or []
```

3f. Trace the stream-failure terminal. Replace:

```python
        except Exception as exc:  # noqa: BLE001 — surface LLM/stream failure as a terminal error
            yield {
                "type": "error",
                "message": f"stream failed ({exc})",
                "partial": len(emitted) > 0,
            }
            return
```

with:

```python
        except Exception as exc:  # noqa: BLE001 — surface LLM/stream failure as a terminal error
            trace.event("error", message=f"stream failed ({exc})",
                        partial=len(emitted) > 0, sse=True)
            yield {
                "type": "error",
                "message": f"stream failed ({exc})",
                "partial": len(emitted) > 0,
            }
            return
```

3g. Trace the round, right after the except block. Replace:

```python
        messages.append({"role": "assistant", "content": turn_content})
```

with:

```python
        trace.event("llm.round", round_i=round_i, closing=is_closing,
                    ms=int((time.perf_counter() - round_t0) * 1000),
                    stop_reason=stop_reason, usage=usage)
        messages.append({"role": "assistant", "content": turn_content})
```

3h. Hook the widget-fixation backstop. Replace:

```python
        if (not is_closing and emit_status
                and all(reason is not None for reason in emit_status.values())):
            if _is_visual_request(question):
                directive = WIDGET_RECOVERY_DIRECTIVE_VISUAL
            elif _is_run_request(question):
                directive = WIDGET_RECOVERY_DIRECTIVE_RUN
            else:
                directive = WIDGET_RECOVERY_DIRECTIVE
            _inject_directive(messages, directive)
```

with:

```python
        if (not is_closing and emit_status
                and all(reason is not None for reason in emit_status.values())):
            if _is_visual_request(question):
                directive, variant = WIDGET_RECOVERY_DIRECTIVE_VISUAL, "visual"
            elif _is_run_request(question):
                directive, variant = WIDGET_RECOVERY_DIRECTIVE_RUN, "run"
            else:
                directive, variant = WIDGET_RECOVERY_DIRECTIVE, "generic"
            trace.event("recovery.directive", variant=variant)
            _inject_directive(messages, directive)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py tests/test_cuaderno_compositor.py -q`
Expected: all pass (the existing compositor suite proves `trace=None` is transparent)

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_trace_integration.py
git commit -m "feat(cuaderno): trace block accept/reject, llm rounds and recovery directives in the compositor"
```

---

### Task 4: Compositor hooks — tool.run, verdict.cheap, retry (with reason), verdict.judge, floor

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`
- Test: `tests/test_cuaderno_trace_integration.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cuaderno_trace_integration.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py -q`
Expected: the 4 new tests FAIL (no `tool.run` / `retry` / `verdict.judge` / `floor` events in the file)

- [ ] **Step 3: Implement the hooks**

In `src/copyclip/intelligence/cuaderno/compositor.py`:

3a. Helper for the judge event (place after `_judge_status`):

```python
def _trace_judge(trace, jv) -> None:
    payload: dict[str, Any] = {
        "verdict": judge_verdict_dict(jv),
        "decision": jv.decision,
        "judged": jv.judged,
        "fail_open_error": None if jv.judged else jv.reason,
    }
    if trace.wire:
        payload["raw"] = getattr(jv, "raw", None)
    trace.event("verdict.judge", **payload)
```

3b. Cheap verdict at the terminal. Replace:

```python
            if emitted:
                verdict = assess(question=question, blocks=emitted, ledger=ledger)
```

with:

```python
            if emitted:
                verdict = assess(question=question, blocks=emitted, ledger=ledger)
                trace.event("verdict.cheap", **asdict(verdict))
```

3c. Grounding/language retry. Replace:

```python
                    grounding_retry_used = True
                    emitted.clear()
                    # Answer the terminal turn's tool_use blocks before re-calling
                    # the model — a dangling tool_call 400s on real APIs.
                    acks = _ack_terminal_tools(turn_content, emit_status)
                    if acks:
                        messages.append({"role": "user", "content": acks})
                    _inject_directive(messages, _retry_directive(verdict))
                    yield {"type": "reset"}
                    continue
```

with:

```python
                    grounding_retry_used = True
                    discarded = len(emitted)
                    emitted.clear()
                    # Answer the terminal turn's tool_use blocks before re-calling
                    # the model — a dangling tool_call 400s on real APIs.
                    acks = _ack_terminal_tools(turn_content, emit_status)
                    if acks:
                        messages.append({"role": "user", "content": acks})
                    directive = _retry_directive(verdict)
                    _inject_directive(messages, directive)
                    trace.event(
                        "retry",
                        kind=("grounding" if verdict.status != FRAME_STATUS_ANSWER
                              else "language"),
                        reason=verdict.reason, directive=directive,
                        discarded_blocks=discarded, sse=True)
                    yield {"type": "reset"}
                    continue
```

3d. Judge call + responsiveness retry. Replace:

```python
                if judge is not None:
                    jv = judge(question, emitted, ledger)
                    if (jv.decision == "retry" and not responsiveness_retry_used
                            and can_retry):
                        responsiveness_retry_used = True
                        emitted.clear()
                        acks = _ack_terminal_tools(turn_content, emit_status)
                        if acks:
                            messages.append({"role": "user", "content": acks})
                        _inject_directive(
                            messages, jv.retry_directive or RESPONSIVENESS_RETRY_FALLBACK)
                        yield {"type": "reset"}
                        continue
                    yield {"type": "frame",
                           "frame": _floored_frame(
                               _seal(question, emitted, _judge_status(jv),
                                     judge_verdict_dict(jv)),
                               question, conn, project_id, ledger)}
                    return
```

with:

```python
                if judge is not None:
                    jv = judge(question, emitted, ledger)
                    _trace_judge(trace, jv)
                    if (jv.decision == "retry" and not responsiveness_retry_used
                            and can_retry):
                        responsiveness_retry_used = True
                        discarded = len(emitted)
                        emitted.clear()
                        acks = _ack_terminal_tools(turn_content, emit_status)
                        if acks:
                            messages.append({"role": "user", "content": acks})
                        directive = jv.retry_directive or RESPONSIVENESS_RETRY_FALLBACK
                        _inject_directive(messages, directive)
                        trace.event("retry", kind="responsiveness", reason=jv.reason,
                                    directive=directive, discarded_blocks=discarded,
                                    sse=True)
                        yield {"type": "reset"}
                        continue
                    yield {"type": "frame",
                           "frame": _floored_frame(
                               _seal(question, emitted, _judge_status(jv),
                                     judge_verdict_dict(jv)),
                               question, conn, project_id, ledger, trace=trace)}
                    return
```

3e. Tool dispatch. Replace the dispatch try/except (from `t0 = time.perf_counter()` through the `except` block's final `yield`):

```python
            t0 = time.perf_counter()
            try:
                result = dispatch_tool(
                    name, args, project_root=project_root,
                    project_id=project_id, conn=conn,
                )
                paths_before = set(ledger.read_paths) | set(ledger.evidence_paths)
                ledger.record(name, result)
                new_paths = sorted(
                    (set(ledger.read_paths) | set(ledger.evidence_paths)) - paths_before)
                if name == "get_module_graph":
                    evidence.add_module_graph(result)
                elif name == "get_callers":
                    evidence.add_callers(args.get("symbol", ""), result)
                elif name == "get_callees":
                    evidence.add_callees(args.get("symbol", ""), result)
                ms = int((time.perf_counter() - t0) * 1000)
                tool_results.append(_ack(tuid, result))
                trace.event("tool.run", id=tuid, name=name, args=args_str, ms=ms,
                            error=None,
                            content_bearing=is_content_bearing_read(name, result),
                            result_paths=new_paths, sse=True)
                yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                       "state": "done", "ms": ms}
            except Exception as exc:  # noqa: BLE001 — surface tool failures to the LLM and the UI
                ms = int((time.perf_counter() - t0) * 1000)
                tool_results.append(
                    _ack(tuid, {"error": "tool_failed", "detail": str(exc)}, is_error=True))
                trace.event("tool.run", id=tuid, name=name, args=args_str, ms=ms,
                            error=str(exc), content_bearing=False, result_paths=[],
                            sse=True)
                yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                       "state": "error", "ms": ms}
```

(The only changes vs. the current code: the `paths_before`/`new_paths` delta capture and the two `trace.event("tool.run", ...)` calls.)

3f. Floor events. Change `_floored_frame`'s signature and body:

```python
def _floored_frame(frame_dict: dict[str, Any], question: str,
                   conn: Optional[sqlite3.Connection], project_id: Optional[int],
                   ledger: Optional[ReadLedger], trace: Any = NULL_TRACE) -> dict[str, Any]:
```

(docstring unchanged) and replace the body after the two early returns:

```python
    blocks = [Block.from_dict(b) for b in frame_dict.get("blocks", [])]
    if _has_playground(blocks):
        # The model already delivered the runnable artifact: a run-request answered
        # WITH a playground is responsive by definition. An off_target label here is
        # the judge mislabeling form as relevance — reclassify, don't relabel.
        trace.event("floor", attempted=True, reclassified=True, symbol=None,
                    decline_reason=None)
        return _seal(question, blocks, FRAME_STATUS_ANSWER, _floor_verdict_dict(status))
    # fallback's only block is a system 'couldn't finish' message — drop it.
    base: list[Block] = [] if status == FRAME_STATUS_FALLBACK else blocks
    floor = _construct_playground_floor(question, conn, project_id, ledger, base)
    if floor is None:
        trace.event("floor", attempted=True, reclassified=False, symbol=None,
                    decline_reason="no symbol resolved against the symbols table")
        return frame_dict
    trace.event("floor", attempted=True, reclassified=False,
                symbol=floor.to_dict()["widget"]["function_ref"], decline_reason=None)
    base.append(floor)
    return _seal(question, base, FRAME_STATUS_ANSWER, _floor_verdict_dict(status))
```

3g. `_sealed_frame` gains trace and traces its verdicts:

```python
def _sealed_frame(question: str, emitted: list[Block], ledger: ReadLedger, judge=None,
                  trace: Any = NULL_TRACE) -> dict[str, Any]:
    """Seal a terminal that cannot retry (the budget-exhausted tail). A
    would-be-`answer` is still judged here (Option A — no `answer` escapes the
    judge); a judge `retry` cannot retry (the loop is over) so it seals
    `off_target`."""
    verdict = assess(question=question, blocks=emitted, ledger=ledger)
    trace.event("verdict.cheap", **asdict(verdict))
    if verdict.status != FRAME_STATUS_ANSWER:
        return _seal(question, emitted, verdict.status, cheap_verdict_dict(verdict))
    if judge is not None:
        jv = judge(question, emitted, ledger)
        _trace_judge(trace, jv)
        return _seal(question, emitted, _judge_status(jv), judge_verdict_dict(jv))
    return _seal(question, emitted, FRAME_STATUS_ANSWER, cheap_verdict_dict(verdict))
```

3h. Pass `trace` at the remaining `_floored_frame` / `_sealed_frame` call sites (no-blocks fallback at the terminal, and both budget-exhausted seals):

```python
                yield {"type": "frame",
                       "frame": _floored_frame(
                           frame_to_dict(
                               _fallback_frame(question, "the model produced no answer blocks")),
                           question, conn, project_id, ledger, trace=trace)}
```

```python
    if emitted:
        yield {"type": "frame",
               "frame": _floored_frame(
                   _sealed_frame(question, emitted, ledger, judge=judge, trace=trace),
                   question, conn, project_id, ledger, trace=trace)}
    else:
        yield {"type": "frame",
               "frame": _floored_frame(
                   frame_to_dict(_fallback_frame(question, "tool-call budget exhausted")),
                   question, conn, project_id, ledger, trace=trace)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py tests/test_cuaderno_compositor.py tests/test_cuaderno_playground_floor.py tests/test_cuaderno_retry_recovery.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_trace_integration.py
git commit -m "feat(cuaderno): trace tool runs, verdicts, retries-with-reason and floor decisions"
```

---

### Task 5: Wire capture under `COPYCLIP_TRACE_WIRE=1` + judge raw text

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`
- Modify: `src/copyclip/intelligence/cuaderno/judge.py`
- Test: `tests/test_cuaderno_trace_integration.py`, `tests/test_cuaderno_judge.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cuaderno_trace_integration.py`:

```python
def test_wire_events_only_under_flag(tmp_path, monkeypatch):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "x"}),
        _msg_stop("end_turn", [_content("b1", "emit_block", {"kind": "lead", "text": "x"})]),
    ]
    # without the flag: no wire events
    monkeypatch.delenv("COPYCLIP_TRACE_WIRE", raising=False)
    _, lines = _run(tmp_path / "off", [list(turn)])
    assert not _by_event(lines, "wire.request") and not _by_event(lines, "wire.response")
    # with the flag: full request + response per round
    monkeypatch.setenv("COPYCLIP_TRACE_WIRE", "1")
    _, lines = _run(tmp_path / "on", [list(turn)])
    reqs = _by_event(lines, "wire.request")
    resps = _by_event(lines, "wire.response")
    assert len(reqs) == 1 and len(resps) == 1
    assert reqs[0]["model"] and reqs[0]["system"]
    assert reqs[0]["messages"][0] == {"role": "user", "content": "q"}
    assert isinstance(reqs[0]["tools"], list) and "emit_block" in reqs[0]["tools"]
    assert resps[0]["stop_reason"] == "end_turn"
    assert resps[0]["content"][0]["name"] == "emit_block"
```

Append to `tests/test_cuaderno_judge.py`:

```python
def test_judge_answer_captures_raw_text():
    from copyclip.intelligence.cuaderno.judge import judge_answer
    from copyclip.intelligence.cuaderno.read_ledger import ReadLedger

    class StubClient:
        def __init__(self, text):
            self._text = text

        def messages_create(self, **kwargs):
            return {"content": [{"type": "text", "text": self._text}]}

    good = '{"decision": "ok", "grounded": true, "responsive": true, "language_ok": true, "reason": "fine"}'
    v = judge_answer(client=StubClient(good), question="q", blocks=[],
                     ledger=ReadLedger(), model="m")
    assert v.judged is True and v.raw == good

    v2 = judge_answer(client=StubClient("not json at all"), question="q", blocks=[],
                      ledger=ReadLedger(), model="m")
    assert v2.judged is False and v2.raw == "not json at all"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py::test_wire_events_only_under_flag tests/test_cuaderno_judge.py::test_judge_answer_captures_raw_text -q`
Expected: FAIL (no wire events; `JudgeVerdict` has no attribute `raw`)

- [ ] **Step 3: Implement**

3a. In `judge.py`, add the field to `JudgeVerdict` (after `judged`):

```python
    judged: bool = True            # False when this is a fail-open default, not a real judgment
    raw: Optional[str] = None      # the judge's raw text (trace/debug only; never persisted)
```

and in `judge_answer`, replace the tail:

```python
    except Exception as exc:  # noqa: BLE001 — fail-open is the whole point
        return _ok_verdict(f"judge unavailable: {exc}")
    return v if v is not None else _ok_verdict("judge output unparseable")
```

with:

```python
    except Exception as exc:  # noqa: BLE001 — fail-open is the whole point
        return _ok_verdict(f"judge unavailable: {exc}")
    out = v if v is not None else _ok_verdict("judge output unparseable")
    out.raw = text
    return out
```

(`judge_verdict_dict` builds its dict from explicit fields, so `raw` never reaches the persisted frame.)

3b. In `compositor.py`, inside the round loop, right before the `try:` that wraps `client.messages_stream` (after `round_t0 = time.perf_counter()` from Task 3):

```python
        if trace.wire:
            trace.event("wire.request", round_i=round_i, model=model,
                        system=SYSTEM_PROMPT, messages=messages,
                        tools=[t["name"] for t in round_tools])
```

and right after the Task-3 `llm.round` event:

```python
        if trace.wire:
            trace.event("wire.response", round_i=round_i, stop_reason=stop_reason,
                        content=turn_content)
```

(`trace.event` serializes immediately, so the mutable `messages` list is snapshotted at call time. The judge's `raw` is already wired into `_trace_judge` from Task 4.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py tests/test_cuaderno_judge.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py src/copyclip/intelligence/cuaderno/judge.py tests/test_cuaderno_trace_integration.py tests/test_cuaderno_judge.py
git commit -m "feat(cuaderno): full LLM wire capture under COPYCLIP_TRACE_WIRE=1, judge raw text on the verdict"
```

---

### Task 6: ask_stream owns the trace lifecycle

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/ask_stream.py`
- Test: `tests/test_cuaderno_trace_integration.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cuaderno_trace_integration.py`:

```python
import sqlite3

from copyclip.intelligence.db import init_cuaderno_schema
from copyclip.intelligence.cuaderno.persistence import create_session
from copyclip.intelligence.cuaderno.ask_stream import iter_ask_events


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py -q`
Expected: the 2 new tests FAIL — `iter_ask_events() got an unexpected keyword argument 'provider'`

- [ ] **Step 3: Implement**

Rewrite `src/copyclip/intelligence/cuaderno/ask_stream.py` (whole file — it is small):

```python
from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterator, Optional

from .compositor import iter_compose_events
from .i18n import tr
from .language import detect_language
from .persistence import save_question
from .schema import Block, Frame, FRAME_STATUS_PARTIAL, frame_from_dict
from .trace import InteractionTrace, trace_logs_dir


def _persist_partial(conn, session_id: str, question: str, emitted: list[dict],
                     message: Optional[str] = None) -> None:
    lang = detect_language(question)
    blocks = [Block.from_dict(b) for b in emitted]
    if not blocks:
        reason = message or tr("partial_default_reason", lang)
        blocks = [Block.paragraph(tr("partial", lang, reason=reason))]
    pframe = Frame(question=question, blocks=blocks, status=FRAME_STATUS_PARTIAL,
                   question_language=lang)
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
    judge: Any = None,
    provider: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> Iterator[dict[str, Any]]:
    """Wrap iter_compose_events for the HTTP layer.

    - Prepends a `meta` event carrying session_id.
    - On the terminal `frame`, persists the Frame and attaches its `position`.
    - On a terminal `error` with partial=True (or on client disconnect, which
      arrives as GeneratorExit in the finally), persists the partial Frame from
      the blocks already emitted.
    - Owns the InteractionTrace lifecycle: one JSONL debug timeline per ask in
      `<project_root>/.copyclip/logs/cuaderno/` (spec 2026-06-10). The trace can
      never break this path — it swallows its own failures.
    """
    lang = detect_language(question)
    trace = InteractionTrace.start(
        "ask", trace_logs_dir(project_root),
        {
            "question": question,
            "session_id": session_id,
            "question_language": lang,
            "model": model,
            "judge_model": judge_model,
            "provider": provider,
            "max_tool_rounds": max_tool_rounds,
            "copyclip_version": os.environ.get("COPYCLIP_VERSION", "dev"),
        },
        tag=(session_id or "")[:8] or None,
    )
    outcome = "incomplete"
    yield {"type": "meta", "session_id": session_id, "question_language": lang}
    emitted: list[dict] = []
    persisted = False
    try:
        for ev in iter_compose_events(
            client=client, question=question, project_root=project_root,
            project_id=project_id, conn=conn, model=model,
            max_tool_rounds=max_tool_rounds, max_tokens=max_tokens,
            judge=judge, trace=trace,
        ):
            if ev["type"] == "block":
                emitted.append(ev["block"])
                yield ev
            elif ev["type"] == "reset":
                # The compositor discarded the provisional answer (a grounding /
                # language retry). Drop our own buffered copy so a disconnect
                # during the retry can never persist the discarded blocks, and
                # forward it so the client drops its provisional render too.
                emitted.clear()
                yield ev
            elif ev["type"] == "tool":
                yield ev
            elif ev["type"] == "frame":
                frame = frame_from_dict(ev["frame"])
                position = save_question(conn, session_id, question, frame)
                persisted = True
                trace.event("seal", status=ev["frame"].get("status"),
                            verdict=ev["frame"].get("verdict"),
                            blocks=len(ev["frame"].get("blocks") or []),
                            position=position, sse=True)
                trace.event("persist", outcome="ok", error=None)
                outcome = ev["frame"].get("status") or "answer"
                yield {"type": "frame", "position": position, "frame": ev["frame"]}
            elif ev["type"] == "error":
                # Always persist the turn so it is never silently lost — a stream
                # error is a `partial` per the status taxonomy. Surviving blocks
                # ride as the partial body; with none (e.g. an error after a
                # retry's reset cleared the buffer) a marker block keeps the
                # question in the conversation.
                _persist_partial(conn, session_id, question, emitted, message=ev.get("message"))
                persisted = True
                trace.event("persist", outcome="partial", error=ev.get("message"))
                outcome = "error"
                yield ev
    finally:
        # Client disconnect (GeneratorExit) or abnormal stop: persist partial once.
        if not persisted and emitted:
            try:
                _persist_partial(conn, session_id, question, emitted)
                trace.event("persist", outcome="partial", error="client disconnect")
            except Exception as exc:
                # Best-effort: a persistence failure during teardown must not
                # mask the GeneratorExit (client disconnect) that triggered it.
                trace.event("persist", outcome="failed", error=str(exc))
        if outcome == "incomplete":
            outcome = "disconnect"
        trace.close(outcome=outcome)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_trace_integration.py tests/test_cuaderno_ask_stream.py tests/test_cuaderno_e2e.py -q`
Expected: all pass (existing ask_stream/e2e suites prove behavior is unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/ask_stream.py tests/test_cuaderno_trace_integration.py
git commit -m "feat(cuaderno): ask_stream owns the interaction trace lifecycle (header, seal, persist, close)"
```

---

### Task 7: Launch trace — playground.py, MarimoRunner, StubMarimoRunner

**Files:**
- Modify: `src/copyclip/intelligence/playground.py`
- Modify: `src/copyclip/intelligence/marimo_runner.py`
- Test: `tests/test_playground_trace.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_playground_trace.py`:

```python
import json
import os
import shutil
import sqlite3

import pytest

from copyclip.intelligence.playground import (
    FunctionNotFoundError, MarimoSpawnError, PlaygroundLaunchRequest, launch_playground,
)
from copyclip.intelligence.cuaderno.trace import InteractionTrace


class FakeRunner:
    def launch(self, notebook_path, mode="edit", trace=None):
        if trace is not None:
            trace.event("launch.spawn", cmd=["python", "-m", "marimo", mode],
                        port=1234, pid=42, mode=mode)
        return "pgid123", "http://127.0.0.1:1234/"

    def kill(self, playground_id):
        return True

    def status(self, playground_id):
        return "running"


class FailingRunner(FakeRunner):
    def launch(self, notebook_path, mode="edit", trace=None):
        raise MarimoSpawnError("boom")


def _conn_with_symbol():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE symbols (project_id INT, name TEXT, kind TEXT,"
        " file_path TEXT, line_start INT, module TEXT)")
    conn.execute(
        "INSERT INTO symbols VALUES (1, 'foo', 'function', 'src/copyclip/util.py', 10, 'copyclip')")
    return conn


def _req(name="foo"):
    return PlaygroundLaunchRequest.from_dict({
        "source": "cuaderno",
        "function_ref": {"file": "src/copyclip/util.py", "name": name},
        "breadcrumb": "bc",
        "suggested_inputs": ["src/copyclip/foo.py"],
    })


def _lines(trace):
    return [json.loads(l) for l in trace.path.read_text(encoding="utf-8").splitlines()]


def test_launch_traces_resolve_notebook_spawn_ready(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {"source": "cuaderno"})
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
                             FakeRunner(), trace=trace)
    trace.close(outcome="ready")
    assert resp.playground_id == "pgid123"
    lines = _lines(trace)
    names = [l["event"] for l in lines]
    assert names == ["launch.start", "launch.resolve", "launch.notebook",
                     "launch.spawn", "launch.ready", "launch.end"]
    resolve = lines[1]
    assert resolve["module"] == "copyclip.util" and resolve["name"] == "foo"
    notebook = lines[2]
    assert notebook["path"].endswith("playground.py") and "mo.ui.text" in notebook["input_element"]
    spawn = lines[3]
    assert spawn["port"] == 1234 and spawn["pid"] == 42 and spawn["mode"] == "run"
    assert lines[4]["playground_id"] == "pgid123"
    shutil.rmtree(os.path.dirname(notebook["path"]), ignore_errors=True)


def test_resolve_failure_traces_launch_error_stage_resolve(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(FunctionNotFoundError):
        launch_playground(_req(name="missing"), str(tmp_path), _conn_with_symbol(), 1,
                          FakeRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next(l for l in lines if l["event"] == "launch.error")
    assert err["stage"] == "resolve" and "missing" in err["error"]


def test_spawn_failure_traces_launch_error_stage_spawn(tmp_path):
    trace = InteractionTrace.start("launch", tmp_path / "logs", {})
    with pytest.raises(MarimoSpawnError):
        launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1,
                          FailingRunner(), trace=trace)
    trace.close(outcome="error")
    lines = _lines(trace)
    err = next(l for l in lines if l["event"] == "launch.error")
    assert err["stage"] == "spawn" and "boom" in err["error"]


def test_launch_without_trace_still_works(tmp_path):
    resp = launch_playground(_req(), str(tmp_path), _conn_with_symbol(), 1, FakeRunner())
    assert resp.playground_id == "pgid123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_playground_trace.py -q`
Expected: FAIL — `launch_playground() got an unexpected keyword argument 'trace'`

- [ ] **Step 3: Implement**

3a. In `src/copyclip/intelligence/playground.py`, add the import (after the stdlib imports):

```python
from .cuaderno.trace import NULL_TRACE
```

3b. Update the `MarimoRunner` Protocol's launch signature:

```python
class MarimoRunner(Protocol):
    def launch(self, notebook_path: str, mode: str = "edit", trace: object = None) -> tuple[str, str]:
        """Return (playground_id, iframe_url) after a healthy spawn."""
        ...
```

3c. Replace `launch_playground`:

```python
def launch_playground(
    req: PlaygroundLaunchRequest,
    project_root: str,
    conn: sqlite3.Connection,
    pid: int,
    runner: MarimoRunner,
    trace: object = None,
) -> PlaygroundLaunchResponse:
    """Resolve, generate, launch. May raise PlaygroundError subclasses.

    If the runner fails after the notebook has been written, the temp dir is
    cleaned up best-effort so we don't leak per-request directories in the
    common error path. Crash-cleanup of orphans across CopyClip restarts is
    the runner's responsibility on startup (see spec, "Orphan cleanup").

    `trace` is an optional InteractionTrace (spec 2026-06-10): each stage emits
    a `launch.*` event; failures emit `launch.error` with the failing stage.
    """
    trace = trace if trace is not None else NULL_TRACE
    try:
        resolved = resolve_function_ref(conn, pid, req.function_ref)
    except Exception as exc:
        trace.event("launch.error", stage="resolve", error=str(exc))
        raise
    trace.event("launch.resolve", file=resolved.file, name=resolved.name,
                qualname=resolved.qualname, kind=resolved.kind,
                module=resolved.module, line_start=resolved.line_start,
                parent_class=resolved.parent_class)
    try:
        notebook_path = generate_marimo_notebook(req, project_root, resolved)
    except Exception as exc:
        trace.event("launch.error", stage="notebook", error=str(exc))
        raise
    trace.event("launch.notebook", path=notebook_path,
                input_element=_build_input_element(req.suggested_inputs),
                deps_hint=req.deps_hint)
    mode = "run" if req.source == "cuaderno" else "edit"
    try:
        playground_id, iframe_url = runner.launch(notebook_path, mode=mode, trace=trace)
    except Exception as exc:
        trace.event("launch.error", stage="spawn", error=str(exc))
        shutil.rmtree(os.path.dirname(notebook_path), ignore_errors=True)
        raise
    trace.event("launch.ready", playground_id=playground_id, iframe_url=iframe_url)
    return PlaygroundLaunchResponse(
        playground_id=playground_id,
        iframe_url=iframe_url,
    )
```

3d. Update `StubMarimoRunner.launch` (same file, bottom):

```python
    def launch(self, notebook_path: str, mode: str = "edit", trace: object = None) -> tuple[str, str]:
        raise MarimoSpawnError(
            "marimo subprocess manager not yet implemented (issue #88); "
            f"notebook generated at {notebook_path}"
        )
```

3e. In `src/copyclip/intelligence/marimo_runner.py`, add the import:

```python
from .cuaderno.trace import NULL_TRACE
```

change the real `MarimoRunner.launch` signature:

```python
    def launch(self, notebook_path: str, mode: str = "edit", trace=None) -> tuple[str, str]:
        if trace is None:
            trace = NULL_TRACE
        if mode not in ("edit", "run"):
            raise MarimoSpawnError(f"unknown marimo mode: {mode!r}")
```

and emit `launch.spawn` right after the `_StderrCollector` is created (the subprocess exists and has a pid; health is still pending):

```python
            collector = _StderrCollector(process.stderr)
            trace.event("launch.spawn", cmd=cmd, port=port, pid=process.pid, mode=mode)
            try:
                self._wait_for_healthy(process, port, collector)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_playground_trace.py tests/test_playground.py tests/test_marimo_runner.py -q`
Expected: all pass (existing suites prove the keyword-only `trace` addition is backward compatible)

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/playground.py src/copyclip/intelligence/marimo_runner.py tests/test_playground_trace.py
git commit -m "feat(cuaderno): launch trace — resolve, notebook, spawn, ready/error per playground launch"
```

---

### Task 8: Server wiring — ask header fields + launch route trace

**Files:**
- Modify: `src/copyclip/intelligence/server.py` (ask route ~2188, launch route ~1620, playground import block ~30)

- [ ] **Step 1: Wire the ask route**

In `server.py`, the `/api/cuaderno/ask` handler, replace:

```python
                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id, model=resolved["model"],
                        judge=_judge,
                    )
```

with:

```python
                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id, model=resolved["model"],
                        judge=_judge, provider=resolved["provider"],
                        judge_model=judge_model,
                    )
```

- [ ] **Step 2: Wire the launch route**

In `server.py`, the `/api/playground/launch` handler, replace:

```python
                    try:
                        req = PlaygroundLaunchRequest.from_dict(data)
                        response = launch_playground(req, root, conn, pid, playground_runner)
                        self._json(response.to_dict())
                    except PlaygroundError as e:
                        payload = {"error": e.error_code, "message": str(e)}
                        if isinstance(e, MarimoNotInstalledError):
                            payload["install_hint"] = "pip install copyclip[playground]"
                        self._json(payload, e.http_status)
                    return
```

with:

```python
                    from .cuaderno.trace import InteractionTrace, trace_logs_dir
                    ltrace = InteractionTrace.start("launch", trace_logs_dir(root), {
                        "source": (data or {}).get("source"),
                        "function_ref": (data or {}).get("function_ref"),
                        "breadcrumb": (data or {}).get("breadcrumb"),
                        "suggested_inputs": (data or {}).get("suggested_inputs"),
                    })
                    parsed_ok = False
                    try:
                        req = PlaygroundLaunchRequest.from_dict(data)
                        parsed_ok = True
                        response = launch_playground(req, root, conn, pid,
                                                     playground_runner, trace=ltrace)
                        self._json(response.to_dict())
                        ltrace.close(outcome="ready")
                    except PlaygroundError as e:
                        if not parsed_ok:
                            # request-stage failures never reach launch_playground's
                            # own launch.error events — record them here.
                            ltrace.event("launch.error", stage="request",
                                         error=f"{e.error_code}: {e}")
                        payload = {"error": e.error_code, "message": str(e)}
                        if isinstance(e, MarimoNotInstalledError):
                            payload["install_hint"] = "pip install copyclip[playground]"
                        self._json(payload, e.http_status)
                        ltrace.close(outcome="error")
                    return
```

- [ ] **Step 3: Run the server-facing suites**

Run: `python -m pytest tests/test_cuaderno_endpoint.py tests/test_intelligence_server_api.py tests/test_cuaderno_sse_response.py tests/test_playground.py -q`
Expected: all pass (signatures are backward compatible; the new kwargs are optional)

- [ ] **Step 4: Commit**

```bash
git add src/copyclip/intelligence/server.py
git commit -m "feat(cuaderno): wire interaction traces into the ask and playground-launch routes"
```

---

### Task 9: Full suite + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest tests/ -q`
Expected: all pass, no new warnings about unclosed files (the tracer closes its handle in `close()`; pytest's `-W error::ResourceWarning` is NOT required, but if a ResourceWarning about a trace file appears, a `close()` call is missing on some path — fix before committing).

- [ ] **Step 2: Live smoke (manual, with Samuel)**

1. Start the intelligence server (`.copyclip-verify.py` in the repo root launches it on `127.0.0.1:4310`, skipping onboarding).
2. Ask the cuaderno any question; confirm a new `ask_*.jsonl` appears under `.copyclip/logs/cuaderno/` and reads as a coherent timeline (`ask.start` → `llm.round`/`tool.run`/`block.accept` → `verdict.*` → `seal` → `persist` → `ask.end`).
3. Click "correr ejemplo" on a playground widget; confirm a `launch_*.jsonl` with `launch.start → resolve → notebook → spawn → ready → end`.
4. Re-ask with `COPYCLIP_TRACE_WIRE=1` set in the server's environment; confirm `wire.request`/`wire.response` lines appear.

- [ ] **Step 3: Final commit if the smoke revealed fixes; otherwise done**

```bash
git status   # should be clean
```

---

## Self-review (run after writing, fixed inline)

- **Spec coverage:** §4.1 API → Task 1; §4.2 naming/retention → Tasks 1-2; §4.3 line format → Task 1; §5.1 ask events → Tasks 3, 4, 6 (`ask.start`/`ask.end`/`seal`/`persist` in 6; `llm.round`/`block.*`/`recovery.directive`/`error` in 3; `tool.run`/`verdict.*`/`retry`/`floor` in 4); §5.2 launch events → Tasks 7-8; §5.3 wire → Task 5; §6 integration points → Tasks 3-8; §7 golden rule → Task 1 (disable tests); §8 testing → mirrored 1:1.
- **Type consistency:** `trace.event(name, **payload)` used uniformly; `InteractionTrace.start(kind, logs_dir, header, tag)` matches all call sites; `trace: Any = None` resolved via `NULL_TRACE` in compositor/playground/runner; `JudgeVerdict.raw` only read via `getattr` in `_trace_judge` (safe before Task 5 lands — Tasks 4 and 5 are order-independent for that line).
- **No placeholders:** every step carries complete code or an exact command with expected output.
