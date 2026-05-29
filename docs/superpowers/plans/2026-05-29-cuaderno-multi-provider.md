# Cuaderno Multi-Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cuaderno provider-agnostic — DeepSeek (the project default) and any OpenAI-compatible provider work alongside Anthropic, with an in-cuaderno provider/model selector — by adding an OpenAI-compatible streaming-tool-use adapter and routing the `/api/cuaderno/ask` handler through CopyClip's existing `resolve_provider`.

**Architecture:** The compositor is untouched (it keeps building Anthropic-shaped messages/tools). A new `OpenAICompatAdapter` implements the same `messages_stream`/`messages_create` contract as `AnthropicAdapter`, translating Anthropic-shaped requests → OpenAI Chat Completions on input and the OpenAI streamed `tool_calls` → the compositor's normalized `block_stop`/`message_stop` events on output (block-by-block, emitted as each tool call completes). A small `cuaderno/provider.py` resolves which adapter to build by layering a SQLite `config` overlay (`cuaderno_provider`/`cuaderno_model`, written by the UI selector) over `resolve_provider` (which supplies the API key + base URL from `llm.yaml`/ENV).

**Tech Stack:** Python 3.10+, the `openai` Python SDK (NEW dep) for the OpenAI-compatible adapter, the existing `anthropic` SDK, `sqlite3`, the stdlib server, `pytest`. Frontend: React 18 + TypeScript + Vite (type-checked via `tsc -b`, no unit-test harness — matches the project).

**Design spec:** [`../specs/2026-05-29-cuaderno-multi-provider-design.md`](../specs/2026-05-29-cuaderno-multi-provider-design.md). Read it before starting.

