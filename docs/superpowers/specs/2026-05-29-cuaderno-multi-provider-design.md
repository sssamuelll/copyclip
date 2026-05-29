# CopyClip Cuaderno — Multi-Provider Design Spec

**Date:** 2026-05-29
**Status:** Approved for implementation planning
**Builds on:** [Cuaderno SSE Streaming](2026-05-29-cuaderno-sse-streaming-design.md) — this work depends on that spec's normalized streaming-adapter abstraction (`messages_stream` yielding `block_stop`/`message_stop` events). It is implemented on a branch **stacked** on `feat/cuaderno-sse-streaming` (PR #117).
**Parent design:** [Cuaderno Conversacional](2026-05-28-copyclip-cuaderno-conversacional-design.md). Closes that design's *Open Question #1* (LLM provider/model selection), which Phase 1 scoped to Anthropic.

---

## Why

The cuaderno is hardcoded to Anthropic: its `AnthropicAdapter` (`cuaderno/anthropic_client.py`) reaches directly for the `anthropic` SDK, `ANTHROPIC_API_KEY`, and `claude-sonnet-4-5`. It bypasses CopyClip's existing provider abstraction (`llm/provider_config.py` `resolve_provider`, which supports `openai`/`deepseek`/`anthropic` and defaults to **deepseek**), which the analyzer and agents already use. The result: a user whose configured provider is DeepSeek — the project default — cannot use the cuaderno at all without obtaining an Anthropic key. The streaming work (PR #117) cannot even be validated against a real LLM for such a user.

