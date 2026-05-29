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
            fn = getattr(tc, "function", None)
            if fn is None:  # skip non-function (custom) tool calls — see streaming path
                continue
            try:
                parsed = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                continue
            content.append({"type": "tool_use", "id": tc.id,
                            "name": fn.name, "input": parsed})
        return {"stop_reason": _STOP_REASON.get(choice.finish_reason, "end_turn"),
                "content": content}
