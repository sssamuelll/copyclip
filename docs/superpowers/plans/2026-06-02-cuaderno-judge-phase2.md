# Cuaderno Answer Quality — Phase 2 (The Semantic Judge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-open semantic judge that runs on every would-be-`answer`, catches non-responsiveness ("what not how"), produces `insufficient_evidence` (World A), and persists the full multi-axis verdict on the frame.

**Architecture:** The judge is a single non-streaming structured-JSON call (cheap model, e.g. haiku) over the finished answer, injected into the compositor terminal as a callable so it is decoupled and stub-testable. It runs only when the Phase-1 cheap layer would seal `answer`. Correction uses per-property non-fungible latches (`grounding_retry_used` / `responsiveness_retry_used`). The frame gains a persisted `verdict` (the multi-axis pre-image) and a new `off_target` disposition.

**Tech Stack:** Python 3.14 (stdlib, `dataclasses`, `json`), pytest (`asyncio_mode=auto`); React 18 + Vite + TS (frontend, verified via `tsc -b`). Run pytest as `python -m pytest` from the repo root (Windows). Both LLM adapters already expose `messages_create(**kwargs) -> {"stop_reason", "content": [blocks]}`.

**Spec:** `docs/superpowers/specs/2026-06-02-cuaderno-judge-phase2-design.md`. **Builds on** Phase 1 (shipped #125): `Frame.status` with `answer|ungrounded|insufficient_evidence|partial|fallback|legacy`, the `assess()` cheap verdict (`QualityVerdict(status, suspicion, language_mismatch, question_language, reason)`), the `reset` event, and the single `grounding_retry_used` latch in `iter_compose_events`.

---

## File Structure

**Create:**
- `src/copyclip/intelligence/cuaderno/judge.py` — `JudgeVerdict`, `parse_judge_verdict`, `judge_answer` (fail-open), `judge_verdict_dict`.
- `tests/test_cuaderno_judge.py` — unit tests.

**Modify:**
- `src/copyclip/intelligence/cuaderno/prompts.py` — add `JUDGE_PROMPT` and `RESPONSIVENESS_RETRY_FALLBACK`.
- `src/copyclip/intelligence/cuaderno/schema.py` — `FRAME_STATUS_OFF_TARGET`; `Frame.verdict: Optional[dict]`; serialization.
- `src/copyclip/intelligence/cuaderno/quality.py` — `cheap_verdict_dict(QualityVerdict)`.
- `src/copyclip/intelligence/cuaderno/compositor.py` — thread `judge` callable + `responsiveness_retry_used`; judge the would-be-`answer`; map decision; persist verdict.
- `src/copyclip/intelligence/cuaderno/ask_stream.py` — pass `judge` through.
- `src/copyclip/intelligence/cuaderno/provider.py` — `resolve_judge_model`.
- `src/copyclip/intelligence/server.py` — build the real `judge` callable and pass it to `iter_ask_events`.
- `frontend/src/types/api.ts` — `off_target` in `FrameStatus`; `Frame.verdict?`.
- `frontend/src/components/cuaderno/frames/FrameDynamic.tsx` — `off_target` banner.

---

## Task 1: `JudgeVerdict` + `parse_judge_verdict`

**Files:** Create `src/copyclip/intelligence/cuaderno/judge.py`; Test `tests/test_cuaderno_judge.py`.

- [ ] **Step 1: Write the failing test** — create `tests/test_cuaderno_judge.py`:

```python
from copyclip.intelligence.cuaderno.judge import (
    JudgeVerdict, parse_judge_verdict,
)


def test_parses_a_clean_ok_verdict():
    v = parse_judge_verdict(
        '{"question_kind":"code_comprehension","grounded":true,"responsive":true,'
        '"language_ok":true,"decision":"ok","reason":"answers the mechanism"}'
    )
    assert v is not None
    assert v.decision == "ok" and v.responsive is True


def test_parses_retry_with_directive():
    v = parse_judge_verdict(
        '{"decision":"retry","responsive":false,"grounded":true,"language_ok":true,'
        '"question_kind":"code_comprehension","retry_directive":"explain the mechanism, not what it is","reason":"answered what not how"}'
    )
    assert v.decision == "retry" and v.responsive is False
    assert "mechanism" in v.retry_directive


def test_parses_insufficient_with_world():
    v = parse_judge_verdict(
        '{"decision":"insufficient","world":"consulted_empty","grounded":false,'
        '"responsive":true,"language_ok":true,"question_kind":"code_comprehension","reason":"no evidence in repo"}'
    )
    assert v.decision == "insufficient" and v.world == "consulted_empty"


def test_extracts_json_from_surrounding_prose():
    v = parse_judge_verdict('Here is my verdict:\n```json\n{"decision":"ok"}\n```\nDone.')
    assert v is not None and v.decision == "ok"


def test_unparseable_returns_none():
    assert parse_judge_verdict("not json at all") is None
    assert parse_judge_verdict('{"decision":"bogus"}') is None  # unknown decision
    assert parse_judge_verdict("") is None
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: ... judge`.

- [ ] **Step 3: Implement the parser in `judge.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

_DECISIONS = frozenset({"ok", "retry", "insufficient"})


@dataclass
class JudgeVerdict:
    question_kind: str          # code_comprehension | meta | conceptual
    grounded: bool
    responsive: bool
    language_ok: bool
    decision: str               # ok | retry | insufficient
    world: Optional[str]        # consulted_empty | not_consulted (insufficient only)
    retry_directive: Optional[str]
    reason: str


def _extract_json(text: str) -> str:
    """Slice the first {...} object out of a model response that may wrap it in
    prose or a ```json fence."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return ""
    return text[start : end + 1]


def parse_judge_verdict(text: str) -> Optional[JudgeVerdict]:
    """Parse a judge response into a JudgeVerdict, or None if it is unusable
    (caller treats None as fail-open)."""
    if not text:
        return None
    try:
        obj = json.loads(_extract_json(text))
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or obj.get("decision") not in _DECISIONS:
        return None
    return JudgeVerdict(
        question_kind=str(obj.get("question_kind", "code_comprehension")),
        grounded=bool(obj.get("grounded", True)),
        responsive=bool(obj.get("responsive", True)),
        language_ok=bool(obj.get("language_ok", True)),
        decision=obj["decision"],
        world=obj.get("world") if isinstance(obj.get("world"), str) else None,
        retry_directive=obj.get("retry_directive") if isinstance(obj.get("retry_directive"), str) else None,
        reason=str(obj.get("reason", "")),
    )
```

- [ ] **Step 4: Run, confirm PASS**

Run: `python -m pytest tests/test_cuaderno_judge.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/judge.py tests/test_cuaderno_judge.py
git commit -m "feat(cuaderno): judge verdict dataclass + tolerant JSON parser"
```

---

## Task 2: `judge_answer` (fail-open) + `judge_verdict_dict`

**Files:** Modify `src/copyclip/intelligence/cuaderno/judge.py`; Test `tests/test_cuaderno_judge.py`.

- [ ] **Step 1: Write the failing test** — append:

```python
from copyclip.intelligence.cuaderno.judge import judge_answer, judge_verdict_dict
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.schema import Block


class _StubClient:
    def __init__(self, text=None, raises=False):
        self._text = text
        self._raises = raises
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise RuntimeError("api down")
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": self._text}]}


def _ledger():
    led = ReadLedger()
    led.record("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})
    return led


def test_judge_answer_parses_client_text():
    client = _StubClient(text='{"decision":"retry","responsive":false,"retry_directive":"explain how"}')
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("it is X")],
                     ledger=_ledger(), model="claude-haiku-4-5")
    assert v.decision == "retry" and v.responsive is False
    assert client.calls[0]["model"] == "claude-haiku-4-5"