This spec makes the cuaderno **provider-agnostic** (priority: DeepSeek, the user's actual key), reusing CopyClip's existing config/onboarding, and adds an in-cuaderno provider/model selector.

---

## Decisions locked in brainstorming (2026-05-29)

1. **Block-by-block streaming on every provider.** Non-Anthropic providers get the same block-by-block UX as Claude. The OpenAI-compatible adapter translates the provider's streamed `tool_calls` into the same `block` events the compositor already consumes. The compositor is unchanged (uniform `emit_block` protocol). The behavioral risk — whether DeepSeek reliably drives the multi-round `emit_block` protocol — is real and is gated by a real-API validation step, not by code.
2. **Reuse existing config + add a cuaderno UI selector.** Provider/key configuration reuses what already exists (`copyclip start` onboarding, the dashboard `/settings` page, `/api/config`). Additionally, a small provider/model selector lives inside the cuaderno UI, writing through the same config.
3. **Adapter translates; the compositor is untouched.** The compositor keeps building Anthropic-shaped messages/tools (its current internal format). The OpenAI-compatible adapter translates bidirectionally — Anthropic→OpenAI on input, OpenAI→normalized events on output. All provider-specificity lives in the adapters. (Rejected: refactoring the compositor to a neutral message format — touches the validated Anthropic path for no present gain. YAGNI.)

---

## Architectural invariant (unchanged)

The LLM never invents; every block is validated and carries verifiable citations. Adding providers changes only *which* model produces the blocks, not the anti-invention contract. The compositor's validation (`validate_block_dict`) and the `emit_block`/`finish` protocol are provider-independent.

---

## Config surfaces (the layering)

CopyClip has **two** config surfaces; the design bridges them deliberately:

- **`llm.yaml` + ENV** — read by `llm/config.py:load_config` and `llm/provider_config.py:resolve_provider`. This is where **API keys and base URLs** live (populated by the `copyclip start` onboarding and env vars like `DEEPSEEK_API_KEY`). The analyzer and agents already resolve providers from here.
- **The `config` SQLite table** (per project) — read/written by `/api/config` and `/api/settings` (`server_routes_core.py:handle_settings_get/post`), a generic key/value store backing the dashboard `/settings` page.

The cuaderno resolves its provider in two layers:

1. **Which provider + model** — read keys `cuaderno_provider` and `cuaderno_model` from the SQLite `config` table (the UI selector writes them). If unset, fall back to `resolve_provider`'s default (`deepseek`) and the provider's default model.
2. **API key + base URL** — obtained from `resolve_provider(<chosen provider>, load_config(...))`, i.e. `llm.yaml`/ENV. Keys are **not** stored in the SQLite table and **not** settable from the cuaderno UI; they remain in the onboarding/`/settings` flow (one source of truth for secrets).

If the chosen provider's key is missing, the cuaderno returns `llm_not_configured` naming the provider, and the UI points the user to Settings.

---

## Components

### 1. Adapter contract

The contract the streaming compositor already consumes (from PR #117):

- `messages_stream(**kwargs) -> Iterator[dict]` yielding `{"type":"block_stop","block":<normalized>}` per content block and a terminal `{"type":"message_stop","stop_reason":str,"content":[<normalized>]}`.
- `messages_create(**kwargs) -> dict` (non-streaming convenience; used by the `compose_frame` wrapper and tests).

`kwargs` are the cuaderno's current Anthropic-shaped call: `model`, `system`, `tools` (Anthropic tool defs), `messages` (Anthropic content-block conversation), `max_tokens`.

### 2. `AnthropicAdapter` (existing)

Unchanged. Implements the contract over the `anthropic` SDK. Used when the resolved provider is `anthropic`.

### 3. `OpenAICompatAdapter` (new)

`cuaderno/openai_client.py`. Implements the same contract over the OpenAI Chat Completions API (sync `openai` SDK, `base_url` from the resolved provider — covers `deepseek`, `openai`, and OpenAI-compatible endpoints). It is the bidirectional translator:

**Input translation (Anthropic-shaped → OpenAI):**
- `system` (string) → a leading `{"role":"system","content":...}` message.
- tools: `{name, description, input_schema}` → `{"type":"function","function":{"name","description","parameters":input_schema}}`.
- `messages`:
  - user string (`{"role":"user","content":"<question>"}`) → same.
  - assistant turn `content:[{type:"text",text},{type:"tool_use",id,name,input}]` → `{"role":"assistant","content":<joined text or null>,"tool_calls":[{"id","type":"function","function":{"name","arguments":json.dumps(input)}}]}`.
  - user tool-results `content:[{type:"tool_result",tool_use_id,content,is_error?}]` → one `{"role":"tool","tool_call_id":...,"content":...}` per result.

**Output translation (OpenAI stream → normalized events):**
- Stream `chat.completions.create(stream=True, tools=..., messages=...)`. Accumulate `choices[0].delta`: text deltas and `tool_calls` deltas (each carries an `index`, and incrementally an `id`, `function.name`, and `function.arguments` string fragments).
- When a tool-call at a given index is complete (the next index begins, or the stream finishes), parse its accumulated `arguments` JSON and emit `{"type":"block_stop","block":{"type":"tool_use","id","name","input":<parsed>}}`. Emit text content blocks similarly.
- At stream end emit `{"type":"message_stop","stop_reason":<mapped>,"content":[<all normalized blocks>]}` where `finish_reason` maps: `tool_calls`→`tool_use`, `stop`→`end_turn`, `length`→`end_turn`.
- Tolerate malformed/partial `arguments` JSON by skipping that block (the compositor's `validate_block_dict` is the second guard).

### 4. Client factory

`cuaderno/provider.py` (new): `resolve_cuaderno_provider(conn) -> ResolvedCuaderno` (provider name, api_key, base_url, model) by layering the SQLite `config` overlay over `resolve_provider`, **catching `ProviderConfigError`** (which `resolve_provider` raises when the key is missing) and surfacing it as a typed "key missing for provider X" result rather than letting it propagate as a 500; and `build_cuaderno_client(resolved) -> AnthropicAdapter | OpenAICompatAdapter`. A separate non-raising helper reports per-provider `key_configured` for the selector (it inspects each provider's `api_key_env`/config without calling the fail-fast `resolve_provider`).

### 5. Handler integration

`/api/cuaderno/ask` (`server.py`): replace the bare `AnthropicAdapter()` with `resolve_cuaderno_provider(conn)` → `build_cuaderno_client(...)`, passing the resolved `model` into `iter_ask_events`. The 503 `llm_not_configured` guard names the resolved provider. The SSE streaming path is otherwise unchanged.

### 6. Cuaderno UI provider selector

A small control in the cuaderno surface (top-crumb area or a popover) that:
- reads available providers + the current selection from a new `GET /api/cuaderno/providers` (lists the `PROVIDERS` keys from `provider_config.py` — anthropic/openai/deepseek — with each provider's `key_configured: bool` via the non-raising check, default model, and the current `cuaderno_provider`/`cuaderno_model`).
- lets the user pick provider + model and persists via `POST /api/config` (`cuaderno_provider`, `cuaderno_model`).
- does **not** accept API keys; when a provider's key is missing it shows "key not configured" linking to `/settings`.

### 7. DeepSeek specifics

The cuaderno requires tool-calling, so for DeepSeek the model must be `deepseek-chat` (V3; supports function calling). `deepseek-reasoner` does **not** support tools and must be rejected with a clear error (and excluded/flagged in the selector). Default for deepseek: `deepseek-chat`, `base_url=https://api.deepseek.com/v1`. (Model capabilities are verified against current DeepSeek docs at implementation time.) New dependency: the `openai` Python SDK.

---

## Error handling

- **Missing key for the resolved provider** → `503 {"error":"llm_not_configured","provider":<name>,"detail":...}`; UI surfaces it and links to Settings.
- **Non-tool-capable model** (e.g. `deepseek-reasoner`) → fail fast before the agentic loop with a clear `model_lacks_tool_support` error naming the model.
- **Provider API/stream failure mid-turn** → the existing terminal `error` SSE event (`partial` flag) from PR #117, unchanged.
- **Malformed tool-call arguments from the model** → the adapter skips the block; the compositor's `validate_block_dict` rejects unknown kinds; both keep anti-invention intact.

---

## Testing

**Backend (pytest, stubbed):**
- `OpenAICompatAdapter` input translation: Anthropic-shaped `system`/`tools`/`messages` (incl. a tool_use assistant turn and a tool_result user turn) → assert the exact OpenAI-format payload.
- `OpenAICompatAdapter` output normalization: feed a fake OpenAI streaming response (a sequence of `tool_calls` argument-fragment deltas across two tool calls + a finish) → assert it yields `block_stop` per completed tool call with parsed `input`, then `message_stop` with mapped `stop_reason` and full `content`. Include a malformed-arguments fragment → assert that block is skipped.
- `resolve_cuaderno_provider`: SQLite overlay (`cuaderno_provider`/`cuaderno_model`) wins over the `resolve_provider` default; missing key surfaces correctly; `deepseek-reasoner` flagged as tool-incapable.
- `build_cuaderno_client`: anthropic→AnthropicAdapter, deepseek/openai→OpenAICompatAdapter.
- `GET /api/cuaderno/providers`: returns providers with `key_configured` + current selection.
- Provider-agnostic parity: with a stubbed OpenAICompatAdapter, the existing `iter_compose_events`/`iter_ask_events` produce the same event shapes as with the Anthropic stub (the compositor is unchanged).

**Frontend:** `npx tsc -b` clean for the selector + types (no unit-test harness, matching the project).

**Validation gate (real API — the behavioral risk from Decision 1):** with a real `DEEPSEEK_API_KEY`, run the cuaderno end to end and confirm `deepseek-chat` reliably drives the agentic loop: multiple read-tool rounds, then `emit_block` once per block, then `finish`, with blocks arriving incrementally and carrying valid citations. This cannot be verified with stubs.

---

## Anti-scope

- **Native non-OpenAI/Anthropic formats** (Gemini, Bedrock native) — supported only insofar as they expose an OpenAI-compatible endpoint; native adapters are out of scope.
- **API-key management from the cuaderno UI** — stays in onboarding / the `/settings` page. The cuaderno selector switches provider/model only.
- **Refactoring the compositor's internal message format** — the adapter-translates approach keeps it Anthropic-shaped.
- **Changing the streaming protocol or the frontend stream consumption** — those are PR #117; this spec adds providers beneath the same protocol.
- **Per-question provider switching** — selection is project-level config, not per-message.

---

## Branch / sequencing

This work depends on PR #117's adapter abstraction and is developed on `feat/cuaderno-multi-provider`, **stacked on** `feat/cuaderno-sse-streaming`. Because PR #117 cannot be validated against a real LLM for a DeepSeek user until this lands, the two are validated together with a real `DEEPSEEK_API_KEY`. Merge order: streaming (#117) first, then multi-provider — or combined if that proves simpler at integration time. The implementation plan decides the concrete branch/PR mechanics.

---

## Related

- Builds on: [`2026-05-29-cuaderno-sse-streaming-design.md`](2026-05-29-cuaderno-sse-streaming-design.md) (PR #117).
- Parent: [`2026-05-28-copyclip-cuaderno-conversacional-design.md`](2026-05-28-copyclip-cuaderno-conversacional-design.md) — closes Open Question #1.
- Reuses: `llm/provider_config.py` (`resolve_provider`, `PROVIDERS`, default `deepseek`), `llm/config.py` (`load_config`), `server_routes_core.py` (`/api/config`), `cuaderno/anchor.py` + `cuaderno/compositor.py` (unchanged).
- Memory: [[copyclip-personal-tool]], [[copyclip-temporal-causal-wedge]].
