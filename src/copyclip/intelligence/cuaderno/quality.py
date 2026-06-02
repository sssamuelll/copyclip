from __future__ import annotations

from dataclasses import dataclass

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
        for key in ("text",):
            v = b.data.get(key)
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts)


@dataclass
class QualityVerdict:
    status: str
    suspicion: bool
    language_mismatch: bool
    reason: str


def assess(*, question: str, blocks: list[Block], ledger: ReadLedger) -> QualityVerdict:
    """Phase-1 deterministic verdict. Hard-seals ONLY the cardinal case
    (code question + zero content-bearing reads -> ungrounded). Language
    mismatch raises suspicion (for the one retry) but does not seal."""
    q_lang = detect_language(question)
    a_lang = detect_language(_answer_text(blocks))
    language_mismatch = not languages_match(q_lang, a_lang)

    codey = looks_like_code_question(question)
    if codey and ledger.content_bearing_count == 0:
        return QualityVerdict(
            status=FRAME_STATUS_UNGROUNDED,
            suspicion=True,
            language_mismatch=language_mismatch,
            reason="code question answered with zero content-bearing reads",
        )
    return QualityVerdict(
        status=FRAME_STATUS_ANSWER,
        suspicion=language_mismatch,
        language_mismatch=language_mismatch,
        reason="ok" if not language_mismatch else "language mismatch",
    )