def test_judge_answer_fails_open_on_exception():
    client = _StubClient(raises=True)
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("x")],
                     ledger=_ledger(), model="m")
    assert v.decision == "ok"  # fail-open: never blocks the answer


def test_judge_answer_fails_open_on_garbage():
    client = _StubClient(text="the model rambled and produced no json")
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("x")],
                     ledger=_ledger(), model="m")
    assert v.decision == "ok"


def test_judge_verdict_dict_shape():
    v = JudgeVerdict("code_comprehension", True, False, True, "retry", None, "redo", "off topic")
    d = judge_verdict_dict(v)
    assert d == {
        "grounded": True, "responsive": False, "language_ok": True,
        "question_kind": "code_comprehension", "world": None,
        "reason": "off topic", "source": "judge",
    }
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_judge.py -k "judge_answer or judge_verdict_dict" -v`
Expected: FAIL — `cannot import name 'judge_answer'`.

- [ ] **Step 3: Implement in `judge.py`** (append). Add the import of `Block` at the top: `from .schema import Block`. Then:

```python
from .prompts import JUDGE_PROMPT  # added in Task 3; safe to import now if Task 3 ran first


def _ok_verdict(reason: str) -> JudgeVerdict:
    return JudgeVerdict("code_comprehension", True, True, True, "ok", None, None, reason)


def _ledger_summary(ledger) -> str:
    paths = ", ".join(sorted(ledger.read_paths)) or "(none)"
    return f"content-bearing reads: {ledger.content_bearing_count}; files read: {paths}"


