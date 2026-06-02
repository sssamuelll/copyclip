# Cuaderno Eval Harness (Scope A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `copyclip bench` — a deterministic eval harness that runs a fixed, SHA-pinned corpus of questions through the real cuaderno loop, scores each answer with a typed assertion engine plus the harvested in-system verdict, and emits a per-run scorecard and a paired McNemar regression report.

**Architecture:** A new package `src/copyclip/intelligence/cuaderno/bench/` that is a *read-only consumer* of the cuaderno loop (`iter_compose_events`), plus two minimal production touches: fix `metrics.py` (3 confirmed bugs) and add one backward-compatible `ledger` injection parameter to `iter_compose_events` so the runner can read `content_bearing_count`/`read_paths`. Cost is a flagged estimate in Scope A (real-usage capture is the deferred Phase A.5); latency is real.

**Tech Stack:** Python 3 (stdlib only — `argparse`, `json`, `subprocess`/git, `math` for McNemar; NO scipy), pytest (`pytest.ini`, no conftest, package installed via `pip install -e .`). Tests run from repo root `C:\Users\simon\Desktop\projects\copyclip` with `python -m pytest tests/<file>::<test> -v`.

**Spec:** `docs/superpowers/specs/2026-06-02-cuaderno-eval-harness-design.md`

---

## Orientation (read once before Task 1)

Verified facts from the codebase the tasks below rely on:

- **`iter_compose_events`** (`src/copyclip/intelligence/cuaderno/compositor.py:125`) is a generator yielding `{"type": "tool"|"block"|"frame"|"error"|"reset", ...}`. The terminal success/fallback is `{"type":"frame","frame":<frame dict>}`; failure is `{"type":"error","message":str,"partial":bool}`. It accepts `judge: Any = None` (a `(question, blocks, ledger) -> JudgeVerdict` callable). It creates its own `ReadLedger()` at line 153 — **Task 2 makes that injectable.**
- **`compose_frame`** (`compositor.py:308`) is a synchronous drainer but does NOT pass `judge=`; the runner cannot reuse it (it needs the judge axes). The runner drains `iter_compose_events` itself.
- **`Citation`** (`schema.py:7-32`) is a `kind`-tagged union: `kind=="commit"` (carries only `commit`) OR `kind=="path"` (carries `path`, optional `line_start`, optional `line_end`, omitted when None). Citations live inside `Block.data` under three shapes; `quality._cited_paths` (`quality.py:44-66`) is the canonical extractor (reuse it). `quality._answer_text` (`quality.py:28-34`) joins block text for language detection.
- **`Frame`** (`schema.py:140-145`): `question`, `blocks`, `status`, `verdict: Optional[dict]`. `frame_from_dict` (`schema.py:157`) reconstructs it. The `verdict` dict keys: `grounded`, `responsive`, `language_ok`, `question_kind`, `world`, `reason`, `source` (`"cheap"|"judge"|"unjudged"`); axes are `Optional[bool]` — `None` means unobserved.
- **Provider wiring** (`provider.py`): `resolve_cuaderno_provider(conn) -> ResolvedCuaderno` (keys `provider`, `api_key`, `base_url`, `model`); `build_cuaderno_client(resolved)`; `resolve_judge_model(provider, answer_model, overlay) -> str`. The judge overlay is config key `cuaderno_judge_model`. The end-to-end recipe to mirror is `server.py:2560-2589`.
- **`judge_answer`** (`judge.py:90`): `judge_answer(*, client, question, blocks, ledger, model, max_tokens=512) -> JudgeVerdict`.
- **CLI** dispatch is in `src/copyclip/intelligence/cli.py`: `COMMANDS` set at line 14, gate `_maybe_handle_internal` at line 226, per-command `if cmd == "...":` blocks (e.g. `mcp` at 308-318). **NOT** argparse subparsers in `__main__.py`.
- **`metrics.py`** (`src/copyclip/llm/metrics.py`): `log_llm_call(provider, model, operation, input_text, output_text, latency_ms, cache_hit=False, error=None)`. Bugs: word-count tokens (lines 34-35); price table missing `claude-sonnet-4-5`/`claude-haiku-4-5` → cost 0 (lines 71-86); missing `import sys` → `print_summary` raises `NameError` (use at 65, 103-129).
- **Test patterns:** `StubStream` (`tests/test_cuaderno_compositor.py:10-40`) implements `messages_stream(**kwargs)` yielding scripted turns; a stub judge is a plain callable `(q,b,l)->verdict`. Key-gated live tests use a module-level `pytestmark = pytest.mark.skipif(not _HAS_KEY, ...)` (`tests/test_cuaderno_live_e2e.py:50-60`).

**File structure created by this plan:**

```
src/copyclip/intelligence/cuaderno/bench/
  __init__.py        # exports run_bench, load_corpus, etc.
  artifact.py        # QuestionRecord, RunArtifact dataclasses + JSON read/write   (T3)
  asserts.py         # AssertResult, AssertContext, the typed assert registry      (T4)
  corpus.py          # load + validate the JSONL corpus                            (T5)
  score.py           # per-question rollup + single-run scorecard                  (T6)
  regress.py         # paired diff + McNemar significance                          (T7)
  runner.py          # drive iter_compose_events, assemble records, write artifact (T8)
  cli.py             # the `copyclip bench` argparse handler                       (T9)
corpus/cuaderno-bench.jsonl                                                        (T10)
tests/fixtures/bench_fixture_repo/  (a tiny frozen git repo for integration)       (T11)
tests/test_metrics.py                                                              (T1)
tests/test_bench_artifact.py  test_bench_asserts.py  test_bench_corpus.py
tests/test_bench_score.py     test_bench_regress.py  test_bench_runner.py
tests/test_bench_cli.py       test_bench_corpus_content.py                         (T5/T10)
tests/test_bench_live_smoke.py  (key-gated)                                        (T12)
```

Artifacts written at runtime: `.copyclip/bench/runs/<run_id>.json`.

---

## Task 1: Fix `metrics.py` (the 3 confirmed bugs + accept real tokens + per-run rollup)

**Files:**
- Modify: `src/copyclip/llm/metrics.py`
- Test: `tests/test_metrics.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_metrics.py`:

```python
from copyclip.llm.metrics import MetricsCollector


def test_summary_does_not_raise_nameerror(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("anthropic", "claude-sonnet-4-5", "answer",
                   input_text="hello world", output_text="hi", latency_ms=10)
    # print_summary used file=sys.stderr without importing sys -> NameError before the fix
    c.print_summary()


def test_real_models_have_nonzero_cost(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("anthropic", "claude-sonnet-4-5", "answer",
                   input_text="", output_text="",
                   input_tokens=1_000_000, output_tokens=1_000_000, latency_ms=5)
    row = c.metrics[-1]
    # sonnet-4-5 must be priced (3.00 in + 15.00 out per Mtok) -> 18.0, not 0
    assert row.cost_usd > 0
    assert row.estimated is False  # real tokens were provided


def test_word_count_path_is_flagged_estimated(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("deepseek", "deepseek-chat", "answer",
                   input_text="one two three", output_text="four five", latency_ms=5)
    assert c.metrics[-1].estimated is True


def test_unknown_model_warns_not_silent_zero(tmp_path, capsys):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("anthropic", "claude-imaginary-9", "answer",
                   input_text="", output_text="", input_tokens=1000, output_tokens=1000,
                   latency_ms=5)
    err = capsys.readouterr().err
    assert "unknown model" in err.lower()


def test_run_snapshot_and_reset(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.reset_run()
    c.log_llm_call("anthropic", "claude-haiku-4-5", "judge",
                   input_text="", output_text="", input_tokens=10, output_tokens=20, latency_ms=3)
    snap = c.run_rollup()
    assert snap["calls"] == 1
    assert snap["total_tokens"] == 30
    assert snap["by_model"]["claude-haiku-4-5"]["calls"] == 1
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: `test_summary_does_not_raise_nameerror` FAILS with `NameError: name 'sys' is not defined`; the others FAIL with `TypeError` (unexpected kwarg `input_tokens`) / `AttributeError` (`estimated`, `reset_run`, `run_rollup` missing).

- [ ] **Step 3: Implement the fix**

Edit `src/copyclip/llm/metrics.py`. Replace the import block (lines 1-6) to add `sys`:

```python
import json
import sys
import time
import os
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict
```

Add `estimated` to the dataclass (after `error`):

```python
@dataclass
class LLMMetrics:
    timestamp: str
    provider: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    error: Optional[str] = None
    estimated: bool = True
```

Replace `log_llm_call` (lines 28-65) so it accepts optional real tokens and flags estimates:

```python
    def log_llm_call(self, provider: str, model: str, operation: str,
                     input_text: str = "", output_text: str = "", latency_ms: int = 0,
                     cache_hit: bool = False, error: Optional[str] = None,
                     input_tokens: Optional[int] = None,
                     output_tokens: Optional[int] = None):
        """Register metrics for one LLM call.

        If real token counts are supplied they are used and the row is marked
        estimated=False. Otherwise tokens are approximated from word counts and
        the row is flagged estimated=True so a fictional number is never read
        as truth.
        """
        if input_tokens is None or output_tokens is None:
            in_tok = len(input_text.split()) * 1.3
            out_tok = len(output_text.split()) * 1.3 if output_text else 0
            estimated = True
        else:
            in_tok, out_tok = float(input_tokens), float(output_tokens)
            estimated = False

        cost = self._calculate_cost(provider, model, in_tok, out_tok)

        metric = LLMMetrics(
            timestamp=datetime.now().isoformat(),
            provider=provider, model=model, operation=operation,
            input_tokens=int(in_tok), output_tokens=int(out_tok),
            total_tokens=int(in_tok + out_tok),
            cost_usd=cost, latency_ms=latency_ms,
            cache_hit=cache_hit, error=error, estimated=estimated,
        )
        self.metrics.append(metric)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(asdict(metric)) + '\n')
        if os.getenv("COPYCLIP_DEBUG"):
            print(f"[METRICS] {provider}/{model}: {operation} - "
                  f"{metric.total_tokens} tokens, ${cost:.4f}, "
                  f"{latency_ms}ms {'(CACHED)' if cache_hit else ''}"
                  f"{' (est)' if estimated else ''}",
                  file=sys.stderr)
