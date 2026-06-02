# Cuaderno Answer Quality — Phase 1 (Deterministic Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cuaderno never seal a code-comprehension answer that consulted zero evidence as a confident answer, persist an honest per-frame `status`, and mirror the user's language — all deterministically, with no second LLM call.

**Architecture:** A per-turn *read ledger* in the compositor records which tool calls returned real content. At the terminal, a pure `quality.assess(...)` produces a `Frame.status`. The closing round is decoupled so an ungrounded finish can trigger **one** bounded grounding/language retry before sealing honestly. The verdict rides inside `frame_json`, so persistence and restore carry it for free. The frontend renders each non-`answer` status honestly and suppresses the "got it?" affirmation on non-answers.

**Tech Stack:** Python 3.14 (stdlib `http.server`, `sqlite3`, `dataclasses`), pytest (`asyncio_mode=auto`); React 18 + Vite + TypeScript (frontend, verified via `tsc -b` — the repo has no frontend unit-test runner).

**Scope note:** This is **Phase 1** of the approved spec (`docs/superpowers/specs/2026-06-01-cuaderno-answer-quality-design.md`). The semantic **judge** (Phase 2) and full UI-chrome i18n are deliberately deferred to their own plan. Phase-1 planning decision (narrows spec §11): without the judge we hard-seal only the high-confidence cardinal case (zero content-bearing reads on a code question → `ungrounded`); `insufficient_evidence` (World A, "consulted and genuinely empty") requires the judge and is produced in Phase 2. This avoids false-sealing legitimate answers that read code without emitting a formal citation block.

---

## File Structure

**Backend — create:**
- `src/copyclip/intelligence/cuaderno/read_ledger.py` — `is_content_bearing_read()` + `ReadLedger` (tracks content-bearing reads and read paths). Pure.
- `src/copyclip/intelligence/cuaderno/language.py` — `detect_language()` + `languages_match()`. Pure heuristic (es/en/unknown).
- `src/copyclip/intelligence/cuaderno/quality.py` — `assess()` → `QualityVerdict`. Pure; the Phase-1 status decision.
- `tests/test_cuaderno_read_ledger.py`, `tests/test_cuaderno_language.py`, `tests/test_cuaderno_quality.py` — unit tests.

**Backend — modify:**
- `src/copyclip/intelligence/cuaderno/schema.py` — `FRAME_STATUS_*` constants, `KNOWN_FRAME_STATUSES`, `Frame.status` field, `frame_to_dict`/`frame_from_dict` carry status (default `legacy` on read).
- `src/copyclip/intelligence/cuaderno/compositor.py` — build the ledger during dispatch; compute status at terminal; closing-round decouple; one bounded grounding/language retry; status on fallback paths.
- `src/copyclip/intelligence/cuaderno/ask_stream.py` — partial/disconnect terminal paths set `status`.
- `src/copyclip/intelligence/cuaderno/prompts.py` — language mirroring, ground-before-answer, answer-the-question-asked; a `GROUNDING_RETRY_DIRECTIVE`.

**Frontend — modify:**
- `frontend/src/types/api.ts` — `FrameStatus` union + `Frame.status`.
- `frontend/src/components/cuaderno/frames/FrameDynamic.tsx` — honest status banner.
- `frontend/src/components/cuaderno/Cuaderno.tsx` — suppress `GotItMarkers` on non-`answer` statuses.

---

## Task 1: `Frame.status` in the schema

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/schema.py`
- Test: `tests/test_cuaderno_schema.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_schema.py`:

```python
from copyclip.intelligence.cuaderno.schema import (
    Frame, Block, frame_to_dict, frame_from_dict,
    FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED, FRAME_STATUS_LEGACY,
    KNOWN_FRAME_STATUSES,
)


def test_frame_defaults_to_answer_status():
    f = Frame(question="q", blocks=[Block.lead("hi")])
    assert f.status == FRAME_STATUS_ANSWER


def test_frame_to_dict_includes_status():
    f = Frame(question="q", blocks=[Block.lead("hi")], status=FRAME_STATUS_UNGROUNDED)
    d = frame_to_dict(f)
    assert d["status"] == FRAME_STATUS_UNGROUNDED
    assert d["question"] == "q"
    assert d["blocks"] == [{"kind": "lead", "text": "hi"}]


def test_frame_from_dict_defaults_absent_status_to_legacy():
    # A pre-existing persisted frame has no "status" key.
    legacy = {"question": "q", "blocks": [{"kind": "lead", "text": "hi"}]}
    f = frame_from_dict(legacy)
    assert f.status == FRAME_STATUS_LEGACY


def test_frame_status_round_trip():
    f = Frame(question="q", blocks=[Block.paragraph("p")], status=FRAME_STATUS_UNGROUNDED)
    assert frame_from_dict(frame_to_dict(f)).status == FRAME_STATUS_UNGROUNDED


