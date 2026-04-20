import re
from typing import Any

from .context_bundle_builder import build_context_bundle
from .cognitive_debt import quick_debt_signal


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
TYPE_BOOST = {"decision": 1000, "risk": 500, "commit": 100, "file": 50, "symbol": 750}


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
        "answer_evidence_ids": [],
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
        "debt_hints": [],
    }


def _contradiction_response(
    bundle_manifest: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    evidence_groups: dict[str, list[dict[str, Any]]],
    answer_evidence_ids: list[str],
    next_drill_down: dict[str, Any],
    debt_hints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "answer": "Indexed project evidence is pulling in conflicting directions, so I can’t give a confident grounded answer yet.",
        "answer_summary": "The strongest project signals contradict each other.",
        "answer_kind": "contradiction_detected",
        "confidence": "low",
        "citations": citations,
        "grounded": False,
        "evidence": evidence_groups,
        "answer_evidence_ids": answer_evidence_ids,
        "evidence_selection_rationale": [
            "A decision suggests one direction while current risk signals suggest the area is drifting or under tension.",
        ],
        "gaps_or_unknowns": [
            "The decision record and current risk/change signals appear to conflict.",
            "Inspect the linked file and decision history before trusting a single interpretation.",
        ],
        "next_questions": [
            "Which recent commit introduced the conflicting behavior?",
            "Does the accepted decision still match the current implementation?",
        ],
        "next_drill_down": next_drill_down,
        "bundle_manifest": bundle_manifest,
        "debt_hints": list(debt_hints or []),
    }


def _build_evidence_item(
    evidence_type: str,
    item_id: Any,
    label: str,
    snippet: str,
    score: int | float,
    why_selected: list[str],
    ref_target: Any,
    related_file: str | None = None,
) -> dict[str, Any]:
    item = {
        "evidence_id": f"{evidence_type}:{item_id}",
        "id": item_id,
        "label": label,
        "snippet": snippet,
        "score": score,
        "why_selected": why_selected,
        "ref": {"type": evidence_type, "target": ref_target},
    }
    if related_file:
        item["related_file"] = related_file
    return item


def _churn_by_file(conn, project_id: int) -> dict[str, int]:
    return {
        row[0]: int(row[1] or 0)
        for row in conn.execute(
            "SELECT file_path, COUNT(*) AS c FROM file_changes WHERE project_id=? GROUP BY file_path",
            (project_id,),
        ).fetchall()
        if row[0]
    }


def _risk_by_file(conn, project_id: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT id, area, kind, rationale, score FROM risks WHERE project_id=? ORDER BY score DESC, id DESC",
        (project_id,),
    ).fetchall():
        area = row[1]
        if area and area not in out:
            out[area] = {
                "id": int(row[0]),
                "kind": row[2],
                "rationale": row[3] or "",
                "score": int(row[4] or 0),
            }
    return out


def _decision_ref_targets(conn, project_id: int) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for row in conn.execute(
        """
        SELECT dr.ref_value, d.id
        FROM decision_refs dr
        JOIN decisions d ON d.id = dr.decision_id
        WHERE d.project_id=? AND d.status IN ('accepted', 'resolved') AND dr.ref_type='file'
        ORDER BY d.id DESC
        """,
        (project_id,),
    ).fetchall():
        if row[0]:
            out.setdefault(str(row[0]), []).append(int(row[1]))
    return out


