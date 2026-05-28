from __future__ import annotations

import os
from typing import Any, Optional


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