def test_known_frame_statuses_membership():
    assert FRAME_STATUS_ANSWER in KNOWN_FRAME_STATUSES
    assert FRAME_STATUS_LEGACY in KNOWN_FRAME_STATUSES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_schema.py -k "status or legacy" -v`
Expected: FAIL — `ImportError: cannot import name 'FRAME_STATUS_ANSWER'`.

- [ ] **Step 3: Implement in `schema.py`** — add constants near the top (after imports) and modify `Frame`, `frame_to_dict`, `frame_from_dict`:

```python
# Frame-level verdict about answer quality (see the answer-quality spec).
FRAME_STATUS_ANSWER = "answer"                       # a normal, grounded answer
FRAME_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # World A: consulted, genuinely empty
FRAME_STATUS_UNGROUNDED = "ungrounded"               # World B: never consulted the code
FRAME_STATUS_PARTIAL = "partial"                     # interrupted mid-composition
FRAME_STATUS_FALLBACK = "fallback"                   # no blocks / budget exhausted
FRAME_STATUS_LEGACY = "legacy"                       # pre-existing frame with no recorded status

KNOWN_FRAME_STATUSES: frozenset[str] = frozenset({
    FRAME_STATUS_ANSWER, FRAME_STATUS_INSUFFICIENT_EVIDENCE, FRAME_STATUS_UNGROUNDED,
    FRAME_STATUS_PARTIAL, FRAME_STATUS_FALLBACK, FRAME_STATUS_LEGACY,
})
```

Change the `Frame` dataclass:

```python
@dataclass
class Frame:
    question: str
    blocks: list[Block]
    status: str = FRAME_STATUS_ANSWER
```

Change `frame_to_dict` and `frame_from_dict`:

```python
def frame_to_dict(f: Frame) -> dict[str, Any]:
    return {
        "question": f.question,
        "blocks": [b.to_dict() for b in f.blocks],
        "status": f.status,
    }


def frame_from_dict(d: dict[str, Any]) -> Frame:
    return Frame(
        question=d["question"],
        blocks=[Block.from_dict(b) for b in d["blocks"]],
        status=d.get("status", FRAME_STATUS_LEGACY),
    )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_schema.py -k "status or legacy" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Fix the now-broken exact-equality tests across the suite.** Adding `status` to `frame_to_dict` breaks every test that asserts an exact frame dict.

Run: `python -m pytest tests/test_cuaderno_compositor.py tests/test_cuaderno_ask_stream.py tests/test_cuaderno_endpoint.py -v`
Expected: several FAILs on assertions like `events[2]["frame"] == {"question": ..., "blocks": ...}`.

For each failing exact-equality assertion, add `"status": "answer"` to the expected dict. Example in `tests/test_cuaderno_compositor.py::test_emits_blocks_then_frame_in_one_turn`:

```python
    assert events[2]["frame"] == {
        "question": "q",
        "blocks": [{"kind": "lead", "text": "hi"},
                   {"kind": "paragraph", "text": "body"}],
        "status": "answer",
    }
```

(Apply the same `"status": "answer"` addition to `test_implicit_finish_on_end_turn`, `test_emit_block_across_two_turns_emits_once`, and any equivalent exact-frame assertions the run reports. Budget/fallback exact-frame assertions get `"status": "fallback"` once Task 5 lands — for now they only check substrings, so they pass.)

- [ ] **Step 6: Run the full cuaderno suite to confirm green**

Run: `python -m pytest tests/ -k cuaderno -q`
Expected: PASS (no failures).

- [ ] **Step 7: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/schema.py tests/test_cuaderno_schema.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): add Frame.status verdict field (default legacy on read)"
```

---

## Task 2: Content-bearing read ledger

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/read_ledger.py`
- Test: `tests/test_cuaderno_read_ledger.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_cuaderno_read_ledger.py`:

```python
from copyclip.intelligence.cuaderno.read_ledger import (
    is_content_bearing_read, ReadLedger,
)


def test_read_file_with_lines_is_content_bearing():
    assert is_content_bearing_read("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})


def test_read_file_error_is_not_content_bearing():
    assert not is_content_bearing_read("read_file", {"error": "file_not_found", "path": "a.py"})


def test_empty_grep_symbols_is_not_content_bearing():
    assert not is_content_bearing_read("grep_symbols", {"symbols": []})


def test_nonempty_grep_symbols_is_content_bearing():
    assert is_content_bearing_read("grep_symbols", {"symbols": [{"name": "f"}]})


def test_list_dir_with_entries_is_content_bearing():
    assert is_content_bearing_read("list_dir", {"path": ".", "entries": ["a", "b"]})


def test_answer_tools_are_never_content_bearing_reads():
    assert not is_content_bearing_read("emit_block", {"kind": "lead", "text": "x"})
    assert not is_content_bearing_read("finish", {"ok": True})


def test_ledger_counts_and_paths():
    led = ReadLedger()
    led.record("list_dir", {"path": ".", "entries": ["a"]})
    led.record("read_file", {"path": "src/a.py", "lines": [{"n": 1, "text": "x"}]})
    led.record("read_file", {"error": "file_not_found", "path": "missing.py"})
    assert led.content_bearing_count == 2
    assert "src/a.py" in led.read_paths
    assert "missing.py" not in led.read_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_read_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: ... read_ledger`.

