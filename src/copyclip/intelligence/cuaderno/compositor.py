from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterator, Optional

from .prompts import SYSTEM_PROMPT
from .read_ledger import ReadLedger
from .quality import assess
from .schema import (
    Block, Frame, frame_from_dict, frame_to_dict, validate_block_dict,
    FRAME_STATUS_FALLBACK,
)
from .tool_catalog import ANSWER_TOOLS, build_tool_definitions, dispatch_tool

CLOSING_DIRECTIVE = (
    "You have gathered your evidence — the research tools are no longer "
    "available. Compose your answer NOW: call emit_block for each block (at "
    "least a lead and a paragraph), anchoring every claim to what you have "
    "already read, then call finish. If the evidence is thin, say so honestly "
    "in the answer rather than asking for more."
)


def _inject_directive(messages: list[dict[str, Any]], text: str) -> None:
    """Append a user-side directive, merging into the trailing user turn when
    possible so we never emit two consecutive user messages."""
    block = {"type": "text", "text": text}
    if messages and messages[-1].get("role") == "user":
        content = messages[-1]["content"]
        if isinstance(content, str):
            messages[-1]["content"] = [{"type": "text", "text": content}, block]
        elif isinstance(content, list):
            content.append(block)
        else:
            messages.append({"role": "user", "content": [block]})
    else:
        messages.append({"role": "user", "content": [block]})


def _fallback_frame(question: str, reason: str) -> Frame:
    return Frame(
        question=question,
        blocks=[
            Block.paragraph(
                f"I couldn't finish this turn — {reason}. Try rephrasing, or "
                "ask a narrower question (a specific file, function, or commit)."
            ),
        ],
        status=FRAME_STATUS_FALLBACK,
    )


def _sealed_frame(question: str, emitted: list[Block], ledger: ReadLedger) -> dict[str, Any]:
    verdict = assess(question=question, blocks=emitted, ledger=ledger)
    return frame_to_dict(Frame(question=question, blocks=emitted, status=verdict.status))


def _ack(tool_use_id: str, payload: dict, *, is_error: bool = False) -> dict[str, Any]:
    r: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(payload),
    }
    if is_error:
        r["is_error"] = True
    return r


def _args_summary(name: str, args: dict[str, Any]) -> str:
    """A short label for the tool-call row (e.g. 'src/foo.py:10-20')."""
    if args.get("path"):
        s = str(args["path"])
        if args.get("line_start"):
            s += f":{args['line_start']}"
            if args.get("line_end"):
                s += f"-{args['line_end']}"
        return s
    for key in ("symbol", "name", "commit_sha", "module"):
        if args.get(key):
            return str(args[key])
    return ""