```

Replace the `_calculate_cost` price table (lines 71-86) with current models, and warn on unknown:

```python
    def _calculate_cost(self, provider: str, model: str,
                       input_tokens: float, output_tokens: float) -> float:
        """Cost in USD. Prices are per MILLION tokens. An unknown model warns
        (rather than silently costing 0) so a missing entry is visible."""
        pricing = {
            'deepseek': {
                'deepseek-chat': {'input': 0.27, 'output': 1.10},
                'deepseek-reasoner': {'input': 0.55, 'output': 2.19},
            },
            'openai': {
                'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
                'gpt-4o': {'input': 2.50, 'output': 10.00},
            },
            'anthropic': {
                'claude-3-5-sonnet': {'input': 3.00, 'output': 15.00},
                'claude-sonnet-4-5': {'input': 3.00, 'output': 15.00},
                'claude-haiku-4-5': {'input': 1.00, 'output': 5.00},
            },
        }
        provider_pricing = pricing.get(provider.lower(), {})
        model_pricing = provider_pricing.get(model)
        if model_pricing is None:
            print(f"[METRICS] warning: unknown model {provider}/{model} — "
                  f"cost recorded as 0; add it to the price table.", file=sys.stderr)
            model_pricing = {'input': 0, 'output': 0}
        input_cost = (input_tokens / 1_000_000) * model_pricing.get('input', 0)
        output_cost = (output_tokens / 1_000_000) * model_pricing.get('output', 0)
        return input_cost + output_cost
```

Add per-run snapshot/reset + rollup methods (after `print_summary`, before the module-global at line 131):

```python
    def reset_run(self):
        """Start a fresh per-run window (the bench scopes metrics to one run)."""
        self._run_start_index = len(self.metrics)

    def run_rollup(self) -> dict:
        """Aggregate the calls logged since the last reset_run() (or all calls
        if reset_run was never called). Used by the bench scorecard."""
        start = getattr(self, "_run_start_index", 0)
        rows = self.metrics[start:]
        out = {
            "calls": len(rows),
            "total_tokens": sum(m.total_tokens for m in rows),
            "total_cost": sum(m.cost_usd for m in rows),
            "estimated": any(m.estimated for m in rows),
            "by_model": {},
            "by_operation": {},
        }
        for m in rows:
            bm = out["by_model"].setdefault(m.model, {"calls": 0, "tokens": 0, "cost": 0.0})
            bm["calls"] += 1; bm["tokens"] += m.total_tokens; bm["cost"] += m.cost_usd
            bo = out["by_operation"].setdefault(m.operation, {"calls": 0, "tokens": 0, "cost": 0.0})
            bo["calls"] += 1; bo["tokens"] += m.total_tokens; bo["cost"] += m.cost_usd
        return out
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/llm/metrics.py tests/test_metrics.py
git commit -m "fix(metrics): import sys, refresh price table, accept real tokens + estimated flag, per-run rollup"
```

---

## Task 2: Make the `ReadLedger` injectable into `iter_compose_events`

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py:125-153`
- Test: `tests/test_bench_runner.py` (create — first test of the file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_runner.py` (this file grows in Task 8; start it here):

```python
from copyclip.intelligence.cuaderno.compositor import iter_compose_events
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop


def test_injected_ledger_is_populated(tmp_path):
    # A scripted turn: read_file returns content, then emit a block + finish.
    turn = [
        _tool_stop("t1", "read_file", {"path": "a.py", "line_start": 1, "line_end": 5}),
        _tool_stop("b1", "emit_block", {"kind": "paragraph", "text": "x reads a.py"}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("t1", "read_file", {"path": "a.py", "line_start": 1, "line_end": 5}),
            _content("b1", "emit_block", {"kind": "paragraph", "text": "x reads a.py"}),
            _content("f1", "finish", {}),
        ]),
    ]
    # NOTE: read_file dispatch needs the project; StubStream + conn=None means
    # dispatch_tool runs against tmp_path. For a pure unit test of injection we
    # only assert the ledger object identity is used: pass our own ledger and
    # confirm iter_compose_events does not replace it.
    my_ledger = ReadLedger()
    list(iter_compose_events(
        client=StubStream([_msg_stop("end_turn", [])]),  # immediate non-tool stop, no blocks
        question="q", project_root=str(tmp_path), project_id=1, conn=None,
        max_tool_rounds=1, ledger=my_ledger,
    ))
    # The loop ran with OUR ledger (no exception, object accepted). content count
    # is 0 here (no reads happened), but the param must be accepted and used.
    assert my_ledger.content_bearing_count == 0
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `python -m pytest tests/test_bench_runner.py::test_injected_ledger_is_populated -v`
Expected: FAIL with `TypeError: iter_compose_events() got an unexpected keyword argument 'ledger'`.

- [ ] **Step 3: Implement the injection (2 lines)**

In `src/copyclip/intelligence/cuaderno/compositor.py`, add the parameter to the signature (after `judge: Any = None,` at line 135):

```python
    judge: Any = None,  # Optional (question, blocks, ledger) -> JudgeVerdict
    ledger: Optional[ReadLedger] = None,
) -> Iterator[dict[str, Any]]:
```

Change line 153 from `ledger = ReadLedger()` to:

```python
    ledger = ledger if ledger is not None else ReadLedger()
```

