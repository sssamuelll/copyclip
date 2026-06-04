from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

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


def _walk_citations(node: Any, out: list[Any]) -> None:
    """Recursively collect citation-shaped values from arbitrary widget data.
    Recursive descent (not per-kind extractors) is deliberate: future widget
    kinds are covered for free, so the artifact blind spot cannot be recreated
    by forgetting to register a kind."""
    if isinstance(node, dict):
        if node.get("citation") is not None:
            out.append(node["citation"])
        cits = node.get("citations")
        if isinstance(cits, list):
            out.extend(cits)
        for v in node.values():
            _walk_citations(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_citations(v, out)


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
        w = d.get("widget")
        if isinstance(w, dict):
            _walk_citations(w, candidates)
        for c in candidates:
            if isinstance(c, dict) and c.get("kind") == "path" and c.get("path"):
                paths.add(_norm_path(str(c["path"])))
    return paths


def _flatten_strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for k in ("label", "text", "name", "id"):
            v = node.get(k)
            if isinstance(v, str) and v:
                out.append(v)
        for v in node.values():
            _flatten_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten_strings(v, out)


def _artifact_summary(blocks: list[Block]) -> str:
    """Deterministic textual rendering of widget claims for the judge. Known
    kinds get a readable shape; unknown kinds hit the generic fallback so no
    widget kind is ever invisible to the judge."""
    parts: list[str] = []
    for b in blocks:
        if b.kind != "widget":
            continue
        w = b.data.get("widget")
        if not isinstance(w, dict):
            continue
        kind = w.get("kind")
        if kind == "graph_subset":
            nodes = [n for n in (w.get("nodes") or []) if isinstance(n, dict)]
            edges = [e for e in (w.get("edges") or []) if isinstance(e, dict)]
            labels = [str(n.get("label") or n.get("id") or "?") for n in nodes]
            arrows = [
                f"{e.get('from') or e.get('source') or '?'} -> {e.get('to') or e.get('target') or '?'}"
                for e in edges
            ]
            parts.append(f"graph: nodes [{', '.join(labels)}]; edges [{'; '.join(arrows)}]")
        elif kind == "sequence_diagram":
            steps = [s for s in (w.get("steps") or []) if isinstance(s, dict)]
            lines = [
                f"{s.get('from') or '?'} -> {s.get('to') or '?'}: {s.get('text') or ''}".strip()
                for s in steps
            ]
            parts.append("sequence: " + "; ".join(lines))
        elif kind == "callers_tree":
            callers = [c for c in (w.get("callers") or []) if isinstance(c, dict)]
            names = [str(c.get("name") or "?") for c in callers]
            parts.append(f"callers of {w.get('root') or '?'}: [{', '.join(names)}]")
        else:
            flat: list[str] = []
            _flatten_strings(w, flat)
            parts.append(f"{kind or 'widget'}: " + "; ".join(flat))
    return "\n".join(parts)


def artifacts_cited(blocks: list[Block]) -> Optional[bool]:
    """Confession axis, never a verdict: None = no widgets in the frame;
    True = at least one citation collected from widget data; False = widgets
    present, zero citations. Computed at _seal (the one chokepoint) because
    cheap and judge verdict dicts replace each other."""
    found: list[Any] = []
    has_widget = False
    for b in blocks:
        if b.kind != "widget":
            continue
        has_widget = True
        w = b.data.get("widget")
        if isinstance(w, dict):
            _walk_citations(w, found)
    if not has_widget:
        return None
    return len(found) > 0


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
    evidenced = {_norm_path(p) for p in getattr(ledger, "evidence_paths", set())}
    comparable = read | evidenced
    # Fabricated grounding: the answer cites evidence, but none of the cited
    # paths were actually read or tool-evidenced this turn. Requires `comparable`
    # to be non-empty — a turn grounded purely through grep_symbols/git_* with no
    # path-bearing results has no comparable paths and must NOT be condemned (we
    # cannot verify those citations, so we do not flag them).
    # Conservative all-disjoint also tolerates a real citation beside a near-miss.
    if codey and cited and comparable and cited.isdisjoint(comparable):
        return QualityVerdict(
            status=FRAME_STATUS_UNGROUNDED,
            suspicion=True,
            language_mismatch=language_mismatch,
            question_language=q_lang,
            reason=f"answer cites paths neither read nor tool-evidenced: {sorted(cited)}",
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