def _answer_text_for_judge(blocks: "list[Block]") -> str:
    out: list[str] = []
    for b in blocks:
        v = b.data.get("text")
        if isinstance(v, str):
            out.append(v)
    return "\n\n".join(out)


def judge_answer(*, client, question, blocks, ledger, model, max_tokens: int = 512) -> JudgeVerdict:
    """Run the semantic judge over a finished answer. FAIL-OPEN: any error or
    unparseable output returns an `ok` verdict so a judge outage never blocks,
    hangs, or downgrades an answer that already passed the deterministic gate."""
    user = (
        f"QUESTION:\n{question}\n\n"
        f"EVIDENCE THE TUTOR CONSULTED:\n{_ledger_summary(ledger)}\n\n"
        f"THE TUTOR'S ANSWER:\n{_answer_text_for_judge(blocks)}\n\n"
        "Return ONLY the JSON verdict."
    )
    try:
        resp = client.messages_create(
            model=model, system=JUDGE_PROMPT,
            messages=[{"role": "user", "content": user}], max_tokens=max_tokens,
        )
        text = "".join(
            b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"
        )
    except Exception as exc:  # noqa: BLE001 — fail-open is the whole point
        return _ok_verdict(f"judge unavailable: {exc}")
    v = parse_judge_verdict(text)
    return v if v is not None else _ok_verdict("judge output unparseable")


def judge_verdict_dict(v: JudgeVerdict) -> dict[str, Any]:
    """The persisted pre-image (the record), excluding the transient action
    fields (`decision`, `retry_directive`)."""
    return {
        "grounded": v.grounded,
        "responsive": v.responsive,
        "language_ok": v.language_ok,
        "question_kind": v.question_kind,
        "world": v.world,
        "reason": v.reason,
        "source": "judge",
    }
```

(Note: if Task 3 has not run yet, `from .prompts import JUDGE_PROMPT` fails. Do Task 3 first, or temporarily inline a placeholder — but the recommended order is Task 3 before Task 2's Step 3. If executing in number order, move the `from .prompts import JUDGE_PROMPT` line in after Task 3. The tests in this task do NOT exercise the prompt, only the stub client, so the import is the only coupling.)

- [ ] **Step 4: Run, confirm PASS** (after Task 3's `JUDGE_PROMPT` exists)

Run: `python -m pytest tests/test_cuaderno_judge.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/judge.py tests/test_cuaderno_judge.py
git commit -m "feat(cuaderno): judge_answer (fail-open) + persisted verdict dict"
```

---

## Task 3: `JUDGE_PROMPT`

**Files:** Modify `src/copyclip/intelligence/cuaderno/prompts.py`; Test `tests/test_cuaderno_prompt.py`.

**Do this BEFORE Task 2's Step 3** (Task 2 imports `JUDGE_PROMPT`).

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_prompt.py`:

```python
def test_judge_prompt_demands_structured_verdict_and_responsiveness():
    from copyclip.intelligence.cuaderno.prompts import JUDGE_PROMPT
    low = JUDGE_PROMPT.lower()
    assert "json" in low
    assert "decision" in low and "responsive" in low and "world" in low
    # It must teach the how-vs-what distinction and the two worlds.
    assert ("mechanism" in low or "how it works" in low)
    assert "consulted_empty" in low and "not_consulted" in low
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_prompt.py -k judge_prompt -v`
Expected: FAIL — `cannot import name 'JUDGE_PROMPT'`.

- [ ] **Step 3: Add to `prompts.py`** (near `GROUNDING_RETRY_DIRECTIVE`):

```python
RESPONSIVENESS_RETRY_FALLBACK = (
    "Your answer addressed a different question than the one asked. Re-answer the "
    "question that was actually asked — if it asks HOW something works, explain "
    "the mechanism, not what it is — keeping it anchored to the same evidence."
)

JUDGE_PROMPT = """\
You are a strict reviewer of a tutor's answer about a codebase. You did NOT write
the answer; judge it as a finished artifact. Return ONLY a JSON object, no prose.

Judge three things:
- responsive: does the answer address the QUESTION THAT WAS ASKED? If the question
  asks HOW something works (mechanism), an answer that only says WHAT it is (a
  definition) is NOT responsive. This is the failure you exist to catch.
- grounded: are the claims supported by the evidence the tutor consulted?
- language_ok: is the answer in the same language as the question?

Then choose a decision:
- "ok": responsive, grounded, right language.
- "retry": fixable by re-answering (e.g. answered what-not-how) — give a short
  retry_directive telling the tutor what to fix.
- "insufficient": the question cannot be answered well, and you must say WHICH
  world it is via "world":
    - "consulted_empty": the tutor DID consult the code and it genuinely lacks
      the evidence to answer (a fact about the project).
    - "not_consulted": the tutor did not actually consult relevant code (a fact
      about the tutor).

For meta or conceptual questions (about the tutor, or general concepts not about
THIS code), a grounded-in-code answer is not required: return "ok" if responsive.

JSON shape (all fields required except world/retry_directive):
{"question_kind":"code_comprehension|meta|conceptual","grounded":true|false,
 "responsive":true|false,"language_ok":true|false,
 "decision":"ok|retry|insufficient","world":"consulted_empty|not_consulted",
 "retry_directive":"...","reason":"one short sentence"}
"""
```