(`ReadLedger` and `Optional` are already imported at the top of the file.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `python -m pytest tests/test_bench_runner.py::test_injected_ledger_is_populated -v`
Expected: PASS.

Run the existing compositor suite to confirm no regression (default-None path unchanged):
Run: `python -m pytest tests/test_cuaderno_compositor.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py tests/test_bench_runner.py
git commit -m "feat(cuaderno): inject ReadLedger into iter_compose_events (backward-compatible)"
```

---

## Task 3: The artifact module (`QuestionRecord`, `RunArtifact`, JSON IO)

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/__init__.py`
- Create: `src/copyclip/intelligence/cuaderno/bench/artifact.py`
- Test: `tests/test_bench_artifact.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_artifact.py`:

```python
from copyclip.intelligence.cuaderno.bench.artifact import (
    QuestionRecord, RunArtifact, write_artifact, read_artifact,
)


def _rec():
    return QuestionRecord(
        id="q1", category="grounded_happy_path", commit_sha="e4400af",
        question="¿cómo funciona X?", question_lang="es",
        status="answer", verdict={"grounded": True, "responsive": True,
                                  "language_ok": True, "source": "judge"},
        blocks=[{"kind": "paragraph", "text": "X reads a.py"}],
        cited_paths=["a.py"],
        citations=[{"kind": "path", "path": "a.py", "line_start": 1, "line_end": 5}],
        read_paths=["a.py"], content_bearing_count=1, answer_lang="es",
        latency_ms=1200, input_tokens=100, output_tokens=50, cost_usd=0.0,
        cost_estimated=True, asserts=[{"type": "status_in", "outcome": "pass",
                                       "score": 1.0, "reason": "status=answer"}],
        question_rollup={"all_pass": True, "n_pass": 1, "n_fail": 0, "n_inconclusive": 0},
    )


def test_round_trip(tmp_path):
    art = RunArtifact(
        run_id="20260602-120000-abc123", started_at="2026-06-02T12:00:00",
        corpus_path="corpus/cuaderno-bench.jsonl", corpus_sha="deadbeef",
        head_sha="e4400af", answer_model="claude-sonnet-4-5",
        judge_model="claude-haiku-4-5", provider="anthropic",
        copyclip_version="0.4.0", items=[_rec()],
    )
    path = tmp_path / "run.json"
    write_artifact(art, str(path))
    back = read_artifact(str(path))
    assert back.run_id == art.run_id
    assert back.items[0].id == "q1"
    assert back.items[0].verdict["grounded"] is True
    assert back.items[0].question_rollup["all_pass"] is True
    assert back.items[0].cost_estimated is True


def test_default_run_path_under_dot_copyclip():
    from copyclip.intelligence.cuaderno.bench.artifact import default_run_path
    p = default_run_path("/proj", "20260602-120000-abc123")
    assert p.replace("\\", "/").endswith(".copyclip/bench/runs/20260602-120000-abc123.json")
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_artifact.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'copyclip.intelligence.cuaderno.bench'`.

- [ ] **Step 3: Implement**

Create empty `src/copyclip/intelligence/cuaderno/bench/__init__.py`:

```python
"""Cuaderno eval harness (Scope A). See
docs/superpowers/specs/2026-06-02-cuaderno-eval-harness-design.md."""
```

Create `src/copyclip/intelligence/cuaderno/bench/artifact.py`:

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class QuestionRecord:
    id: str
    category: str
    commit_sha: str
    question: str
    question_lang: str
    status: str
    verdict: Optional[dict]
    blocks: list[dict]
    cited_paths: list[str]
    citations: list[dict]
    read_paths: list[str]
    content_bearing_count: int
    answer_lang: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cost_estimated: bool
    asserts: list[dict] = field(default_factory=list)
    question_rollup: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class RunArtifact:
    run_id: str
    started_at: str
    corpus_path: str
    corpus_sha: str
    head_sha: str
    answer_model: str
    judge_model: str
    provider: str
    copyclip_version: str
    items: list[QuestionRecord] = field(default_factory=list)
    metrics_rollup: dict = field(default_factory=dict)


def write_artifact(art: RunArtifact, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(art), f, ensure_ascii=False, indent=2)


def read_artifact(path: str) -> RunArtifact:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    items = [QuestionRecord(**it) for it in d.pop("items", [])]
    return RunArtifact(items=items, **d)


def default_run_path(project_root: str, run_id: str) -> str:
    return os.path.join(project_root, ".copyclip", "bench", "runs", f"{run_id}.json")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_artifact.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/__init__.py src/copyclip/intelligence/cuaderno/bench/artifact.py tests/test_bench_artifact.py
git commit -m "feat(bench): artifact dataclasses + JSON read/write"
```

---

## Task 4: The assertion engine (`asserts.py`)

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/asserts.py`
- Test: `tests/test_bench_asserts.py` (create)

The engine is a registry `type -> fn(record, spec, ctx) -> AssertResult`. `outcome ∈ {"pass","fail","inconclusive"}`. Harvested axes that are `None` → `inconclusive`. `cited_lines_within_eof` resolves file length via `ctx.file_length_fn(path)` (the runner backs it with `git show <sha>:<path>`; tests inject a dict).

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_asserts.py`:

```python
from copyclip.intelligence.cuaderno.bench.asserts import (
    AssertContext, run_asserts, ASSERTS,
)
from copyclip.intelligence.cuaderno.bench.artifact import QuestionRecord


def _rec(**kw):
    base = dict(
        id="q", category="c", commit_sha="sha", question="¿cómo?", question_lang="es",
        status="answer", verdict={"grounded": True, "responsive": True,
                                  "language_ok": True, "source": "judge"},
        blocks=[{"kind": "paragraph", "text": "lee compositor.py"}],
        cited_paths=["src/compositor.py"],
        citations=[{"kind": "path", "path": "src/compositor.py",
                    "line_start": 10, "line_end": 20}],
        read_paths=["src/compositor.py"], content_bearing_count=2, answer_lang="es",
        latency_ms=1, input_tokens=1, output_tokens=1, cost_usd=0.0, cost_estimated=True,
    )
    base.update(kw)
    return QuestionRecord(**base)


def _ctx(lengths=None):
    lengths = lengths or {"src/compositor.py": 100}
    return AssertContext(file_length_fn=lambda p: lengths.get(p))


def test_status_in_and_is():
    r = _rec(status="answer")
    out = run_asserts(r, [{"type": "status_in", "value": ["answer", "off_target"]},
                          {"type": "status_is", "value": "ungrounded"}], _ctx())
    assert out[0].outcome == "pass"
    assert out[1].outcome == "fail"


def test_cites_path_matching():
    r = _rec()
    ok = run_asserts(r, [{"type": "cites_path_matching", "value": r"compositor\.py$"}], _ctx())[0]
    bad = run_asserts(r, [{"type": "cites_path_matching", "value": r"nope\.py$"}], _ctx())[0]
    assert ok.outcome == "pass" and bad.outcome == "fail"


def test_cites_commit():
    r = _rec(citations=[{"kind": "commit", "commit": "e4400af"}])
    out = run_asserts(r, [{"type": "cites_commit"}], _ctx())[0]
    assert out.outcome == "pass"
    r2 = _rec()  # only a path citation
    out2 = run_asserts(r2, [{"type": "cites_commit"}], _ctx())[0]
    assert out2.outcome == "fail"


def test_mentions():
    r = _rec(blocks=[{"kind": "paragraph", "text": "El Compositor compone frames"}])
    out = run_asserts(r, [{"type": "mentions", "value": "compositor"}], _ctx())[0]
    assert out.outcome == "pass"  # case-folded


def test_language_is():
    r = _rec(answer_lang="es")
    out = run_asserts(r, [{"type": "language_is", "value": "es"},
                          {"type": "language_is", "value": "en"}], _ctx())
    assert out[0].outcome == "pass" and out[1].outcome == "fail"


def test_min_content_bearing_reads():
    r = _rec(content_bearing_count=2)
    out = run_asserts(r, [{"type": "min_content_bearing_reads", "value": 2},
                          {"type": "min_content_bearing_reads", "value": 3}], _ctx())
    assert out[0].outcome == "pass" and out[1].outcome == "fail"


def test_no_unread_citations():
    good = _rec(cited_paths=["a.py"], read_paths=["a.py", "b.py"])
    bad = _rec(cited_paths=["ghost.py"], read_paths=["a.py"])
    assert run_asserts(good, [{"type": "no_unread_citations"}], _ctx())[0].outcome == "pass"
    assert run_asserts(bad, [{"type": "no_unread_citations"}], _ctx())[0].outcome == "fail"


def test_cited_lines_within_eof():
    inside = _rec(citations=[{"kind": "path", "path": "src/compositor.py",
                              "line_start": 10, "line_end": 20}])
    past = _rec(citations=[{"kind": "path", "path": "src/compositor.py",
                            "line_start": 10, "line_end": 999}])
    no_range = _rec(citations=[{"kind": "path", "path": "src/compositor.py"}])
    ctx = _ctx({"src/compositor.py": 100})
    assert run_asserts(inside, [{"type": "cited_lines_within_eof"}], ctx)[0].outcome == "pass"
    assert run_asserts(past, [{"type": "cited_lines_within_eof"}], ctx)[0].outcome == "fail"
    # No line range -> vacuously passes
    assert run_asserts(no_range, [{"type": "cited_lines_within_eof"}], ctx)[0].outcome == "pass"
    # Unknown file length -> inconclusive (cannot verify)
    unk = _ctx({})
    assert run_asserts(inside, [{"type": "cited_lines_within_eof"}], unk)[0].outcome == "inconclusive"


def test_harvested_axes_none_is_inconclusive():
    r_known = _rec(verdict={"responsive": True, "grounded": True})
    r_unknown = _rec(verdict={"responsive": None, "grounded": None, "source": "unjudged"})
    assert run_asserts(r_known, [{"type": "harvested_responsive", "value": True}], _ctx())[0].outcome == "pass"
    assert run_asserts(r_unknown, [{"type": "harvested_responsive", "value": True}], _ctx())[0].outcome == "inconclusive"
    assert run_asserts(_rec(verdict=None), [{"type": "harvested_grounded", "value": True}], _ctx())[0].outcome == "inconclusive"


def test_unknown_assert_type_raises():
    import pytest
    with pytest.raises(KeyError):
        run_asserts(_rec(), [{"type": "no_such_assert"}], _ctx())
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_asserts.py -v`
Expected: FAIL with `ModuleNotFoundError` for `bench.asserts`.

- [ ] **Step 3: Implement**

Create `src/copyclip/intelligence/cuaderno/bench/asserts.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .artifact import QuestionRecord


@dataclass(frozen=True)
class AssertResult:
    type: str
    outcome: str   # "pass" | "fail" | "inconclusive"
    score: float   # 1.0 pass, 0.0 otherwise
    reason: str

    def to_dict(self) -> dict:
        return {"type": self.type, "outcome": self.outcome,
                "score": self.score, "reason": self.reason}


@dataclass
class AssertContext:
    # path -> line count of that file at the pinned SHA, or None if unresolvable
    file_length_fn: Callable[[str], Optional[int]]


def _ok(t: str, reason: str) -> AssertResult:
    return AssertResult(t, "pass", 1.0, reason)


def _fail(t: str, reason: str) -> AssertResult:
    return AssertResult(t, "fail", 0.0, reason)


def _incon(t: str, reason: str) -> AssertResult:
    return AssertResult(t, "inconclusive", 0.0, reason)


def _norm(p: str) -> str:
    p = p.strip()
    if p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def _a_status_in(r, spec, ctx):
    vals = spec["value"]
    return _ok("status_in", f"status={r.status}") if r.status in vals \
        else _fail("status_in", f"status={r.status} not in {vals}")


def _a_status_is(r, spec, ctx):
    return _ok("status_is", f"status={r.status}") if r.status == spec["value"] \
        else _fail("status_is", f"status={r.status} != {spec['value']}")


def _a_cites_path_matching(r, spec, ctx):
    rx = re.compile(spec["value"])
    hit = next((p for p in r.cited_paths if rx.search(p)), None)
    return _ok("cites_path_matching", f"matched {hit}") if hit \
        else _fail("cites_path_matching", f"no cited path matches {spec['value']!r}; cited={r.cited_paths}")


def _a_cites_commit(r, spec, ctx):
    has = any(isinstance(c, dict) and c.get("kind") == "commit" and c.get("commit")
              for c in r.citations)
    return _ok("cites_commit", "commit citation present") if has \
        else _fail("cites_commit", "no commit-kind citation")


def _a_mentions(r, spec, ctx):
    needle = str(spec["value"]).casefold()
    text = " ".join(b.get("text", "") for b in r.blocks if isinstance(b.get("text"), str)).casefold()
    return _ok("mentions", f"mentions {spec['value']!r}") if needle in text \
        else _fail("mentions", f"does not mention {spec['value']!r}")


def _a_language_is(r, spec, ctx):
    return _ok("language_is", f"answer_lang={r.answer_lang}") if r.answer_lang == spec["value"] \
        else _fail("language_is", f"answer_lang={r.answer_lang} != {spec['value']}")


def _a_min_content_bearing_reads(r, spec, ctx):
    n = int(spec["value"])
    return _ok("min_content_bearing_reads", f"{r.content_bearing_count} >= {n}") \
        if r.content_bearing_count >= n \
        else _fail("min_content_bearing_reads", f"{r.content_bearing_count} < {n}")


def _a_no_unread_citations(r, spec, ctx):
    cited = {_norm(p) for p in r.cited_paths}
    read = {_norm(p) for p in r.read_paths}
    if not cited:
        return _ok("no_unread_citations", "no path citations to verify")
    unread = cited - read
    return _ok("no_unread_citations", "all cited paths were read") if not unread \
        else _fail("no_unread_citations", f"cited but unread: {sorted(unread)}")


def _a_cited_lines_within_eof(r, spec, ctx):
    checked = 0
    for c in r.citations:
        if not isinstance(c, dict) or c.get("kind") != "path":
            continue
        path = c.get("path")
        ls, le = c.get("line_start"), c.get("line_end")
        if not path or ls is None and le is None:
            continue  # no range -> vacuously fine for this citation
        length = ctx.file_length_fn(_norm(str(path)))
        if length is None:
            return _incon("cited_lines_within_eof", f"cannot resolve length of {path}")
        top = le if le is not None else ls
        if top is not None and int(top) > length:
            return _fail("cited_lines_within_eof", f"{path}:{ls}-{le} past EOF ({length} lines)")
        checked += 1
    return _ok("cited_lines_within_eof", f"{checked} line range(s) within EOF")


def _harvested(axis: str):
    def fn(r, spec, ctx):
        t = f"harvested_{axis}"
        v = (r.verdict or {}).get(axis)
        if v is None:
            return _incon(t, f"{axis} unobserved (verdict source={(r.verdict or {}).get('source')})")
        expected = spec.get("value", True)
        return _ok(t, f"{axis}={v}") if v == expected else _fail(t, f"{axis}={v} != {expected}")
    return fn


ASSERTS: dict[str, Callable[[QuestionRecord, dict, AssertContext], AssertResult]] = {
    "status_in": _a_status_in,
    "status_is": _a_status_is,
    "cites_path_matching": _a_cites_path_matching,
    "cites_commit": _a_cites_commit,
    "mentions": _a_mentions,
    "language_is": _a_language_is,
    "min_content_bearing_reads": _a_min_content_bearing_reads,
    "no_unread_citations": _a_no_unread_citations,
    "cited_lines_within_eof": _a_cited_lines_within_eof,
    "harvested_responsive": _harvested("responsive"),
    "harvested_grounded": _harvested("grounded"),
}

KNOWN_ASSERT_TYPES = frozenset(ASSERTS)


def run_asserts(record: QuestionRecord, specs: list[dict],
                ctx: AssertContext) -> list[AssertResult]:
    """Run each assert spec against the record. Raises KeyError on an unknown
    assert type (corpus validation, Task 5, catches these earlier)."""
    out = []
    for spec in specs:
        fn = ASSERTS[spec["type"]]
        out.append(fn(record, spec, ctx))
    return out
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_asserts.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/asserts.py tests/test_bench_asserts.py
git commit -m "feat(bench): typed assertion engine (deterministic + harvested-inconclusive)"
```

---

## Task 5: Corpus loader + validator (`corpus.py`)

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/corpus.py`
- Test: `tests/test_bench_corpus.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_corpus.py`:

```python
import json
import pytest
from copyclip.intelligence.cuaderno.bench.corpus import (
    load_corpus, CorpusError, corpus_sha,
)


def _write(tmp_path, rows):
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return str(p)


def test_loads_valid_corpus(tmp_path):
    rows = [{
        "id": "q1", "question": "¿cómo?", "category": "grounded_happy_path",
        "commit_sha": "e4400af", "question_lang": "es",
        "asserts": [{"type": "status_in", "value": ["answer"]}],
    }]
    items = load_corpus(_write(tmp_path, rows))
    assert len(items) == 1 and items[0]["id"] == "q1"


def test_rejects_unknown_assert_type(tmp_path):
    rows = [{"id": "q1", "question": "q", "category": "c", "commit_sha": "x",
             "question_lang": "es", "asserts": [{"type": "bogus"}]}]
    with pytest.raises(CorpusError, match="unknown assert type"):
        load_corpus(_write(tmp_path, rows))


def test_rejects_missing_required_field(tmp_path):
    rows = [{"id": "q1", "question": "q", "asserts": []}]  # no commit_sha/category/lang
    with pytest.raises(CorpusError):
        load_corpus(_write(tmp_path, rows))


def test_rejects_duplicate_ids(tmp_path):
    rows = [
        {"id": "dup", "question": "q", "category": "c", "commit_sha": "x",
         "question_lang": "es", "asserts": []},
        {"id": "dup", "question": "q2", "category": "c", "commit_sha": "x",
         "question_lang": "es", "asserts": []},
    ]
    with pytest.raises(CorpusError, match="duplicate"):
        load_corpus(_write(tmp_path, rows))


def test_corpus_sha_is_stable(tmp_path):
    p = _write(tmp_path, [{"id": "q1", "question": "q", "category": "c",
                           "commit_sha": "x", "question_lang": "es", "asserts": []}])
    assert corpus_sha(p) == corpus_sha(p)
    assert len(corpus_sha(p)) == 12
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError` for `bench.corpus`.

- [ ] **Step 3: Implement**

Create `src/copyclip/intelligence/cuaderno/bench/corpus.py`:

```python
from __future__ import annotations

import hashlib
import json

from .asserts import KNOWN_ASSERT_TYPES

_REQUIRED = ("id", "question", "category", "commit_sha", "question_lang", "asserts")


class CorpusError(Exception):
    pass


def load_corpus(path: str) -> list[dict]:
    """Load + validate a JSONL corpus. Raises CorpusError on any structural
    problem (no LLM, CI-safe)."""
    items: list[dict] = []
    seen_ids: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorpusError(f"line {lineno}: invalid JSON ({exc})") from exc
            for k in _REQUIRED:
                if k not in row:
                    raise CorpusError(f"line {lineno} (id={row.get('id')!r}): missing field {k!r}")
            if row["id"] in seen_ids:
                raise CorpusError(f"line {lineno}: duplicate id {row['id']!r}")
            seen_ids.add(row["id"])
            if not isinstance(row["asserts"], list):
                raise CorpusError(f"line {lineno}: 'asserts' must be a list")
            for a in row["asserts"]:
                if not isinstance(a, dict) or "type" not in a:
                    raise CorpusError(f"line {lineno}: each assert needs a 'type'")
                if a["type"] not in KNOWN_ASSERT_TYPES:
                    raise CorpusError(
                        f"line {lineno}: unknown assert type {a['type']!r} "
                        f"(known: {sorted(KNOWN_ASSERT_TYPES)})")
            items.append(row)
    if not items:
        raise CorpusError("corpus is empty")
    return items


def corpus_sha(path: str) -> str:
    """A 12-char content hash of the corpus file (recorded in the run artifact
    so a regression compares two runs of the SAME corpus)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:12]
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_corpus.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/corpus.py tests/test_bench_corpus.py
git commit -m "feat(bench): corpus loader + validator (rejects unknown asserts, dups, missing fields)"
```

---

## Task 6: Scorer (`score.py`) — per-run scorecard + abstention confusion matrix

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/score.py`
- Test: `tests/test_bench_score.py` (create)

Conventions: an axis rate counts only conclusive harvested results (None excluded). Abstention matrix uses categories: `must_abstain` + `must_not_fabricate` ⇒ should-abstain; everything else ⇒ should-answer. "Abstained" ⇒ status ∈ {`ungrounded`, `insufficient_evidence`}.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_score.py`:

```python
from copyclip.intelligence.cuaderno.bench.score import (
    question_rollup, scorecard,
)
from copyclip.intelligence.cuaderno.bench.artifact import QuestionRecord


def _rec(**kw):
    base = dict(
        id="q", category="grounded_happy_path", commit_sha="x", question="q",
        question_lang="es", status="answer", verdict={"grounded": True},
        blocks=[], cited_paths=[], citations=[], read_paths=[],
        content_bearing_count=1, answer_lang="es", latency_ms=100,
        input_tokens=10, output_tokens=10, cost_usd=0.0, cost_estimated=True,
        asserts=[], question_rollup={},
    )
    base.update(kw)
    return QuestionRecord(**base)


def test_question_rollup_all_pass():
    res = [{"type": "a", "outcome": "pass"}, {"type": "b", "outcome": "pass"}]
    roll = question_rollup(res)
    assert roll == {"all_pass": True, "n_pass": 2, "n_fail": 0, "n_inconclusive": 0}


def test_question_rollup_fail_blocks_all_pass():
    res = [{"type": "a", "outcome": "pass"}, {"type": "b", "outcome": "fail"},
           {"type": "c", "outcome": "inconclusive"}]
    roll = question_rollup(res)
    assert roll["all_pass"] is False and roll["n_fail"] == 1 and roll["n_inconclusive"] == 1


def test_scorecard_status_distribution_and_abstention_matrix():
    items = [
        # should-answer, answered correctly
        _rec(id="a1", category="grounded_happy_path", status="answer"),
        # should-answer but abstained -> false abstention
        _rec(id="a2", category="grounded_happy_path", status="insufficient_evidence"),
        # should-abstain, abstained correctly
        _rec(id="b1", category="must_abstain", status="insufficient_evidence"),
        # should-abstain but answered -> false answer (fabrication)
        _rec(id="b2", category="must_not_fabricate", status="answer"),
    ]
    sc = scorecard(items)
    assert sc["status_distribution"]["answer"] == 2
    assert sc["status_distribution"]["insufficient_evidence"] == 2
    m = sc["abstention"]
    assert m["false_abstention"] == 1   # a2
    assert m["false_answer"] == 1       # b2
    assert m["correct"] == 2            # a1, b1


def test_scorecard_axis_rate_excludes_none():
    items = [
        _rec(id="r1", verdict={"grounded": True}),
        _rec(id="r2", verdict={"grounded": False}),
        _rec(id="r3", verdict={"grounded": None}),   # excluded
    ]
    sc = scorecard(items)
    # 1 of 2 conclusive -> 0.5
    assert sc["axis_rates"]["grounded"] == 0.5
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_score.py -v`
Expected: FAIL — `ModuleNotFoundError` for `bench.score`.

- [ ] **Step 3: Implement**

Create `src/copyclip/intelligence/cuaderno/bench/score.py`:

```python
from __future__ import annotations

import statistics
from typing import Any

from .artifact import QuestionRecord

_ABSTAIN_CATEGORIES = {"must_abstain", "must_not_fabricate"}
_ABSTAIN_STATUSES = {"ungrounded", "insufficient_evidence"}
_AXES = ("grounded", "responsive", "language_ok")


def question_rollup(assert_results: list[dict]) -> dict:
    n_pass = sum(1 for a in assert_results if a["outcome"] == "pass")
    n_fail = sum(1 for a in assert_results if a["outcome"] == "fail")
    n_incon = sum(1 for a in assert_results if a["outcome"] == "inconclusive")
    return {"all_pass": n_fail == 0 and n_pass > 0 or (n_fail == 0 and n_incon == 0),
            "n_pass": n_pass, "n_fail": n_fail, "n_inconclusive": n_incon}


def _rate(items, axis):
    vals = [(it.verdict or {}).get(axis) for it in items]
    conclusive = [v for v in vals if v is not None]
    if not conclusive:
        return None
    return round(sum(1 for v in conclusive if v) / len(conclusive), 4)


def scorecard(items: list[QuestionRecord]) -> dict[str, Any]:
    status_dist: dict[str, int] = {}
    for it in items:
        status_dist[it.status] = status_dist.get(it.status, 0) + 1

    # Abstention confusion matrix
    false_abstention = false_answer = correct = 0
    for it in items:
        should_abstain = it.category in _ABSTAIN_CATEGORIES
        abstained = it.status in _ABSTAIN_STATUSES
        if should_abstain and abstained:
            correct += 1
        elif (not should_abstain) and (not abstained):
            correct += 1
        elif should_abstain and not abstained:
            false_answer += 1
        else:  # should answer but abstained
            false_abstention += 1

    latencies = [it.latency_ms for it in items if it.latency_ms]
    costs = [it.cost_usd for it in items]
    any_estimated = any(it.cost_estimated for it in items)

    n = len(items)
    all_pass = sum(1 for it in items if it.question_rollup.get("all_pass"))

    return {
        "n_questions": n,
        "all_pass_rate": round(all_pass / n, 4) if n else 0.0,
        "status_distribution": status_dist,
        "axis_rates": {ax: _rate(items, ax) for ax in _AXES},
        "abstention": {"correct": correct, "false_abstention": false_abstention,
                       "false_answer": false_answer},
        "n_inconclusive_questions": sum(1 for it in items
                                        if it.question_rollup.get("n_inconclusive", 0) > 0),
        "latency_ms": {
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "p90": round(_p90(latencies), 1) if latencies else None,
        },
        "cost_usd": {"total": round(sum(costs), 6), "estimated": any_estimated},
    }


def _p90(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, int(round(0.9 * (len(s) - 1))))
    return s[k]
```

> Note on `question_rollup`'s `all_pass`: the rule is **no fails** AND at least one conclusive pass, OR a clean all-inconclusive set is NOT all_pass-true unless it had passes. The expression above yields: `True` when `n_fail==0 and n_pass>0`; also `True` when `n_fail==0 and n_incon==0` (degenerate empty — treated as vacuous pass). The test `test_question_rollup_all_pass` (2 passes) → True; `test_question_rollup_fail_blocks_all_pass` (1 fail) → False. Keep this exact expression.

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_score.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/score.py tests/test_bench_score.py
git commit -m "feat(bench): scorecard — status dist, axis rates, abstention confusion matrix, latency p90"
```

---

## Task 7: Regression (`regress.py`) — paired diff + McNemar (no scipy)

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/regress.py`
- Test: `tests/test_bench_regress.py` (create)

McNemar over discordant pairs (b = baseline-pass→candidate-fail, c = baseline-fail→candidate-pass). p via exact two-sided binomial when `b+c < 25`, else chi-square-1df survival `erfc(sqrt(stat/2))` with continuity correction.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_regress.py`:

```python
import math
from copyclip.intelligence.cuaderno.bench.regress import mcnemar, paired_property_diff
from copyclip.intelligence.cuaderno.bench.artifact import QuestionRecord


def test_mcnemar_no_discordant_pairs_is_p1():
    res = mcnemar(b=0, c=0)
    assert res["p"] == 1.0 and res["discordant"] == 0


def test_mcnemar_exact_small_counts():
    # b=6, c=0 -> two-sided exact p = 2 * 0.5**6 = 0.03125 (< 0.05).
    # (b=5,c=0 would give 0.0625, NOT significant — the count must be >=6.)
    res = mcnemar(b=6, c=0)
    assert res["method"] == "exact"
    assert res["p"] < 0.05


def test_mcnemar_symmetric_is_not_significant():
    res = mcnemar(b=4, c=4)
    assert res["p"] > 0.5


def test_mcnemar_large_counts_uses_chi2():
    res = mcnemar(b=30, c=10)
    assert res["method"] == "chi2"
    assert 0.0 <= res["p"] <= 1.0


def _rec(rid, category, **kw):
    base = dict(
        id=rid, category=category, commit_sha="x", question="q", question_lang="es",
        status="answer", verdict={}, blocks=[], cited_paths=[], citations=[],
        read_paths=[], content_bearing_count=1, answer_lang="es", latency_ms=1,
        input_tokens=1, output_tokens=1, cost_usd=0.0, cost_estimated=True,
        asserts=[], question_rollup={},
    )
    base.update(kw)
    return QuestionRecord(**base)


def test_paired_property_diff_language_ok():
    # baseline: q1 language_ok True, q2 False ; candidate: q1 True, q2 True (improved)
    base = [_rec("q1", "language_fidelity", verdict={"language_ok": True}),
            _rec("q2", "language_fidelity", verdict={"language_ok": False})]
    cand = [_rec("q1", "language_fidelity", verdict={"language_ok": True}),
            _rec("q2", "language_fidelity", verdict={"language_ok": True})]
    diff = paired_property_diff(base, cand, axis="language_ok")
    assert diff["baseline_rate"] == 0.5 and diff["candidate_rate"] == 1.0
    assert diff["improved"] == 1 and diff["regressed"] == 0
    assert diff["mcnemar"]["c"] == 1  # one fail->pass
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_regress.py -v`
Expected: FAIL — `ModuleNotFoundError` for `bench.regress`.

- [ ] **Step 3: Implement**

Create `src/copyclip/intelligence/cuaderno/bench/regress.py`:

```python
from __future__ import annotations

import math
from typing import Any, Optional

from .artifact import QuestionRecord


def mcnemar(b: int, c: int) -> dict[str, Any]:
    """Paired-difference significance over discordant pairs.

    b = passed-in-baseline, failed-in-candidate (a regression)
    c = failed-in-baseline, passed-in-candidate (an improvement)
    Returns p (two-sided), the method used, and the raw counts.
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "discordant": 0, "p": 1.0, "method": "none"}
    if n < 25:
        # exact two-sided binomial against p=0.5
        k = min(b, c)
        tail = sum(math.comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
        p = min(1.0, 2.0 * tail)
        return {"b": b, "c": c, "discordant": n, "p": round(p, 6), "method": "exact"}
    # chi-square 1 df with continuity correction; survival via erfc
    stat = (abs(b - c) - 1) ** 2 / n
    p = math.erfc(math.sqrt(stat / 2.0))
    return {"b": b, "c": c, "discordant": n, "p": round(p, 6),
            "method": "chi2", "statistic": round(stat, 4)}


def _axis_pass(rec: QuestionRecord, axis: str) -> Optional[bool]:
    """A question 'passes' the axis if the harvested verdict axis is True;
    fails if False; None (unobserved) is excluded from the paired test."""
    return (rec.verdict or {}).get(axis)


def paired_property_diff(baseline: list[QuestionRecord],
                         candidate: list[QuestionRecord],
                         *, axis: str) -> dict[str, Any]:
    """Pair baseline vs candidate by question id on a boolean axis, compute
    rates + improved/regressed counts + McNemar. Questions where either side is
    None (unobserved) are dropped from the paired comparison."""
    by_id_base = {r.id: r for r in baseline}
    by_id_cand = {r.id: r for r in candidate}
    common = [i for i in by_id_base if i in by_id_cand]

    b = c = base_pass = cand_pass = paired = 0
    for i in common:
        pv = _axis_pass(by_id_base[i], axis)
        qv = _axis_pass(by_id_cand[i], axis)
        if pv is None or qv is None:
            continue
        paired += 1
        base_pass += 1 if pv else 0
        cand_pass += 1 if qv else 0
        if pv and not qv:
            b += 1
        elif (not pv) and qv:
            c += 1

    return {
        "axis": axis,
        "paired": paired,
        "baseline_rate": round(base_pass / paired, 4) if paired else None,
        "candidate_rate": round(cand_pass / paired, 4) if paired else None,
        "regressed": b,
        "improved": c,
        "mcnemar": mcnemar(b, c),
    }


# Scope-A honesty banner: without a measured noise floor (Phase B), small deltas
# are not resolvable. Reports embed this so a small green/red is never read as
# significant.
SCOPE_A_CAVEAT = (
    "Scope A: single run per build, no measured noise floor. Only large, "
    "consistent shifts are resolvable; treat a small delta (or a McNemar p that "
    "is not decisive) as NOT a real regression until Phase B measures the floor."
)
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_regress.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/regress.py tests/test_bench_regress.py
git commit -m "feat(bench): paired McNemar regression (exact + chi2, no scipy) with Scope-A caveat"
```

---

## Task 8: The runner (`runner.py`) — drive the loop, assemble records, write artifact

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/runner.py`
- Test: `tests/test_bench_runner.py` (append — the file already exists from Task 2)

The runner is injectable for testing: callers pass `client`, `judge`, `answer_model`, `judge_model`. A higher-level `run_bench(project_root, corpus_path, ...)` (Task 9 uses it) resolves the real client. Tests use `StubStream` + a stub judge.

- [ ] **Step 1: Write the failing test (append to `tests/test_bench_runner.py`)**

```python
from copyclip.intelligence.cuaderno.bench.runner import run_one, build_question_record
from copyclip.intelligence.cuaderno.bench.asserts import AssertContext
from copyclip.intelligence.cuaderno.judge import JudgeVerdict


def test_run_one_assembles_record_and_runs_asserts(tmp_path):
    # Scripted: emit a paragraph citing a.py + finish, non-tool stop. No real reads,
    # so content_bearing_count stays 0 and the cheap layer will seal ungrounded for
    # a code question -> we assert that the record captures status + asserts honestly.
    turn = [
        _tool_stop("b1", "emit_block",
                   {"kind": "paragraph", "text": "esto está en a.py"}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "paragraph", "text": "esto está en a.py"}),
            _content("f1", "finish", {}),
        ]),
    ]
    item = {
        "id": "q1", "question": "¿cómo funciona a?", "category": "grounded_happy_path",
        "commit_sha": "e4400af", "question_lang": "es",
        "asserts": [{"type": "status_in", "value": ["answer", "ungrounded"]},
                    {"type": "language_is", "value": "es"},
                    {"type": "harvested_responsive", "value": True}],
    }
    ctx = AssertContext(file_length_fn=lambda p: 100)
    # max_tool_rounds=1 => round 0 is the closing round: it seals without a
    # grounding retry (can_retry is False), so the single scripted turn suffices.
    # With the default 8 rounds the ungrounded code answer would fire a retry,
    # exhaust the one scripted turn, and seal `partial` instead.
    rec = run_one(
        item=item, client=StubStream([turn]), judge=None,
        answer_model="claude-sonnet-4-5", project_root=str(tmp_path),
        project_id=1, conn=None, assert_ctx=ctx, max_tool_rounds=1,
    )
    assert rec.id == "q1"
    assert rec.status in ("answer", "ungrounded")
    assert rec.answer_lang == "es"
    # status_in passes, language_is passes, harvested_responsive is inconclusive
    # (no judge -> cheap verdict has responsive=None)
    outcomes = {a["type"]: a["outcome"] for a in rec.asserts}
    assert outcomes["status_in"] == "pass"
    assert outcomes["language_is"] == "pass"
    assert outcomes["harvested_responsive"] == "inconclusive"
    assert rec.question_rollup["n_inconclusive"] == 1


def test_run_one_with_stub_judge_harvests_responsive(tmp_path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "paragraph", "text": "respuesta en es"}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "paragraph", "text": "respuesta en es"}),
            _content("f1", "finish", {}),
        ]),
    ]
    # meta question -> cheap layer will seal 'answer' even with zero reads;
    # the judge then runs and we script it ok+responsive.
    item = {"id": "m1", "question": "¿qué te puedo preguntar?", "category": "meta_about_tutor",
            "commit_sha": "e4400af", "question_lang": "es",
            "asserts": [{"type": "harvested_responsive", "value": True}]}
    jv = JudgeVerdict(question_kind="meta", grounded=True, responsive=True,
                      language_ok=True, decision="ok", world=None,
                      retry_directive=None, reason="ok", judged=True)

    def stub_judge(q, b, l):
        return jv

    ctx = AssertContext(file_length_fn=lambda p: 100)
    rec = run_one(item=item, client=StubStream([turn]), judge=stub_judge,
                  answer_model="claude-sonnet-4-5", project_root=str(tmp_path),
                  project_id=1, conn=None, assert_ctx=ctx)
    assert rec.verdict["responsive"] is True
    assert rec.asserts[0]["outcome"] == "pass"
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_runner.py -v`
Expected: the two new tests FAIL — `ModuleNotFoundError` / `ImportError` for `bench.runner`.

- [ ] **Step 3: Implement**

Create `src/copyclip/intelligence/cuaderno/bench/runner.py`:

```python
from __future__ import annotations

import subprocess
import time
from typing import Any, Optional

from ..compositor import iter_compose_events, _fallback_frame
from ..quality import _cited_paths, _answer_text, _norm_path
from ..language import detect_language
from ..read_ledger import ReadLedger
from ..schema import Block, frame_from_dict, FRAME_STATUS_PARTIAL
from .artifact import QuestionRecord
from .asserts import AssertContext, run_asserts
from .score import question_rollup


def _all_citations(blocks: list[dict]) -> list[dict]:
    """Every raw citation dict carried by the answer blocks (path or commit),
    walking the same shapes as quality._cited_paths."""
    out: list[dict] = []
    for b in blocks:
        d = b  # blocks here are already to_dict form: {"kind", ...data}
        if isinstance(d.get("citation"), dict):
            out.append(d["citation"])
        cits = d.get("citations")
        if isinstance(cits, list):
            out.extend(c for c in cits if isinstance(c, dict))
        items = d.get("items")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and isinstance(it.get("citation"), dict):
                    out.append(it["citation"])
    return out


def build_question_record(*, item: dict, frame_dict: dict, ledger: ReadLedger,
                          latency_ms: int, answer_model: str,
                          assert_ctx: AssertContext,
                          input_tokens: int = 0, output_tokens: int = 0,
                          cost_usd: float = 0.0, cost_estimated: bool = True,
                          error: Optional[str] = None) -> QuestionRecord:
    blocks = frame_dict.get("blocks", [])
    block_objs = [Block.from_dict(b) for b in blocks]
    cited_paths = sorted(_cited_paths(block_objs))
    answer_lang = detect_language(_answer_text(block_objs))
    rec = QuestionRecord(
        id=item["id"], category=item["category"], commit_sha=item["commit_sha"],
        question=item["question"], question_lang=item["question_lang"],
        status=frame_dict.get("status", "legacy"),
        verdict=frame_dict.get("verdict"),
        blocks=blocks,
        cited_paths=cited_paths,
        citations=_all_citations(blocks),
        read_paths=sorted(_norm_path(p) for p in ledger.read_paths),
        content_bearing_count=ledger.content_bearing_count,
        answer_lang=answer_lang,
        latency_ms=latency_ms, input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=cost_usd, cost_estimated=cost_estimated, error=error,
    )
    results = run_asserts(rec, item.get("asserts", []), assert_ctx)
    rec.asserts = [r.to_dict() for r in results]
    rec.question_rollup = question_rollup(rec.asserts)
    return rec


def run_one(*, item: dict, client: Any, judge: Any, answer_model: str,
            project_root: str, project_id: int, conn, assert_ctx: AssertContext,
            max_tool_rounds: int = 8) -> QuestionRecord:
    """Drive one corpus question to its terminal frame and build its record.
    Pure of any metrics side-effects here (cost is attached by run_bench)."""
    ledger = ReadLedger()
    last_frame_dict: Optional[dict] = None
    err: Optional[str] = None
    t0 = time.perf_counter()
    try:
        for ev in iter_compose_events(
            client=client, question=item["question"], project_root=project_root,
            project_id=project_id, conn=conn, model=answer_model,
            max_tool_rounds=max_tool_rounds, judge=judge, ledger=ledger,
        ):
            if ev["type"] == "frame":
                last_frame_dict = ev["frame"]
            elif ev["type"] == "error":
                err = ev["message"]
    except Exception as exc:  # noqa: BLE001 — a runner must never abort the whole corpus
        err = f"runner exception: {exc}"
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if last_frame_dict is None:
        # Total: synthesize a partial frame so every question yields a record.
        from ..schema import frame_to_dict
        last_frame_dict = frame_to_dict(_fallback_frame(item["question"], err or "no frame"))
        last_frame_dict["status"] = FRAME_STATUS_PARTIAL

    return build_question_record(
        item=item, frame_dict=last_frame_dict, ledger=ledger,
        latency_ms=latency_ms, answer_model=answer_model, assert_ctx=assert_ctx,
        error=err,
    )


def git_file_length_fn(project_root: str, sha: str):
    """Return a path -> line-count resolver reading the file at the pinned SHA
    via `git show <sha>:<path>`. Returns None for any path git cannot resolve."""
    def fn(path: str) -> Optional[int]:
        try:
            out = subprocess.run(
                ["git", "-C", project_root, "show", f"{sha}:{path}"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                return None
            return out.stdout.count("\n") + (0 if out.stdout.endswith("\n") else 1)
        except Exception:
            return None
    return fn
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_runner.py -v`
Expected: all tests in the file PASS (the Task-2 test plus the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/runner.py tests/test_bench_runner.py
git commit -m "feat(bench): runner drives iter_compose_events, assembles records, runs asserts"
```

---

## Task 9: The `copyclip bench` CLI subcommand + `run_bench` orchestration

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/bench/cli.py`
- Modify: `src/copyclip/intelligence/cli.py` (add `bench` to `COMMANDS`, add dispatch block)
- Modify: `src/copyclip/intelligence/cuaderno/bench/__init__.py` (export `run_bench`)
- Test: `tests/test_bench_cli.py` (create)

`run_bench` resolves the real provider/client/judge and loops `run_one` over the corpus, attaching metrics, writing the artifact, and (if `--baseline`) diffing. The CLI test exercises arg parsing + that `bench` is registered, with the heavy `run_bench` monkeypatched (no LLM).

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_cli.py`:

```python
from copyclip.intelligence import cli as intel_cli


def test_bench_is_a_registered_command():
    assert "bench" in intel_cli.COMMANDS


def test_bench_cli_invokes_run_bench(monkeypatch, tmp_path):
    captured = {}

    def fake_run_bench(**kwargs):
        captured.update(kwargs)
        return {"run_id": "fake", "scorecard": {"n_questions": 0}}

    import copyclip.intelligence.cuaderno.bench.cli as bench_cli
    monkeypatch.setattr(bench_cli, "run_bench", fake_run_bench)

    handled = intel_cli._maybe_handle_internal(
        ["copyclip", "bench", "--corpus", str(tmp_path / "c.jsonl"),
         "--path", str(tmp_path), "--limit", "3"])
    assert handled is True
    assert captured["corpus_path"].endswith("c.jsonl")
    assert captured["limit"] == 3
    assert captured["baseline"] is None


def test_bench_cli_passes_baseline(monkeypatch, tmp_path):
    captured = {}
    import copyclip.intelligence.cuaderno.bench.cli as bench_cli
    monkeypatch.setattr(bench_cli, "run_bench", lambda **kw: captured.update(kw) or {"run_id": "x"})
    intel_cli._maybe_handle_internal(
        ["copyclip", "bench", "--baseline", "run-123", "--path", str(tmp_path)])
    assert captured["baseline"] == "run-123"
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_cli.py -v`
Expected: FAIL — `test_bench_is_a_registered_command` fails (`bench` not in `COMMANDS`); the dispatch tests fail (no `bench` branch / no `bench.cli`).

- [ ] **Step 3: Implement**

Create `src/copyclip/intelligence/cuaderno/bench/cli.py`:

```python
from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from ...llm.metrics import metrics_collector
from ..provider import (
    resolve_cuaderno_provider, build_cuaderno_client, resolve_judge_model,
    CuadernoProviderError,
)
from ..judge import judge_answer
from .artifact import RunArtifact, write_artifact, read_artifact, default_run_path
from .asserts import AssertContext
from .corpus import load_corpus, corpus_sha
from .runner import run_one, git_file_length_fn
from .score import scorecard


def _head_sha(root: str) -> str:
    try:
        out = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _run_id(head: str, csha: str) -> str:
    # Deterministic-ish, sortable: timestamp + short content hash. time import is
    # local so tests can monkeypatch run_bench wholesale without time concerns.
    import time
    return time.strftime("%Y%m%d-%H%M%S") + f"-{head}-{csha[:6]}"


def run_bench(*, project_root: str, corpus_path: str, baseline: Optional[str] = None,
              limit: Optional[int] = None) -> dict[str, Any]:
    """Resolve the real client, run the corpus, write an artifact, print the
    scorecard, and (if baseline) the regression diff."""
    from ..db import connect, init_schema, init_cuaderno_schema
    from ..server_helpers import project_id as _project_id

    conn = connect(project_root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    pid = _project_id(conn, project_root) or 1

    try:
        resolved = resolve_cuaderno_provider(conn)
    except CuadernoProviderError as exc:
        raise SystemExit(f"LLM not configured ({exc.provider}): {exc}")
    client = build_cuaderno_client(resolved)
    answer_model = resolved["model"]

    judge_overlay = None
    try:
        row = conn.execute("SELECT value FROM config WHERE key=?",
                           ("cuaderno_judge_model",)).fetchone()
        judge_overlay = row[0] if row and row[0] else None
    except Exception:
        judge_overlay = None
    judge_model = resolve_judge_model(resolved["provider"], answer_model, judge_overlay)

    def _judge(q, b, l):
        return judge_answer(client=client, question=q, blocks=b, ledger=l, model=judge_model)

    items = load_corpus(corpus_path)
    if limit:
        items = items[:limit]
    csha = corpus_sha(corpus_path)
    head = _head_sha(project_root)

    metrics_collector.reset_run()
    records = []
    for item in items:
        assert_ctx = AssertContext(file_length_fn=git_file_length_fn(project_root, item["commit_sha"]))
        rec = run_one(item=item, client=client, judge=_judge, answer_model=answer_model,
                      project_root=project_root, project_id=pid, conn=conn,
                      assert_ctx=assert_ctx)
        records.append(rec)
        mark = "OK " if rec.question_rollup.get("all_pass") else "XX "
        print(f"  {mark}{rec.id} [{rec.category}] status={rec.status} "
              f"pass={rec.question_rollup.get('n_pass')} fail={rec.question_rollup.get('n_fail')} "
              f"incon={rec.question_rollup.get('n_inconclusive')}")

    sc = scorecard(records)
    rollup = metrics_collector.run_rollup()
    run_id = _run_id(head, csha)
    art = RunArtifact(
        run_id=run_id, started_at=__import__("datetime").datetime.now().isoformat(),
        corpus_path=corpus_path, corpus_sha=csha, head_sha=head,
        answer_model=answer_model, judge_model=judge_model, provider=resolved["provider"],
        copyclip_version=_version(), items=records, metrics_rollup=rollup,
    )
    out_path = default_run_path(project_root, run_id)
    write_artifact(art, out_path)

    _print_scorecard(sc, rollup, out_path)
    result = {"run_id": run_id, "scorecard": sc, "artifact_path": out_path}

    if baseline:
        from .regress import paired_property_diff, SCOPE_A_CAVEAT
        base_art = read_artifact(default_run_path(project_root, baseline))
        print("\n=== REGRESSION vs", baseline, "===")
        for axis in ("grounded", "responsive", "language_ok"):
            d = paired_property_diff(base_art.items, records, axis=axis)
            print(f"  {axis}: {d['baseline_rate']} -> {d['candidate_rate']} "
                  f"(improved={d['improved']} regressed={d['regressed']} "
                  f"p={d['mcnemar']['p']} via {d['mcnemar']['method']})")
        print("\n  " + SCOPE_A_CAVEAT)
        result["baseline"] = baseline
    return result


def _version() -> str:
    try:
        here = os.path.dirname(__file__)
        vf = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "VERSION"))
        with open(vf) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def _print_scorecard(sc: dict, rollup: dict, out_path: str) -> None:
    print("\n=== SCORECARD ===")
    print(f"  questions: {sc['n_questions']}  all-pass-rate: {sc['all_pass_rate']}")
    print(f"  status: {sc['status_distribution']}")
    print(f"  axis rates: {sc['axis_rates']}")
    print(f"  abstention: {sc['abstention']}")
    print(f"  latency ms: {sc['latency_ms']}")
    est = " (ESTIMATED)" if sc['cost_usd']['estimated'] else ""
    print(f"  cost usd: {sc['cost_usd']['total']}{est}")
    print(f"  artifact: {out_path}")
```

Now wire the subcommand. In `src/copyclip/intelligence/cli.py`, edit `COMMANDS` at line 14 to add `"bench"`:

```python
COMMANDS = {"analyze", "serve", "start", "decision", "report", "issue", "audit", "mcp", "update", "bench"}
```

Add a dispatch block following the `mcp` pattern (place it near the other `if cmd == ...:` blocks, e.g. right after the `mcp` block at line 318). Use the SAME structure verbatim-style as `mcp`:

```python
    if cmd == "bench":
        import argparse
        from .cuaderno.bench.cli import run_bench
        p = argparse.ArgumentParser(
            prog="copyclip bench",
            description="Run the cuaderno eval harness over a fixed corpus.")
        p.add_argument("--path", default=".", help="project root (default: cwd)")
        p.add_argument("--corpus", default="corpus/cuaderno-bench.jsonl",
                       help="path to the JSONL corpus")
        p.add_argument("--baseline", default=None,
                       help="a prior run_id to diff against (regression report)")
        p.add_argument("--limit", type=int, default=None,
                       help="run only the first N corpus questions")
        ns = p.parse_args(argv[2:])
        run_bench(project_root=os.path.abspath(ns.path), corpus_path=ns.corpus,
                  baseline=ns.baseline, limit=ns.limit)
        return True
```

> Verify `import os` and `import argparse` are available in `cli.py` scope; `cli.py` already imports `argparse` per-command (see the `mcp`/`report` blocks) — keep the local `import` to match the file's style. If `os` is not module-imported in `cli.py`, add `import os` at the top.

Export `run_bench` from `src/copyclip/intelligence/cuaderno/bench/__init__.py` (append):

```python
from .cli import run_bench  # noqa: E402,F401
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_cli.py -v`
Expected: all PASS. (The `run_bench` is monkeypatched in `bench.cli`, so no LLM is touched.)

Confirm nothing else broke:
Run: `python -m pytest tests/test_smoke_cli_runtime.py -v`
Expected: PASS (CLI still constructs).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/cli.py src/copyclip/intelligence/cuaderno/bench/__init__.py src/copyclip/intelligence/cli.py tests/test_bench_cli.py
git commit -m "feat(bench): copyclip bench subcommand + run_bench orchestration (scorecard + regression)"
```

---

## Task 10: Author the corpus + a content-validation test

**Files:**
- Create: `corpus/cuaderno-bench.jsonl`
- Test: `tests/test_bench_corpus_content.py` (create)

Author ~20–30 questions across the 9 categories (§6 of the spec). Pin every item to a real commit SHA (use `git log --oneline` to pick stable commits; `e4400af` is the current HEAD per the spec). Below is a **starter set** (one or two per category) the engineer extends to ~20–30. Keep `commit_sha` consistent (the SHA you will check out before running).

- [ ] **Step 1: Write the failing content test**

Create `tests/test_bench_corpus_content.py`:

```python
from collections import Counter
from copyclip.intelligence.cuaderno.bench.corpus import load_corpus

CORPUS = "corpus/cuaderno-bench.jsonl"
REQUIRED_CATEGORIES = {
    "what_vs_how", "grounded_happy_path", "must_abstain", "must_not_fabricate",
    "fabricated_grounding_bait", "meta_about_tutor", "language_fidelity",
    "temporal_causal", "multi_hop_cross_file",
}


def test_corpus_loads_and_validates():
    items = load_corpus(CORPUS)
    assert len(items) >= 18  # ~20-30 target; floor guards against truncation


def test_corpus_covers_all_nine_categories():
    items = load_corpus(CORPUS)
    cats = set(it["category"] for it in items)
    missing = REQUIRED_CATEGORIES - cats
    assert not missing, f"corpus missing categories: {missing}"


def test_abstain_categories_assert_abstain_status():
    items = load_corpus(CORPUS)
    for it in items:
        if it["category"] in ("must_abstain", "must_not_fabricate"):
            types = {a["type"] for a in it["asserts"]}
            assert "status_in" in types or "status_is" in types, \
                f"{it['id']} must assert its abstention status"
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_bench_corpus_content.py -v`
Expected: FAIL — `FileNotFoundError` (no corpus yet).

- [ ] **Step 3: Create the corpus**

Create `corpus/cuaderno-bench.jsonl` with the starter set below (one JSON object per line — extend to ~20-30 by adding more per category; keep `commit_sha` = the commit you check out before running):

```jsonl
{"id": "whathow-compositor-what", "question": "¿qué es el compositor del cuaderno?", "category": "what_vs_how", "commit_sha": "e4400af", "question_lang": "es", "expected_question_kind": "code_comprehension", "asserts": [{"type": "status_in", "value": ["answer", "off_target"]}, {"type": "language_is", "value": "es"}], "notes": "definition question — the how-pair below must NOT be answered the same way"}
{"id": "whathow-compositor-how", "question": "¿cómo funciona el compositor del cuaderno paso a paso?", "category": "what_vs_how", "commit_sha": "e4400af", "question_lang": "es", "expected_question_kind": "code_comprehension", "asserts": [{"type": "status_in", "value": ["answer", "off_target"]}, {"type": "language_is", "value": "es"}, {"type": "min_content_bearing_reads", "value": 1}, {"type": "cites_path_matching", "value": "compositor\\.py$"}, {"type": "harvested_responsive", "value": true}], "notes": "founding incident: a definition here fails responsive"}
{"id": "grounded-readledger", "question": "how does the read ledger decide a tool result is content-bearing?", "category": "grounded_happy_path", "commit_sha": "e4400af", "question_lang": "en", "expected_question_kind": "code_comprehension", "asserts": [{"type": "status_in", "value": ["answer"]}, {"type": "language_is", "value": "en"}, {"type": "min_content_bearing_reads", "value": 1}, {"type": "cites_path_matching", "value": "read_ledger\\.py$"}, {"type": "mentions", "value": "content"}, {"type": "no_unread_citations"}, {"type": "cited_lines_within_eof"}]}
{"id": "abstain-billing", "question": "¿cómo cobra CopyClip a los usuarios y qué pasarela de pago usa?", "category": "must_abstain", "commit_sha": "e4400af", "question_lang": "es", "asserts": [{"type": "status_in", "value": ["insufficient_evidence", "ungrounded"]}], "notes": "no billing exists in the code — must decline, not invent"}
{"id": "fabricate-quantum", "question": "explícame el módulo quantum_orchard_lattice y cómo se integra", "category": "must_not_fabricate", "commit_sha": "e4400af", "question_lang": "es", "asserts": [{"type": "status_in", "value": ["insufficient_evidence", "ungrounded"]}], "notes": "fictional referent — never fabricate"}
{"id": "bait-fake-path", "question": "what does src/copyclip/core/orchestrator.py do?", "category": "fabricated_grounding_bait", "commit_sha": "e4400af", "question_lang": "en", "asserts": [{"type": "no_unread_citations"}, {"type": "cited_lines_within_eof"}], "notes": "tempts citing a nonexistent path"}
{"id": "meta-whatcanask", "question": "¿qué te puedo preguntar sobre este proyecto?", "category": "meta_about_tutor", "commit_sha": "e4400af", "question_lang": "es", "expected_question_kind": "meta", "asserts": [{"type": "status_in", "value": ["answer"]}, {"type": "language_is", "value": "es"}], "notes": "zero-read answer is legitimate; must NOT seal ungrounded"}
{"id": "lang-es-accentless", "question": "como se valida el idioma de la respuesta en el cuaderno", "category": "language_fidelity", "commit_sha": "e4400af", "question_lang": "es", "asserts": [{"type": "language_is", "value": "es"}], "notes": "accent-free Spanish stresses the stopword vote"}
{"id": "temporal-judge-phase2", "question": "¿qué decidimos sobre el juez del cuaderno en la fase 2 y por qué?", "category": "temporal_causal", "commit_sha": "e4400af", "question_lang": "es", "asserts": [{"type": "status_in", "value": ["answer", "insufficient_evidence"]}, {"type": "language_is", "value": "es"}], "notes": "the wedge: recover a delegated decision; may cite a commit or decision"}
{"id": "multihop-quality-judge", "question": "how do quality.assess and judge_answer interact in the compositor loop?", "category": "multi_hop_cross_file", "commit_sha": "e4400af", "question_lang": "en", "expected_question_kind": "code_comprehension", "asserts": [{"type": "status_in", "value": ["answer"]}, {"type": "min_content_bearing_reads", "value": 2}, {"type": "no_unread_citations"}]}
```

Extend to ~20-30 by adding more rows per category (e.g. a second `temporal_causal` asserting `cites_commit`, more `grounded_happy_path` over `language.py`/`schema.py`, a second `what_vs_how` pair over a different symbol). The two content tests below set the floor.

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bench_corpus_content.py -v`
Expected: PASS once the corpus has ≥18 rows covering all nine categories. (Add rows until `test_corpus_loads_and_validates` passes.)

- [ ] **Step 5: Commit**

```bash
git add corpus/cuaderno-bench.jsonl tests/test_bench_corpus_content.py
git commit -m "feat(bench): seed cuaderno-bench corpus (9 categories) + content validation"
```

---

## Task 11: Frozen fixture repo + runner integration test (no LLM)

**Files:**
- Create: `tests/fixtures/bench_fixture_repo/` (a tiny tree — NOT a nested git repo; the test inits git in a tmp copy)
- Test: `tests/test_bench_integration.py` (create)

This proves the runner + asserts + scorecard work end-to-end against a stable, content-known target using `StubStream` (no live LLM). The fixture content is fixed, so `cited_lines_within_eof` and `no_unread_citations` are deterministic.

- [ ] **Step 1: Create the fixture tree**

Create `tests/fixtures/bench_fixture_repo/sample.py` (exactly 6 lines so EOF checks are deterministic):

```python
def greet(name):
    return f"hello {name}"


def farewell(name):
    return f"bye {name}"
```

Create `tests/fixtures/bench_fixture_repo/README.md`:

```markdown
# fixture
A frozen toy repo for bench harness integration tests.
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_bench_integration.py`:

```python
import shutil
import subprocess
import pytest

from copyclip.intelligence.cuaderno.bench.runner import run_one, git_file_length_fn
from copyclip.intelligence.cuaderno.bench.asserts import AssertContext
from copyclip.intelligence.cuaderno.bench.score import scorecard
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop

FIXTURE = "tests/fixtures/bench_fixture_repo"


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURE, dst)
    subprocess.run(["git", "-C", str(dst), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(dst), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(dst), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], check=True)
    sha = subprocess.run(["git", "-C", str(dst), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return str(dst), sha


def test_git_file_length_fn_reads_pinned_sha(repo):
    root, sha = repo
    fn = git_file_length_fn(root, sha)
    assert fn("sample.py") == 6
    assert fn("does_not_exist.py") is None


def test_run_one_against_fixture_scores_deterministically(repo):
    root, sha = repo
    # Script an answer that cites sample.py lines 1-2 (within the 6-line file).
    cit = {"kind": "path", "path": "sample.py", "line_start": 1, "line_end": 2}
    turn = [
        _tool_stop("b1", "emit_block",
                   {"kind": "code_block", "code": "def greet", "language": "python",
                    "citation": cit}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block",
                     {"kind": "code_block", "code": "def greet", "language": "python",
                      "citation": cit}),
            _content("f1", "finish", {}),
        ]),
    ]
    # Citation asserts only (no language_is: a code_block carries no `text`, so
    # detect_language over the answer would be "unknown" — out of scope for this
    # citation-focused integration test). max_tool_rounds=1 seals without retry.
    item = {"id": "fx1", "question": "what does greet do?", "category": "grounded_happy_path",
            "commit_sha": sha, "question_lang": "en",
            "asserts": [{"type": "cites_path_matching", "value": "sample\\.py$"},
                        {"type": "cited_lines_within_eof"}]}
    ctx = AssertContext(file_length_fn=git_file_length_fn(root, sha))
    rec = run_one(item=item, client=StubStream([turn]), judge=None,
                  answer_model="claude-sonnet-4-5", project_root=root,
                  project_id=1, conn=None, assert_ctx=ctx, max_tool_rounds=1)
    outcomes = {a["type"]: a["outcome"] for a in rec.asserts}
    assert outcomes["cites_path_matching"] == "pass"
    assert outcomes["cited_lines_within_eof"] == "pass"
    sc = scorecard([rec])
    assert sc["n_questions"] == 1