def iter_compose_events(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    model: str = "claude-sonnet-4-5",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
) -> Iterator[dict[str, Any]]:
    """Run the agentic loop as a generator of events.

    Yields, in order:
      {"type": "tool",  "id", "name", "args", "state": running|done|error, "ms"}
      {"type": "block", "block": <block dict>}
      {"type": "frame", "frame": <frame dict>}              # terminal success/fallback
      {"type": "error", "message": str, "partial": bool}    # terminal failure

    The model delivers its answer by calling emit_block once per block then
    finish. Read tools (read_file, grep_symbols, ...) run during the evidence
    phase and surface as tool events.
    """
    tools = build_tool_definitions()
    answer_only = [t for t in tools if t["name"] in ANSWER_TOOLS]
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    emitted: list[Block] = []
    ledger = ReadLedger()

    for round_i in range(max_tool_rounds):
        # Final round: take the research tools away and force an answer, so a
        # model that keeps exploring still produces a real Frame instead of the
        # budget-exhausted fallback.
        is_closing = round_i == max_tool_rounds - 1
        if is_closing:
            _inject_directive(messages, CLOSING_DIRECTIVE)
        round_tools = answer_only if is_closing else tools

        turn_content: list[dict[str, Any]] = []
        stop_reason: Optional[str] = None
        finish_seen = False
        emit_status: dict[str, Optional[str]] = {}  # tool_use_id -> reason (None = ok)

        try:
            for sev in client.messages_stream(
                model=model,
                system=SYSTEM_PROMPT,
                tools=round_tools,
                messages=messages,
                max_tokens=max_tokens,
            ):
                if sev.get("type") == "block_stop":
                    blk = sev.get("block") or {}
                    if blk.get("type") == "tool_use" and blk.get("name") == "emit_block":
                        inp = blk.get("input") or {}
                        reason = validate_block_dict(inp)
                        emit_status[blk["id"]] = reason
                        if reason is None:
                            b = Block.from_dict(inp)
                            emitted.append(b)
                            yield {"type": "block", "block": b.to_dict()}
                    elif blk.get("type") == "tool_use" and blk.get("name") == "finish":
                        finish_seen = True
                elif sev.get("type") == "message_stop":
                    stop_reason = sev.get("stop_reason")
                    turn_content = sev.get("content", []) or []
        except Exception as exc:  # noqa: BLE001 — surface LLM/stream failure as a terminal error
            yield {
                "type": "error",
                "message": f"stream failed ({exc})",
                "partial": len(emitted) > 0,
            }
            return

        messages.append({"role": "assistant", "content": turn_content})

        # Terminal: explicit finish, or a non-tool stop reason (implicit finish).
        if finish_seen or stop_reason != "tool_use":
            if emitted:
                yield {"type": "frame", "frame": _sealed_frame(question, emitted, ledger)}
            else:
                yield {"type": "frame",
                       "frame": frame_to_dict(
                           _fallback_frame(question, "the model produced no answer blocks"))}
            return

        # Continue: ack every tool_use block. Dispatch read tools (with events);
        # ack emit_block (already emitted/rejected during the stream) and finish.
        tool_results: list[dict[str, Any]] = []
        for blk in turn_content:
            if blk.get("type") != "tool_use":
                continue
            name = blk.get("name")
            tuid = blk["id"]
            if name == "emit_block":
                reason = emit_status.get(tuid)
                if reason is None:
                    tool_results.append(_ack(tuid, {"ok": True}))
                else:
                    tool_results.append(
                        _ack(tuid, {"error": "invalid_block", "detail": reason}, is_error=True))
                continue
            if name == "finish":
                tool_results.append(_ack(tuid, {"ok": True}))
                continue

            args = blk.get("input") or {}
            args_str = _args_summary(name, args)
            yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                   "state": "running", "ms": None}
            t0 = time.perf_counter()
            try:
                result = dispatch_tool(
                    name, args, project_root=project_root,
                    project_id=project_id, conn=conn,
                )
                ledger.record(name, result)
                ms = int((time.perf_counter() - t0) * 1000)
                tool_results.append(_ack(tuid, result))
                yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                       "state": "done", "ms": ms}
            except Exception as exc:  # noqa: BLE001 — surface tool failures to the LLM and the UI
                ms = int((time.perf_counter() - t0) * 1000)
                tool_results.append(
                    _ack(tuid, {"error": "tool_failed", "detail": str(exc)}, is_error=True))
                yield {"type": "tool", "id": tuid, "name": name, "args": args_str,
                       "state": "error", "ms": ms}

        messages.append({"role": "user", "content": tool_results})

    # Budget exhausted → fallback frame (terminal; parity with the wrapper below).
    if emitted:
        yield {"type": "frame", "frame": _sealed_frame(question, emitted, ledger)}
    else:
        yield {"type": "frame",
               "frame": frame_to_dict(_fallback_frame(question, "tool-call budget exhausted"))}


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
    """Drain iter_compose_events and return the terminal Frame.

    Non-streaming convenience used by tests and for live-vs-restore parity. On a
    terminal error event it returns a fallback Frame, so this is total.
    """
    last_frame: Optional[Frame] = None
    for ev in iter_compose_events(
        client=client, question=question, project_root=project_root,
        project_id=project_id, conn=conn, model=model,
        max_tool_rounds=max_tool_rounds, max_tokens=max_tokens,
    ):
        if ev["type"] == "frame":
            last_frame = frame_from_dict(ev["frame"])
        elif ev["type"] == "error":
            return _fallback_frame(question, ev["message"])
    if last_frame is not None:
        return last_frame
    return _fallback_frame(question, "no terminal frame produced")
