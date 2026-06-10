from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import asdict
from typing import Any, Iterator, Optional

from .prompts import (
    SYSTEM_PROMPT, GROUNDING_RETRY_DIRECTIVE, LANGUAGE_RETRY_DIRECTIVE,
    RESPONSIVENESS_RETRY_FALLBACK, INVALID_BLOCK_RECOVERY, WIDGET_RECOVERY_DIRECTIVE,
    WIDGET_RECOVERY_DIRECTIVE_VISUAL, WIDGET_RECOVERY_DIRECTIVE_RUN,
)
from .read_ledger import ReadLedger, is_content_bearing_read
from .trace import NULL_TRACE
from .quality import assess, cheap_verdict_dict, artifacts_cited
from .judge import judge_verdict_dict
from .language import detect_language
from .i18n import tr
from .schema import (
    Block, Frame, Widget, frame_from_dict, frame_to_dict, validate_block_dict,
    FRAME_STATUS_FALLBACK, FRAME_STATUS_ANSWER,
    FRAME_STATUS_UNGROUNDED, FRAME_STATUS_INSUFFICIENT_EVIDENCE, FRAME_STATUS_OFF_TARGET,
)
from .tool_catalog import ANSWER_TOOLS, build_tool_definitions, dispatch_tool
from .widget_checks import GraphEvidence, validate_widget_payload
from ..playground import FunctionRef, resolve_function_ref

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


# A question that explicitly asks to SEE a graph: for these, the prose off-ramp
# is the wrong exit (prose earns off_target), so recovery pushes a widget rebuild.
_VISUAL_REQUEST_TERMS = (
    "show", "draw", "graph", "diagram", "visuali", "chart", "plot",
    "muestra", "muéstra", "dibuj", "grafic", "grafo", "diagrama", "visualiz",
)

# A question that asks to RUN/execute an example: the responsive artifact is a
# playground widget, not a description, so recovery pushes a widget emit.
_RUN_REQUEST_TERMS = (
    "run ", "runnable", "execute", "executable",
    "ejecut", "córre", "corre ", "prueba", "pruéba",
)


def _is_visual_request(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in _VISUAL_REQUEST_TERMS)


def _is_run_request(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in _RUN_REQUEST_TERMS)


# --- The deterministic playground floor (Epic #139) -------------------------
# A run-request's required output TYPE (a playground widget) is a property the
# system guarantees, so it must be enforced OUTSIDE the model: when the model
# answers a run-request in prose and the turn would seal off_target, the SYSTEM
# constructs the playground from a symbol that RESOLVES against the symbols table.
# It never invents — if no symbol resolves, the honest off_target stands.

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _candidate_symbol_names(question: str) -> list[str]:
    """Identifiers in the question that might name a symbol. Underscore-bearing
    and longer names rank first — they look most like a symbol reference."""
    seen: list[str] = []
    for m in _IDENT_RE.findall(question):
        if len(m) >= 3 and m not in seen:
            seen.append(m)
    seen.sort(key=lambda s: (("_" not in s), -len(s)))
    return seen


def _resolve_floor_symbol(conn: sqlite3.Connection, project_id: int,
                          names: list[str], ledger: Optional[ReadLedger]):
    """Resolve the FIRST candidate name that maps to a real symbol. A name that
    spans multiple files is disambiguated to the one the model actually touched
    (the ledger); still ambiguous -> skip (the floor declines rather than guess)."""
    touched: set[str] = set()
    if ledger is not None:
        touched = set(ledger.read_paths) | set(ledger.evidence_paths)
    for name in names:
        rows = conn.execute(
            "SELECT file_path FROM symbols WHERE project_id=? AND name=? "
            "AND kind IN ('function','method','class')",
            (project_id, name),
        ).fetchall()
        files = [r[0] for r in rows]
        if not files:
            continue
        if len(files) == 1:
            chosen = files[0]
        else:
            inter = [f for f in files if f in touched]
            if len(inter) != 1:
                continue
            chosen = inter[0]
        try:
            return resolve_function_ref(conn, project_id, FunctionRef(file=chosen, name=name))
        except Exception:  # noqa: BLE001 — any resolution failure means: do not offer a floor
            continue
    return None


def _has_playground(emitted: list[Block]) -> bool:
    for b in emitted:
        if b.kind == "widget":
            w = b.data.get("widget")
            if isinstance(w, dict) and w.get("kind") == "playground":
                return True
    return False