- [ ] **Step 4: Run, confirm PASS**

Run: `python -m pytest tests/test_cuaderno_prompt.py -k judge_prompt -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/prompts.py tests/test_cuaderno_prompt.py
git commit -m "feat(cuaderno): JUDGE_PROMPT (responsiveness + two worlds, JSON verdict)"
```

---

## Task 4: `off_target` status + `Frame.verdict`

**Files:** Modify `src/copyclip/intelligence/cuaderno/schema.py`; Test `tests/test_cuaderno_schema.py`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_schema.py`:

```python
def test_off_target_status_known():
    from copyclip.intelligence.cuaderno.schema import (
        FRAME_STATUS_OFF_TARGET, KNOWN_FRAME_STATUSES,
    )
    assert FRAME_STATUS_OFF_TARGET == "off_target"
    assert FRAME_STATUS_OFF_TARGET in KNOWN_FRAME_STATUSES


def test_frame_carries_verdict_round_trip():
    from copyclip.intelligence.cuaderno.schema import Frame, Block, frame_to_dict, frame_from_dict
    vd = {"grounded": True, "responsive": False, "source": "judge"}
    f = Frame(question="q", blocks=[Block.lead("x")], status="off_target", verdict=vd)
    d = frame_to_dict(f)
    assert d["verdict"] == vd and d["status"] == "off_target"
    assert frame_from_dict(d).verdict == vd


def test_frame_verdict_defaults_none_for_legacy():
    from copyclip.intelligence.cuaderno.schema import frame_from_dict
    f = frame_from_dict({"question": "q", "blocks": [{"kind": "lead", "text": "x"}]})
    assert f.verdict is None and f.status == "legacy"
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_schema.py -k "off_target or verdict" -v`
Expected: FAIL.

- [ ] **Step 3: Implement in `schema.py`.** Add the constant to the status block and to the frozenset:

```python
FRAME_STATUS_OFF_TARGET = "off_target"            # grounded, but answers a different question
```

Add it to `KNOWN_FRAME_STATUSES`:

```python
KNOWN_FRAME_STATUSES: frozenset[str] = frozenset({
    FRAME_STATUS_ANSWER, FRAME_STATUS_INSUFFICIENT_EVIDENCE, FRAME_STATUS_UNGROUNDED,
    FRAME_STATUS_OFF_TARGET, FRAME_STATUS_PARTIAL, FRAME_STATUS_FALLBACK, FRAME_STATUS_LEGACY,
})
```

Add `verdict` to the `Frame` dataclass (after `status`):

```python
@dataclass
class Frame:
    question: str
    blocks: list[Block]
    status: str = FRAME_STATUS_ANSWER
    verdict: Optional[dict[str, Any]] = None
```

(`Optional` and `Any` are already imported in schema.py.) Update `frame_to_dict` and `frame_from_dict`:

```python
def frame_to_dict(f: Frame) -> dict[str, Any]:
    return {
        "question": f.question,
        "blocks": [b.to_dict() for b in f.blocks],
        "status": f.status,
        "verdict": f.verdict,
    }


def frame_from_dict(d: dict[str, Any]) -> Frame:
    return Frame(
        question=d["question"],
        blocks=[Block.from_dict(b) for b in d["blocks"]],
        status=d.get("status", FRAME_STATUS_LEGACY),
        verdict=d.get("verdict"),
    )
```

- [ ] **Step 4: Run, confirm PASS**

Run: `python -m pytest tests/test_cuaderno_schema.py -k "off_target or verdict" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Fix broken exact-frame-dict tests.** Adding `"verdict"` to `frame_to_dict` breaks exact-equality assertions.

Run: `python -m pytest tests/ -k cuaderno -q`
Expected: FAILs on exact `== {"question":..., "blocks":..., "status":...}` assertions.

For each, add `"verdict": None` (for cheap/fallback seals which have no verdict yet — they get one in Task 6/7; until then they serialize `None`) to the expected dict. The known sites: `tests/test_cuaderno_compositor.py::test_emits_blocks_then_frame_in_one_turn`. Apply `"verdict": None`:

```python
    assert events[2]["frame"] == {
        "question": "q",
        "blocks": [{"kind": "lead", "text": "hi"},
                   {"kind": "paragraph", "text": "body"}],
        "status": "ungrounded",
        "verdict": None,
    }
```

(Apply the same `"verdict": None` addition to any other exact-frame-dict assertion the run reports.)

- [ ] **Step 6: Run the full cuaderno suite, confirm green**

Run: `python -m pytest tests/ -k cuaderno -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/schema.py tests/test_cuaderno_schema.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): off_target status + persisted Frame.verdict"
```

---

## Task 5: `cheap_verdict_dict` (so cheap-only seals persist a verdict)

**Files:** Modify `src/copyclip/intelligence/cuaderno/quality.py`; Test `tests/test_cuaderno_quality.py`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_quality.py`:

```python
def test_cheap_verdict_dict_shape():
    from copyclip.intelligence.cuaderno.quality import cheap_verdict_dict
    led = ReadLedger()
    led.record("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})
    v = assess(question="como funciona", blocks=[Block.lead("hi")], ledger=led)
    d = cheap_verdict_dict(v)
    assert d["source"] == "cheap"
    assert d["grounded"] is True            # status == answer
    assert d["language_ok"] is True         # es question, but answer too short to mismatch
    assert d["responsive"] is None          # the cheap layer cannot judge responsiveness
    assert "reason" in d
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_quality.py -k cheap_verdict_dict -v`
Expected: FAIL — `cannot import name 'cheap_verdict_dict'`.

- [ ] **Step 3: Implement in `quality.py`** (append). Import `Any` is already present; import the status constant if needed (`FRAME_STATUS_ANSWER` is already imported):

```python
def cheap_verdict_dict(v: QualityVerdict) -> dict[str, Any]:
    """The cheap layer's partial verdict as the persisted pre-image. The cheap
    layer cannot judge responsiveness, so `responsive` is None (unknown)."""
    return {
        "grounded": v.status == FRAME_STATUS_ANSWER,
        "responsive": None,
        "language_ok": not v.language_mismatch,
        "question_kind": None,
        "world": None,
        "reason": v.reason,
        "source": "cheap",
    }
```

- [ ] **Step 4: Run, confirm PASS**

Run: `python -m pytest tests/test_cuaderno_quality.py -k cheap_verdict_dict -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/quality.py tests/test_cuaderno_quality.py
git commit -m "feat(cuaderno): cheap_verdict_dict for persisting cheap-layer verdicts"
```

---

## Task 6: Wire the judge into the compositor terminal

**Files:** Modify `src/copyclip/intelligence/cuaderno/compositor.py`; Test `tests/test_cuaderno_compositor.py`.

This restructures the terminal `if emitted:` branch. READ the current `iter_compose_events` terminal block first. The signature gains a `judge` parameter (a callable `(question, blocks, ledger) -> JudgeVerdict`, default `None` = Phase-1 behavior, keeping every existing test green).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_cuaderno_compositor.py`:

```python
from copyclip.intelligence.cuaderno.judge import JudgeVerdict


def _grounded_answer_turns(text="It walks the AST in analyzer.py."):
    (Path  # noqa: B018 — readability marker; real file written by caller
     )
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
    calls = {"n": 0}
    def _judge(question, blocks, ledger):
        calls["n"] += 1
        return verdict
    _judge.calls = calls
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
    # Phase-1 behavior preserved: judge=None -> cheap seal, verdict source cheap.
    (tmp_path / "README.md").write_text("# X\n", encoding="utf-8")
    client = StubStream(_grounded_answer_turns())
    events = list(iter_compose_events(
        client=client, question="how does it work?", project_root=str(tmp_path),
        project_id=1, conn=None,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer" and frame["verdict"]["source"] == "cheap"
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "judge_ok or judge_insufficient or no_judge_seals" -v`
Expected: FAIL — `iter_compose_events() got an unexpected keyword argument 'judge'`.

- [ ] **Step 3: Implement in `compositor.py`.**

(a) Add imports:
```python
from .quality import assess, cheap_verdict_dict
from .judge import judge_verdict_dict
from .prompts import (
    SYSTEM_PROMPT, GROUNDING_RETRY_DIRECTIVE, LANGUAGE_RETRY_DIRECTIVE,
    RESPONSIVENESS_RETRY_FALLBACK,
)
from .schema import (
    Block, Frame, frame_from_dict, frame_to_dict, validate_block_dict,
    FRAME_STATUS_FALLBACK, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED,
    FRAME_STATUS_INSUFFICIENT_EVIDENCE, FRAME_STATUS_OFF_TARGET,
)
```

(b) Add `judge=None` to the `iter_compose_events` signature (a keyword-only param alongside the others):
```python
    judge=None,            # Optional callable (question, blocks, ledger) -> JudgeVerdict
```

(c) Add the responsiveness latch next to `grounding_retry_used`:
```python
    grounding_retry_used = False
    responsiveness_retry_used = False
```

(d) Add a sealing helper and a judge-status mapper near `_sealed_frame`:
```python
def _seal(question: str, emitted: list[Block], status: str, verdict: dict) -> dict[str, Any]:
    return frame_to_dict(Frame(question=question, blocks=emitted, status=status, verdict=verdict))


def _judge_status(jv) -> str:
    if jv.decision == "ok":
        return FRAME_STATUS_ANSWER
    if jv.decision == "insufficient":
        return (FRAME_STATUS_INSUFFICIENT_EVIDENCE
                if jv.world == "consulted_empty" else FRAME_STATUS_UNGROUNDED)
    return FRAME_STATUS_OFF_TARGET   # retry with the responsiveness latch spent
```

(e) Replace the terminal `if emitted:` body (the block that currently computes `verdict`, does the grounding retry, and yields the sealed frame) with:
```python
            if emitted:
                verdict = assess(question=question, blocks=emitted, ledger=ledger)
                # Cheap layer owns the grounding/language shot.
                cheap_needs_retry = (verdict.status != FRAME_STATUS_ANSWER
                                     or verdict.language_mismatch)
                can_retry = round_i < max_tool_rounds - 2
                if cheap_needs_retry and not grounding_retry_used and can_retry:
                    grounding_retry_used = True
                    emitted.clear()
                    _inject_directive(messages, _retry_directive(verdict))
                    yield {"type": "reset"}
                    continue
                if verdict.status != FRAME_STATUS_ANSWER:
                    yield {"type": "frame",
                           "frame": _seal(question, emitted, verdict.status,
                                          cheap_verdict_dict(verdict))}
                    return
                # The cheap layer would seal `answer` -> the judge runs (Option A).
                if judge is not None:
                    jv = judge(question, emitted, ledger)
                    if (jv.decision == "retry" and not responsiveness_retry_used
                            and can_retry):
                        responsiveness_retry_used = True
                        emitted.clear()
                        _inject_directive(
                            messages, jv.retry_directive or RESPONSIVENESS_RETRY_FALLBACK)
                        yield {"type": "reset"}
                        continue
                    yield {"type": "frame",
                           "frame": _seal(question, emitted, _judge_status(jv),
                                          judge_verdict_dict(jv))}
                    return
                yield {"type": "frame",
                       "frame": _seal(question, emitted, FRAME_STATUS_ANSWER,
                                      cheap_verdict_dict(verdict))}
                return
            else:
                yield {"type": "frame",
                       "frame": frame_to_dict(
                           _fallback_frame(question, "the model produced no answer blocks"))}
            return
```

(f) Update the budget-exhausted tail's `_sealed_frame` to also persist a cheap verdict. Change `_sealed_frame` to:
```python
def _sealed_frame(question: str, emitted: list[Block], ledger: ReadLedger) -> dict[str, Any]:
    verdict = assess(question=question, blocks=emitted, ledger=ledger)
    return _seal(question, emitted, verdict.status, cheap_verdict_dict(verdict))
```

Adapt the exact replacement to the real current text (the Phase-1 fixes shaped this region; preserve the `reset`/`continue` mechanics and only fold in the judge branch + verdict persistence). The grounding retry and its `_retry_directive`/`reset` are unchanged.

- [ ] **Step 4: Run the new tests, confirm PASS**

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "judge_ok or judge_insufficient or no_judge_seals" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the whole compositor file + full cuaderno suite**

Run: `python -m pytest tests/test_cuaderno_compositor.py -q` then `python -m pytest tests/ -k cuaderno -q`
Expected: PASS. Existing grounding-retry/ungrounded tests still pass (judge defaults None). If a fallback exact-dict test now reports a `verdict` key, add `"verdict": {...source: cheap...}` or assert the subfields instead of exact-equality.

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): run the judge on would-be-answers; map ok/insufficient; persist verdict"
```

---

## Task 7: Responsiveness retry, off_target, fail-open, per-property non-fungibility

**Files:** Modify `tests/test_cuaderno_compositor.py` (behavior already implemented in Task 6; this task adds the tests that lock the harder paths).

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_judge_retry_then_ok_seals_corrected_answer(tmp_path: Path):
    """Judge asks for a responsiveness retry; the re-composed answer is judged ok."""
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
    """A judge that raises must not break the stream — the answer seals `answer`.
    (judge_answer is fail-open; here the injected judge itself returns ok per
    that contract — we simulate by injecting the fail-open result.)"""
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
    """A grounding retry fires (cheap layer), AND the judge still gets its own
    responsiveness retry on the re-grounded answer — neither consumes the other."""
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
    # round0 ungrounded(zero reads)->grounding retry; round1 read; round2 grounded->judge retry; round3 read?; here keep simple:
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
    assert len(resets) == 2   # one grounding reset + one responsiveness reset
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer"
```

