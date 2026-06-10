# Cuaderno Interaction Trace — debug logging that replaces screenshots

**Status:** Design (approved 2026-06-10) — ready for implementation planning
**Surface:** `src/copyclip/intelligence/cuaderno/` + `src/copyclip/intelligence/playground.py` + `src/copyclip/intelligence/marimo_runner.py` + launch handler in `server.py`
**Author:** Samuel + Claude Code

---

## 1. Motivation — the ask path is a black box

Debugging the cuaderno today means pasting screenshots or flattened render text into a Claude session. Both lose the structure: a paste cannot show which blocks were widgets, which gate fired, or why a provisional answer was discarded.

The underlying problem is that **an ask leaves almost no trace**. The entire `intelligence/` package contains zero uses of the `logging` module. One interaction's only durable records are the stderr HTTP access line and the final frame in `cuaderno_questions.frame_json`. Everything diagnostic evaporates:

- A `reset` SSE event carries no reason — there is no record of *why* a retry discarded the streamed blocks (`compositor.py:413-447`).
- Widget payloads rejected by `validate_block_dict` / `validate_widget_payload` are sent back to the model as `is_error` tool_results and persisted nowhere (`compositor.py:479-481`).
- The widget-fixation recovery directives (`compositor.py:524-532`), playground-floor declines (`compositor.py:99-179`), and judge fail-opens (`judge.py:125-127`, recorded only as `source:"unjudged"`) are invisible.
- The tool/read trace travels in SSE `tool` events and dies with the connection; the `ReadLedger` is request-local.
- The interactive path records no model name, token usage, or latency (the offline bench does, via `QuestionRecord` — but `iter_ask_events` produces none of it).

This spec adds an **interaction trace**: one append-only JSONL file per interaction, written incrementally at every decision point, designed to be read top-to-bottom by Claude during a debug session. "Revisa la última pregunta" becomes `Read` on one file.

## 2. Goals

- Every cuaderno ask and every playground launch writes a **self-contained JSONL timeline** to `<project_root>/.copyclip/logs/cuaderno/`.
- Every decision the pipeline takes is recorded **with its reason**: gate rejections (with the full rejected payload), retries (with type and injected directive), judge verdicts (with fail-open cause), floor resolutions and declines.
- The trace survives crashes: events are appended and flushed one line at a time, so a dead server leaves a readable partial trace.
- Full LLM wire fidelity (system + messages per round, raw responses, raw judge output) is available **under a flag** (`COPYCLIP_TRACE_WIRE=1`), never by default.
- Tracing can **never break or slow the ask path** in any user-visible way: all tracer errors are swallowed, the tracer self-disables on first write failure.
- The bench, existing tests, and the SSE wire format are untouched.

## 3. Non-goals

- No stdlib `logging` adoption, no log levels, no rotating handler. This is an artifact writer, not a logger.
- No HTTP debug endpoint and no CLI reader. Files are the interface (an endpoint can be sugar later).
- No frontend/JS-side logging. The trace records what the server emitted; that is what the frontend renders.
- No bench integration in v1. The bench keeps `QuestionRecord`/`RunArtifact`; the compositor's `trace` parameter defaults to no-op there.
- No tracing of other server routes (analyze, decisions, handoff CRUD).
- No UI for viewing traces.

## 4. Architecture

One new module: `src/copyclip/intelligence/cuaderno/trace.py`.

```
ask_stream.iter_ask_events                     launch handler (server.py)
   │ creates                                       │ creates
   ▼                                               ▼
InteractionTrace("ask", …)                  InteractionTrace("launch", …)
   │ passed as optional param                      │ passed as optional param
   ▼                                               ▼
iter_compose_events(…, trace=…)             launch_playground(…, trace=…)
   │ one-line trace.event(…) calls                 │ → marimo_runner spawn/ready/error
   ▼
.copyclip/logs/cuaderno/ask_<UTC>_<sid8>.jsonl     launch_<UTC>_<pid8>.jsonl
```

### 4.1 `InteractionTrace`