- [ ] **Step 3: Implement `read_ledger.py`**

```python
from __future__ import annotations

from typing import Any

from .tool_catalog import ANSWER_TOOLS

# Per-tool key whose non-empty value means the read returned real content.
_CONTENT_KEYS: tuple[str, ...] = (
    "lines", "entries", "symbols", "callers", "callees",
    "commits", "blame", "diff", "tests",
)


def is_content_bearing_read(tool_name: str, result: dict[str, Any]) -> bool:
    """True iff a research-tool call returned real evidence.

    Excludes answer tools (emit_block/finish), anything with an "error" key, and
    results whose content payload is empty (e.g. grep_symbols → {"symbols": []},
    the NORMAL path on an unanalyzed project).
    """
    if tool_name in ANSWER_TOOLS:
        return False
    if not isinstance(result, dict) or result.get("error"):
        return False
    return any(result.get(k) for k in _CONTENT_KEYS)


class ReadLedger:
    """Accumulates, across a turn, which reads returned content and which file
    paths were actually read. Request-local; never shared across threads."""

    def __init__(self) -> None:
        self.content_bearing_count = 0
        self.read_paths: set[str] = set()

    def record(self, tool_name: str, result: dict[str, Any]) -> None:
        if is_content_bearing_read(tool_name, result):
            self.content_bearing_count += 1
            path = result.get("path")
            if isinstance(path, str) and path:
                self.read_paths.add(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_read_ledger.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/read_ledger.py tests/test_cuaderno_read_ledger.py
git commit -m "feat(cuaderno): content-bearing read ledger"
```

---

## Task 3: Language detection

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/language.py`
- Test: `tests/test_cuaderno_language.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_cuaderno_language.py`:

```python
from copyclip.intelligence.cuaderno.language import detect_language, languages_match


def test_detects_spanish_question():
    assert detect_language("¿cómo funciona el analizador?") == "es"


def test_detects_english_question():
    assert detect_language("how does the analyzer work?") == "en"


def test_short_ambiguous_is_unknown():
    assert detect_language("ok") == "unknown"


def test_accent_or_inverted_punctuation_forces_spanish():
    assert detect_language("como funciona?") == "es" or detect_language("¿y?") == "es"


def test_languages_match_treats_unknown_as_compatible():
    assert languages_match("unknown", "en")
    assert languages_match("es", "unknown")
    assert languages_match("es", "es")
    assert not languages_match("es", "en")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_language.py -v`
Expected: FAIL — `ModuleNotFoundError: ... language`.

- [ ] **Step 3: Implement `language.py`** (cheap heuristic; no external dependency)

```python
from __future__ import annotations

import re

# Spanish-only orthographic signals — any one is decisive.
_ES_CHARS = set("áéíóúñ¿¡")
_ES_WORDS = {
    "el", "la", "los", "las", "un", "una", "qué", "que", "cómo", "como",
    "por", "para", "dónde", "donde", "cuál", "cual", "funciona", "hace",
    "y", "de", "es", "con", "sin", "porque", "cuando", "este", "esta",
}
_EN_WORDS = {
    "the", "how", "what", "why", "does", "do", "is", "are", "a", "an",
    "of", "and", "to", "in", "this", "that", "where", "which", "with", "for",
}


def detect_language(text: str) -> str:
    """Return 'es', 'en', or 'unknown'. Cheap, dependency-free, biased toward
    the es/en pair the cuaderno actually serves. Spanish orthography (accents,
    inverted punctuation) is decisive; otherwise a stopword vote decides."""
    if not text:
        return "unknown"
    low = text.lower()
    if any(ch in _ES_CHARS for ch in low):
        return "es"
    words = re.findall(r"[a-záéíóúñ]+", low)
    if len(words) < 2:
        return "unknown"
    es = sum(1 for w in words if w in _ES_WORDS)
    en = sum(1 for w in words if w in _EN_WORDS)
    if es == en:
        return "unknown"
    return "es" if es > en else "en"