- [ ] **Step 2: Run, confirm PASS** (Task 6 already implemented the behavior)

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "off_target or non_fungible or retry_then_ok or fails_open" -v`
Expected: PASS (4 tests). If `test_grounding_and_responsiveness_retries_are_non_fungible` fails because the scripted turn count doesn't line up with the round flow, adjust the number of scripted turns to match (the invariant under test is: two distinct resets occur and the final status is `answer`).

- [ ] **Step 3: Run the full cuaderno suite**

Run: `python -m pytest tests/ -k cuaderno -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cuaderno_compositor.py
git commit -m "test(cuaderno): off_target, fail-open, and non-fungible per-property retries"
```

---

## Task 8: Wire the real judge through the server

**Files:** Modify `src/copyclip/intelligence/cuaderno/provider.py`, `src/copyclip/intelligence/cuaderno/ask_stream.py`, `src/copyclip/intelligence/server.py`; Test `tests/test_cuaderno_provider.py`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_provider.py`:

```python
def test_resolve_judge_model_defaults():
    from copyclip.intelligence.cuaderno.provider import resolve_judge_model
    # Anthropic -> haiku; other providers -> the answer model (always serveable).
    assert resolve_judge_model("anthropic", "claude-sonnet-4-5", overlay=None) == "claude-haiku-4-5"
    assert resolve_judge_model("deepseek", "deepseek-chat", overlay=None) == "deepseek-chat"
    assert resolve_judge_model("anthropic", "claude-sonnet-4-5", overlay="claude-opus-4-8") == "claude-opus-4-8"
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `python -m pytest tests/test_cuaderno_provider.py -k resolve_judge_model -v`
Expected: FAIL — `cannot import name 'resolve_judge_model'`.

- [ ] **Step 3: Implement `resolve_judge_model` in `provider.py`**:

```python
# Cheap default judge model per provider (the judge is classification, not authoring).
JUDGE_DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-haiku-4-5"}