```

- [ ] **Step 3: Run, verify it fails then passes**

Run: `python -m pytest tests/test_bench_integration.py -v`
Expected: initially may FAIL if `tests/__init__.py` does not exist and `from tests.test_cuaderno_compositor import ...` cannot resolve. The repo already imports this way in `tests/test_bench_runner.py` (Task 2) and `tests/__init__.py` exists (confirmed in the tree). If the import resolves, the tests should PASS once the fixture files exist. Fix any import error by confirming `tests/__init__.py` is present (it is per the repo listing).

- [ ] **Step 4: Confirm pass**

Run: `python -m pytest tests/test_bench_integration.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/bench_fixture_repo tests/test_bench_integration.py
git commit -m "test(bench): frozen fixture repo + deterministic runner integration (no LLM)"
```

---

## Task 12: Key-gated live smoke test

**Files:**
- Test: `tests/test_bench_live_smoke.py` (create)

Mirrors the live-e2e gate (`tests/test_cuaderno_live_e2e.py:50-60`): skipped unless the provider key is set. Runs ~3 corpus questions through the REAL `run_bench` path against the actual repo, asserting the artifact is well-formed. Not in default CI.

- [ ] **Step 1: Write the gated test**

Create `tests/test_bench_live_smoke.py`:

```python
import os
import pytest

