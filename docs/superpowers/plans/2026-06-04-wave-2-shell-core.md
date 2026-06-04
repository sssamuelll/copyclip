# Wave 2 — Shell Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cuaderno the front door of `copyclip` and make the honesty regime (cheap gate + judge) artifact-aware, before any heavy artifact ships; collapse AskPage; record the dashboard death date.

**Architecture:** The citation collector in `quality.py` gains a recursive descent into widget payloads so widget citations join the existing fabricated-grounding check with zero new verdict logic. A new `artifacts_cited` axis is injected at `_seal` (the single chokepoint — cheap and judge verdict dicts REPLACE each other, so neither layer alone can carry it). The judge sees a deterministic `[ARTIFACTS]` text rendering. The bare CLI flips to start semantics; export moves behind `copyclip export`. AskPage + `/api/ask` + `ask_project.py` die together (sole-consumer chain, verified).

**Tech Stack:** Python (pytest, stdlib server), React/TypeScript (`npm --prefix frontend run build` = tsc -b + vite; NO frontend test runner, by standing decision).

**Spec:** `docs/superpowers/specs/2026-06-04-wave-2-shell-core-design.md`

**Verified facts the plan relies on:**
- `quality.py:44 _cited_paths` walks `citation`/`citations`/`items[].citation` at `b.data` top level; widget payloads live under `b.data["widget"]` — invisible today.
- `compositor.py:63/66/260/277`: `cheap_verdict_dict` and `judge_verdict_dict` replace each other; `_seal` (compositor.py:70-72) is the single seal chokepoint.
- `judge.py:107` puts `_answer_text(blocks)` between fences.
- `__main__.py:103`: bare `copyclip` runs the clipboard export (folder positional defaults `"."`). Intelligence commands dispatch first via `maybe_handle_intelligence` (`cli.py:_maybe_handle_internal`, gated on `argv[1] in COMMANDS`).
- `/api/ask` (server.py:1887) is AskPage's only call; `build_ask_response` (server.py:17) has no other production importer; `build_context_bundle` lives in `context_bundle_builder.py` (server.py:16,692,1935) and is NOT affected by ask_project's death.
- `tests/test_debt_integration.py:10` imports `build_ask_response` (4 call sites); 3 dedicated ask test files + `ask_project_eval_fixture.py` exist.
- Two known Windows-flaky test families (port/timing) rotate in full-suite runs; they pass individually — verify flakiness by individual re-run, never ignore silently.

---