def resolve_judge_model(provider: str, answer_model: str, overlay: Optional[str]) -> str:
    """The judge model: an explicit overlay wins; else a cheap per-provider
    default; else the answer model (always serveable by the current provider)."""
    if overlay:
        return overlay
    return JUDGE_DEFAULT_MODELS.get(provider, answer_model)
```

- [ ] **Step 4: Thread `judge` through `ask_stream.py`.** Add a `judge=None` keyword param to `iter_ask_events` and pass it into `iter_compose_events`:

```python
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
    judge=None,
) -> Iterator[dict[str, Any]]:
    ...
        for ev in iter_compose_events(
            client=client, question=question, project_root=project_root,
            project_id=project_id, conn=conn, model=model,
            max_tool_rounds=max_tool_rounds, max_tokens=max_tokens, judge=judge,
        ):
```

- [ ] **Step 5: Build the judge in `server.py`.** At the `/api/cuaderno/ask` handler, after `resolved = resolve_cuaderno_provider(conn)` and `client = build_cuaderno_client(resolved)`, build the judge callable and pass it to `iter_ask_events`:

```python
                    from .cuaderno.provider import resolve_judge_model
                    from .cuaderno.judge import judge_answer
                    judge_overlay = None
                    try:
                        row = conn.execute("SELECT value FROM config WHERE key=?",
                                           ("cuaderno_judge_model",)).fetchone()
                        judge_overlay = row[0] if row and row[0] else None
                    except Exception:
                        judge_overlay = None
                    judge_model = resolve_judge_model(
                        resolved["provider"], resolved["model"], judge_overlay)
                    judge = lambda q, b, l: judge_answer(
                        client=client, question=q, blocks=b, ledger=l, model=judge_model)
                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id, model=resolved["model"], judge=judge,
                    )
```

(Read the current handler block; only add the judge construction and the `judge=judge` argument — keep everything else identical.)

- [ ] **Step 6: Run the affected suites**

Run: `python -m pytest tests/test_cuaderno_provider.py tests/test_cuaderno_ask_stream.py tests/test_cuaderno_endpoint.py -q`
Expected: PASS. (`iter_ask_events` callers without `judge` still work — it defaults None.)

- [ ] **Step 7: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/provider.py src/copyclip/intelligence/cuaderno/ask_stream.py src/copyclip/intelligence/server.py tests/test_cuaderno_provider.py
git commit -m "feat(cuaderno): resolve judge model + wire the live judge through the ask endpoint"
```