def _construct_playground_floor(question: str, conn: Optional[sqlite3.Connection],
                                project_id: Optional[int], ledger: Optional[ReadLedger],
                                emitted: list[Block]) -> Optional[Block]:
    """Build the playground Block for a run-request from a resolved symbol, or
    None when nothing resolves (then the honest off_target stands)."""
    if conn is None or project_id is None or not _is_run_request(question):
        return None
    if _has_playground(emitted):
        return None
    resolved = _resolve_floor_symbol(conn, project_id,
                                     _candidate_symbol_names(question), ledger)
    if resolved is None:
        return None
    fr: dict[str, Any] = {"file": resolved.file, "name": resolved.name}
    if resolved.line_start is not None:
        fr["line"] = resolved.line_start
    if resolved.qualname and resolved.qualname != resolved.name:
        fr["qualname"] = resolved.qualname
    lang = detect_language(question)
    breadcrumb = (f"Ejecuta {resolved.name} con un ejemplo"
                  if lang == "es" else f"Run {resolved.name} with an example")
    block = Block.widget(Widget.playground(function_ref=fr, breadcrumb=breadcrumb).to_dict())
    # Defensive: the floor must meet the same emit-time bar as a model widget.
    if validate_widget_payload(block.to_dict(), GraphEvidence()) is not None:
        return None
    return block


def _floor_verdict_dict(prior_status: str) -> dict[str, Any]:
    """Honest verdict for a floor-sealed answer: the artifact is grounded by DB
    resolution and responsive by construction; `source` marks it system-built and
    records what it upgraded from."""
    return {
        "question_kind": "code_comprehension",
        "grounded": True,
        "responsive": True,
        "language_ok": True,
        "world": None,
        "source": "floor",
        "reason": f"playground constructed deterministically from a resolved symbol (was {prior_status})",
    }


def _floored_frame(frame_dict: dict[str, Any], question: str,
                   conn: Optional[sqlite3.Connection], project_id: Optional[int],
                   ledger: Optional[ReadLedger]) -> dict[str, Any]:
    """Apply the playground floor to a sealed terminal frame: a run-request that
    would seal `off_target` (prose, not a runnable artifact) or `fallback` (no
    answer at all) is upgraded to an `answer` carrying a system-constructed
    playground — when a named symbol RESOLVES against the symbols table. Off_target
    keeps its grounded prose and gains the artifact; fallback's 'couldn't finish'
    message is dropped for the artifact. Any other status, or no resolvable symbol,
    is returned unchanged — the honest verdict stands. Never invents."""
    status = frame_dict.get("status")
    if not _is_run_request(question):
        return frame_dict
    if status not in (FRAME_STATUS_OFF_TARGET, FRAME_STATUS_FALLBACK):
        return frame_dict
    blocks = [Block.from_dict(b) for b in frame_dict.get("blocks", [])]
    if _has_playground(blocks):
        # The model already delivered the runnable artifact: a run-request answered
        # WITH a playground is responsive by definition. An off_target label here is
        # the judge mislabeling form as relevance — reclassify, don't relabel.
        return _seal(question, blocks, FRAME_STATUS_ANSWER, _floor_verdict_dict(status))
    # fallback's only block is a system 'couldn't finish' message — drop it.
    base: list[Block] = [] if status == FRAME_STATUS_FALLBACK else blocks
    floor = _construct_playground_floor(question, conn, project_id, ledger, base)
    if floor is None:
        return frame_dict
    base.append(floor)
    return _seal(question, base, FRAME_STATUS_ANSWER, _floor_verdict_dict(status))


def _fallback_frame(question: str, reason: str) -> Frame:
    lang = detect_language(question)
    return Frame(
        question=question,
        blocks=[Block.paragraph(tr("fallback", lang, reason=reason))],
        status=FRAME_STATUS_FALLBACK,
        question_language=lang,
    )


def _sealed_frame(question: str, emitted: list[Block], ledger: ReadLedger, judge=None) -> dict[str, Any]:
    """Seal a terminal that cannot retry (the budget-exhausted tail). A
    would-be-`answer` is still judged here (Option A — no `answer` escapes the
    judge); a judge `retry` cannot retry (the loop is over) so it seals
    `off_target`."""
    verdict = assess(question=question, blocks=emitted, ledger=ledger)
    if verdict.status != FRAME_STATUS_ANSWER:
        return _seal(question, emitted, verdict.status, cheap_verdict_dict(verdict))
    if judge is not None:
        jv = judge(question, emitted, ledger)
        return _seal(question, emitted, _judge_status(jv), judge_verdict_dict(jv))
    return _seal(question, emitted, FRAME_STATUS_ANSWER, cheap_verdict_dict(verdict))