**Branch:** Developed on `feat/cuaderno-multi-provider`, stacked on `feat/cuaderno-sse-streaming` (PR #117). All paths below assume that branch is checked out.

---

## File structure

### Backend — new files
- `src/copyclip/intelligence/cuaderno/openai_client.py` — `OpenAICompatAdapter`: the bidirectional Anthropic↔OpenAI translator implementing `messages_stream`/`messages_create`.
- `src/copyclip/intelligence/cuaderno/provider.py` — `resolve_cuaderno_provider`, `build_cuaderno_client`, `provider_key_status`, model defaults + tool-capability check.

### Backend — modified files
- `pyproject.toml` — add `openai` dependency.
- `src/copyclip/intelligence/server.py` — `/api/cuaderno/ask` handler routes through provider resolution; add `GET /api/cuaderno/providers`.

### Frontend — modified files
- `frontend/src/types/api.ts` — `ProviderInfo`, `CuadernoProvidersResponse`.
- `frontend/src/api/cuaderno.ts` — `getCuadernoProviders`, `setCuadernoProvider`.
- `frontend/src/components/cuaderno/ProviderSelector.tsx` — NEW small selector component.
- `frontend/src/components/cuaderno/Cuaderno.tsx` — render the selector in the top-crumb; new props.
- `frontend/src/pages/CuadernoPage.tsx` — load providers + own the selection state.
- `src/copyclip/intelligence/ui/index.html` — regenerated bundle (final task).

### Tests — new files
- `tests/test_cuaderno_openai_adapter.py`
- `tests/test_cuaderno_provider.py`
- `tests/test_cuaderno_providers_endpoint.py`

---

## PR1 — Backend provider abstraction (no change to the Anthropic path)

### Task 1: Add the `openai` SDK dependency

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: Add dependency**

In `pyproject.toml`, in the `dependencies = [...]` list, add the line `"openai>=1.40",` immediately after the existing `"anthropic>=0.39",` line.

- [ ] **Step 2: Install editable**

Run: `python -m pip install -e .`
Expected: `Successfully installed openai-x.y.z ...` (or "Requirement already satisfied").

- [ ] **Step 3: Verify import**

Run: `python -c "import openai; from openai import OpenAI; print(openai.__version__)"`
Expected: a version string `1.40.0` or higher.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add openai SDK for the cuaderno OpenAI-compatible adapter"
```

---

### Task 2: `OpenAICompatAdapter`

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/openai_client.py`
- Test: `tests/test_cuaderno_openai_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_openai_adapter.py`:

```python
import json

from copyclip.intelligence.cuaderno.openai_client import (
    OpenAICompatAdapter, _to_openai_request,
)


# --- input translation -------------------------------------------------------

def test_to_openai_request_translates_system_tools_and_messages():
    system = "you are the cuaderno"
    tools = [{
        "name": "read_file",
        "description": "read a file",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }]
    messages = [
        {"role": "user", "content": "what does this do?"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "let me look"},
            {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "README.md"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "# Hello"},
        ]},
    ]
    oai_messages, oai_tools = _to_openai_request(system, tools, messages)

    assert oai_messages[0] == {"role": "system", "content": "you are the cuaderno"}
    assert oai_messages[1] == {"role": "user", "content": "what does this do?"}
    assert oai_messages[2]["role"] == "assistant"
    assert oai_messages[2]["content"] == "let me look"
    assert oai_messages[2]["tool_calls"] == [{
        "id": "t1", "type": "function",
        "function": {"name": "read_file", "arguments": json.dumps({"path": "README.md"})},
    }]
    assert oai_messages[3] == {"role": "tool", "tool_call_id": "t1", "content": "# Hello"}
    assert oai_tools == [{
        "type": "function",
        "function": {
            "name": "read_file", "description": "read a file",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    }]


# --- streaming output normalization -----------------------------------------

class _Fn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _TC:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = _Fn(name, arguments)


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class _Chunk:
    def __init__(self, choice):
        self.choices = [choice]


class _FakeChatCompletions:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._chunks)


class _FakeChat:
    def __init__(self, chunks):
        self.completions = _FakeChatCompletions(chunks)


class _FakeOpenAI:
    def __init__(self, chunks):
        self.chat = _FakeChat(chunks)


def _adapter(chunks):
    return OpenAICompatAdapter(raw_client=_FakeOpenAI(chunks))


def test_messages_stream_emits_a_block_per_completed_tool_call():
    # Two emit_block tool calls streamed as argument fragments, then a finish.
    chunks = [
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, id="c0", name="emit_block")]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, arguments='{"kind":"lead",')]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, arguments='"text":"hi"}')]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(1, id="c1", name="emit_block")]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(1, arguments='{"kind":"paragraph","text":"body"}')]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(2, id="c2", name="finish")]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(2, arguments='{}')]))),
        _Chunk(_Choice(_Delta(), finish_reason="tool_calls")),
    ]
    events = list(_adapter(chunks).messages_stream(
        model="deepseek-chat", system="s", tools=[], messages=[], max_tokens=100))

    block_stops = [e for e in events if e["type"] == "block_stop"]
    assert [b["block"]["name"] for b in block_stops] == ["emit_block", "emit_block", "finish"]
    assert block_stops[0]["block"]["input"] == {"kind": "lead", "text": "hi"}
    assert block_stops[1]["block"]["input"] == {"kind": "paragraph", "text": "body"}
    assert block_stops[0]["block"]["id"] == "c0"

    msg_stop = events[-1]
    assert msg_stop["type"] == "message_stop"
    assert msg_stop["stop_reason"] == "tool_use"
    assert [b["name"] for b in msg_stop["content"]] == ["emit_block", "emit_block", "finish"]


def test_messages_stream_skips_malformed_arguments():
    chunks = [
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, id="c0", name="emit_block", arguments="{not json")]))),
        _Chunk(_Choice(_Delta(), finish_reason="tool_calls")),
    ]
    events = list(_adapter(chunks).messages_stream(
        model="deepseek-chat", messages=[], max_tokens=100))
    assert [e for e in events if e["type"] == "block_stop"] == []
    assert events[-1]["type"] == "message_stop"


def test_messages_stream_maps_stop_reason_stop_to_end_turn():
    chunks = [
        _Chunk(_Choice(_Delta(content="hello"), finish_reason="stop")),
    ]
    events = list(_adapter(chunks).messages_stream(
        model="deepseek-chat", messages=[], max_tokens=100))
    assert events[-1]["stop_reason"] == "end_turn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_openai_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: ... cuaderno.openai_client`.

- [ ] **Step 3: Implement `openai_client.py`**

Create `src/copyclip/intelligence/cuaderno/openai_client.py`:

```python
from __future__ import annotations

import json
from typing import Any, Optional


def _to_openai_request(system, tools, messages):
    """Translate the cuaderno's Anthropic-shaped (system, tools, messages) into
    OpenAI Chat Completions (messages, tools)."""
    oai_messages: list[dict[str, Any]] = []
    if system:
        oai_messages.append({"role": "system", "content": system})

    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, str):
            oai_messages.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text_parts = [b["text"] for b in content if b.get("type") == "text"]
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": ("".join(text_parts) or None)}
            if tool_uses:
                msg["tool_calls"] = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})},
                    }
                    for b in tool_uses
                ]
            oai_messages.append(msg)
        else:  # user turn carrying tool_result (and/or text) blocks
            for b in content:
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    oai_messages.append({
                        "role": "tool",
                        "tool_call_id": b["tool_use_id"],
                        "content": c if isinstance(c, str) else json.dumps(c),
                    })
                elif b.get("type") == "text":
                    oai_messages.append({"role": "user", "content": b["text"]})

    oai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in (tools or [])
    ]
    return oai_messages, oai_tools


_STOP_REASON = {"tool_calls": "tool_use", "stop": "end_turn", "length": "end_turn"}


class OpenAICompatAdapter:
    """messages_stream/messages_create over the OpenAI Chat Completions API,
    translating to/from the cuaderno's Anthropic-shaped contract. Covers OpenAI,
    DeepSeek, and any OpenAI-compatible endpoint (via base_url)."""

    def __init__(self, *, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 raw_client: Optional[Any] = None):
        if raw_client is not None:
            self._client = raw_client
        else:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, base_url=base_url)

    def _create(self, *, model, oai_messages, oai_tools, max_tokens, stream):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
        return self._client.chat.completions.create(**kwargs)

    @staticmethod
    def _finish_block(acc: dict) -> Optional[dict]:
        try:
            parsed = json.loads(acc["arguments"] or "{}")
        except json.JSONDecodeError:
            return None
        return {
            "type": "tool_use",
            "id": acc["id"] or f"call_{acc['index']}",
            "name": acc["name"],
            "input": parsed,
        }

    def messages_stream(self, *, model, messages, system=None, tools=None,
                        max_tokens=8192, **_ignored):
        oai_messages, oai_tools = _to_openai_request(system, tools, messages)
        stream = self._create(model=model, oai_messages=oai_messages,
                              oai_tools=oai_tools, max_tokens=max_tokens, stream=True)

        content: list[dict[str, Any]] = []
        text_acc = ""
        cur: Optional[dict] = None
        finish_reason = None

        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if getattr(delta, "content", None):
                text_acc += delta.content
            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = tc.index
                if cur is None:
                    cur = {"index": idx, "id": None, "name": None, "arguments": ""}
                elif idx != cur["index"]:
                    blk = self._finish_block(cur)
                    if blk:
                        content.append(blk)
                        yield {"type": "block_stop", "block": blk}
                    cur = {"index": idx, "id": None, "name": None, "arguments": ""}
                if getattr(tc, "id", None):
                    cur["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        cur["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        cur["arguments"] += fn.arguments
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

        if cur is not None:
            blk = self._finish_block(cur)
            if blk:
                content.append(blk)
                yield {"type": "block_stop", "block": blk}

        if text_acc:
            # A text block is not part of the emit_block protocol; the compositor
            # ignores it, but include it in content so the assistant turn echo is
            # faithful.
            content.append({"type": "text", "text": text_acc})

        yield {
            "type": "message_stop",
            "stop_reason": _STOP_REASON.get(finish_reason, "end_turn"),
            "content": content,
        }

    def messages_create(self, *, model, messages, system=None, tools=None,
                        max_tokens=8192, **_ignored) -> dict[str, Any]:
        oai_messages, oai_tools = _to_openai_request(system, tools, messages)
        resp = self._create(model=model, oai_messages=oai_messages,
                           oai_tools=oai_tools, max_tokens=max_tokens, stream=False)
        choice = resp.choices[0]
        msg = choice.message
        content: list[dict[str, Any]] = []
        if getattr(msg, "content", None):
            content.append({"type": "text", "text": msg.content})
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                parsed = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                continue
            content.append({"type": "tool_use", "id": tc.id,
                            "name": tc.function.name, "input": parsed})
        return {"stop_reason": _STOP_REASON.get(choice.finish_reason, "end_turn"),
                "content": content}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_openai_adapter.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/openai_client.py tests/test_cuaderno_openai_adapter.py
git commit -m "feat(cuaderno): OpenAI-compatible streaming-tool-use adapter"
```

---

### Task 3: Provider resolution + client factory

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/provider.py`
- Test: `tests/test_cuaderno_provider.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_provider.py`:

```python
import sqlite3

import pytest

from copyclip.intelligence.cuaderno.provider import (
    resolve_cuaderno_provider, build_cuaderno_client, provider_key_status,
    CuadernoProviderError, DEFAULT_MODELS, TOOL_INCAPABLE_MODELS,
)
from copyclip.intelligence.cuaderno.anthropic_client import AnthropicAdapter
from copyclip.intelligence.cuaderno.openai_client import OpenAICompatAdapter


def _conn_with_config(pairs):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    for k, v in pairs.items():
        conn.execute("INSERT INTO config(key,value) VALUES(?,?)", (k, v))
    conn.commit()
    return conn


def test_sqlite_overlay_selects_provider_and_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    conn = _conn_with_config({"cuaderno_provider": "deepseek", "cuaderno_model": "deepseek-chat"})
    r = resolve_cuaderno_provider(conn)
    assert r["provider"] == "deepseek"
    assert r["model"] == "deepseek-chat"
    assert r["api_key"] == "sk-ds"
    assert "deepseek.com" in r["base_url"]


def test_falls_back_to_default_model_when_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-an")
    conn = _conn_with_config({"cuaderno_provider": "anthropic"})
    r = resolve_cuaderno_provider(conn)
    assert r["model"] == DEFAULT_MODELS["anthropic"]


def test_missing_key_raises_typed_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    conn = _conn_with_config({"cuaderno_provider": "deepseek"})
    with pytest.raises(CuadernoProviderError) as exc:
        resolve_cuaderno_provider(conn)
    assert exc.value.provider == "deepseek"


def test_tool_incapable_model_rejected(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    conn = _conn_with_config({"cuaderno_provider": "deepseek", "cuaderno_model": "deepseek-reasoner"})
    with pytest.raises(CuadernoProviderError) as exc:
        resolve_cuaderno_provider(conn)
    assert "tool" in str(exc.value).lower()
    assert "deepseek-reasoner" in TOOL_INCAPABLE_MODELS


def test_build_client_picks_adapter(monkeypatch):
    anth = build_cuaderno_client({"provider": "anthropic", "api_key": "k", "base_url": "u", "model": "m"})
    assert isinstance(anth, AnthropicAdapter)
    oai = build_cuaderno_client({"provider": "deepseek", "api_key": "k", "base_url": "u", "model": "m"})
    assert isinstance(oai, OpenAICompatAdapter)


def test_provider_key_status_is_non_raising(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    status = provider_key_status()
    assert status["deepseek"] is True
    assert status["anthropic"] is False
    assert status["openai"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: ... cuaderno.provider`.

- [ ] **Step 3: Implement `provider.py`**

Create `src/copyclip/intelligence/cuaderno/provider.py`:

```python
from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional, TypedDict

from ...llm.config import load_config
from ...llm.provider_config import PROVIDERS, resolve_provider, ProviderConfigError
from .anthropic_client import AnthropicAdapter
from .openai_client import OpenAICompatAdapter

# Default cuaderno model per provider when the user has not chosen one.
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o",
}

# Models that cannot drive tool-calling and therefore cannot run the cuaderno's
# agentic emit_block protocol.
TOOL_INCAPABLE_MODELS: frozenset[str] = frozenset({"deepseek-reasoner"})

# Providers whose wire format is the Anthropic Messages API.
_ANTHROPIC_PROVIDERS: frozenset[str] = frozenset({"anthropic"})


class ResolvedCuaderno(TypedDict):
    provider: str
    api_key: str
    base_url: str
    model: str


class CuadernoProviderError(RuntimeError):
    def __init__(self, message: str, provider: str):
        super().__init__(message)
        self.provider = provider


def _read_config_key(conn: Optional[sqlite3.Connection], key: str) -> Optional[str]:
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row and row[0] else None


def resolve_cuaderno_provider(conn: Optional[sqlite3.Connection]) -> ResolvedCuaderno:
    """Resolve the cuaderno's provider/model/key/base_url.

    Layering: the SQLite `config` overlay (cuaderno_provider/cuaderno_model,
    written by the UI selector) selects which provider + model; the API key and
    base URL come from resolve_provider (llm.yaml/ENV). Raises
    CuadernoProviderError (naming the provider) when the key is missing or the
    chosen model cannot do tool-calling.
    """
    overlay_provider = _read_config_key(conn, "cuaderno_provider")
    overlay_model = _read_config_key(conn, "cuaderno_model")

    cfg = load_config(None)
    try:
        resolved = resolve_provider(overlay_provider, cfg)
    except ProviderConfigError as exc:
        provider = (overlay_provider or cfg.get("default_provider") or "deepseek").lower()
        raise CuadernoProviderError(
            f"LLM not configured for provider '{provider}': {exc}. "
            f"Run `copyclip start` or open Settings to add the key.",
            provider,
        ) from exc

    provider = resolved["name"]
    model = overlay_model or resolved.get("model") or DEFAULT_MODELS.get(provider, "")

    if model in TOOL_INCAPABLE_MODELS:
        raise CuadernoProviderError(
            f"Model '{model}' does not support tool-calling, which the cuaderno "
            f"requires. Pick a tool-capable model (e.g. deepseek-chat).",
            provider,
        )

    return ResolvedCuaderno(
        provider=provider,
        api_key=resolved["api_key"],
        base_url=resolved["base_url"],
        model=model,
    )


def build_cuaderno_client(resolved: ResolvedCuaderno):
    """Build the adapter matching the resolved provider's wire format."""
    if resolved["provider"] in _ANTHROPIC_PROVIDERS:
        return AnthropicAdapter(api_key=resolved["api_key"])
    return OpenAICompatAdapter(api_key=resolved["api_key"], base_url=resolved["base_url"])


def provider_key_status() -> dict[str, bool]:
    """Non-raising per-provider key check for the selector (does NOT call the
    fail-fast resolve_provider)."""
    return {
        name: bool((os.environ.get(meta.api_key_env) or "").strip())
        for name, meta in PROVIDERS.items()
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_provider.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/provider.py tests/test_cuaderno_provider.py
git commit -m "feat(cuaderno): provider resolution (SQLite overlay + resolve_provider) + client factory"
```

---

## PR2 — Backend wiring

### Task 4: Route `/api/cuaderno/ask` through provider resolution

**Files:** Modify `src/copyclip/intelligence/server.py` (lines 2522-2538, the ask-handler body)

- [ ] **Step 1: Replace the adapter construction**

In `src/copyclip/intelligence/server.py`, find this block inside the `/api/cuaderno/ask` handler:

```python
                    from .cuaderno.anthropic_client import AnthropicAdapter
                    from .cuaderno.ask_stream import iter_ask_events
                    from .cuaderno.persistence import create_session
                    if not session_id:
                        session_id = create_session(conn, project_root=ctx.root)
                    try:
                        client = AnthropicAdapter()
                    except RuntimeError as exc:
                        self._json({"error": "llm_not_configured", "detail": str(exc)}, 503)
                        return
                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id,
                    )
                    sse_response(self, events)
                    return
```

Replace it with:

```python
                    from .cuaderno.ask_stream import iter_ask_events
                    from .cuaderno.persistence import create_session
                    from .cuaderno.provider import (
                        resolve_cuaderno_provider, build_cuaderno_client,
                        CuadernoProviderError,
                    )
                    if not session_id:
                        session_id = create_session(conn, project_root=ctx.root)
                    try:
                        resolved = resolve_cuaderno_provider(conn)
                    except CuadernoProviderError as exc:
                        self._json({"error": "llm_not_configured",
                                    "provider": exc.provider, "detail": str(exc)}, 503)
                        return
                    client = build_cuaderno_client(resolved)
                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id, model=resolved["model"],
                    )
                    sse_response(self, events)
                    return
```

This threads the resolved `model` into `iter_ask_events` (which already accepts a `model` kwarg and passes it down to `iter_compose_events` → the adapter).

- [ ] **Step 2: Verify the module parses**

Run: `python -c "import ast; ast.parse(open(r'src/copyclip/intelligence/server.py',encoding='utf-8').read()); print('parse ok')"`
Expected: `parse ok`.

- [ ] **Step 3: Update the full-stack e2e to exercise a configured provider**

The e2e test (`tests/test_cuaderno_e2e.py`) patches `AnthropicAdapter.messages_stream`. It now needs a configured provider so `resolve_cuaderno_provider` succeeds. Add, at the very top of `test_e2e_example_A_streams_frame_over_sse` (right after the docstring), an env + config setup so the resolver returns anthropic and the patched adapter is used:

```python
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
```

Then, after `init_cuaderno_schema(conn)` and before `conn.close()`, set the cuaderno provider in the config table so resolution is deterministic:

```python
    conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('cuaderno_provider','anthropic')")
```

(The `config` table is created by `init_schema`. With `cuaderno_provider=anthropic` and `ANTHROPIC_API_KEY` set, `resolve_cuaderno_provider` returns anthropic and `build_cuaderno_client` builds an `AnthropicAdapter` — which the test patches, so no real API call happens.)

Run: `python -m pytest tests/test_cuaderno_e2e.py -v`
Expected: PASS, 1 test. If it fails because `config` has no such table, confirm `init_schema(conn)` ran before the INSERT.

- [ ] **Step 4: Update the endpoint tests similarly**

`tests/test_cuaderno_endpoint.py` already sets `ANTHROPIC_API_KEY` (module level) and patches the adapter; add `cuaderno_provider=anthropic` to the config table in each test's DB setup (right after `init_cuaderno_schema`), mirroring Step 3, so resolution is deterministic. Then run:

Run: `python -m pytest tests/test_cuaderno_endpoint.py -v`
Expected: PASS. If a test does not create the project DB with `init_schema`, the `config` table may be absent — in that case set the env var `COPYCLIP_LLM_PROVIDER=anthropic` for that test instead (resolve_provider reads it), which avoids the SQLite overlay entirely.

- [ ] **Step 5: Run the full cuaderno suite**

Run: `python -m pytest tests/ -k cuaderno -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/server.py tests/test_cuaderno_e2e.py tests/test_cuaderno_endpoint.py
git commit -m "feat(cuaderno): /ask resolves provider via resolve_cuaderno_provider"
```

---

### Task 5: `GET /api/cuaderno/providers` endpoint

**Files:**
- Modify: `src/copyclip/intelligence/server.py` (add a route in `do_GET`, near the other `/api/cuaderno/*` GET routes around line 1633-1672)
- Test: `tests/test_cuaderno_providers_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_providers_endpoint.py`:

```python
import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request

from copyclip.intelligence.db import connect, init_schema, init_cuaderno_schema
from copyclip.intelligence.server import run_server


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _wait_port(port, timeout_s=3.0):
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


def test_providers_endpoint_lists_providers_and_current(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    td = tempfile.mkdtemp(prefix="cuaderno-prov-")
    root = str(Path(td).absolute())
    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('cuaderno_provider','deepseek')")
    conn.commit(); conn.close()

    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start(); _wait_port(port)

    with request.urlopen(f"http://127.0.0.1:{port}/api/cuaderno/providers", timeout=10) as r:
        body = json.loads(r.read().decode("utf-8"))

    assert body["current"]["provider"] == "deepseek"
    names = {p["name"] for p in body["providers"]}
    assert {"anthropic", "openai", "deepseek"} <= names
    ds = next(p for p in body["providers"] if p["name"] == "deepseek")
    assert ds["key_configured"] is True
    assert ds["default_model"] == "deepseek-chat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_providers_endpoint.py -v`
Expected: FAIL — the endpoint returns 404 (`not_found`), so `urlopen` raises `HTTPError`.

- [ ] **Step 3: Add the route**

In `src/copyclip/intelligence/server.py`, in `do_GET`, immediately before the `if parsed.path == "/api/cuaderno/file":` block (around line 1637), add:

```python
                if parsed.path == "/api/cuaderno/providers":
                    from .cuaderno.provider import (
                        provider_key_status, DEFAULT_MODELS, TOOL_INCAPABLE_MODELS,
                    )
                    status = provider_key_status()
                    cur_provider = None
                    cur_model = None
                    row = conn.execute(
                        "SELECT value FROM config WHERE key='cuaderno_provider'").fetchone()
                    if row:
                        cur_provider = row[0]
                    row = conn.execute(
                        "SELECT value FROM config WHERE key='cuaderno_model'").fetchone()
                    if row:
                        cur_model = row[0]
                    providers = [
                        {
                            "name": name,
                            "key_configured": configured,
                            "default_model": DEFAULT_MODELS.get(name),
                        }
                        for name, configured in status.items()
                    ]
                    self._json({
                        "providers": providers,
                        "tool_incapable_models": sorted(TOOL_INCAPABLE_MODELS),
                        "current": {"provider": cur_provider, "model": cur_model},
                    })
                    return
```

(`conn` and `self._json` are already in scope in `do_GET`, as used by the adjacent cuaderno routes.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_providers_endpoint.py -v`
Expected: PASS, 1 test.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/server.py tests/test_cuaderno_providers_endpoint.py
git commit -m "feat(cuaderno): GET /api/cuaderno/providers (list + key status + current)"
```

---

## PR3 — Frontend provider selector

Frontend tasks verify via `npx tsc -b` from `frontend/`; behavior is verified in the manual e2e (Task 10).

### Task 6: Provider types

**Files:** Modify `frontend/src/types/api.ts` (append after `CuadernoStreamEvent`)

- [ ] **Step 1: Add the types**

Append to `frontend/src/types/api.ts`:

```typescript
export type ProviderInfo = {
  name: string
  key_configured: boolean
  default_model: string | null
}

export type CuadernoProvidersResponse = {
  providers: ProviderInfo[]
  tool_incapable_models: string[]
  current: { provider: string | null; model: string | null }
}
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno): provider info types"
```

---

### Task 7: API client for providers

**Files:** Modify `frontend/src/api/cuaderno.ts`

- [ ] **Step 1: Add the import and functions**

Replace line 1 of `frontend/src/api/cuaderno.ts`:

```typescript
import type { CuadernoSession, CuadernoStreamEvent, CuadernoProvidersResponse } from '../types/api'
```

Add a `postJson` helper (it was removed in the streaming PR; re-add it for `/api/config`) right after the `getJson` helper (after line 23 in the current file):

```typescript
async function postJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`POST ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}
```

Add two methods to the `cuadernoApi` object (alongside `session` and `patchQuestion`):

```typescript
  providers() {
    return getJson<CuadernoProvidersResponse>('/api/cuaderno/providers')
  },
  setProvider(provider: string, model: string) {
    return postJson<{ status: string }>('/api/config', {
      cuaderno_provider: provider,
      cuaderno_model: model,
    })
  },
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/cuaderno.ts
git commit -m "feat(cuaderno): providers() + setProvider() API client"
```

---

### Task 8: ProviderSelector component + wiring

**Files:**
- Create: `frontend/src/components/cuaderno/ProviderSelector.tsx`
- Modify: `frontend/src/components/cuaderno/Cuaderno.tsx`
- Modify: `frontend/src/pages/CuadernoPage.tsx`

- [ ] **Step 1: Create the selector component**

Create `frontend/src/components/cuaderno/ProviderSelector.tsx`:

```typescript
import { useState } from 'react'
import type { CuadernoProvidersResponse } from '../../types/api'

type Props = {
  data: CuadernoProvidersResponse | null
  onChange: (provider: string, model: string) => void
}

export function ProviderSelector({ data, onChange }: Props) {
  const [open, setOpen] = useState(false)
  if (!data) return null

  const current = data.current.provider ?? data.providers[0]?.name ?? '—'
  const currentModel = data.current.model ?? ''

  return (
    <div className="cua-provider" style={{ position: 'relative' }}>
      <button
        className="provider-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label="LLM provider"
        style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-2)' }}
      >
        {current}
        {currentModel ? ` · ${currentModel}` : ''}
      </button>
      {open && (
        <div
          className="provider-menu"
          style={{
            position: 'absolute', right: 0, top: '100%', zIndex: 20,
            background: 'var(--surface)', border: '1px solid var(--line)',
            padding: 8, fontFamily: 'var(--font-mono)', fontSize: 11, minWidth: 200,
          }}
        >
          {data.providers.map((p) => {
            const model = p.default_model ?? ''
            const disabled = !p.key_configured
            return (
              <button
                key={p.name}
                disabled={disabled}
                onClick={() => {
                  onChange(p.name, model)
                  setOpen(false)
                }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left', padding: '4px 6px',
                  opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer',
                }}
                title={disabled ? 'API key not configured — open Settings' : ''}
              >
                {p.name}
                {model ? ` · ${model}` : ''}
                {disabled ? ' · no key' : ''}
              </button>
            )
          })}
          <div style={{ marginTop: 6, color: 'var(--ink-3)' }}>
            Keys: configure in Settings
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Wire it into the Cuaderno top-crumb**

In `frontend/src/components/cuaderno/Cuaderno.tsx`:

Update the type import on line 2 to add `CuadernoProvidersResponse`:

```typescript
import type { Block, Citation, CuadernoQuestion, ToolRow, CuadernoProvidersResponse } from '../../types/api'
```

Add the component import after the other component imports (after line 9):

```typescript
import { ProviderSelector } from './ProviderSelector'
```

Add to the `Props` type (after `toolCalls?: ToolRow[]`, line 19):

```typescript
  providers?: CuadernoProvidersResponse | null
  onSetProvider?: (provider: string, model: string) => void
```

Add to the destructure (after `toolCalls = [],`, line 33):

```typescript
  providers = null,
  onSetProvider,
```

In the `.right` div of the top-crumb (currently lines 60-69), add the selector before the `session` span:

```typescript
        <div className="right">
          {onSetProvider && (
            <ProviderSelector data={providers} onChange={onSetProvider} />
          )}
          <span className="session">{questionNumber}</span>
          <button
            className="hamb"
            onClick={() => setHistoryOpen((h) => !h)}
            aria-label="session history"
          >
            ≡
          </button>
        </div>
```

- [ ] **Step 3: Load providers + own selection in CuadernoPage**

In `frontend/src/pages/CuadernoPage.tsx`:

Add to the type import (line 2):

```typescript
import type { Block, CuadernoQuestion, ToolRow, CuadernoProvidersResponse } from '../types/api'
```

Add state after `const [error, setError] = useState<string | null>(null)` (line 15):

```typescript
  const [providers, setProviders] = useState<CuadernoProvidersResponse | null>(null)
```

Add a load effect after the restore effect (after line 45):

```typescript
  // Load the provider list / current selection once on mount.
  useEffect(() => {
    cuadernoApi.providers().then(setProviders).catch(() => {})
  }, [])

  const onSetProvider = (provider: string, model: string) => {
    cuadernoApi.setProvider(provider, model).catch(() => {})
    setProviders((prev) =>
      prev ? { ...prev, current: { provider, model } } : prev,
    )
  }
```

Pass the new props to `<Cuaderno>` (in the JSX, alongside the existing props):

```typescript
        providers={providers}
        onSetProvider={onSetProvider}
```

- [ ] **Step 4: Type-check**

Run (from `frontend/`): `npx tsc -b`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cuaderno/ProviderSelector.tsx frontend/src/components/cuaderno/Cuaderno.tsx frontend/src/pages/CuadernoPage.tsx
git commit -m "feat(cuaderno): in-cuaderno provider/model selector"
```

---

### Task 9: Regenerate the served UI bundle

**Files:** Modify `src/copyclip/intelligence/ui/index.html` (build artifact)

- [ ] **Step 1: Build + copy**

Run (from the repo root):

```bash
cd frontend && npm run build && cp dist/index.html ../src/copyclip/intelligence/ui/index.html && cd ..
```

Expected: `✓ built` and the bundle copied. (PowerShell: `Copy-Item frontend\dist\index.html src\copyclip\intelligence\ui\index.html -Force`.)

- [ ] **Step 2: Commit**

```bash
git add src/copyclip/intelligence/ui/index.html
git commit -m "build(cuaderno): regenerate UI bundle with provider selector"
```

---

## PR4 — Validation gate (user)

### Task 10: Manual end-to-end with a real DeepSeek key

**Files:** none (requires a real `DEEPSEEK_API_KEY`; the human runs this). This is the gate for Decision 1's behavioral risk — that DeepSeek reliably drives the `emit_block` protocol — which no stubbed test can cover. It also validates the streaming work (PR #117) end to end for the first time against a real LLM.

- [ ] **Step 1: Build the bundle and configure DeepSeek**

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
copyclip start    # or: python -m copyclip start
```

If DeepSeek is not already the configured provider, set it via the dashboard `/settings` page or the onboarding, or `$env:COPYCLIP_LLM_PROVIDER = "deepseek"`.

- [ ] **Step 2: Open the cuaderno and select DeepSeek**

Open the printed URL → cuaderno page. The provider selector (top-right) should show the current provider; pick `deepseek · deepseek-chat`.

- [ ] **Step 3: Ask and observe**

Ask "what does this project do?" and verify:
- Tool rows animate (read tools running → done).
- Answer blocks appear one by one (the emit_block protocol driven by DeepSeek).
- Blocks carry valid citations (`▸ path:line`) that open the side panel.
- The frame settles; markers appear.

- [ ] **Step 4: Verify provider switching + key affordance**

- Switch the selector to `anthropic` — if no Anthropic key, the option shows "no key" and is disabled (points to Settings).
- Confirm `deepseek-reasoner` (if offered/typed) is rejected with a clear `model_lacks_tool_support` message rather than a broken stream.

- [ ] **Step 5: Record the verdict**

Note whether DeepSeek drives the agentic protocol reliably (per Decision 1). If it does not (e.g. malformed/empty blocks, fails to call `finish`, or single-shots the answer), that is the documented risk materializing — capture the behavior for a follow-up (prompt tuning, or a per-provider fallback to the whole-Frame protocol).

---

## Self-review notes

- **Spec coverage:** OpenAI-compat adapter w/ bidirectional translation + incremental block emission (Task 2); provider resolution with SQLite overlay + key from resolve_provider + ProviderConfigError handling + tool-incapable-model rejection (Task 3); handler routing + provider-named 503 + model threading (Task 4); providers endpoint with non-raising key status (Task 5); UI selector reusing /api/config, no key management, disabled-when-no-key (Tasks 6-8); deepseek-chat default + reasoner rejected (Task 3); validation gate (Task 10); bundle regen (Task 9). All spec sections map to a task.
- **Compositor untouched:** confirmed — no task modifies `compositor.py`/`ask_stream.py`/`sse_response`/the frontend stream consumption; the new adapter satisfies the existing `messages_stream`/`messages_create` contract.
- **Incremental emission:** the OpenAI adapter emits a `block_stop` when each tool call completes (next index begins) — not all at the end — preserving block-by-block UX (Task 2, test `test_messages_stream_emits_a_block_per_completed_tool_call`).
- **Frontend testing:** `tsc -b` + the manual e2e (Task 10), matching the project's no-unit-test-harness frontend.
- **Stacking:** built on `feat/cuaderno-sse-streaming`; merge order streaming → multi-provider, validated together with DeepSeek.
```