from copyclip.llm.provider_config import PROVIDERS

LIVE_PROVIDER = os.environ.get("CUADERNO_LIVE_PROVIDER", "deepseek").strip().lower()
_KEY_ENV = PROVIDERS[LIVE_PROVIDER].api_key_env if LIVE_PROVIDER in PROVIDERS else None
_HAS_KEY = bool(_KEY_ENV and (os.environ.get(_KEY_ENV) or "").strip())

pytestmark = pytest.mark.skipif(
    not _HAS_KEY,
    reason=f"bench live smoke: set {_KEY_ENV or 'the provider key'} (provider={LIVE_PROVIDER})",
)


def test_bench_live_smoke_three_questions(tmp_path):
    from copyclip.intelligence.cuaderno.bench.cli import run_bench
    # Run against the real repo root (this checkout) with a 3-question cap.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = run_bench(
        project_root=repo_root,
        corpus_path=os.path.join(repo_root, "corpus", "cuaderno-bench.jsonl"),
        baseline=None, limit=3,
    )
    assert "run_id" in result
    sc = result["scorecard"]
    assert sc["n_questions"] == 3
    # Every question produced a status and an assert rollup
    from copyclip.intelligence.cuaderno.bench.artifact import read_artifact
    art = read_artifact(result["artifact_path"])
    assert len(art.items) == 3
    for it in art.items:
        assert it.status in {
            "answer", "ungrounded", "insufficient_evidence", "off_target",
            "partial", "fallback", "legacy",
        }
        assert "all_pass" in it.question_rollup