def _seal(question: str, emitted: list[Block], status: str, verdict: dict) -> dict[str, Any]:
    # artifacts_cited is injected HERE because the cheap and judge verdict
    # dicts replace each other — neither layer alone reaches every sealed frame.
    verdict = {**verdict, "artifacts_cited": artifacts_cited(emitted)}
    return frame_to_dict(Frame(question=question, blocks=emitted, status=status,
                               verdict=verdict, question_language=detect_language(question)))


def _judge_status(jv) -> str:
    if jv.decision == "ok":
        return FRAME_STATUS_ANSWER
    if jv.decision == "insufficient":
        return (FRAME_STATUS_INSUFFICIENT_EVIDENCE
                if jv.world == "consulted_empty" else FRAME_STATUS_UNGROUNDED)
    return FRAME_STATUS_OFF_TARGET   # retry with the responsiveness latch spent


_LANGUAGE_NAMES = {"es": "Spanish", "en": "English"}


def _retry_directive(verdict) -> str:
    """Compose the one corrective round's directive from whatever the verdict
    flagged: grounding (unsound answer) and/or language (wrong language)."""
    parts: list[str] = []
    if verdict.status != FRAME_STATUS_ANSWER:
        parts.append(GROUNDING_RETRY_DIRECTIVE)
    if verdict.language_mismatch:
        lang = _LANGUAGE_NAMES.get(verdict.question_language, verdict.question_language)
        parts.append(LANGUAGE_RETRY_DIRECTIVE.format(language=lang))
    return " ".join(parts) if parts else GROUNDING_RETRY_DIRECTIVE


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


