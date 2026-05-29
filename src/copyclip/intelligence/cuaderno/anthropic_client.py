from __future__ import annotations

import os
from typing import Any, Optional


def _normalize_block(blk) -> dict:
    if blk.type == "text":
        return {"type": "text", "text": blk.text}
    if blk.type == "tool_use":
        return {"type": "tool_use", "id": blk.id, "name": blk.name, "input": blk.input or {}}
    return {"type": blk.type}


class AnthropicAdapter:
    """Normalizes the anthropic SDK response into the dict shape compose_frame expects."""

    def __init__(self, raw_client: Optional[Any] = None, api_key: Optional[str] = None):
        if raw_client is not None:
            self._client = raw_client
        else:
            import anthropic
            key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not configured. Run `copyclip start` to onboard, "
                    "or export the env var."
                )
            self._client = anthropic.Anthropic(api_key=key)

    def messages_create(self, **kwargs) -> dict[str, Any]:
        resp = self._client.messages.create(**kwargs)
        content = []
        for block in resp.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input or {},
                })
        return {"stop_reason": resp.stop_reason, "content": content}

    def messages_stream(self, **kwargs):
        """Yield normalized streaming events from the Anthropic streaming API:

          {"type": "block_stop", "block": <normalized block>}      # per content block
          {"type": "message_stop", "stop_reason": str, "content": [<normalized blocks>]}

        Reacting at content_block_stop is what lets the compositor emit a block
        event the moment each emit_block tool call completes.
        """
        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_stop":
                    yield {"type": "block_stop",
                           "block": _normalize_block(event.content_block)}
            final = stream.get_final_message()
            yield {
                "type": "message_stop",
                "stop_reason": final.stop_reason,
                "content": [_normalize_block(b) for b in final.content],
            }