### Task 1: Recursive citation collector (`_walk_citations` + widget descent in `_cited_paths`)

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/quality.py`
- Test: `tests/test_cuaderno_artifact_honesty.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Wave-2 honesty backbone: the gate and judge stop being blind to widgets."""
from copyclip.intelligence.cuaderno.quality import _cited_paths, assess
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.schema import Block, FRAME_STATUS_UNGROUNDED


def _widget_block(widget: dict) -> Block:
    return Block.widget(widget)


def test_cited_paths_descends_into_widget_nodes():
    w = {"kind": "graph_subset",
         "nodes": [{"id": "a", "label": "A",
                    "citation": {"kind": "path", "path": "src/a.py"}}],
         "edges": []}
    paths = _cited_paths([_widget_block(w)])
    assert paths == {"src/a.py"}


def test_cited_paths_collects_nested_citations_lists():
    w = {"kind": "future_kind",
         "groups": [{"items": [{"citations": [
             {"kind": "path", "path": "src/deep.py"},
             {"kind": "commit", "commit": "abc123"},  # commit-kind: not a path
         ]}]}]}
    paths = _cited_paths([_widget_block(w)])
    assert paths == {"src/deep.py"}


def test_non_widget_blocks_unchanged():
    b = Block.code_block("x = 1", "python", citation={"kind": "path", "path": "src/x.py"})
    assert _cited_paths([b]) == {"src/x.py"}


def test_fabricated_grounding_via_widget_seals_ungrounded():
    """Code question; ledger read a.py; the ONLY citation in the answer lives
    inside a widget and points at never-read b.py -> ungrounded."""
    ledger = ReadLedger()
    ledger.record_read("src/a.py", content_bearing=True)
    w = {"kind": "graph_subset",
         "nodes": [{"id": "b", "citation": {"kind": "path", "path": "src/b.py"}}],
         "edges": []}
    v = assess(question="how does the parser work?",
               blocks=[Block.paragraph("It parses."), _widget_block(w)],
               ledger=ledger)
    assert v.status == FRAME_STATUS_UNGROUNDED
    assert "unread" in v.reason
```

Check `ReadLedger`'s recording API first (`grep -n "def " src/copyclip/intelligence/cuaderno/read_ledger.py`) — if the method is not `record_read(path, content_bearing=...)`, adapt the test helper to the real API (the existing tests in `tests/test_cuaderno_quality*.py` show the working pattern; copy it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_artifact_honesty.py -v`
Expected: the two widget tests FAIL (empty set collected); the non-widget test PASSES (regression guard).

- [ ] **Step 3: Implement the recursive walk**

In `quality.py`, add after `_norm_path` (line ~41):

```python
def _walk_citations(node: Any, out: list[Any]) -> None:
    """Recursively collect citation-shaped values from arbitrary widget data.
    Recursive descent (not per-kind extractors) is deliberate: future widget
    kinds are covered for free, so the artifact blind spot cannot be recreated
    by forgetting to register a kind."""
    if isinstance(node, dict):
        if node.get("citation") is not None:
            out.append(node["citation"])
        cits = node.get("citations")
        if isinstance(cits, list):
            out.extend(cits)
        for v in node.values():
            _walk_citations(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_citations(v, out)
```

In `_cited_paths`, after the `items` handling (line ~62), add:

```python
        w = d.get("widget")
        if isinstance(w, dict):
            _walk_citations(w, candidates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_artifact_honesty.py tests/ -q -k "quality or artifact"`
Expected: all PASS (new tests green, existing quality tests untouched).

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/quality.py tests/test_cuaderno_artifact_honesty.py
git commit -m "feat(shell): citation collector descends into widget payloads — fabricated grounding now covers artifacts"
```

---

### Task 2: `artifacts_cited` axis injected at `_seal`

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/quality.py`
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py:70-72` (`_seal`)
- Test: `tests/test_cuaderno_artifact_honesty.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cuaderno_artifact_honesty.py`:

```python
from copyclip.intelligence.cuaderno.quality import artifacts_cited


def test_artifacts_cited_none_without_widgets():
    assert artifacts_cited([Block.paragraph("hi")]) is None


def test_artifacts_cited_true_with_cited_widget():
    w = {"kind": "graph_subset",
         "nodes": [{"id": "a", "citation": {"kind": "path", "path": "src/a.py"}}],
         "edges": []}
    assert artifacts_cited([_widget_block(w)]) is True


def test_artifacts_cited_false_with_uncited_widget():
    w = {"kind": "graph_subset", "nodes": [{"id": "a"}], "edges": []}
    assert artifacts_cited([_widget_block(w)]) is False


def test_seal_injects_artifacts_cited():
    from copyclip.intelligence.cuaderno.compositor import _seal
    w = {"kind": "graph_subset", "nodes": [{"id": "a"}], "edges": []}
    frame = _seal("q?", [_widget_block(w)], "answer", {"source": "cheap"})
    assert frame["verdict"]["artifacts_cited"] is False
    frame2 = _seal("q?", [Block.paragraph("hi")], "answer", {"source": "cheap"})
    assert frame2["verdict"]["artifacts_cited"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cuaderno_artifact_honesty.py -v -k artifacts_cited or seal`
Expected: FAIL with ImportError (`artifacts_cited` not defined).

- [ ] **Step 3: Implement**

In `quality.py`, after `_cited_paths`:

```python
def artifacts_cited(blocks: list[Block]) -> Optional[bool]:
    """Confession axis, never a verdict: None = no widgets in the frame;
    True = at least one citation collected from widget data; False = widgets
    present, zero citations. Computed at _seal (the one chokepoint) because
    cheap and judge verdict dicts replace each other."""
    found: list[Any] = []
    has_widget = False
    for b in blocks:
        if b.kind != "widget":
            continue
        has_widget = True
        w = b.data.get("widget")
        if isinstance(w, dict):
            _walk_citations(w, found)
    if not has_widget:
        return None
    return len(found) > 0
```

Add `Optional` to quality.py's typing import if absent. In `compositor.py`, change `_seal` to:

```python
def _seal(question: str, emitted: list[Block], status: str, verdict: dict) -> dict[str, Any]:
    # artifacts_cited is injected HERE because the cheap and judge verdict
    # dicts replace each other — neither layer alone reaches every sealed frame.
    verdict = {**verdict, "artifacts_cited": artifacts_cited(emitted)}
    return frame_to_dict(Frame(question=question, blocks=emitted, status=status,
                               verdict=verdict, question_language=detect_language(question)))
```

and extend the existing import at compositor.py:10: `from .quality import assess, cheap_verdict_dict, artifacts_cited`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_cuaderno_artifact_honesty.py tests/ -q -k "cuaderno"`
Expected: all PASS. If an existing test does exact-dict equality on a sealed verdict, extend its expected dict with `"artifacts_cited": None` (the legitimate Task-3-style update from the i18n wave) — do not weaken any other assertion.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/quality.py src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_artifact_honesty.py
git commit -m "feat(shell): artifacts_cited confession axis, injected at _seal so both verdict paths carry it"
```

---

### Task 3: `_artifact_summary` — the judge sees artifacts

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/quality.py`
- Modify: `src/copyclip/intelligence/cuaderno/judge.py:100-110`
- Test: `tests/test_cuaderno_artifact_honesty.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
from copyclip.intelligence.cuaderno.quality import _artifact_summary


def test_artifact_summary_graph_subset():
    w = {"kind": "graph_subset",
         "nodes": [{"id": "a", "label": "Parser"}, {"id": "b", "label": "Lexer"}],
         "edges": [{"from": "a", "to": "b"}]}
    s = _artifact_summary([_widget_block(w)])
    assert "Parser" in s and "Lexer" in s and "->" in s


def test_artifact_summary_unknown_kind_falls_back():
    w = {"kind": "never_seen", "things": [{"label": "X9"}, {"name": "Y7"}]}
    s = _artifact_summary([_widget_block(w)])
    assert "X9" in s and "Y7" in s   # generic fallback: nothing is invisible


def test_artifact_summary_empty_without_widgets():
    assert _artifact_summary([Block.paragraph("hi")]) == ""


def test_judge_fence_includes_artifacts(monkeypatch):
    """The judge's user message must contain the [ARTIFACTS] section when the
    answer carries widgets."""
    from copyclip.intelligence.cuaderno import judge as judge_mod

    captured = {}

    class _Client:
        def messages_create(self, **kw):
            captured["user"] = kw["messages"][0]["content"]
            return {"content": [{"type": "text", "text": '{"decision": "ok", "reason": "fine"}'}]}

    ledger = ReadLedger()
    w = {"kind": "graph_subset", "nodes": [{"id": "n", "label": "Compositor"}], "edges": []}
    judge_mod.judge_answer(client=_Client(), question="q?",
                           blocks=[Block.paragraph("answer"), _widget_block(w)],
                           ledger=ledger, model="m")
    assert "[ARTIFACTS]" in captured["user"]
    assert "Compositor" in captured["user"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cuaderno_artifact_honesty.py -v -k summary or fence`
Expected: FAIL (ImportError / missing section).

- [ ] **Step 3: Implement**

In `quality.py`, after `artifacts_cited`:

```python
def _flatten_strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for k in ("label", "text", "name", "id"):
            v = node.get(k)
            if isinstance(v, str) and v:
                out.append(v)
        for v in node.values():
            _flatten_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten_strings(v, out)


def _artifact_summary(blocks: list[Block]) -> str:
    """Deterministic textual rendering of widget claims for the judge. Known
    kinds get a readable shape; unknown kinds hit the generic fallback so no
    widget kind is ever invisible to the judge."""
    parts: list[str] = []
    for b in blocks:
        if b.kind != "widget":
            continue
        w = b.data.get("widget")
        if not isinstance(w, dict):
            continue
        kind = w.get("kind")
        if kind == "graph_subset":
            nodes = [n for n in (w.get("nodes") or []) if isinstance(n, dict)]
            edges = [e for e in (w.get("edges") or []) if isinstance(e, dict)]
            labels = [str(n.get("label") or n.get("id") or "?") for n in nodes]
            arrows = [
                f"{e.get('from') or e.get('source') or '?'} -> {e.get('to') or e.get('target') or '?'}"
                for e in edges
            ]
            parts.append(f"graph: nodes [{', '.join(labels)}]; edges [{'; '.join(arrows)}]")
        elif kind == "sequence_diagram":
            steps = [s for s in (w.get("steps") or []) if isinstance(s, dict)]
            lines = [
                f"{s.get('from') or '?'} -> {s.get('to') or '?'}: {s.get('text') or ''}".strip()
                for s in steps
            ]
            parts.append("sequence: " + "; ".join(lines))
        elif kind == "callers_tree":
            callers = [c for c in (w.get("callers") or []) if isinstance(c, dict)]
            names = [str(c.get("name") or "?") for c in callers]
            parts.append(f"callers of {w.get('root') or '?'}: [{', '.join(names)}]")
        else:
            flat: list[str] = []
            _flatten_strings(w, flat)
            parts.append(f"{kind or 'widget'}: " + "; ".join(flat))
    return "\n".join(parts)
```

Before finalizing the graph edge fields, check the real shape: `grep -n "from\|to\|source\|target" frontend/src/components/cuaderno/widgets/GraphSubset.tsx | head -8` — keep whichever pair the component reads first in the f-string (the `or` fallback already tolerates both).

In `judge.py`: change the import (line 9) to `from .quality import _answer_text, _artifact_summary`, and replace the fence body construction (line ~107):

```python
    answer = _answer_text(blocks)
    art = _artifact_summary(blocks)
    if art:
        answer = f"{answer}\n\n[ARTIFACTS]\n{art}"
```

then use `{answer}` between the fences instead of `{_answer_text(blocks)}`.

**Language detection stays prose-only:** do NOT touch `assess`'s use of `_answer_text`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_cuaderno_artifact_honesty.py tests/test_cuaderno_judge*.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/quality.py src/copyclip/intelligence/cuaderno/judge.py tests/test_cuaderno_artifact_honesty.py
git commit -m "feat(shell): judge sees a deterministic [ARTIFACTS] rendering — per-kind summaries with a generic fallback"
```

---

### Task 4: Frontend confession — provenance line for uncited artifacts

**Files:**
- Modify: `frontend/src/components/cuaderno/strings.ts`
- Modify: `frontend/src/components/cuaderno/frames/FrameDynamic.tsx:43-46,65-77`
- Modify: `frontend/src/types/api.ts` (the Frame verdict type)

- [ ] **Step 1: Add the strings**

In `strings.ts`, after `provenance_unjudged` in BOTH locales:

```ts
    // en:
    provenance_artifacts_uncited: 'the diagrams in this answer cite no read code',
    // es:
    provenance_artifacts_uncited: 'los diagramas de esta respuesta no citan código leído',
```

- [ ] **Step 2: Type the axis**

In `types/api.ts`, find the Frame `verdict` type (`grep -n "verdict" frontend/src/types/api.ts`) and add to its object type: `artifacts_cited?: boolean | null`.

- [ ] **Step 3: Stack the provenance notes in FrameDynamic**

Replace the single-note logic (lines 43-46) and its render (lines 65-77) with a notes array — both notes can apply at once:

```tsx
  const showProvenance = isLegacy || preJudge || judgeUnavailable
  const provenanceNotes: string[] = []
  if (showProvenance) {
    provenanceNotes.push(
      judgeUnavailable ? t('provenance_unjudged', lang) : t('provenance_legacy', lang),
    )
  }
  // Wave-2 honesty backbone: a frame whose widgets carry zero citations
  // confesses it — the axis never changes status, it only discloses.
  if (frame.verdict?.artifacts_cited === false) {
    provenanceNotes.push(t('provenance_artifacts_uncited', lang))
  }
```

and in the JSX replace the `{showProvenance ? (...) : null}` block with:

```tsx
      {provenanceNotes.length > 0 ? (
        <div
          style={{
            fontFamily: 'var(--font-ui)',
            fontSize: 11,
            letterSpacing: '0.04em',
            color: 'var(--ink-4)',
            marginBottom: 12,
          }}
        >
          {provenanceNotes.map((n, i) => (
            <div key={i}>{n}</div>
          ))}
        </div>
      ) : null}
```

- [ ] **Step 4: Verify build**

Run: `npm --prefix frontend run build`
Expected: tsc -b + vite green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cuaderno/strings.ts frontend/src/components/cuaderno/frames/FrameDynamic.tsx frontend/src/types/api.ts
git commit -m "feat(shell): frame-level confession line when artifacts cite no read code (es/en)"
```

---

### Task 5: Tutor contract — widgets must cite

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/tool_catalog.py:119-124` (emit_block description)

- [ ] **Step 1: Extend the emit_block description**

```python
            "description": (
                "Emit ONE block of your answer. Call once per block, in order. "
                "Each block must conform to the Block schema in the system prompt. "
                "Your answer IS the ordered sequence of emit_block calls. "
                "Widget primitives (nodes, steps, callers) that assert something "
                "about the code MUST carry a `citation` "
                "({kind:'path', path, line_start?, line_end?}) on the asserting item."
            ),
```

- [ ] **Step 2: Verify no contract test breaks**

Run: `python -m pytest tests/ -q -k "tool_catalog or catalog or compositor"`
Expected: PASS (if a test snapshots the description string verbatim, update the snapshot — the new sentence is the spec).

- [ ] **Step 3: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/tool_catalog.py
git commit -m "feat(shell): emit_block contract — widget primitives that assert about code must cite"
```

---

### Task 6: Bench `has_artifact` assert

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/bench/asserts.py:131-145`
- Test: `tests/test_bench_asserts.py` (append; check the existing test-file name with `ls tests/test_bench*` and use the file that tests asserts)

- [ ] **Step 1: Write the failing tests**

Append to the existing bench-asserts test file (match its existing `QuestionRecord` construction helper — copy the pattern used by the `mentions` tests):

```python
def test_has_artifact_passes_on_widget(record_factory):
    r = record_factory(blocks=[{"kind": "widget",
                                "widget": {"kind": "graph_subset",
                                           "nodes": [{"id": "a", "citation": {"kind": "path", "path": "src/a.py"}}],
                                           "edges": []}}])
    res = run_asserts(r, [{"type": "has_artifact", "kind": "graph_subset", "cited": True}], ctx_stub())
    assert res[0].outcome == "pass"


def test_has_artifact_fails_without_widget(record_factory):
    r = record_factory(blocks=[{"kind": "paragraph", "text": "hi"}])
    res = run_asserts(r, [{"type": "has_artifact"}], ctx_stub())
    assert res[0].outcome == "fail"


def test_has_artifact_cited_fails_on_uncited_widget(record_factory):
    r = record_factory(blocks=[{"kind": "widget",
                                "widget": {"kind": "graph_subset", "nodes": [{"id": "a"}], "edges": []}}])
    res = run_asserts(r, [{"type": "has_artifact", "cited": True}], ctx_stub())
    assert res[0].outcome == "fail"
```

If the existing test file has no `record_factory`/`ctx_stub` fixtures, inline a minimal `QuestionRecord(...)` construction copying the field list from `bench/artifact.py:10-31` (id/category/commit_sha/question/question_lang/status/verdict/blocks/cited_paths/citations/read_paths/content_bearing_count/answer_lang/latency_ms/input_tokens/output_tokens/cost_usd/cost_estimated) and a `AssertContext(file_length_fn=lambda p: 100)`.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_bench_asserts.py -v -k has_artifact` (adjust filename)
Expected: FAIL with KeyError `'has_artifact'`.

- [ ] **Step 3: Implement**

In `asserts.py`, import at top: `from ..quality import _walk_citations`, then before the `ASSERTS` dict:

```python
def _a_has_artifact(r, spec, ctx):
    kinds: list = []
    cited_any = False
    for b in r.blocks:
        if not isinstance(b, dict) or b.get("kind") != "widget":
            continue
        w = b.get("widget")
        if not isinstance(w, dict):
            continue
        kinds.append(w.get("kind"))
        found: list = []
        _walk_citations(w, found)
        if found:
            cited_any = True
    if not kinds:
        return _fail("has_artifact", "no widget blocks in answer")
    want = spec.get("kind")
    if want and want not in kinds:
        return _fail("has_artifact", f"no widget of kind {want!r}; kinds={kinds}")
    if spec.get("cited") and not cited_any:
        return _fail("has_artifact", "widgets present but none carries a citation")
    return _ok("has_artifact", f"kinds={kinds}, cited={cited_any}")
```

Register: `"has_artifact": _a_has_artifact,` in `ASSERTS`. (`KNOWN_ASSERT_TYPES = frozenset(ASSERTS)` picks it up automatically; the corpus is untouched, so **corpus_sha must NOT change** — verify with `git status` that no corpus file is modified.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_bench*.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/bench/asserts.py tests/
git commit -m "feat(shell): bench has_artifact assert — artifact-bearing answers stop scoring as content-less"
```

---

### Task 7: Front door flip — `copyclip` opens the shell, export becomes a subcommand

**Files:**
- Modify: `src/copyclip/__main__.py` (help text, bare-invocation routing, `run_export` extraction)
- Modify: `src/copyclip/intelligence/cli.py` (add `export` to `COMMANDS` + dispatch)
- Modify: `README.md` (Quick Start: note `copyclip export`)
- Test: `tests/test_front_door.py` (create)

- [ ] **Step 1: Locate the moving parts**

```bash
grep -n "COMMANDS" src/copyclip/intelligence/cli.py | head -3
grep -n "def main\|def _main_inner\|args = parser.parse_args" src/copyclip/__main__.py
```

- [ ] **Step 2: Write the failing tests**

```python
"""Front door: bare copyclip = the shell; export is an explicit subcommand."""
import subprocess
import sys

from copyclip.__main__ import classify_bare_invocation

EXPORT_ONLY_FLAGS = ["--minimize", "--prompt", "--preset", "--extension", "--include",
                     "--exclude", "--only", "--view", "--docstrings",
                     "--with-dependencies", "--output", "--print"]


def test_bare_invocation_routes_to_start():
    assert classify_bare_invocation(["copyclip"]) == ("start", ".")


def test_positional_folder_routes_to_start_with_path():
    assert classify_bare_invocation(["copyclip", "./myapp"]) == ("start", "./myapp")


def test_export_flag_on_bare_invocation_is_an_error():
    kind, detail = classify_bare_invocation(["copyclip", ".", "--minimize", "basic"])
    assert kind == "error"
    assert "--minimize" in detail


def test_export_flag_with_equals_detected():
    kind, detail = classify_bare_invocation(["copyclip", "--minimize=basic"])
    assert kind == "error"


def test_export_subcommand_help_smoke():
    out = subprocess.run([sys.executable, "-m", "copyclip", "export", "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "--minimize" in out.stdout


def test_bare_help_carries_the_claim():
    out = subprocess.run([sys.executable, "-m", "copyclip", "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    assert "understanding your own codebase" in out.stdout
    assert "Intent Authority" not in out.stdout
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_front_door.py -v`
Expected: FAIL (ImportError: `classify_bare_invocation`).

- [ ] **Step 4: Implement**

In `__main__.py`:

1. Add near the top (module level, after imports):

```python
EXPORT_ONLY_FLAGS = frozenset({
    "--minimize", "--prompt", "--preset", "--extension", "--include", "--exclude",
    "--only", "--view", "--docstrings", "--with-dependencies", "--output", "--print",
})


def classify_bare_invocation(argv: list[str]) -> tuple[str, str]:
    """Route a non-subcommand invocation. Returns ('start', folder) or
    ('error', offending_flag). The front door opens the shell; export flags
    on the bare invocation get the hint instead of silently exporting."""
    folder = "."
    for a in argv[1:]:
        base = a.split("=", 1)[0]
        if base in EXPORT_ONLY_FLAGS:
            return ("error", base)
        if not a.startswith("-") and folder == ".":
            folder = a
    return ("start", folder)
```

2. Extract the CURRENT export parser + pipeline body of `_main_inner` (the argparse from `parser = argparse.ArgumentParser(...)` through the end of the export flow) into `def run_export(argv_tail: list[str]) -> None:` — identical flags, but `prog="copyclip export"` and `parser.parse_args(argv_tail)`. Do not change pipeline behavior.

3. New `_main_inner` after `maybe_handle_intelligence(sys.argv)` returns False. **`--help`/`-h` must short-circuit BEFORE classify** — otherwise `copyclip --help` would start the server:

```python
    if any(a in ("--help", "-h") for a in sys.argv[1:]):
        _build_root_parser().print_help()
        return
    kind, detail = classify_bare_invocation(sys.argv)
    if kind == "error":
        print(f"[ERROR] {detail} belongs to the export flow — did you mean 'copyclip export'?",
              file=sys.stderr)
        sys.exit(2)
    from copyclip.intelligence.cli import maybe_handle as _dispatch
    _dispatch([sys.argv[0], "start", "--path", detail])
```

where `_build_root_parser()` is a small function returning an `argparse.ArgumentParser` whose `description` is the new claim text and whose `epilog` is the updated command list/examples (no arguments need defining — it exists to print help). The old export parser moves wholesale into `run_export`, so the root parser is help-only.

4. New prog description (replace lines 82-85): `"CopyClip v0.4.0 — Keeps you understanding your own codebase while AI agents write most of it."` and update the epilog: document `export` (`copyclip export .  Copy project context to clipboard`), move the `copyclip .` examples under `copyclip export`, and change the bare example to `copyclip  Open the cuaderno for the current project`. Update the KeyboardInterrupt hint (lines 65-66) to `Run 'copyclip' to open the cuaderno.`

In `cli.py`: add `"export"` to `COMMANDS`, and in `_maybe_handle_internal`:

```python
    if cmd == "export":
        from copyclip.__main__ import run_export
        run_export(argv[2:])
        return True
```

(Import inside the handler — `cli.py` is imported BY `__main__.py`, so a top-level import would be circular.)

In `README.md` Quick Start §3, after the `copyclip start` block add one line: `The clipboard context export now lives at` `` `copyclip export` ``.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_front_door.py tests/test_smoke_cli_runtime.py -q`
Expected: all PASS (the CLI smokes prove start/mcp still dispatch).

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/__main__.py src/copyclip/intelligence/cli.py README.md tests/test_front_door.py
git commit -m "feat(shell): front door flip — bare copyclip opens the cuaderno, export moves behind 'copyclip export'"
```

---

### Task 8: AskPage collapse — frontend + `/api/ask` route

**Files:**
- Delete: `frontend/src/pages/AskPage.tsx`
- Modify: `frontend/src/App.tsx` (import line 5, `Page` union line 28, branch line 134)
- Modify: `frontend/src/components/Sidebar.tsx` (the `{ id: 'ask', label: 'ask project' }` entry, line ~9)
- Modify: `frontend/src/api/client.ts` (the `ask:` method line 149 + `AskResponse` in the import)
- Modify: `frontend/src/types/api.ts` (delete `AskCitation`, `AskEvidenceItem`, `AskEvidenceGroup`, `AskResponse` — AFTER verifying each has no other consumer: `grep -rn "AskCitation\|AskEvidenceItem\|AskEvidenceGroup\|AskResponse" frontend/src/ --include="*.ts" --include="*.tsx"`)
- Modify: `src/copyclip/intelligence/server.py` (the `/api/ask` block at ~1887-1900 + the `from .ask_project import build_ask_response` import at line 17)
- Modify: `tests/test_intelligence_server_api.py` (delete the test functions that POST `/api/ask` — 7 sites at lines ~243-463; keep shared helpers used by surviving tests)

- [ ] **Step 1: Prove the consumer chain**

```bash
grep -rn "api.ask(" frontend/src/            # expect: only AskPage.tsx:53
grep -n "api/ask" src/copyclip/intelligence/server.py   # expect: route block only
grep -rn "build_ask_response" src/ --include="*.py"     # expect: server.py:17,1896 + ask_project.py only
```

If any OTHER consumer appears, STOP and report BLOCKED.

- [ ] **Step 2: Delete + edit**

`git rm frontend/src/pages/AskPage.tsx`, then remove the App.tsx import/union-member/branch, the Sidebar entry, the client method + import entry, the four api.ts types (verified orphaned), the server route block + line-17 import, and the `/api/ask` test functions.

- [ ] **Step 3: Verify green**

```bash
grep -rn "AskPage\|api/ask\|AskResponse\|AskEvidence\|AskCitation" frontend/src/ src/ tests/ --include="*.py" --include="*.ts" --include="*.tsx" && echo LEFTOVERS || echo CLEAN
python -c "import ast; ast.parse(open('src/copyclip/intelligence/server.py', encoding='utf-8').read())"
npm --prefix frontend run build && python -m pytest tests/test_intelligence_server_api.py -q
```
Expected: CLEAN (note: `ask_project.py` itself still matches `build_ask_response` — that is Task 9's file; CLEAN here means no matches OUTSIDE ask_project.py and its dedicated tests); parse OK; builds green.

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(shell): collapse AskPage into the cuaderno — page, sidebar entry, /api/ask route and bindings die together"
```

---

### Task 9: `ask_project.py` retirement

**Files:**
- Delete: `src/copyclip/intelligence/ask_project.py`
- Delete: `tests/test_ask_project_evaluation.py`, `tests/test_ask_project_provenance.py`, `tests/test_ask_project_ranking.py`, `tests/ask_project_eval_fixture.py`
- Modify: `tests/test_debt_integration.py` (remove the import at line 10 and the test functions calling `build_ask_response` — 4 call sites at lines ~123,142,192,205; keep every other test)

- [ ] **Step 1: Prove the module is production-orphaned (Task 8 must be committed)**

```bash
grep -rn "ask_project\|build_ask_response" src/ --include="*.py" | grep -v "ask_project.py:"
```
Expected: no matches (the route import died in Task 8). `build_context_bundle` is NOT affected — verify: `grep -n "build_context_bundle" src/copyclip/intelligence/server.py src/copyclip/intelligence/context_bundle_builder.py` still shows server.py:16(±1),692,1935 + the definition.

- [ ] **Step 2: Delete + surgery**

```bash
git rm src/copyclip/intelligence/ask_project.py tests/test_ask_project_evaluation.py tests/test_ask_project_provenance.py tests/test_ask_project_ranking.py tests/ask_project_eval_fixture.py
```
In `test_debt_integration.py`: remove the line-10 import and the test functions containing the 4 `build_ask_response` calls. If any of those functions also asserts debt behavior NOT covered by the remaining tests, report DONE_WITH_CONCERNS naming the lost coverage instead of silently deleting.

- [ ] **Step 3: Verify green**

```bash
grep -rn "ask_project\|build_ask_response" src/ tests/ --include="*.py" && echo LEFTOVERS || echo CLEAN
python -m pytest tests/test_debt_integration.py tests/ -q
```
Expected: CLEAN; full suite green (individual re-run for any rotating Windows-flaky failure).

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(shell): retire ask_project — its evidence-first scaffolding lives in the compositor (Axiom-0: absorb, then delete)"
```

---

### Task 10: Dashboard death date in the roadmap

**Files:**
- Modify: `src/copyclip/roadmap.md`

- [ ] **Step 1: Add the schedule section**

Insert near the top of `roadmap.md` (after its title/intro line):

```markdown
## Scheduled: dashboard retirement — Friday 2026-06-19

Ratified 2026-06-04 (cuaderno-shell consensus, Wave 5): the legacy App.tsx
router, the Sidebar, and the remaining dashboard pages are deleted on
2026-06-19, after every surviving route is re-homed to a tutor tool or a
side surface. Until then the dashboard is reachable only through the
cuaderno's existing toggle — it is an escape hatch, not a peer. No
indefinite coexistence.
```

- [ ] **Step 2: Commit**

```bash
git add src/copyclip/roadmap.md
git commit -m "docs(shell): record the dashboard death date — 2026-06-19, no indefinite coexistence"
```

---

### Task 11: Wave gate — full verification

- [ ] **Step 1: Full suites**

```bash
python -m pytest tests/ -q
npm --prefix frontend run build
bash scripts/dev-smoke.sh
```
Expected: green (re-run any rotating Windows-flaky test individually; both must pass in isolation).

- [ ] **Step 2: Regenerate the served UI bundle** (frontend changed: AskPage gone, FrameDynamic notes)

```bash
cp frontend/dist/index.html src/copyclip/intelligence/ui/index.html
grep -c "api/ask\|AskResponse" src/copyclip/intelligence/ui/index.html || echo "ARTIFACT CLEAN"
git add src/copyclip/intelligence/ui/index.html
git commit -m "chore(shell): regenerate served UI bundle for wave 2"
```

- [ ] **Step 3: Manual checks**

- `copyclip --help` shows the claim, no "Intent Authority", documents `export`.
- `copyclip export --help` lists the export flags.
- `python -m copyclip . --minimize basic` exits 2 with the hint.
- `copyclip start` still opens the dashboard+cuaderno (unchanged).
- A question whose answer includes an uncited widget renders the confession line (forceable in dev by asking for a diagram of something; acceptable to defer to live use if not reproducible on demand).

- [ ] **Step 4: Branch ready for PR**

Squash subject: `feat(shell): wave 2 — front door flip + artifact-aware honesty backbone (#NN)`.
