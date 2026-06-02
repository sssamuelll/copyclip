from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .language import detect_language, languages_match
from .read_ledger import ReadLedger
from .schema import Block, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED

# Question phrasings that are ABOUT the tutor/session, not the code. These never
# require evidence, so a zero-read answer to one of them is legitimate.
_META_MARKERS = (
    "what can i ask", "qué te puedo preguntar", "que te puedo preguntar",
    "qué me puedes", "que me puedes", "why did you", "por qué respondiste",
    "por que respondiste", "who are you", "quién eres", "quien eres",
    "how do i use", "cómo te uso", "como te uso",
)


def looks_like_code_question(question: str) -> bool:
    """Conservative: a question is code-comprehension unless it clearly targets
    the tutor/session itself. Default True so the gate errs toward demanding
    evidence."""
    low = question.lower().strip()
    return not any(m in low for m in _META_MARKERS)


def _answer_text(blocks: list[Block]) -> str:
    parts: list[str] = []
    for b in blocks:
        v = b.data.get("text")
        if isinstance(v, str):
            parts.append(v)
    return " ".join(parts)


def _norm_path(p: str) -> str:
    p = p.strip()
    if p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def _cited_paths(blocks: list[Block]) -> set[str]:
    """Every file path the answer cites (path-kind citations only; commits are
    not path-checked). Walks the citation shapes a block can carry: a direct
    `citation`, a `citations` list (callout), and `items[].citation`
    (citation_stack / ordered_list)."""
    paths: set[str] = set()
    for b in blocks:
        d = b.data
        candidates: list[Any] = []
        if d.get("citation") is not None:
            candidates.append(d["citation"])
        cits = d.get("citations")
        if isinstance(cits, list):
            candidates.extend(cits)
        items = d.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("citation") is not None:
                    candidates.append(item["citation"])
        for c in candidates:
            if isinstance(c, dict) and c.get("kind") == "path" and c.get("path"):
                paths.add(_norm_path(str(c["path"])))
    return paths


@dataclass
class QualityVerdict:
    status: str
    suspicion: bool
    language_mismatch: bool
    question_language: str
    reason: str


def assess(*, question: str, blocks: list[Block], ledger: ReadLedger) -> QualityVerdict:
    """Phase-1 deterministic verdict. Seals `ungrounded` for the cardinal case
    (code question + zero content-bearing reads) AND for fabricated grounding
    (a code answer whose citations point ONLY to paths never read this turn).
    A language mismatch raises suspicion (it drives the one retry in the
    compositor) but never seals — language is corrected, not condemned."""
    q_lang = detect_language(question)
    a_lang = detect_language(_answer_text(blocks))
    language_mismatch = not languages_match(q_lang, a_lang)
    codey = looks_like_code_question(question)

    if codey and ledger.content_bearing_count == 0:
        return QualityVerdict(
            status=FRAME_STATUS_UNGROUNDED,
            suspicion=True,
            language_mismatch=language_mismatch,
            question_language=q_lang,
            reason="code question answered with zero content-bearing reads",
        )

    cited = _cited_paths(blocks)
    read = {_norm_path(p) for p in ledger.read_paths}
    # Fabricated grounding: the answer cites evidence, but none of the cited
    # paths were actually read this turn. Requires `read` to be non-empty —
    # the ledger only records paths from read_file/list_dir, so a turn grounded
    # purely through grep_symbols/git_* has no comparable paths and must NOT be
    # condemned (we cannot verify those citations, so we do not flag them).
    # Conservative all-disjoint also tolerates a real citation beside a near-miss.
    if codey and cited and read and cited.isdisjoint(read):
        return QualityVerdict(
            status=FRAME_STATUS_UNGROUNDED,
            suspicion=True,
            language_mismatch=language_mismatch,
            question_language=q_lang,
            reason=f"answer cites only unread paths: {sorted(cited)}",
        )

    return QualityVerdict(
        status=FRAME_STATUS_ANSWER,
        suspicion=language_mismatch,
        language_mismatch=language_mismatch,
        question_language=q_lang,
        reason="ok" if not language_mismatch else "language mismatch",
    )


def cheap_verdict_dict(v: QualityVerdict) -> dict[str, Any]:
    """The cheap layer's partial verdict as the persisted pre-image. The cheap
    layer cannot judge responsiveness, so `responsive` is None (unknown)."""
    return {
        "grounded": v.status == FRAME_STATUS_ANSWER,
        "responsive": None,
        "language_ok": not v.language_mismatch,
        "question_kind": None,
        "world": None,
        "reason": v.reason,
        "source": "cheap",
    }
