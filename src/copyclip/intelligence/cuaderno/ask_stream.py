from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterator, Optional

from .compositor import iter_compose_events
from .i18n import tr
from .language import detect_language
from .persistence import save_question
from .schema import Block, Frame, FRAME_STATUS_PARTIAL, frame_from_dict
from .trace import InteractionTrace, trace_logs_dir


def _persist_partial(conn, session_id: str, question: str, emitted: list[dict],
                     message: Optional[str] = None) -> None:
    lang = detect_language(question)
    blocks = [Block.from_dict(b) for b in emitted]
    if not blocks:
        reason = message or tr("partial_default_reason", lang)
        blocks = [Block.paragraph(tr("partial", lang, reason=reason))]
    pframe = Frame(question=question, blocks=blocks, status=FRAME_STATUS_PARTIAL,
                   question_language=lang)
    save_question(conn, session_id, question, pframe)


def iter_ask_events(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    session_id: str,
    model: str = "claude-sonnet-4-5",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
    judge: Any = None,
    provider: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> Iterator[dict[str, Any]]:
    """Wrap iter_compose_events for the HTTP layer.

    - Prepends a `meta` event carrying session_id.
    - On the terminal `frame`, persists the Frame and attaches its `position`.
    - On a terminal `error` with partial=True (or on client disconnect, which
      arrives as GeneratorExit in the finally), persists the partial Frame from
      the blocks already emitted.
    - Owns the InteractionTrace lifecycle: one JSONL debug timeline per ask in
      `<project_root>/.copyclip/logs/cuaderno/` (spec 2026-06-10). The trace can
      never break this path — it swallows its own failures.
    """
    lang = detect_language(question)
    trace = InteractionTrace.start(
        "ask", trace_logs_dir(project_root),
        {
            "question": question,
            "session_id": session_id,
            "question_language": lang,
            "model": model,
            "judge_model": judge_model,
            "provider": provider,
            "max_tool_rounds": max_tool_rounds,
            "copyclip_version": os.environ.get("COPYCLIP_VERSION", "dev"),
        },
        tag=(session_id or "")[:8] or None,
    )
    outcome = "incomplete"
    crash_error: Optional[str] = None
    emitted: list[dict] = []
    persisted = False
    try:
        yield {"type": "meta", "session_id": session_id, "question_language": lang}
        for ev in iter_compose_events(
            client=client, question=question, project_root=project_root,
            project_id=project_id, conn=conn, model=model,
            max_tool_rounds=max_tool_rounds, max_tokens=max_tokens,
            judge=judge, trace=trace,
        ):
            if ev["type"] == "block":
                emitted.append(ev["block"])
                yield ev
            elif ev["type"] == "reset":
                # The compositor discarded the provisional answer (a grounding /
                # language retry). Drop our own buffered copy so a disconnect
                # during the retry can never persist the discarded blocks, and
                # forward it so the client drops its provisional render too.
                emitted.clear()
                yield ev
            elif ev["type"] == "tool":
                yield ev
            elif ev["type"] == "frame":
                frame = frame_from_dict(ev["frame"])
                position = save_question(conn, session_id, question, frame)
                persisted = True
                trace.event("seal", status=ev["frame"].get("status"),
                            verdict=ev["frame"].get("verdict"),
                            blocks=len(ev["frame"].get("blocks") or []),
                            position=position, sse=True)
                trace.event("persist", outcome="ok", error=None)
                outcome = ev["frame"].get("status") or "answer"
                yield {"type": "frame", "position": position, "frame": ev["frame"]}
            elif ev["type"] == "error":
                # Always persist the turn so it is never silently lost — a stream
                # error is a `partial` per the status taxonomy. Surviving blocks
                # ride as the partial body; with none (e.g. an error after a
                # retry's reset cleared the buffer) a marker block keeps the
                # question in the conversation.
                _persist_partial(conn, session_id, question, emitted, message=ev.get("message"))
                persisted = True
                trace.event("persist", outcome="partial", error=ev.get("message"))
                outcome = "error"
                yield ev
    except GeneratorExit:
        # Client disconnect: the SSE writer closed us mid-stream.
        outcome = "disconnect"
        raise
    except BaseException as exc:
        # A real crash (judge raised, persistence failed, ...): label it
        # honestly — this is exactly the case the trace exists to explain.
        outcome = "crash"
        crash_error = str(exc) or type(exc).__name__
        raise
    finally:
        # Client disconnect (GeneratorExit) or abnormal stop: persist partial once.
        if not persisted and emitted:
            try:
                _persist_partial(conn, session_id, question, emitted)
                trace.event("persist", outcome="partial", error=crash_error or "client disconnect")
            except Exception as exc:
                # Best-effort: a persistence failure during teardown must not
                # mask the GeneratorExit (client disconnect) that triggered it.
                trace.event("persist", outcome="failed", error=str(exc))
        trace.close(outcome=outcome)