def languages_match(a: str, b: str) -> bool:
    """Unknown is compatible with anything (we never penalize on uncertainty)."""
    if a == "unknown" or b == "unknown":
        return True
    return a == b
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_language.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/language.py tests/test_cuaderno_language.py
git commit -m "feat(cuaderno): cheap es/en language detection"
```

---

## Task 4: The cheap quality verdict

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/quality.py`
- Test: `tests/test_cuaderno_quality.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_cuaderno_quality.py`:

```python
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.quality import assess, looks_like_code_question
from copyclip.intelligence.cuaderno.schema import (
    Block, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED,
)


def _ledger(content_reads: int) -> ReadLedger:
    led = ReadLedger()
    for i in range(content_reads):
        led.record("read_file", {"path": f"f{i}.py", "lines": [{"n": 1, "text": "x"}]})
    return led


def test_code_question_with_zero_reads_is_ungrounded():
    v = assess(question="how does the analyzer work?",
               blocks=[Block.lead("It is a CLI that scans your codebase.")],
               ledger=_ledger(0))
    assert v.status == FRAME_STATUS_UNGROUNDED
    assert v.suspicion is True


def test_code_question_with_reads_is_answer():
    v = assess(question="how does the analyzer work?",
               blocks=[Block.lead("It walks the AST in analyzer.py.")],
               ledger=_ledger(2))
    assert v.status == FRAME_STATUS_ANSWER


def test_meta_question_with_zero_reads_is_answer():
    v = assess(question="what can I ask you?",
               blocks=[Block.lead("Ask broad, relational, or atomic questions.")],
               ledger=_ledger(0))
    assert v.status == FRAME_STATUS_ANSWER


def test_language_mismatch_sets_suspicion_but_not_ungrounded():
    # Spanish question, English answer, but grounded → suspicion for the retry,
    # status stays answer (language is corrected by retry, not sealed).
    v = assess(question="¿cómo funciona el analizador?",
               blocks=[Block.lead("It walks the AST in analyzer.py.")],
               ledger=_ledger(1))
    assert v.status == FRAME_STATUS_ANSWER
    assert v.suspicion is True
    assert v.language_mismatch is True


def test_looks_like_code_question_detects_meta():
    assert looks_like_code_question("how does read_file work?") is True
    assert looks_like_code_question("what can I ask you?") is False
    assert looks_like_code_question("por qué respondiste en inglés?") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: ... quality`.

- [ ] **Step 3: Implement `quality.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from .language import detect_language, languages_match
from .read_ledger import ReadLedger
from .schema import Block, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED

# Question phrasings that are ABOUT the tutor/session, not the code. These never
# require evidence, so a zero-read answer to one of them is legitimate.
_META_MARKERS = (
    "what can i ask", "qué te puedo preguntar", "que te puedo preguntar",
    "qué me puedes", "que me puedes", "why did you", "por qué respondiste",
    "por que respondiste", "who are you", "quién eres", "quien eres",
    "how do i use", "cómo te uso", "como te uso",
)


def looks_like_code_question(question: str) -> bool:
    """Conservative: a question is code-comprehension unless it clearly targets
    the tutor/session itself. Default True so the gate errs toward demanding
    evidence."""
    low = question.lower().strip()
    return not any(m in low for m in _META_MARKERS)


def _answer_text(blocks: list[Block]) -> str:
    parts: list[str] = []
    for b in blocks:
        for key in ("text",):
            v = b.data.get(key)
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts)


@dataclass
class QualityVerdict:
    status: str
    suspicion: bool
    language_mismatch: bool
    reason: str


def assess(*, question: str, blocks: list[Block], ledger: ReadLedger) -> QualityVerdict:
    """Phase-1 deterministic verdict. Hard-seals ONLY the cardinal case
    (code question + zero content-bearing reads → ungrounded). Language
    mismatch raises suspicion (for the one retry) but does not seal."""
    q_lang = detect_language(question)
    a_lang = detect_language(_answer_text(blocks))
    language_mismatch = not languages_match(q_lang, a_lang)

    codey = looks_like_code_question(question)
    if codey and ledger.content_bearing_count == 0:
        return QualityVerdict(
            status=FRAME_STATUS_UNGROUNDED,
            suspicion=True,
            language_mismatch=language_mismatch,
            reason="code question answered with zero content-bearing reads",
        )
    return QualityVerdict(
        status=FRAME_STATUS_ANSWER,
        suspicion=language_mismatch,
        language_mismatch=language_mismatch,
        reason="ok" if not language_mismatch else "language mismatch",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_quality.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/quality.py tests/test_cuaderno_quality.py
git commit -m "feat(cuaderno): Phase-1 deterministic quality verdict"
```

---

