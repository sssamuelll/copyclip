# CopyClip Cuaderno — SSE Streaming Design Spec (Task 32)

**Date:** 2026-05-29
**Status:** Approved for implementation planning
**Implements:** Task 32 of the [Cuaderno Phase 1 plan](../plans/2026-05-28-cuaderno-phase-1.md) — the streaming finisher that was deliberately deferred to v1.1 to keep the Phase 1 critical path narrow.
**Parent design:** [Cuaderno Conversacional design](2026-05-28-copyclip-cuaderno-conversacional-design.md) — the source of truth for *what the cuaderno is*. This spec only adds *live streaming of the answer*.
**Tracking:** to be opened as the v1.1 streaming epic (4 PRs, see *Sequencing*).

> **Terminology note.** This is the **Task 32 / v1.1 streaming finisher**, not the parent design's "Phase 2" (which is interactive widgets + executable code blocks). The parent design lists streaming inside the Phase 1 *success criteria* ("tool calls visible during streaming", "frame begins streaming text within 5 seconds"); the implementation plan carved it out as Task 32. This spec closes that gap.

---

## Why

Phase 1 shipped the cuaderno as a one-shot request/response: `POST /api/cuaderno/ask` runs the entire blocking agentic loop (up to `max_tool_rounds=8` synchronous Anthropic calls) and returns one fully-materialized `Frame` in a single JSON write (`server.py:2535-2544`). The user sees nothing — no tool activity, no answer — until the whole loop finishes, which for a multi-round question can exceed the design's "begins streaming within 5 seconds" criterion by a wide margin.

The mid-stream UI is already built and prop-wired (`Cuaderno.tsx:16-22` declares `partialText`/`toolCalls` and forwards them to `FrameMidStream`; `FrameMidStream.tsx:16-46` renders tool-call rows and a streaming caret), but it is **dead wiring**: `CuadernoPage.tsx:99-108` never supplies those props, so it renders only empty defaults for the brief blocking window. Phase-1 self-review recorded this explicitly: streaming was "postponed in Task 32 ... so it isn't surprise scope."

This spec makes the cuaderno stream its answer live: the user watches the tutor read evidence, then watches the answer compose itself block by block.

---

## Decisions locked in brainstorming (2026-05-29)

Three decisions were made before this spec and govern the entire design:

1. **Granularity: block-by-block, complete.** Each block (lead, paragraph, code_block, widget, …) appears whole and in order. No intra-block token typing. This is editorial — it honors "the frame is the page" and never shows the user half-formed prose or raw JSON.
2. **Emission protocol: `emit_block` tool-use.** The model delivers its answer by calling a structured tool once per block, then `finish` — instead of returning a final text blob of JSON. The SDK delivers each tool input as structured data, so there is **zero free-text JSON parsing** on the answer path. This is the most anti-invention-safe option and matches the system's core commitment: every claim is structured, anchored, and verifiable.
3. **Transport: fetch-stream, not `EventSource`.** Native `EventSource` is GET-only and cannot carry the JSON POST body (`question`, `session_id`) that `/api/cuaderno/ask` requires. The client uses `fetch()` + `ReadableStream` + `TextDecoder` to parse `text/event-stream` manually, preserving the existing POST-with-body shape.

---

## Architectural invariant (unchanged)

The LLM **never invents**. Every block it emits must be anchored to recoverable evidence (`path:line`, commit SHA, test name), exactly as in Phase 1. Streaming changes only the *framing* of the answer (one block per tool call instead of one JSON blob), not its content. A block that fails server-side validation is **rejected**, not rendered.

---

## Execution model — the two-phase loop

The agentic loop in `compose_frame` (`compositor.py:24-99`) moves from one implicit phase to **two explicit phases**, separated by the *kind* of tool the model calls:

### Phase A — Evidence (read tools)

The model calls the Phase-1 read tools (`read_file`, `grep_symbols`, `get_callers`, `get_callees`, `git_log`, `git_blame`, `git_diff`, `find_tests`). Each returns data to the model exactly as today (`compositor.py:77-96`). For each, the stream emits a `tool` event (`running` → `done · {ms}` / `error`) that feeds the `FrameMidStream` tool-call rows.

