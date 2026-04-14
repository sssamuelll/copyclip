import re
from typing import Any

from .context_bundle_builder import build_context_bundle


STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "what",
    "how",
    "about",
    "tell",
    "happened",
}
TYPE_BOOST = {"decision": 1000, "risk": 500, "commit": 100, "file": 50}


def _terms(question: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-zA-Z0-9_\-]{3,}", (question or "").lower())
        if t not in STOP_WORDS
    ]


def _empty_evidence_groups() -> dict[str, list[dict[str, Any]]]:
    return {
        "files": [],
        "commits": [],
        "decisions": [],
        "risks": [],
        "symbols": [],
    }


def _insufficient_evidence_response(bundle_manifest: list[dict[str, Any]], question: str | None = None) -> dict[str, Any]:
    return {
        "answer": "I don’t have enough indexed evidence to answer that yet. Re-run analyze or ask with more specific entities (module/file/decision).",
        "answer_summary": "I don’t have enough indexed evidence to answer that yet.",
        "answer_kind": "insufficient_evidence",
        "confidence": "low",
        "citations": [],
        "grounded": False,
        "evidence": _empty_evidence_groups(),
        "evidence_selection_rationale": ["No indexed artifacts matched the current question strongly enough."],
        "gaps_or_unknowns": [
            "The current index does not contain enough query-linked evidence for a grounded answer.",
        ],
        "next_questions": [
            "Ask about a specific file, decision, commit, or module.",
            "Re-run analyze if the relevant area changed recently.",
        ],
        "next_drill_down": {"type": "none", "target": None},
        "bundle_manifest": bundle_manifest,
    }


def build_ask_response(conn, project_id: int, question: str) -> dict[str, Any]:
    terms = _terms(question)
    bundle = build_context_bundle(conn, project_id, question, max_files=20)

    evidence: list[dict[str, Any]] = []

    for r in conn.execute(
        "SELECT id,title,summary,status FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 200",
        (project_id,),
    ).fetchall():
        text = f"{r[1]} {r[2] or ''} {r[3]}".lower()
        score = sum(1 for t in terms if t in text)
        if score > 0:
            evidence.append(
                {
                    "score": score + 2,
                    "type": "decision",
                    "id": r[0],
                    "title": r[1],
                    "snippet": (r[2] or "")[:240],
                    "query_linked": True,
                }
            )

    for r in conn.execute(
        "SELECT area,kind,rationale,score FROM risks WHERE project_id=? ORDER BY score DESC LIMIT 300",
        (project_id,),
    ).fetchall():
        text = f"{r[0]} {r[1]} {r[2] or ''}".lower()
        score = sum(1 for t in terms if t in text)
        if score > 0:
            evidence.append(
                {
                    "score": score + 1,
                    "type": "risk",
                    "id": r[0],
                    "title": f"{r[0]} ({r[1]})",
                    "snippet": (r[2] or "")[:240],
                    "query_linked": True,
                }
            )

    for r in conn.execute(
        "SELECT sha,message,date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 300",
        (project_id,),
    ).fetchall():
        text = f"{r[0]} {r[1] or ''}".lower()
        score = sum(1 for t in terms if t in text)
        if score > 0:
            evidence.append(
                {
                    "score": score,
                    "type": "commit",
                    "id": r[0],
                    "title": (r[1] or "")[:120],
                    "snippet": f"commit {r[0][:7]} on {(r[2] or '')[:10]}",
                    "query_linked": True,
                }
            )

    for item in bundle.get("manifest", [])[:10]:
        reasons = item.get("reasons") or []
        evidence.append(
            {
                "score": max(1, int(item.get("score") or 0) // 20),
                "type": "file",
                "id": item.get("path"),
                "title": item.get("path"),
                "snippet": ", ".join(reasons),
                "query_linked": any(str(reason).startswith("term-match:") for reason in reasons),
            }
        )

    for e in evidence:
        e["rank"] = TYPE_BOOST.get(e["type"], 0) + e["score"]
    evidence.sort(key=lambda x: x["rank"], reverse=True)

    seen = set()
    top = []
    for e in evidence:
        key = (e["type"], e["id"])
        if key in seen:
            continue
        seen.add(key)
        top.append(e)
        if len(top) >= 5:
            break

    if not top:
        return _insufficient_evidence_response(bundle.get("manifest", []))

    if not any(bool(e.get("query_linked")) for e in top):
        return _insufficient_evidence_response(bundle.get("manifest", []))

    citations = []
    lines = []
    evidence_groups = _empty_evidence_groups()

    for e in top:
        item = {"id": e["id"], "label": e["title"], "snippet": e.get("snippet", "")}
        if e["type"] == "decision":
            citations.append({"type": "decision", "id": e["id"], "label": f"decision #{e['id']}"})
            lines.append(f"Decision #{e['id']}: {e['title']}")
            evidence_groups["decisions"].append(item)
        elif e["type"] == "risk":
            citations.append({"type": "risk", "id": e["id"], "label": e["title"]})
            lines.append(f"Risk signal: {e['title']}")
            evidence_groups["risks"].append(item)
        elif e["type"] == "commit":
            citations.append({"type": "commit", "id": e["id"], "label": f"commit {str(e['id'])[:7]}"})
            lines.append(f"Recent commit: {e['title']}")
            evidence_groups["commits"].append(item)
        elif e["type"] == "file":
            citations.append({"type": "file", "id": e["id"], "label": e["title"]})
            lines.append(f"Relevant file: {e['title']}")
            evidence_groups["files"].append(item)

    rationale = []
    if evidence_groups["decisions"]:
        rationale.append("Selected decisions because they directly matched the question terms.")
    if evidence_groups["risks"]:
        rationale.append("Included risk signals because they overlap with the same project area.")
    if evidence_groups["commits"]:
        rationale.append("Included recent commits to show the latest activity around the topic.")
    if evidence_groups["files"]:
        rationale.append("Included files from the compact context bundle for direct drill-down.")

    next_drill_down = {"type": "none", "target": None}
    if evidence_groups["decisions"]:
        next_drill_down = {"type": "decision", "target": evidence_groups["decisions"][0]["id"]}
    elif evidence_groups["risks"]:
        next_drill_down = {"type": "risk", "target": evidence_groups["risks"][0]["id"]}
    elif evidence_groups["files"]:
        next_drill_down = {"type": "file", "target": evidence_groups["files"][0]["id"]}
    elif evidence_groups["commits"]:
        next_drill_down = {"type": "commit", "target": evidence_groups["commits"][0]["id"]}

    confidence = "high" if len({c["type"] for c in citations}) >= 2 else "medium"
    answer = "Based on indexed project evidence, here are the strongest signals:\n- " + "\n- ".join(lines)
    answer_summary = lines[0] if lines else "Grounded answer generated from indexed project evidence."

    return {
        "answer": answer,
        "answer_summary": answer_summary,
        "answer_kind": "grounded_answer",
        "confidence": confidence,
        "citations": citations,
        "grounded": True,
        "evidence": evidence_groups,
        "evidence_selection_rationale": rationale or ["Selected the strongest indexed artifacts for this question."],
        "gaps_or_unknowns": [],
        "next_questions": [
            "Which file or decision should I inspect first?",
            "What changed most recently in this area?",
        ],
        "next_drill_down": next_drill_down,
        "bundle_manifest": bundle.get("manifest", []),
    }