- `InteractionTrace.start(kind, logs_dir, header: dict) -> InteractionTrace` — creates the directory if needed, runs retention pruning, opens the file, writes the header event (`ask.start` / `launch.start`). If anything fails, returns a **disabled** instance (no-op from then on) and prints one `WARN` line to stderr.
- `trace.event(name, **payload)` — appends one JSON line (`json.dumps` + `\n`), flushes immediately. Any exception disables the tracer for the rest of the interaction (one stderr `WARN`, never re-raised).
- `trace.close(**payload)` — writes the footer event (`ask.end` / `launch.end`), closes the handle. Idempotent.
- `NullTrace` — the same interface, every method a pure no-op. `trace=None` parameters resolve to it, so the bench and existing callers are unaffected.
- Wire capture is decided once at `start` by reading `COPYCLIP_TRACE_WIRE`; the instance exposes `trace.wire` (bool) so call sites can skip building large payloads when off.

### 4.2 File layout, naming, retention

- Directory: `<project_root>/.copyclip/logs/cuaderno/` (sibling of `intelligence.db`'s `.copyclip/` home; `.copyclip/` is already covered by `.gitignore:130`, so traces are never committed).
- Names: `ask_<YYYYMMDDTHHMMSSZ>_<session_id[:8]>.jsonl`, `launch_<YYYYMMDDTHHMMSSZ>_<tag>.jsonl` where `tag` is a random 8-hex id (the playground_id does not exist until spawn; `launch.ready` carries the real id). UTC timestamps sort lexicographically, so "the latest ask" is the last `ask_*` file. A same-second name collision gets a `-2`, `-3`… suffix instead of clobbering.
- Retention: at each `start`, if the directory holds more than **200** files, delete the oldest by name until 200 remain. Constant `MAX_TRACE_FILES = 200` in `trace.py`; no config knob in v1.

### 4.3 Line format

Every line carries three fixed fields plus the event payload:

```json
{"seq": 17, "t_ms": 4312, "event": "block.reject", ...payload}
```

- `seq` — per-file monotonic counter from 0.
- `t_ms` — integer milliseconds since `start` (from `time.perf_counter()`).
- `event` — the event name (taxonomy below).
- Events that correspond 1:1 to something emitted to the frontend carry `"sse": true`. SSE emissions are not double-logged.

## 5. Event taxonomy

### 5.1 Ask events (always on)

| event | payload | source |
|---|---|---|
| `ask.start` | question, session_id, question_language, model, judge_model, provider, max_tool_rounds, wire (bool), copyclip_version | header, `ask_stream` |
| `llm.round` | round_i, closing (bool), ms, stop_reason, usage (input/output tokens when the provider reports them, else null) | `compositor` per streaming call |
| `block.accept` | block (full dict), `sse: true` | `compositor` emit_block accepted |
| `block.reject` | block (full dict), reason (the `validate_block_dict` / `validate_widget_payload` string), recovery (which recovery text was sent to the model) | `compositor` emit_block rejected |
| `recovery.directive` | variant: visual \| run \| generic | widget-fixation backstop |
| `tool.run` | id, name, args (short label), ms, error (str or null), content_bearing (bool), result_paths (paths newly contributed to the ledger by this call — a delta; re-reads of already-traced paths show []), `sse: true` | `compositor` tool dispatch |
| `verdict.cheap` | full `QualityVerdict` dict (status, suspicion, language_mismatch, question_language, reason) | `assess()` result |
| `retry` | kind: grounding \| language \| responsiveness, reason, directive (text injected), discarded_blocks (count), `sse: true` (the `reset`) | both retry latches |
| `verdict.judge` | parsed `JudgeVerdict` dict + decision, judged (bool), fail_open_error (str or null) | judge call site |
| `floor` | attempted (bool), symbol (resolved name/file/line or null), decline_reason (str or null), reclassified (bool) | `_floored_frame` |
| `seal` | status, verdict (dict), blocks (count), position (int or null), `sse: true` (the `frame`) | seal points / after persist |
| `persist` | outcome: ok \| partial \| failed, error (str or null) — including the currently-swallowed bare-except at `ask_stream.py:88-91` | `ask_stream` |
| `error` | message, partial (bool), `sse: true` | stream-failure terminal |
| `ask.end` | total_ms, outcome (sealed status, or error/disconnect) | footer, `ask_stream` finally |

### 5.2 Launch events (always on)

| event | payload |
|---|---|
| `launch.start` | source, function_ref (dict), breadcrumb, suggested_inputs |
| `launch.resolve` | resolved {file, name, qualname, kind, module, line_start, parent_class} or failure reason |
| `launch.notebook` | notebook path, input elements built (name → ui element kind), deps_hint |
| `launch.spawn` | cmd, port, pid, mode (run \| edit) |
| `launch.ready` | playground_id, iframe_url (elapsed time is the line's own `t_ms`) |
| `launch.error` | stage (request \| resolve \| notebook \| spawn \| ready), error |
| `launch.end` | total_ms, outcome |

### 5.3 Wire events (only with `COPYCLIP_TRACE_WIRE=1`)

| event | payload |
|---|---|
| `wire.request` | round_i, model, system (full), messages (full serialized list), tools (names only) |
| `wire.response` | round_i, stop_reason, content (raw assistant content blocks) |
| `verdict.judge` gains | raw (the judge's raw text output) |

Captured at the call boundary **in the compositor / judge call site**, not inside `anthropic_client.py` / `openai_client.py` — providers stay untouched.

Size expectation: semantic-only traces run tens of KB per ask; wire traces can reach several MB — hence the flag.

## 6. Integration points

No pipeline restructuring; every hook is a one-line `trace.event(...)` at code that already exists.

- **`ask_stream.py`** — owns the lifecycle. Creates the trace before yielding `meta`, passes it to `iter_compose_events`, traces `seal` (with `position`), `persist`, `error`, and closes in the same `finally` that persists partials on disconnect.
- **`compositor.py`** — `iter_compose_events(..., trace=None)` (and `compose_frame` passes it through). Hooks at: emit_block accept/reject (~377-386), widget-fixation backstop (~524-532), tool dispatch (~487-513), `assess` (~405), both retry latches (~413-447), judge call (~435-453), floor (~448-464, `_floored_frame`), and each streaming call for `llm.round` / wire events.
- **`server.py` launch handler + `playground.py` + `marimo_runner.py`** — `launch_playground(..., trace=None)`; the runner reports spawn/ready/error through it.
- **Bench** — untouched; calls without `trace`, gets `NullTrace`.

## 7. Error handling — the golden rule

The tracer can never break the ask path:

- `start` failure (directory, file, retention) → disabled instance + one stderr `WARN`.
- Any `event`/`close` write failure → tracer flips to disabled for the rest of the interaction, one stderr `WARN`, exception swallowed.
- Serialization safety: payloads pass through a `default=str` JSON encoder so an unexpected object can never raise out of a hook.
- The trace file handle is closed in `ask_stream`'s `finally` / the launch handler's `finally`, the same paths that already handle disconnects.

## 8. Testing

1. **Unit — `trace.py`:** valid JSONL written; `seq`/`t_ms` monotonic; header/footer present; self-disables after an injected write failure without raising; retention prunes oldest beyond 200; `NullTrace` is a pure no-op; wire flag read once at start.
2. **Integration — compositor:** using the existing fake-client test setup: an invalid widget produces `block.reject` with the gate's reason and the full payload; a forced grounding retry produces `retry` with kind and directive and a matching discarded count; the seal event carries the final status. Assertions read the written file, not tracer mocks.
3. **Integration — launch:** with the runner mocked, a successful launch writes `launch.start → resolve → notebook → spawn → ready → end` in order; a resolution failure writes `launch.error` with `stage: "resolve"`.
4. **Wire flag:** with `COPYCLIP_TRACE_WIRE=1`, `wire.request`/`wire.response` appear with full messages; without it, no `wire.*` events exist in the file.

## 9. How a debug session uses this

1. Samuel reproduces the issue in the cuaderno.
2. Claude reads the newest `ask_*.jsonl` (lexicographic max) — no screenshot, no paste.
3. The timeline answers directly: which blocks the model tried to emit, which gate rejected what and why, whether a retry fired and with which directive, what the judge said (or why it failed open), whether the floor stood up a playground, and what was sealed.
4. If the semantics aren't enough, re-run with `COPYCLIP_TRACE_WIRE=1` and read the exact prompts and raw responses.

## 10. Deferred (named, not designed)

- HTTP endpoint serving the latest trace (sugar over the file).
- Bench runs emitting interaction traces through the same tracer.
- A trace-summary CLI command.
- Correlating an ask trace with the launch trace of a widget it emitted (today: by timestamp adjacency; a shared correlation id would require the frontend to pass the ask's session/position into the launch request).