### Phase B — Composition (emit tools)

When the model has enough evidence, instead of returning a final text Frame it calls `emit_block(block)` once per block, in order, and closes with `finish`. Each `emit_block` whose input completes (`content_block_stop` from the streaming SDK) produces a `block` event.

### Read-vs-emit separation

The loop stops being the binary `stop_reason == 'tool_use'` of `compositor.py:56`. For each `tool_use` block in a turn, the compositor classifies by name:

| Tool name | Handling | tool_result fed back |
|---|---|---|
| `read_file`, `grep_symbols`, `get_callers`, `get_callees`, `git_log`, `git_blame`, `git_diff`, `find_tests` | `dispatch_tool` → anchor system | the data (as today) |
| `emit_block` | validate via `Block.from_dict`; on success accumulate + emit `block` event; on failure emit nothing | `{"ok": true}` on success; `{"error": "<reason>"}` on malformed block (model self-corrects) |
| `finish` | terminal marker | not applicable (loop ends) |

### Done detection

The loop terminates when **(a)** `finish` is seen, or **(b)** a turn ends with `stop_reason == 'end_turn'` and no further tool calls (implicit finish — assemble whatever blocks were accumulated). On termination the **compositor** assembles `Frame(question=<the request's question>, blocks=<accumulated blocks>)` and yields it as its terminal event; the **HTTP handler** then persists it (obtaining `position`) and writes the `frame` wire event — see the layer-split note under *SSE event protocol*. If zero blocks were emitted, the compositor falls back to `_fallback_frame(...)` (`compositor.py:68-72`) — the same fallback path Phase 1 uses for parse failure and budget exhaustion.

The model **no longer echoes `question`**. In Phase 1 the model returned `{question, blocks:[...]}` and the server trusted the echoed question. Now the server already knows the question (it is the request input) and constructs the `Frame` with it. One coupling removed.

### Why this forces the streaming SDK

`emit_block`-as-tool-use only streams block-by-block if we use `client.messages.stream`, not `client.messages.create`. With the blocking call (`anthropic_client.py:24`) all `emit_block` tool-use blocks arrive together at the end of the turn — no incremental delivery. With `messages.stream` we read each block at its `content_block_stop`. Multiple `emit_block` blocks may arrive in a single assistant turn (the model can emit many tool_use blocks at once); we stream each as it closes and stop when `finish` is seen, so no extra round-trip is required for the common case. If a turn ends with `stop_reason == 'tool_use'` but no `finish` (the model paused for acks mid-emit), the compositor acks the emitted blocks and re-enters the loop so the model can continue.

---

## SSE event protocol (the wire)

Defined once in Python as the single source of truth, mirrored in TypeScript. Each event is written as one `data: <json>\n\n` record followed by an explicit `wfile.flush()`.

| Event | Payload | Emitted when |
|---|---|---|
| `meta` | `{ session_id }` | First, before any other event — lets the client persist the session id early |
| `tool` | `{ id, name, args, state: "running" \| "done" \| "error", ms? }` | Evidence phase — drives `FrameMidStream` rows |
| `block` | `{ block }` (a single Block dict) | Each `emit_block` whose input completes — appended to the growing `FrameDynamic` |
| `frame` | `{ position, frame }` | `finish` / implicit-finish — the assembled Frame; triggers persistence + commit on the client |
| `error` | `{ message, partial: boolean }` | Fallback, budget exhaustion, parse failure, or client disconnect. `partial: true` means some blocks were already emitted |

`tool` events are Scope A; `block` events are Scope B; both flow through the same stream. The `ToolRow` shape (`state`, `name`, `args`, `ms`) matches the existing `FrameMidStream` prop contract exactly.

**Layer split.** The HTTP handler owns `session_id` (from `create_session`, `server.py:2528-2529`) and `position` (from `save_question`), so it emits `meta` *before* iterating the compositor generator and enriches the terminal event with `position`. The compositor generator (`iter_compose_events`) yields only `tool` and `block` events plus a terminal assembled-Frame event; it knows neither `session_id` nor `position`. This keeps the generator pure and reusable by the non-streaming `compose_frame` wrapper.

---

## Backend changes

