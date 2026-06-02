from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from .prompts import JUDGE_PROMPT
from .schema import Block

_DECISIONS = frozenset({"ok", "retry", "insufficient"})


@dataclass
class JudgeVerdict:
    question_kind: str          # code_comprehension | meta | conceptual
    grounded: bool
    responsive: bool
    language_ok: bool
    decision: str               # ok | retry | insufficient
    world: Optional[str]        # consulted_empty | not_consulted (insufficient only)
    retry_directive: Optional[str]
    reason: str


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return ""
    return text[start : end + 1]


def parse_judge_verdict(text: str) -> Optional[JudgeVerdict]:
    """Parse a judge response into a JudgeVerdict, or None if unusable (the
    caller treats None as fail-open)."""
    if not text:
        return None
    try:
        obj = json.loads(_extract_json(text))
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    decision = obj.get("decision")
    # isinstance(str) guards the `in` against an unhashable decision (e.g. the
    # model returns {"decision": ["ok"]}) — without it the membership test raises
    # TypeError, which would escape judge_answer and break fail-open.
    if not isinstance(decision, str) or decision not in _DECISIONS:
        return None
    return JudgeVerdict(
        question_kind=str(obj.get("question_kind", "code_comprehension")),
        grounded=bool(obj.get("grounded", True)),
        responsive=bool(obj.get("responsive", True)),
        language_ok=bool(obj.get("language_ok", True)),
        decision=decision,
        world=obj.get("world") if isinstance(obj.get("world"), str) else None,
        retry_directive=obj.get("retry_directive") if isinstance(obj.get("retry_directive"), str) else None,
        reason=str(obj.get("reason", "")),
    )


def _ok_verdict(reason: str) -> JudgeVerdict:
    return JudgeVerdict("code_comprehension", True, True, True, "ok", None, None, reason)


def _ledger_summary(ledger) -> str:
    paths = ", ".join(sorted(ledger.read_paths)) or "(none)"
    return f"content-bearing reads: {ledger.content_bearing_count}; files read: {paths}"


def _answer_text_for_judge(blocks: list[Block]) -> str:
    out: list[str] = []
    for b in blocks:
        v = b.data.get("text")
        if isinstance(v, str):
            out.append(v)
    return "\n\n".join(out)


def judge_answer(*, client, question, blocks, ledger, model, max_tokens: int = 512) -> JudgeVerdict:
    """Run the semantic judge over a finished answer. FAIL-OPEN: any error or
    unparseable output returns an `ok` verdict so a judge outage never blocks,
    hangs, or downgrades an answer that already passed the deterministic gate."""
    user = (
        f"QUESTION:\n{question}\n\n"
        f"EVIDENCE THE TUTOR CONSULTED:\n{_ledger_summary(ledger)}\n\n"
        f"THE TUTOR'S ANSWER:\n{_answer_text_for_judge(blocks)}\n\n"
        "Return ONLY the JSON verdict."
    )
    try:
        resp = client.messages_create(
            model=model, system=JUDGE_PROMPT,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens, timeout=20,
        )
        text = "".join(
            b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"
        )
        v = parse_judge_verdict(text)
    except Exception as exc:  # noqa: BLE001 — fail-open is the whole point: a judge
        # error, a HANG (bounded by timeout=20 on the Anthropic path), or any
        # parser surprise must seal the already-streamed answer, never crash the
        # terminal and lock the composer (the #124 invariant).
        return _ok_verdict(f"judge unavailable: {exc}")
    return v if v is not None else _ok_verdict("judge output unparseable")


def judge_verdict_dict(v: JudgeVerdict) -> dict[str, Any]:
    """The persisted pre-image (the record), excluding the transient action
    fields (decision, retry_directive)."""
    return {
        "grounded": v.grounded,
        "responsive": v.responsive,
        "language_ok": v.language_ok,
        "question_kind": v.question_kind,
        "world": v.world,
        "reason": v.reason,
        "source": "judge",
    }