## Task 5: Wire the ledger + verdict into the compositor terminal

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`
- Test: `tests/test_cuaderno_compositor.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_compositor.py`:

```python
def test_pyrrhic_answer_is_sealed_ungrounded(tmp_path: Path):
    """Zero reads + a confident code answer → status ungrounded (the incident)."""
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
        project_root=str(tmp_path), project_id=1, conn=None,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "ungrounded or grounded_answer_is or fallback_are" -v`
Expected: FAIL — `KeyError: 'status'` or `assert 'answer' == 'ungrounded'`.

- [ ] **Step 3: Implement in `compositor.py`.** Add imports at top:

```python
from .read_ledger import ReadLedger
from .quality import assess
from .schema import (
    Block, Frame, frame_from_dict, frame_to_dict, validate_block_dict,
    FRAME_STATUS_FALLBACK,
)
```

Inside `iter_compose_events`, create the ledger next to `emitted`:

```python
    emitted: list[Block] = []
    ledger = ReadLedger()
```

In the tool-dispatch loop, record each successful dispatch into the ledger. Find the `result = dispatch_tool(...)` success branch and add the `ledger.record` call:

```python
                result = dispatch_tool(
                    name, args, project_root=project_root,
                    project_id=project_id, conn=conn,
                )
                ledger.record(name, result)
                ms = int((time.perf_counter() - t0) * 1000)
```

Add a helper that seals a real (non-fallback) answer frame with its verdict:

```python
def _sealed_frame(question: str, emitted: list[Block], ledger: ReadLedger) -> dict[str, Any]:
    verdict = assess(question=question, blocks=emitted, ledger=ledger)
    return frame_to_dict(Frame(question=question, blocks=emitted, status=verdict.status))
```

Replace the two terminal `yield {"type": "frame", ...}` sites that currently build from `emitted`. The explicit/implicit-finish branch (`if finish_seen or stop_reason != "tool_use":`):

```python
        if finish_seen or stop_reason != "tool_use":
            if emitted:
                yield {"type": "frame", "frame": _sealed_frame(question, emitted, ledger)}
            else:
                yield {"type": "frame",
                       "frame": frame_to_dict(
                           Frame(question=question,
                                 blocks=_fallback_frame(question, "the model produced no answer blocks").blocks,
                                 status=FRAME_STATUS_FALLBACK))}
            return
```

And the budget-exhausted branch at the end:

```python
    if emitted:
        yield {"type": "frame", "frame": _sealed_frame(question, emitted, ledger)}
    else:
        yield {"type": "frame",
               "frame": frame_to_dict(
                   Frame(question=question,
                         blocks=_fallback_frame(question, "tool-call budget exhausted").blocks,
                         status=FRAME_STATUS_FALLBACK))}
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "ungrounded or grounded_answer_is or fallback_are" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Update the fallback exact-substring tests if needed and run the whole compositor file**

Run: `python -m pytest tests/test_cuaderno_compositor.py -v`
Expected: PASS. (If `test_zero_blocks_yields_fallback_frame` / `test_budget_exhausted_yields_fallback_frame` now want a status assertion, they already pass on the substring check; optionally add `assert frame["frame"]["status"] == "fallback"`.)

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): seal frames with the deterministic quality verdict"
```

---

## Task 6: Decouple the closing round + one bounded grounding/language retry

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`, `src/copyclip/intelligence/cuaderno/prompts.py`
- Test: `tests/test_cuaderno_compositor.py`

**Design:** When the model attempts `finish` ungrounded **and** budget remains **and** we have not already retried, inject a corrective directive, keep the research tools, and consume one normal round. The retry fires at most once, guarded by a local flag — bounding worst-case round-trips at `max_tool_rounds`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_compositor.py`:

```python
def test_ungrounded_finish_triggers_one_grounding_retry(tmp_path: Path):
    """Turn 1: ungrounded finish (no reads). The gate must NOT seal; it injects
    a grounding directive and grants another round. Turn 2: the model reads and
    composes → status answer. Exactly one retry."""
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
    # The retry round kept research tools (not stripped to answer-only).
    retry_call = client.calls[1]
    retry_names = {t["name"] for t in retry_call["tools"]}
    assert "read_file" in retry_names