| File | Change |
|---|---|
| `cuaderno/anthropic_client.py:23-36` | Add `messages_stream(**kwargs)` using `self._client.messages.stream(...)`, surfacing the SDK event iterator (`content_block_start`, `input_json_delta`, `content_block_stop` with the completed block, `message_stop`) plus `get_final_message()`. Keep `messages_create` for the non-streaming restore path. |
| `cuaderno/compositor.py:24-99` | Refactor the core into a generator `iter_compose_events(...)` that `yield`s typed events. Keep `compose_frame(...) -> Frame` as a thin wrapper that drains the generator and returns the final Frame, so the session-restore path reuses the same core with no logic fork. The read/emit/finish classification, block validation, Frame assembly, and fallback live here. |
| `cuaderno/tool_catalog.py` | Add `emit_block` (input_schema = loose object: required `kind` string + `additionalProperties: true`, validated server-side by `Block.from_dict`) and `finish` (no args). `dispatch_tool` must **not** route these to the anchor system — the compositor intercepts them. |
| `cuaderno/prompts.py:18-21` | Change the output contract: "When you have gathered enough evidence, deliver your answer by calling `emit_block` once per block, in order, then call `finish`. Do not return the answer as text." Keep all anti-invention rules; every block still carries its citations. |
| `server.py:2535-2552` | Convert `/api/cuaderno/ask` to SSE, modeled on the codebase's only working SSE precedent, `server_events.py:21-65`: write `text/event-stream` + `Cache-Control: no-cache` + `Connection: keep-alive` headers, iterate `iter_compose_events`, `wfile.write('data: …\n\n')` + `wfile.flush()` per event. The sqlite connection stays open for the full stream (the `finally` at 2548-2552 must wrap the streaming loop). `save_question` runs on the terminal `frame` event so live and restored sessions produce identical persisted Frames. Handle client disconnect (BrokenPipe → abort the loop cleanly, no half-written DB). Emit a `: keepalive\n\n` comment ping if a round exceeds a threshold. **Do not** copy the 30s self-termination deadline of `/api/events` (`server_events.py:56`) — the ask stream lives until composition completes. |

`json_response` (`server_helpers.py:7-13`) cannot be reused for SSE — it hard-codes `Content-Type: application/json` and a fixed `Content-Length`. The ask handler writes events directly, modeled on `server_events.write_event`.

---

## Frontend changes

| File | Change |
|---|---|
| `types/api.ts:826-849` | Add `CuadernoStreamEvent` (discriminated union mirroring the wire table). Consolidate `ToolRow`, currently duplicated in `FrameMidStream.tsx:1-8` and `Cuaderno.tsx:18`, into one shared type. |
| `api/cuaderno.ts:3-44` | Add `askStream(question, sessionId, { onEvent, signal }): Promise<void>` — `fetch` POST (keeps the JSON body) + `response.body.getReader()` + `TextDecoder`, splitting on `\n\n` SSE record boundaries, parsing each `data:` line to a typed `CuadernoStreamEvent`, dispatching via `onEvent`, resolving when the stream closes. Accept an `AbortSignal`. Keep `postJson`/`ask` for the session-restore path. |
| `pages/CuadernoPage.tsx:40-63` | Rework `onAsk` to consume the stream. New state: `partialBlocks: Block[]`, `toolCalls: ToolRow[]`, and an `AbortController` ref. `meta` → set session id + localStorage early; `tool` → push/update a row; `block` → append to `partialBlocks`; `frame` → commit the `CuadernoQuestion` (the logic currently in the `.then` at lines 45-60) and clear partial state; `error` → set the banner. Abort on unmount and on a new submit while streaming. Pass `toolCalls` and `partialBlocks` down to `<Cuaderno>` — this revives the dead wiring. |
| `components/cuaderno/Cuaderno.tsx:39-40` | Replace the binary `isLoading ? 'midstream' : 'frame'` scene gate with the two-act flow below. |

### Scene gate — two acts, reusing both existing components