def _ack_terminal_tools(turn_content: list[dict[str, Any]],
                        emit_status: dict[str, Optional[str]]) -> list[dict[str, Any]]:
    """tool_result acks for every tool_use in a TERMINAL assistant turn.

    A retry re-invokes the model, and both the Anthropic and OpenAI APIs require
    every assistant tool_use/tool_call to be answered by a tool_result before the
    next turn (OpenAI: 'insufficient tool messages following tool_calls'). The
    normal round acks inline (and dispatches read tools); the terminal round
    skipped acking because it used to always return — until grounding /
    responsiveness retries began re-calling the model from here."""
    results: list[dict[str, Any]] = []
    for blk in turn_content:
        if blk.get("type") != "tool_use":
            continue
        tuid = blk["id"]
        if blk.get("name") == "emit_block":
            reason = emit_status.get(tuid)
            results.append(_ack(tuid, {"ok": True}) if reason is None
                           else _ack(tuid, {"error": "invalid_block", "detail": reason,
                                            "recovery": INVALID_BLOCK_RECOVERY}, is_error=True))
        else:
            results.append(_ack(tuid, {"ok": True}))
    return results


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
    judge: Any = None,  # Optional (question, blocks, ledger) -> JudgeVerdict
    ledger: Optional[ReadLedger] = None,
    trace: Any = None,
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
    ledger = ledger if ledger is not None else ReadLedger()
    trace = trace if trace is not None else NULL_TRACE
    grounding_retry_used = False
    responsiveness_retry_used = False
    evidence = GraphEvidence()  # graph-tool results seen this TURN — accumulates across rounds

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
        usage: Any = None
        finish_seen = False
        emit_status: dict[str, Optional[str]] = {}  # tool_use_id -> reason (None = ok)

        round_t0 = time.perf_counter()
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
                        if reason is None:
                            reason = validate_widget_payload(inp, evidence)
                        emit_status[blk["id"]] = reason
                        if reason is None:
                            b = Block.from_dict(inp)
                            emitted.append(b)
                            trace.event("block.accept", block=b.to_dict(), sse=True)
                            yield {"type": "block", "block": b.to_dict()}
                        else:
                            trace.event("block.reject", block=inp, reason=reason,
                                        recovery=INVALID_BLOCK_RECOVERY)
                    elif blk.get("type") == "tool_use" and blk.get("name") == "finish":
                        finish_seen = True
                elif sev.get("type") == "message_stop":
                    stop_reason = sev.get("stop_reason")
                    usage = sev.get("usage")
                    turn_content = sev.get("content", []) or []
        except Exception as exc:  # noqa: BLE001 — surface LLM/stream failure as a terminal error
            trace.event("error", message=f"stream failed ({exc})",
                        partial=len(emitted) > 0, sse=True)
            yield {
                "type": "error",
                "message": f"stream failed ({exc})",
                "partial": len(emitted) > 0,
            }
            return

        trace.event("llm.round", round_i=round_i, closing=is_closing,
                    ms=int((time.perf_counter() - round_t0) * 1000),
                    stop_reason=stop_reason, usage=usage)
        messages.append({"role": "assistant", "content": turn_content})

        # Terminal: explicit finish, or a non-tool stop reason (implicit finish).
        if finish_seen or stop_reason != "tool_use":
            if emitted:
                verdict = assess(question=question, blocks=emitted, ledger=ledger)
                cheap_needs_retry = (verdict.status != FRAME_STATUS_ANSWER
                                     or verdict.language_mismatch)
                # Only retry if the NEXT round would still be a normal round. The
                # closing round (round_i == max_tool_rounds - 1) strips the
                # research tools, so a grounding retry landing there could not read
                # and would only stack a directive contradicting CLOSING_DIRECTIVE.
                can_retry = round_i < max_tool_rounds - 2
                if cheap_needs_retry and not grounding_retry_used and can_retry:
                    # Refuse the close: DISCARD the unsound blocks so the corrected
                    # answer REPLACES them, and emit a `reset` so downstream
                    # consumers (the HTTP wrapper's own block buffer, the client's
                    # provisional render) drop the discarded blocks too. Inject a
                    # composed grounding/language directive, KEEP tools, spend one
                    # more normal round. Fires at most once.
                    grounding_retry_used = True
                    emitted.clear()
                    # Answer the terminal turn's tool_use blocks before re-calling
                    # the model — a dangling tool_call 400s on real APIs.
                    acks = _ack_terminal_tools(turn_content, emit_status)
                    if acks:
                        messages.append({"role": "user", "content": acks})
                    _inject_directive(messages, _retry_directive(verdict))
                    yield {"type": "reset"}
                    continue
                if verdict.status != FRAME_STATUS_ANSWER:
                    yield {"type": "frame",
                           "frame": _seal(question, emitted, verdict.status,
                                          cheap_verdict_dict(verdict))}
                    return
                if judge is not None:
                    jv = judge(question, emitted, ledger)
                    if (jv.decision == "retry" and not responsiveness_retry_used
                            and can_retry):
                        responsiveness_retry_used = True
                        emitted.clear()
                        acks = _ack_terminal_tools(turn_content, emit_status)
                        if acks:
                            messages.append({"role": "user", "content": acks})
                        _inject_directive(
                            messages, jv.retry_directive or RESPONSIVENESS_RETRY_FALLBACK)
                        yield {"type": "reset"}
                        continue
                    yield {"type": "frame",
                           "frame": _floored_frame(
                               _seal(question, emitted, _judge_status(jv),
                                     judge_verdict_dict(jv)),
                               question, conn, project_id, ledger)}
                    return
                yield {"type": "frame",
                       "frame": _seal(question, emitted, FRAME_STATUS_ANSWER,
                                      cheap_verdict_dict(verdict))}
                return
            else:
                yield {"type": "frame",
                       "frame": _floored_frame(
                           frame_to_dict(
                               _fallback_frame(question, "the model produced no answer blocks")),
                           question, conn, project_id, ledger)}
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
                        _ack(tuid, {"error": "invalid_block", "detail": reason,
                                    "recovery": INVALID_BLOCK_RECOVERY}, is_error=True))
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
                if name == "get_module_graph":
                    evidence.add_module_graph(result)
                elif name == "get_callers":
                    evidence.add_callers(args.get("symbol", ""), result)
                elif name == "get_callees":
                    evidence.add_callees(args.get("symbol", ""), result)
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

        # Widget-fixation backstop: if every emit_block this round was rejected,
        # the round produced no answer block — the model is stuck on a widget it
        # cannot ground. Offer the prose off-ramp so an ungroundable widget
        # degrades to an honest answer instead of draining the budget into a
        # blank frame. Not latched (it neither discards blocks nor costs a round),
        # so each stuck round renews the offer; skip the closing round, whose
        # directive already forces composition and which has no next turn to read.
        if (not is_closing and emit_status
                and all(reason is not None for reason in emit_status.values())):
            if _is_visual_request(question):
                directive, variant = WIDGET_RECOVERY_DIRECTIVE_VISUAL, "visual"
            elif _is_run_request(question):
                directive, variant = WIDGET_RECOVERY_DIRECTIVE_RUN, "run"
            else:
                directive, variant = WIDGET_RECOVERY_DIRECTIVE, "generic"
            trace.event("recovery.directive", variant=variant)
            _inject_directive(messages, directive)

    # Budget exhausted → fallback frame (terminal; parity with the wrapper below).
    if emitted:
        yield {"type": "frame",
               "frame": _floored_frame(_sealed_frame(question, emitted, ledger, judge=judge),
                                       question, conn, project_id, ledger)}
    else:
        yield {"type": "frame",
               "frame": _floored_frame(
                   frame_to_dict(_fallback_frame(question, "tool-call budget exhausted")),
                   question, conn, project_id, ledger)}


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