---

## Task 9: Frontend — `off_target` status + banner + verdict type

**Files:** Modify `frontend/src/types/api.ts`, `frontend/src/components/cuaderno/frames/FrameDynamic.tsx`.

- [ ] **Step 1: `types/api.ts`.** Add `'off_target'` to `FrameStatus` and `verdict?` to `Frame`:

```typescript
export type FrameStatus =
  | 'answer'
  | 'insufficient_evidence'
  | 'ungrounded'
  | 'off_target'
  | 'partial'
  | 'fallback'
  | 'legacy'

export type Frame = {
  question: string
  blocks: Block[]
  status?: FrameStatus
  verdict?: Record<string, unknown> | null
}
```

Run `cd frontend && npx tsc -b` (exit 0). Commit:
```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno): off_target FrameStatus + Frame.verdict type"
```

- [ ] **Step 2: `FrameDynamic.tsx`.** Add the `off_target` entry to `STATUS_BANNER` (the banner only renders for mapped non-answer statuses; got_it is already suppressed for any `status` other than `answer`/`legacy`):

```typescript
  off_target: {
    kicker: 'off target',
    text: 'This is grounded in the code, but it answers a different question than you asked. Re-ask to redirect it to what you meant.',
  },
```

Run `cd frontend && npx tsc -b` (exit 0). Commit:
```bash
git add frontend/src/components/cuaderno/frames/FrameDynamic.tsx
git commit -m "feat(cuaderno): honest banner for off_target answers"
```

---

## Task 10: Full-suite green + manual smoke

**Files:** none (verification).

- [ ] **Step 1: Full Python suite (non-integration)**

Run: `python -m pytest tests/ -q -m "not integration"`
Expected: PASS, no failures.

- [ ] **Step 2: Frontend typecheck**

Run (from `frontend/`): `npx tsc -b`
Expected: exit 0.

- [ ] **Step 3: Manual smoke (optional, key-gated).** With a provider key, ask a "how" question whose answer is likely a definition; confirm the judge fires a responsiveness retry (or seals `off_target`); ask a question the repo cannot answer after real reads → `insufficient_evidence`.

- [ ] **Step 4: No commit (verification).**

---

## Self-Review (against the spec)

**Spec coverage:**
- §4.1 firing on every would-be-answer → Task 6 (judge runs only in the `verdict.status == answer` branch) ✓
- §4.2 judge call + fail-open + JudgeVerdict → Tasks 1, 2, 3 ✓
- §4.3 action mapping (ok/retry/insufficient) → Task 6 + `_judge_status` ✓
- §5 per-property non-fungible latches → Task 6 (`responsiveness_retry_used` separate from `grounding_retry_used`), Task 7 (non-fungibility test) ✓
- §6 off_target + persisted verdict (status=projection, verdict=record) → Task 4 (schema), Task 5 (cheap dict), Task 2 (judge dict), Task 6 (persist on every seal) ✓
- §7 post-stream, fail-open, honest banners → Task 6 (judge in terminal before frame), Task 9 (banner) ✓
- §9 components → judge.py (1,2), JUDGE_PROMPT (3), schema (4), quality (5), compositor (6), provider/ask_stream/server (8), frontend (9) ✓
- §11 testing strategy → mapped across Tasks 1-7, 10 ✓

**Placeholder scan:** none — every step has complete code/commands. The one ordering note (Task 3 before Task 2 Step 3, because Task 2 imports JUDGE_PROMPT) is called out explicitly, not left implicit.

**Type consistency:** `JudgeVerdict(question_kind, grounded, responsive, language_ok, decision, world, retry_directive, reason)` is constructed positionally in tests exactly as defined in Task 1. `judge_verdict_dict`/`cheap_verdict_dict` share the persisted shape (`grounded, responsive, language_ok, question_kind, world, reason, source`). `_seal`/`_judge_status`/`FRAME_STATUS_OFF_TARGET` are consistent across Tasks 4 and 6. `judge` is a `(question, blocks, ledger) -> JudgeVerdict` callable everywhere (compositor param, ask_stream param, server lambda).

**Known deferrals (documented):** UI-chrome i18n; a "checking…" indicator; surfacing `verdict` beyond the banner; `contradiction_detected`. All per spec §13.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-cuaderno-judge-phase2.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, two-stage review between tasks.
2. **Inline Execution** — execute tasks here via executing-plans, batch with checkpoints.

Which approach?