1. **Reading evidence** → `FrameMidStream` shows tool-call rows (`· queued`, `◐ running`, `✓ {ms} ms`).
2. **Writing the answer** → `FrameDynamic` renders `partialBlocks` as it grows (append-only; the index keys at `FrameDynamic.tsx:21` are fine for append). The tool-call rows collapse above it — the "stream-then-collapse" behavior the parent design names as default.
3. **Settled** → `FrameDynamic` with the final, complete Frame.

`FrameMidStream.tsx:16-46` and `FrameDynamic.tsx:13-30` need no structural change — they already render the shapes; they just receive real, growing data instead of empty defaults.

---

## Error handling and partial streams

Consistent with the system's "nothing invented, everything recoverable" ethos:

- **Interrupted stream** (network drop, model error, or budget exhausted) after N blocks were emitted: **keep the already-emitted blocks** — they are real and anchored — show an explicit "stream interrupted" marker, and persist the partial Frame. The `error` event carries `partial: true`.
- **Malformed block** from `emit_block`: rejected with an error tool_result so the model self-corrects; never rendered.
- **Zero blocks / budget exhausted**: terminal `_fallback_frame` (`compositor.py:68-72, 99`) surfaced as a terminal `error` event with `partial: false`.
- **Session id timing**: emitted in the first `meta` event so a mid-stream failure still leaves the session persisted client-side.

---

## Testing

**Backend:**

- `iter_compose_events` with a stubbed `messages.stream` returning scripted turns: assert event ordering (`meta`-free at this layer; `tool` before `block`; terminal `frame`), read-vs-emit-vs-finish classification, implicit-finish on `end_turn`, zero-blocks → fallback, malformed block → error tool_result + loop continues.
- HTTP integration: `POST /api/cuaderno/ask` returns `text/event-stream`; parse the event records; assert the terminal `frame` event equals the Frame produced by the non-streaming `compose_frame` wrapper (**live-vs-restore parity**); assert the session is persisted.
- Disconnect: simulate client close mid-stream → server aborts without crashing and writes no partial DB row beyond the documented partial-persist behavior.

**Frontend:**

- `askStream` parser unit test: feed a synthetic `text/event-stream` byte stream including records split across chunk boundaries → assert typed events emitted in order; assert `AbortSignal` stops it.
- `CuadernoPage` `onAsk`: simulate an event sequence → assert `toolCalls`/`partialBlocks` state transitions and final question commit; assert parity with the one-shot restore path (identical final `blocks[]`).

---

## Sequencing (4 PRs)

1. **Backend core** — event taxonomy + `iter_compose_events` + read/emit/finish handling + `emit_block`/`finish` in the catalog + prompt change. `compose_frame` wrapper preserved for restore. Fully unit-tested, no HTTP change.
2. **Backend streaming SDK + HTTP** — `messages_stream` in the adapter + `/ask` converted to SSE (headers, flush, conn lifetime, disconnect, keepalive, persist-at-terminal). Integration test.
3. **Frontend transport** — types union + `askStream` parser + tests. No UI change.
4. **Frontend wiring** — `CuadernoPage` consumes the stream, two-act scene gate, abort handling, partial rendering. The dead wiring comes alive. e2e.

Each PR merges green on its own.

---

## Anti-scope

Explicitly NOT in this spec:

- **Intra-block token-by-token typing** — granularity is block-complete (decided in brainstorming).
- **Interactive widgets** — the parent design's Phase 2.
- **`read_transcript`** — out of scope per the Phase 1 plan.
- **Cuaderno replacing the home** — the parent design's Phase 3.
- **Editing the user's source files** — permanent anti-scope of the parent design.
- **Reconnection / `Last-Event-ID` resume of an interrupted ask** — an interrupted ask is not resumable; the user re-asks. (The `/api/events` cursor mechanism is not extended to `/ask`.)

---

## Related

- Implements: Task 32 of [`2026-05-28-cuaderno-phase-1.md`](../plans/2026-05-28-cuaderno-phase-1.md).
- Parent design: [`2026-05-28-copyclip-cuaderno-conversacional-design.md`](2026-05-28-copyclip-cuaderno-conversacional-design.md).
- SSE precedent in the codebase: `src/copyclip/intelligence/server_events.py:21-65` (`/api/events`).
- Memory: [[copyclip-temporal-causal-wedge]], [[copyclip-personal-tool]].