def build_ask_response(conn, project_id: int, question: str) -> dict[str, Any]:
    terms = _terms(question)
    bundle = build_context_bundle(conn, project_id, question, max_files=20)
    churn_by_file = _churn_by_file(conn, project_id)
    risk_by_file = _risk_by_file(conn, project_id)
    decision_refs_by_file = _decision_ref_targets(conn, project_id)

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
        "SELECT id, area, kind, rationale, score FROM risks WHERE project_id=? ORDER BY score DESC LIMIT 300",
        (project_id,),
    ).fetchall():
        text = f"{r[1]} {r[2]} {r[3] or ''}".lower()
        score = sum(1 for t in terms if t in text)
        if score > 0:
            evidence.append(
                {
                    "score": score + 1,
                    "type": "risk",
                    "id": int(r[0]),
                    "title": f"{r[1]} ({r[2]})",
                    "snippet": (r[3] or "")[:240],
                    "query_linked": True,
                    "area": r[1],
                    "risk_kind": r[2],
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
        file_path = item.get("path")
        lexical_hits = sum(1 for t in terms if file_path and t in str(file_path).lower())
        churn = churn_by_file.get(str(file_path), 0) if file_path else 0
        linked_decisions = len(decision_refs_by_file.get(str(file_path), [])) if file_path else 0
        risk_score = int((risk_by_file.get(str(file_path), {}) or {}).get("score", 0)) if file_path else 0
        score = (
            lexical_hits * 30
            + min(churn * 10, 60)
            + min(linked_decisions * 40, 80)
            + min(risk_score, 100)
            + max(1, int(item.get("score") or 0) // 20)
        )
        evidence.append(
            {
                "score": score,
                "type": "file",
                "id": file_path,
                "title": file_path,
                "snippet": ", ".join(reasons),
                "query_linked": lexical_hits > 0,
                "signal_details": {
                    "lexical_hits": lexical_hits,
                    "churn": churn,
                    "decision_refs": linked_decisions,
                    "risk_score": risk_score,
                },
            }
        )

    for row in conn.execute(
        "SELECT id, name, kind, file_path, module FROM symbols WHERE project_id=? ORDER BY id DESC LIMIT 300",
        (project_id,),
    ).fetchall():
        symbol_id, name, kind, file_path, module = int(row[0]), row[1], row[2], row[3], row[4] or ""
        text = f"{name} {kind} {file_path} {module}".lower()
        score = sum(1 for t in terms if t in text)
        if score > 0:
            evidence.append(
                {
                    "score": score * 45 + min(churn_by_file.get(file_path, 0) * 5, 40),
                    "type": "symbol",
                    "id": symbol_id,
                    "title": name,
                    "snippet": f"{kind} in {file_path}",
                    "query_linked": True,
                    "file_path": file_path,
                    "symbol_name": name,
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
    answer_evidence_ids: list[str] = []

    for e in top:
        score = e.get("rank", e.get("score", 0))
        item = _build_evidence_item(
            e["type"],
            e["id"],
            e["title"],
            e.get("snippet", ""),
            score,
            [],
            e["id"],
            related_file=e.get("file_path"),
        )
        if e["type"] == "decision":
            citations.append({"type": "decision", "id": e["id"], "label": f"decision #{e['id']}"})
            lines.append(f"Decision #{e['id']}: {e['title']}")
            item["why_selected"] = [
                "Matched the question terms directly in the decision title or summary.",
                "Accepted decisions are ranked ahead of raw activity signals.",
            ]
            item["ref"] = {"type": "decision", "target": e["id"]}
            evidence_groups["decisions"].append(item)
        elif e["type"] == "risk":
            citations.append({"type": "risk", "id": e["id"], "label": e["title"]})
            lines.append(f"Risk signal: {e['title']}")
            item["why_selected"] = [
                "Matched the question against a known project risk.",
                "Risk severity and score increased its ranking priority.",
            ]
            item["ref"] = {"type": "risk", "target": e["id"]}
            item["related_file"] = e.get("area")
            item["risk_kind"] = e.get("risk_kind")
            evidence_groups["risks"].append(item)
        elif e["type"] == "commit":
            citations.append({"type": "commit", "id": e["id"], "label": f"commit {str(e['id'])[:7]}"})
            lines.append(f"Recent commit: {e['title']}")
            item["why_selected"] = [
                "Matched the question terms inside a recent commit message.",
                "Recent activity provides temporal provenance for this answer.",
            ]
            item["ref"] = {"type": "commit", "target": e["id"]}
            evidence_groups["commits"].append(item)
        elif e["type"] == "file":
            citations.append({"type": "file", "id": e["id"], "label": e["title"]})
            lines.append(f"Relevant file: {e['title']}")
            signal = e.get("signal_details", {})
            why = []
            if signal.get("lexical_hits"):
                why.append("Lexical file/path match with the question terms.")
            if signal.get("decision_refs"):
                why.append("Linked from accepted decision refs, increasing architectural relevance.")
            if signal.get("churn"):
                why.append("Recent churn increased the ranking for this file.")
            if signal.get("risk_score"):
                why.append("Risk score contributed to the file ranking.")
            item["why_selected"] = why or ["Selected from the compact context bundle."]
            item["ref"] = {"type": "file", "target": e["id"]}
            evidence_groups["files"].append(item)
        elif e["type"] == "symbol":
            file_path = e.get("file_path")
            if file_path:
                citations.append({"type": "file", "id": file_path, "label": file_path})
            lines.append(f"Relevant symbol: {e['title']}")
            item["why_selected"] = [
                "The question referenced a named code entity or module.",
                "Symbol-aware retrieval linked the question to a concrete definition.",
            ]
            item["ref"] = {"type": "symbol", "target": e["id"]}
            item["related_file"] = file_path
            evidence_groups["symbols"].append(item)

        answer_evidence_ids.append(item["evidence_id"])

    if not evidence_groups["files"]:
        supporting_files = []
        seen_supporting_files = set()
        for item in evidence_groups["risks"] + evidence_groups["symbols"]:
            related_file = item.get("related_file")
            if isinstance(related_file, str) and related_file and related_file not in seen_supporting_files:
                supporting_files.append(related_file)
                seen_supporting_files.add(related_file)
        for file_path, linked_decision_ids in decision_refs_by_file.items():
            if any(decision["id"] in linked_decision_ids for decision in evidence_groups["decisions"]):
                if file_path not in seen_supporting_files:
                    supporting_files.append(file_path)
                    seen_supporting_files.add(file_path)
        for file_path in supporting_files[:2]:
            signal = {
                "lexical_hits": sum(1 for t in terms if t in str(file_path).lower()),
                "churn": churn_by_file.get(str(file_path), 0),
                "decision_refs": len(decision_refs_by_file.get(str(file_path), [])),
                "risk_score": int((risk_by_file.get(str(file_path), {}) or {}).get("score", 0)),
            }
            why = []
            if signal["lexical_hits"]:
                why.append("Lexical file/path match with the question terms.")
            if signal["decision_refs"]:
                why.append("Linked from accepted decision refs, increasing architectural relevance.")
            if signal["churn"]:
                why.append("Recent churn increased the ranking for this file.")
            if signal["risk_score"]:
                why.append("Risk score contributed to the file ranking.")
            if any(risk.get("related_file") == file_path for risk in evidence_groups["risks"]):
                why.append("Backfilled because risk evidence pointed to this file.")
            if any(symbol.get("related_file") == file_path for symbol in evidence_groups["symbols"]):
                why.append("Backfilled because symbol evidence points to this file.")
            file_item = _build_evidence_item(
                "file",
                file_path,
                file_path,
                ", ".join(why) or "Supporting file for the strongest ask evidence.",
                TYPE_BOOST.get("file", 0) + signal["lexical_hits"] * 30 + min(signal["churn"] * 10, 60) + min(signal["decision_refs"] * 40, 80) + min(signal["risk_score"], 100),
                why or ["Supporting file for the strongest ask evidence."],
                file_path,
            )
            evidence_groups["files"].append(file_item)
            answer_evidence_ids.append(file_item["evidence_id"])
            if not any(citation["type"] == "file" and citation["id"] == file_path for citation in citations):
                citations.append({"type": "file", "id": file_path, "label": file_path})

    rationale = []
    if evidence_groups["decisions"]:
        rationale.append("Selected decisions because they directly matched the question terms.")
    if evidence_groups["risks"]:
        rationale.append("Included risk signals because they overlap with the same project area.")
    if evidence_groups["commits"]:
        rationale.append("Included recent commits to show the latest activity around the topic.")
    if evidence_groups["files"]:
        rationale.append("Included files using lexical match plus decision, churn, and risk signals from the compact context bundle.")
    if evidence_groups["symbols"]:
        rationale.append("Included symbol-level evidence because the question referenced named code entities or modules.")

    debt_hints: list[dict[str, Any]] = []
    seen_debt_paths: set[str] = set()
    for file_item in evidence_groups["files"]:
        path = str(file_item.get("id") or "")
        if not path or path in seen_debt_paths:
            continue
        signal = quick_debt_signal(conn, project_id, path)
        if not signal or signal["severity"] == "low":
            continue
        seen_debt_paths.add(path)
        debt_hints.append({
            "target_type": "file",
            "target": path,
            "debt_value": signal["value"],
            "severity": signal["severity"],
            "primary_signal": signal.get("primary_signal"),
        })
    debt_hints.sort(key=lambda x: x["debt_value"], reverse=True)
    debt_hints = debt_hints[:3]
    critical_debt_file = next(
        (hint["target"] for hint in debt_hints if hint["severity"] in {"critical", "high"}),
        None,
    )
    if critical_debt_file:
        rationale.append("Biased next_drill_down toward a high cognitive debt file so the reader re-anchors before editing.")

    next_drill_down = {"type": "none", "target": None}
    if critical_debt_file:
        next_drill_down = {"type": "file", "target": critical_debt_file}
    elif evidence_groups["decisions"]:
        next_drill_down = {"type": "decision", "target": evidence_groups["decisions"][0]["id"]}
    elif evidence_groups["risks"]:
        next_drill_down = {"type": "risk", "target": evidence_groups["risks"][0]["id"]}
    elif evidence_groups["files"]:
        next_drill_down = {"type": "file", "target": evidence_groups["files"][0]["id"]}
    elif evidence_groups["symbols"]:
        next_drill_down = {"type": "file", "target": top[[e["type"] for e in top].index("symbol")].get("file_path")}
    elif evidence_groups["commits"]:
        next_drill_down = {"type": "commit", "target": evidence_groups["commits"][0]["id"]}

    confidence = "high" if len({c["type"] for c in citations}) >= 2 else "medium"
    decision_ids = {int(item["id"]) for item in evidence_groups["decisions"]}
    decision_linked_files = {
        file_path
        for file_path, linked_decision_ids in decision_refs_by_file.items()
        if any(decision_id in decision_ids for decision_id in linked_decision_ids)
    }
    file_ids = {str(file_item["id"]) for file_item in evidence_groups["files"]}
    drift_risk_files = {
        str(item.get("related_file"))
        for item in evidence_groups["risks"]
        if isinstance(item.get("related_file"), str)
        and item.get("related_file")
        and "drift" in str(item.get("risk_kind") or "")
    }
    contradiction_detected = bool(decision_ids) and bool(
        decision_linked_files & file_ids & drift_risk_files
    )

    if contradiction_detected:
        return _contradiction_response(
            bundle.get("manifest", []),
            citations,
            evidence_groups,
            answer_evidence_ids,
            next_drill_down,
            debt_hints=debt_hints,
        )

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
        "answer_evidence_ids": answer_evidence_ids,
        "evidence_selection_rationale": rationale or ["Selected the strongest indexed artifacts for this question."],
        "gaps_or_unknowns": [],
        "next_questions": [
            "Which file or decision should I inspect first?",
            "What changed most recently in this area?",
        ],
        "next_drill_down": next_drill_down,
        "bundle_manifest": bundle.get("manifest", []),
        "debt_hints": debt_hints,
    }