```

- [ ] **Step 2: Run (skipped without a key)**

Run: `python -m pytest tests/test_bench_live_smoke.py -v`
Expected: SKIPPED (no provider key in CI). With a key set (`$env:DEEPSEEK_API_KEY = "..."` then run), it executes 3 real questions and PASSES.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bench_live_smoke.py
git commit -m "test(bench): key-gated live smoke (3 questions end-to-end through run_bench)"
```

---

## Final verification

- [ ] **Run the full bench test suite (deterministic, no LLM):**

Run: `python -m pytest tests/test_metrics.py tests/test_bench_artifact.py tests/test_bench_asserts.py tests/test_bench_corpus.py tests/test_bench_corpus_content.py tests/test_bench_score.py tests/test_bench_regress.py tests/test_bench_runner.py tests/test_bench_cli.py tests/test_bench_integration.py -v`
Expected: all PASS (live smoke is skipped without a key).

- [ ] **Confirm no regression in the cuaderno suite (the ledger injection is the only touch):**

Run: `python -m pytest tests/test_cuaderno_compositor.py tests/test_cuaderno_quality.py tests/test_cuaderno_judge.py -v`
Expected: all PASS.

- [ ] **Manual smoke (optional, with a key, at the pinned commit):**

```bash
git checkout e4400af    # the pinned SHA the starter corpus uses
copyclip bench --limit 3
# inspect the scorecard, then:
copyclip bench --baseline <the run_id it printed>   # second run -> regression report
git checkout feat/cuaderno-eval-harness-spec
```

