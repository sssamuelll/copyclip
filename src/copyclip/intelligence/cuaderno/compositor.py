from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .prompts import SYSTEM_PROMPT
from .schema import Block, Frame, frame_from_dict
from .tool_catalog import build_tool_definitions, dispatch_tool


def _fallback_frame(question: str, reason: str) -> Frame:
    return Frame(
        question=question,
        blocks=[
            Block.paragraph(
                f"I couldn't finish this turn — {reason}. Try rephrasing, or "
                "ask a narrower question (a specific file, function, or commit)."
            ),
        ],
    )


def compose_frame(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    model: str = "claude-sonnet-4-5",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
) -> Frame:
    """Run the agentic loop. Returns a Frame; falls back gracefully on cap or parse failure."""
    tools = build_tool_definitions()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": question},
    ]

    for _ in range(max_tool_rounds):
        resp = client.messages_create(
            model=model,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
            max_tokens=max_tokens,
        )

        stop_reason = resp.get("stop_reason")
        content = resp.get("content", [])

        # Echo assistant turn into conversation
        messages.append({"role": "assistant", "content": content})

        if stop_reason != "tool_use":
            # Extract the final text block and parse as Frame JSON
            text_chunks = [b["text"] for b in content if b.get("type") == "text"]
            raw = "".join(text_chunks).strip()
            # Strip ```json fences if the model added them
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            try:
                data = json.loads(raw)
                return frame_from_dict(data)
            except (json.JSONDecodeError, KeyError) as exc:
                return _fallback_frame(
                    question, f"model output was not valid Frame JSON ({exc})"
                )

        # Tool-use turn: execute every tool_use block, append a single user
        # message with all tool_result blocks before looping.
        tool_results: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            try:
                result = dispatch_tool(
                    block["name"], block.get("input", {}) or {},
                    project_root=project_root, project_id=project_id, conn=conn,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": json.dumps(result),
                })
            except Exception as exc:  # noqa: BLE001 — surface tool failures to the LLM as tool_result errors so it can recover within the same turn
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": json.dumps({"error": "tool_failed", "detail": str(exc)}),
                    "is_error": True,
                })
        messages.append({"role": "user", "content": tool_results})

    return _fallback_frame(question, "tool-call budget exhausted")