def test_grounding_retry_fires_at_most_once(tmp_path: Path):
    """Model stays ungrounded across both the original finish and the retry →
    sealed ungrounded, no infinite loop, and the gate does not retry twice."""
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
    # Original finish + exactly one retry = 2 stream calls (not 8).
    assert len(client.calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "grounding_retry" -v`
Expected: FAIL — the ungrounded finish seals immediately (status ungrounded on turn 1; only 1 call), so both assertions fail.

- [ ] **Step 3: Add the directive to `prompts.py`**

```python
GROUNDING_RETRY_DIRECTIVE = (
    "Your answer is not yet anchored to the code: you have not read evidence "
    "that supports it. Do NOT finish yet. Use the read tools now to ground the "
    "specific claims you want to make, cite what you read, and answer the "
    "question that was actually asked. This supersedes any earlier guidance to "
    "stop reading."
)
```

- [ ] **Step 4: Implement the retry in `compositor.py`.** Import the directive and `assess`:

```python
from .prompts import SYSTEM_PROMPT, CLOSING_DIRECTIVE, GROUNDING_RETRY_DIRECTIVE
```

Add a local flag before the round loop:

```python
    emitted: list[Block] = []
    ledger = ReadLedger()
    grounding_retry_used = False
```

In the terminal branch, before sealing, intercept an ungrounded finish when budget remains and a retry has not been used. Replace the finish branch body:

```python
        if finish_seen or stop_reason != "tool_use":
            if emitted:
                verdict = assess(question=question, blocks=emitted, ledger=ledger)
                rounds_left = round_i < max_tool_rounds - 1
                if (verdict.status != FRAME_STATUS_ANSWER
                        and not grounding_retry_used and rounds_left):
                    # Refuse the close: inject a grounding directive, KEEP tools,
                    # spend one more normal round. Fires at most once.
                    grounding_retry_used = True
                    _inject_directive(messages, GROUNDING_RETRY_DIRECTIVE)
                    continue
                yield {"type": "frame",
                       "frame": frame_to_dict(
                           Frame(question=question, blocks=emitted, status=verdict.status))}
            else:
                yield {"type": "frame",
                       "frame": frame_to_dict(
                           Frame(question=question,
                                 blocks=_fallback_frame(question, "the model produced no answer blocks").blocks,
                                 status=FRAME_STATUS_FALLBACK))}
            return
```

Add the import for `FRAME_STATUS_ANSWER` to the schema import line. Note: `_sealed_frame` from Task 5 is now inlined here (delete the `_sealed_frame` helper if it is now unused, or keep it for the budget branch). Keep the budget branch using `_sealed_frame` for consistency.

Because `continue` re-enters the loop, the injected directive is the trailing user turn and the next `for` iteration drives a fresh stream call with the full toolset (research tools are only stripped on the genuine closing round — that logic is unchanged). The `grounding_retry_used` guard lives outside the retryable path, so the retry cannot re-fire.

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_compositor.py -k "grounding_retry" -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the whole compositor + prompt files**

Run: `python -m pytest tests/test_cuaderno_compositor.py tests/test_cuaderno_prompt.py -v`
Expected: PASS. (`test_final_round_forces_an_answer` still passes: that model reads first, so it is grounded on its closing answer — no retry triggered.)

- [ ] **Step 7: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py src/copyclip/intelligence/cuaderno/prompts.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): one bounded grounding retry before sealing ungrounded"
```

---

## Task 7: Status on the partial / disconnect terminal paths

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/ask_stream.py`
- Test: `tests/test_cuaderno_ask_stream.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_ask_stream.py` (mirror the existing fixtures in that file for `conn`/session setup; this test asserts the persisted partial frame carries `status="partial"`):

```python
import json


def test_partial_persist_marks_status_partial(tmp_path, cuaderno_conn):
    """When the underlying generator yields blocks then errors with partial=True,
    the persisted frame must be status 'partial', not a normal answer."""
    from copyclip.intelligence.cuaderno.ask_stream import iter_ask_events

    def fake_events():
        yield {"type": "block", "block": {"kind": "lead", "text": "half"}}
        yield {"type": "error", "message": "stream died", "partial": True}

    import copyclip.intelligence.cuaderno.ask_stream as mod
    orig = mod.iter_compose_events
    mod.iter_compose_events = lambda **kw: fake_events()
    try:
        sid = "sess-partial"
        _ensure_session(cuaderno_conn, sid)  # helper already in this test module
        list(iter_ask_events(
            client=object(), question="q", project_root=str(tmp_path),
            project_id=1, conn=cuaderno_conn, session_id=sid,
        ))
    finally:
        mod.iter_compose_events = orig

    row = cuaderno_conn.execute(
        "SELECT frame_json FROM cuaderno_questions WHERE session_id=?", (sid,)
    ).fetchone()
    assert json.loads(row[0])["status"] == "partial"
```

> If `cuaderno_conn` / `_ensure_session` fixtures are not already in this file, copy the session-setup pattern from `tests/test_cuaderno_persistence.py` (it constructs the schema via the same `db` init) into a small local fixture at the top of this test module.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_ask_stream.py -k partial -v`
Expected: FAIL — persisted status is `legacy`/`answer`, not `partial`.

- [ ] **Step 3: Implement in `ask_stream.py`.** Change `_persist_partial` to seal `partial`:

```python
from .schema import Block, Frame, frame_from_dict, FRAME_STATUS_PARTIAL


def _persist_partial(conn, session_id: str, question: str, emitted: list[dict]) -> None:
    pframe = Frame(
        question=question,
        blocks=[Block.from_dict(b) for b in emitted],
        status=FRAME_STATUS_PARTIAL,
    )
    save_question(conn, session_id, question, pframe)
```

(The clean `frame` event path already carries the compositor's sealed status via `ev["frame"]`; persist it unchanged — `frame_from_dict(ev["frame"])` now reads `status` automatically.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_ask_stream.py -k partial -v`
Expected: PASS.

- [ ] **Step 5: Run the whole ask_stream file**

Run: `python -m pytest tests/test_cuaderno_ask_stream.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/ask_stream.py tests/test_cuaderno_ask_stream.py
git commit -m "feat(cuaderno): persist partial frames with status=partial"
```

---

## Task 8: Prompt — language mirroring, ground-before-answer, answer-the-question

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/prompts.py`
- Test: `tests/test_cuaderno_prompt.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_cuaderno_prompt.py`:

```python
from copyclip.intelligence.cuaderno.prompts import SYSTEM_PROMPT


def test_prompt_requires_language_mirroring():
    low = SYSTEM_PROMPT.lower()
    assert "language" in low and ("same language" in low or "user's language" in low)


def test_prompt_requires_grounding_before_answering():
    low = SYSTEM_PROMPT.lower()
    assert "before" in low and ("read" in low or "evidence" in low)


def test_prompt_requires_answering_the_question_asked():
    low = SYSTEM_PROMPT.lower()
    assert "asked" in low or "how" in low and "what" in low
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_prompt.py -k "mirroring or grounding_before or question_asked" -v`
Expected: FAIL — the current prompt has no language clause.

- [ ] **Step 3: Edit `SYSTEM_PROMPT` in `prompts.py`.** Add a new rule to the Hard rules block and a Language clause; soften the efficiency directives so they no longer fight grounding. Add after Hard rule #4:

```
5. Answer the question that was ACTUALLY asked. If asked HOW something works,
   explain the mechanism, not merely what it is. Do not substitute a definition
   for an explanation.
6. Respond in the SAME LANGUAGE as the user's question. If the question is in
   Spanish, answer in Spanish; if in English, answer in English. This applies to
   every block, including kickers and follow-up labels.
```

In the "How to explore" section, change the efficiency lines so grounding wins ties. Replace:

```
- Prefer to answer after 1–4 well-chosen reads. You rarely need more. When you
  have enough to say something true and anchored, STOP reading and emit your
  answer — do not keep exploring to feel thorough.
```

with:

```
- Read before you answer. Do not answer a question about the code from memory or
  from the question alone — open the files that bear on it first. A confident
  answer with no reads is a failure, not efficiency.
- Once you have read enough to anchor your specific claims, stop and answer —
  do not keep exploring past that point. But "enough" is never zero for a
  question about how the code works.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/prompts.py tests/test_cuaderno_prompt.py
git commit -m "feat(cuaderno): prompt mirrors language, grounds before answering, answers the question asked"
```

---

## Task 9: Frontend — `Frame.status` type

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add the type.** Find `export type Frame = { question: string; blocks: Block[] }` (~line 826) and replace with:

```typescript
export type FrameStatus =
  | 'answer'
  | 'insufficient_evidence'
  | 'ungrounded'
  | 'partial'
  | 'fallback'
  | 'legacy'

export type Frame = {
  question: string
  blocks: Block[]
  status?: FrameStatus
}
```

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npx tsc -b`
Expected: exit 0 (no errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno): Frame.status type on the frontend"
```

---

## Task 10: Frontend — honest status banner

**Files:**
- Modify: `frontend/src/components/cuaderno/frames/FrameDynamic.tsx`

- [ ] **Step 1: Implement the banner.** In `FrameDynamic.tsx`, add a small map and render it above the blocks when status is a non-answer. At the top of the file (after imports):

```typescript
const STATUS_BANNER: Partial<Record<NonNullable<Frame['status']>, { kicker: string; text: string }>> = {
  ungrounded: {
    kicker: 'not grounded',
    text: 'This answer was not anchored to the code — the tutor answered without reading enough evidence. Re-ask, or rephrase to point at a specific file, function, or commit.',
  },
  insufficient_evidence: {
    kicker: 'insufficient evidence',
    text: 'The tutor looked but the project does not contain enough to answer this confidently. What it would need is named above.',
  },
  partial: {
    kicker: 'partial answer',
    text: 'This answer was interrupted before it finished. It may be incomplete.',
  },
  fallback: {
    kicker: 'no answer',
    text: 'The tutor could not produce an answer for this question this time.',
  },
}
```

In the returned JSX, render the banner right after the `cua-question` div and before the blocks map:

```tsx
  const banner = frame.status ? STATUS_BANNER[frame.status] : undefined
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">{frame.question}</span>
      </div>
      {banner ? (
        <div className="callout" role="status">
          <div className="kicker">{banner.kicker}</div>
          <p>{banner.text}</p>
        </div>
      ) : null}
      {frame.blocks.map((b, i) => (
        <BlockRender key={i} block={b} onOpenCitation={onOpenCitation} onAsk={onAsk} />
      ))}
    </>
  )
```

(Reuses the existing `.callout` styles — no new CSS.)

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npx tsc -b`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/frames/FrameDynamic.tsx
git commit -m "feat(cuaderno): honest banner for non-answer frame statuses"
```

---

## Task 11: Frontend — suppress "got it?" on non-answers

**Files:**
- Modify: `frontend/src/components/cuaderno/Cuaderno.tsx`

- [ ] **Step 1: Gate the GotItMarkers.** In `Cuaderno.tsx`, the `scene === 'frame'` branch renders `<GotItMarkers>` after `<FrameDynamic>`. Wrap it so it only shows for real answers (and legacy, to preserve old behavior):

```tsx
            {scene === 'frame' && activeQuestion && (
              <>
                <FrameDynamic
                  frame={activeQuestion.frame}
                  onOpenCitation={setSidePanelFor}
                  onAsk={onAsk}
                />
                {(!activeQuestion.frame.status ||
                  activeQuestion.frame.status === 'answer' ||
                  activeQuestion.frame.status === 'legacy') && (
                  <GotItMarkers
                    value={activeQuestion.got_it}
                    onSet={(v) => onSetGotIt(activeQuestion.position, v)}
                  />
                )}
              </>
            )}
```

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npx tsc -b`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/Cuaderno.tsx
git commit -m "feat(cuaderno): suppress got-it affirmation on non-answer frames"
```

---

## Task 12: Full-suite green + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the whole Python suite (excluding the key-gated live test)**

Run: `python -m pytest tests/ -k cuaderno -q -m "not integration"`
Expected: PASS, no failures.

- [ ] **Step 2: Frontend typecheck**

Run (from `frontend/`): `npx tsc -b`
Expected: exit 0.

- [ ] **Step 3: Manual smoke (optional, key-gated).** With a provider key configured, start the server, open the cuaderno, ask "como funciona?" — confirm the answer is in Spanish and, if it consults no code, renders the `ungrounded` banner with got-it suppressed.

- [ ] **Step 4: No commit (verification task).**

---

## Self-Review (against the spec)

**Spec coverage:**
- §4.1 content-bearing read → Task 2 ✓
- §4.2 suspicion signals (zero reads; language) → Task 4 ✓ (citation-vs-ledger cross-check and well-formed-citation suspicion deferred to Phase 2 with the judge — Phase 1 keys on the high-confidence zero-read signal; noted in the scope note)
- §5 taxonomy → Task 1 (constants) + Tasks 5/6/7 (assignment); `insufficient_evidence` production deferred to Phase 2 per the scope note ✓ (documented gap)
- §6 closing-round decouple + bounded retry → Task 6 ✓
- §7 persistence in frame_json + all terminal paths + legacy default → Tasks 1, 5, 7 ✓ (clean/fallback/partial covered; the SSE-disconnect GeneratorExit path reuses `_persist_partial` from Task 7 ✓)
- §8 honest UI + got-it suppression + frame-event authoritative → Tasks 10, 11 ✓ (streamed-provisional replacement already holds: `Cuaderno` renders `activeQuestion.frame`, set on the terminal `frame` event)
- §9 language: detect + mirror + cheap check → Tasks 3, 4, 8 ✓ (fixed UI-chrome i18n deferred — noted)
- §10 guaranteed vs hoped → encoded by construction (deterministic seals only for zero-read code Qs; relevance/responsiveness untouched in Phase 1)

**Placeholder scan:** none — every code step shows complete code; commands have expected output.

**Type consistency:** `FRAME_STATUS_*` constants and the `FrameStatus` union use identical literals (`answer`/`insufficient_evidence`/`ungrounded`/`partial`/`fallback`/`legacy`); `assess()` returns `QualityVerdict.status` consumed in Task 5/6; `ReadLedger.content_bearing_count`/`record` used consistently in Tasks 2, 4, 5.

**Known deferrals (documented, not gaps):** the semantic judge, `insufficient_evidence` production, citation-relevance/responsiveness checks, and fixed UI-chrome i18n are Phase 2.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-01-cuaderno-answer-quality-phase1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session via executing-plans, batch execution with checkpoints.

Which approach?