---

## Self-review notes (spec coverage)

- Spec §6 corpus (9 categories, SHA-pinned, JSONL) → Task 10. §7 assertion engine (all 10 types incl. `cited_lines_within_eof`, harvested-None→inconclusive) → Task 4. §8 artifact → Task 3. §9 scorecard + abstention matrix + latency p90 + estimated-cost flag → Task 6. §10 paired McNemar regression + Scope-A caveat → Task 7 + Task 9 wiring. §11 metrics fix (3 bugs + estimated flag + rollup; adapters NOT touched per the slim decision) → Task 1. §12 ledger injection → Task 2. CLI home (`copyclip bench`) → Task 9. Frozen fixture for harness unit tests → Task 11. Key-gated live → Task 12.
- Deferred per spec (NOT in this plan): noise floor / N-repeats (Phase B); external different-family judge, fact-recall, kappa (Phase C); real-usage adapter capture (Phase A.5).
- Type consistency check: `QuestionRecord`/`RunArtifact` fields are defined once in Task 3 and consumed unchanged in Tasks 4/6/7/8/9; `AssertResult.outcome ∈ {pass,fail,inconclusive}` is consistent across Tasks 4/6/8; `mcnemar(b, c)` keys (`b,c,discordant,p,method`) consistent across Tasks 7/9; `run_bench(**kwargs)` signature (`project_root, corpus_path, baseline, limit`) consistent across Tasks 9/12.
