from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
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
    "help",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _project_name(conn, project_id: int) -> str:
    row = conn.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
    return (row[0] if row and row[0] else f"project-{project_id}")


def _stable_packet_id(packet_payload: dict[str, Any]) -> str:
    digest = hashlib.sha1(json.dumps(packet_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    project = packet_payload.get("meta", {}).get("project") or "project"
    return f"handoff_{str(project).replace(' ', '_').lower()}_{digest}"


def _task_type(task_prompt: str) -> str:
    text = (task_prompt or "").lower()
    if any(word in text for word in ["fix", "bug", "repair"]):
        return "bugfix"
    if any(word in text for word in ["refactor", "clean up", "simplify"]):
        return "refactor"
    if any(word in text for word in ["test", "coverage", "regression"]):
        return "test"
    return "feature"


def _append_evidence(evidence_index: list[dict[str, Any]], item: dict[str, Any]) -> None:
    if not any(existing["id"] == item["id"] for existing in evidence_index):
        evidence_index.append(item)


def _evidence_item(item_id: str, item_type: str, label: str, ref: Any) -> dict[str, Any]:
    return {"id": item_id, "type": item_type, "label": label, "ref": ref}


def _decision_matches_scope(target: str, declared_files: list[str], supporting_files: list[str], declared_modules: list[str]) -> bool:
    if target in declared_files or target in supporting_files:
        return True
    return any(target.startswith(module.replace(".", "/")) or module in target for module in declared_modules)


def _module_scope_files(conn, project_id: int, declared_modules: list[str]) -> list[str]:
    if not declared_modules:
        return []
    files = []
    seen = set()
    for module in declared_modules:
        for row in conn.execute(
            "SELECT path FROM analysis_file_insights WHERE project_id=? AND module=? ORDER BY path ASC",
            (project_id, module),
        ).fetchall():
            path = row[0]
            if path and path not in seen:
                seen.add(path)
                files.append(path)
        for row in conn.execute(
            "SELECT DISTINCT file_path FROM symbols WHERE project_id=? AND module=? ORDER BY file_path ASC",
            (project_id, module),
        ).fetchall():
            path = row[0]
            if path and path not in seen:
                seen.add(path)
                files.append(path)
    return files


def _relevant_decisions(
    conn,
    project_id: int,
    declared_files: list[str],
    supporting_files: list[str],
    declared_modules: list[str],
    evidence_index: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.id, d.title, d.summary, d.status, dr.ref_value
        FROM decisions d
        LEFT JOIN decision_refs dr ON dr.decision_id = d.id AND dr.ref_type='file'
        WHERE d.project_id=? AND d.status IN ('accepted', 'resolved')
        ORDER BY d.id DESC
        """,
        (project_id,),
    ).fetchall()
    relevant_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        decision_id = int(row[0])
        ref_value = row[4]
        if not ref_value:
            continue
        if not _decision_matches_scope(str(ref_value), declared_files, supporting_files, declared_modules):
            continue
        item = relevant_by_id.setdefault(
            decision_id,
            {
                "id": decision_id,
                "title": row[1],
                "status": row[3],
                "why_relevant": "Linked to declared or supporting scope for this handoff packet.",
                "linked_targets": [],
                "evidence": [f"decision:{decision_id}"],
            },
        )
        if ref_value not in item["linked_targets"]:
            item["linked_targets"].append(ref_value)
        decision_link_id = f"decision_link:{ref_value}"
        if decision_link_id not in item["evidence"]:
            item["evidence"].append(decision_link_id)
        _append_evidence(evidence_index, _evidence_item(f"decision:{decision_id}", "decision", row[1], decision_id))
        _append_evidence(evidence_index, _evidence_item(decision_link_id, "decision_link", ref_value, ref_value))
        _append_evidence(evidence_index, _evidence_item(f"file:{ref_value}", "file", ref_value, ref_value))
    relevant = list(relevant_by_id.values())
    return relevant[:3]


def _constraints_from_decisions(relevant_decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    constraints = []
    for decision in relevant_decisions:
        constraints.append(
            {
                "constraint_id": f"constraint:decision:{decision['id']}",
                "type": "architectural_decision",
                "summary": decision["title"],
                "source": [f"decision:{decision['id']}"],
                "severity": "high",
                "origin": "system_derived",
            }
        )
    return constraints


def _risk_dark_zones(
    conn,
    project_id: int,
    declared_files: list[str],
    supporting_files: list[str],
    evidence_index: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scope_files = list(dict.fromkeys(declared_files + supporting_files))
    risks: list[dict[str, Any]] = []
    for row in conn.execute(
        "SELECT id, area, severity, kind, rationale, score FROM risks WHERE project_id=? ORDER BY score DESC, id DESC",
        (project_id,),
    ).fetchall():
        if row[1] not in scope_files:
            continue
        risks.append(
            {
                "risk_id": int(row[0]),
                "area": row[1],
                "kind": row[3],
                "severity": row[2],
                "score": int(row[5] or 0),
                "why_it_matters": row[4] or "Project risk overlaps with the declared handoff scope.",
                "recommended_guardrail": "Keep the change bounded and review the affected area carefully.",
                "evidence": [f"risk:{int(row[0])}", f"file:{row[1]}"],
            }
        )
        _append_evidence(evidence_index, _evidence_item(f"risk:{int(row[0])}", "risk", f"{row[3]} in {row[1]}", int(row[0])))
        _append_evidence(evidence_index, _evidence_item(f"file:{row[1]}", "file", row[1], row[1]))
    for row in conn.execute(
        "SELECT path, module, cognitive_debt FROM analysis_file_insights WHERE project_id=? ORDER BY cognitive_debt DESC, id DESC",
        (project_id,),
    ).fetchall():
        path = row[0]
        debt = float(row[2] or 0)
        if path not in scope_files or debt < 70:
            continue
        risks.append(
            {
                "risk_id": f"debt:{path}",
                "area": path,
                "kind": "cognitive_debt",
                "severity": "high" if debt >= 80 else "medium",
                "score": round(debt, 2),
                "why_it_matters": f"This area has elevated cognitive debt ({debt:.1f}).",
                "recommended_guardrail": "Prefer minimal bounded changes and explicit human review.",
                "evidence": [f"risk:debt:{path}", f"file:{path}"],
            }
        )
        _append_evidence(evidence_index, _evidence_item(f"risk:debt:{path}", "risk", f"cognitive_debt in {path}", f"debt:{path}"))
        _append_evidence(evidence_index, _evidence_item(f"file:{path}", "file", path, path))
    return risks[:5]


def _supporting_files(bundle: dict[str, Any], declared_files: list[str]) -> tuple[list[str], list[str]]:
    selected = []
    rationale = []
    for item in bundle.get("manifest", []):
        path = item.get("path")
        reasons = item.get("reasons") or []
        if not path or path in declared_files or path in selected:
            continue
        if not any(reason.startswith("term-match") or reason == "decision-ref" for reason in reasons):
            continue
        selected.append(path)
        rationale.append(f"{path}: {', '.join(reasons) or 'context-bundle match'}")
        if len(selected) >= 5:
            break
    return selected, rationale


def _questions_to_clarify(
    declared_files: list[str],
    declared_modules: list[str],
    relevant_decisions: list[dict[str, Any]],
    risk_dark_zones: list[dict[str, Any]],
    acceptance_criteria: list[str],
    module_scope_files: list[str] | None = None,
) -> list[dict[str, Any]]:
    questions = []
    module_scope_files = module_scope_files or []
    if not declared_files and not declared_modules:
        questions.append(
            {
                "question": "Which files or modules are explicitly in scope for this handoff?",
                "priority": "high",
                "blocking": True,
                "derived_from": ["scope_missing"],
                "resolution": None,
            }
        )
    if declared_modules and not module_scope_files:
        questions.append(
            {
                "question": "The declared modules did not resolve to concrete writable files. Should the scope be narrowed or indexed first?",
                "priority": "high",
                "blocking": True,
                "derived_from": ["module_scope_unresolved"],
                "resolution": None,
            }
        )
    if declared_modules and not declared_files:
        questions.append(
            {
                "question": "Should the declared modules expand to concrete writable files before delegation?",
                "priority": "medium",
                "blocking": False,
                "derived_from": ["module_scope_declared"],
                "resolution": None,
            }
        )
    if not relevant_decisions and not risk_dark_zones:
        questions.append(
            {
                "question": "No linked decisions or risks were found for the selected scope. Is the scope too broad or missing supporting evidence?",
                "priority": "medium",
                "blocking": False,
                "derived_from": ["evidence_gap"],
                "resolution": None,
            }
        )
    if not acceptance_criteria:
        questions.append(
            {
                "question": "What should a reviewer verify before accepting delegated work from this packet?",
                "priority": "medium",
                "blocking": False,
                "derived_from": ["acceptance_missing"],
                "resolution": None,
            }
        )
    return questions[:3]


def build_handoff_packet(
    conn,
    project_id: int,
    task_prompt: str,
    declared_files: list[str] | None = None,
    declared_modules: list[str] | None = None,
    do_not_touch: list[dict[str, Any]] | None = None,
    acceptance_criteria: list[str] | None = None,
    delegation_target: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    declared_files = list(dict.fromkeys(declared_files or []))
    declared_modules = list(dict.fromkeys(declared_modules or []))
    do_not_touch = do_not_touch or []
    acceptance_criteria = acceptance_criteria or []
    evidence_index: list[dict[str, Any]] = []

    module_scope_files = _module_scope_files(conn, project_id, declared_modules)
    write_scope_files = list(dict.fromkeys(declared_files + module_scope_files))
    bundle = build_context_bundle(conn, project_id, task_prompt, max_files=6)
    supporting_files, supporting_rationale = _supporting_files(bundle, write_scope_files)
    relevant_decisions = _relevant_decisions(conn, project_id, write_scope_files, supporting_files, declared_modules, evidence_index)
    constraints = _constraints_from_decisions(relevant_decisions)
    risk_dark_zones = _risk_dark_zones(conn, project_id, write_scope_files, supporting_files, evidence_index)
    questions_to_clarify = _questions_to_clarify(
        write_scope_files,
        declared_modules,
        relevant_decisions,
        risk_dark_zones,
        acceptance_criteria,
        module_scope_files=module_scope_files,
    )

    for boundary in do_not_touch:
        target = boundary.get("target")
        if isinstance(target, str) and target:
            _append_evidence(evidence_index, _evidence_item(f"boundary:{target}", "boundary", target, target))

    state = "draft" if any(item.get("blocking") for item in questions_to_clarify) else "ready_for_review"
    generated_at = generated_at or _now_iso()
    acceptance_items = [
        {"id": f"ac{i+1}", "summary": text, "check_type": "review_readiness"}
        for i, text in enumerate(acceptance_criteria)
    ]

    packet = {
        "meta": {
            "packet_id": None,
            "packet_version": "v1",
            "state": state,
            "created_at": generated_at,
            "updated_at": generated_at,
            "project": _project_name(conn, project_id),
            "created_by": "human",
            "approved_by": None,
            "delegation_target": delegation_target,
            "source_task": {"kind": "freeform_prompt", "value": task_prompt},
        },
        "objective": {
            "summary": task_prompt.strip(),
            "task_type": _task_type(task_prompt),
            "intent": "Prepare a bounded, inspectable delegation packet rather than uncontrolled context delivery.",
            "success_definition": "A human can inspect the packet before delegation and review whether the work respected the declared scope.",
        },
        "scope": {
            "declared_files": write_scope_files,
            "declared_modules": declared_modules,
            "supporting_files": supporting_files,
            "supporting_context_rationale": supporting_rationale,
            "out_of_scope_modules": [],
            "scope_rationale": ["Declared scope is human-provided; supporting files are system-derived from project context."],
        },
        "constraints": constraints,
        "do_not_touch": [
            {
                "target": item.get("target"),
                "reason": item.get("reason") or "Explicit human boundary.",
                "severity": item.get("severity") or "hard_boundary",
                "source": item.get("source") or [f"human_boundary:{item.get('target')}"],
            }
            for item in do_not_touch
            if item.get("target")
        ],
        "relevant_decisions": relevant_decisions,
        "risk_dark_zones": risk_dark_zones,
        "questions_to_clarify": questions_to_clarify,
        "acceptance_criteria": acceptance_items,
        "agent_consumable_packet": {
            "objective": task_prompt.strip(),
            "allowed_write_scope": write_scope_files,
            "read_scope": supporting_files,
            "constraints": [item["summary"] for item in constraints],
            "do_not_touch": [item["target"] for item in do_not_touch if item.get("target")],
            "questions_to_clarify": [item["question"] for item in questions_to_clarify],
            "acceptance_criteria": [item["summary"] for item in acceptance_items],
        },
        "review_contract": {
            "expected_review_type": "post_change_summary",
            "compare_scope_against_touched_files": True,
            "check_decision_conflicts": True,
            "check_dark_zone_entry": True,
            "check_blast_radius": True,
            "required_human_questions": [
                "Did the change stay within declared write scope?",
                "Did it violate any accepted decisions?",
            ],
        },
        "evidence_index": evidence_index,
        "notes": [],
        "bundle_manifest": bundle.get("manifest", []),
    }
    packet["meta"]["packet_id"] = _stable_packet_id(packet)
    return packet
