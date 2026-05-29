from __future__ import annotations

import sqlite3
from typing import Any, Iterator, Optional

from .compositor import iter_compose_events
from .persistence import save_question
from .schema import Block, Frame, frame_from_dict


def _persist_partial(conn, session_id: str, question: str, emitted: list[dict]) -> None:
    pframe = Frame(question=question, blocks=[Block.from_dict(b) for b in emitted])
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
) -> Iterator[dict[str, Any]]:
    """Wrap iter_compose_events for the HTTP layer.

    - Prepends a `meta` event carrying session_id.
    - On the terminal `frame`, persists the Frame and attaches its `position`.
    - On a terminal `error` with partial=True (or on client disconnect, which
      arrives as GeneratorExit in the finally), persists the partial Frame from
      the blocks already emitted.
    """
    yield {"type": "meta", "session_id": session_id}
    emitted: list[dict] = []
    persisted = False
    try:
        for ev in iter_compose_events(
            client=client, question=question, project_root=project_root,
            project_id=project_id, conn=conn, model=model,
            max_tool_rounds=max_tool_rounds, max_tokens=max_tokens,
        ):
            if ev["type"] == "block":
                emitted.append(ev["block"])
                yield ev
            elif ev["type"] == "tool":
                yield ev
            elif ev["type"] == "frame":
                frame = frame_from_dict(ev["frame"])
                position = save_question(conn, session_id, question, frame)
                persisted = True
                yield {"type": "frame", "position": position, "frame": ev["frame"]}
            elif ev["type"] == "error":
                if ev.get("partial") and emitted:
                    _persist_partial(conn, session_id, question, emitted)
                    persisted = True
                yield ev
    finally:
        # Client disconnect (GeneratorExit) or abnormal stop: persist partial once.
        if not persisted and emitted:
            try:
                _persist_partial(conn, session_id, question, emitted)
            except Exception:
                # Best-effort: a persistence failure during teardown must not
                # mask the GeneratorExit (client disconnect) that triggered it.
                pass
