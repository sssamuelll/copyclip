from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .context_bundle_builder import build_context_bundle


PACKET_TRANSITIONS = {
    "draft": {"ready_for_review", "superseded"},
    "ready_for_review": {"draft", "approved_for_handoff", "superseded"},
    "approved_for_handoff": {"delegated", "cancelled", "superseded"},
    "delegated": {"change_received", "cancelled", "superseded"},
    "change_received": {"reviewed", "superseded"},
    "reviewed": {"superseded"},
    "superseded": set(),
    "cancelled": set(),
}

REVIEW_STATES = {"not_started", "generated", "human_reviewed", "accepted", "changes_requested"}


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


def save_handoff_packet(conn, project_id: int, packet: dict[str, Any], commit: bool = True) -> dict[str, Any]:
    packet_id = str(packet.get("meta", {}).get("packet_id") or "")
    if not packet_id:
        raise ValueError("packet_id_required")
    state = str(packet.get("meta", {}).get("state") or "draft")
    objective = str(((packet.get("objective") or {}).get("summary")) or "")
    conn.execute(
        """
        INSERT INTO handoff_packets(project_id, packet_id, state, objective_summary, packet_json, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(project_id, packet_id) DO UPDATE SET
            state=excluded.state,
            objective_summary=excluded.objective_summary,
            packet_json=excluded.packet_json,
            updated_at=excluded.updated_at
        """,
        (
            project_id,
            packet_id,
            state,
            objective,
            json.dumps(packet, sort_keys=True),
            packet["meta"].get("created_at"),
            packet["meta"].get("updated_at"),
        ),
    )
    if commit:
        conn.commit()
    return packet


def list_handoff_packets(conn, project_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) FROM handoff_packets WHERE project_id=?", (project_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT packet_id, state, objective_summary, created_at, updated_at FROM handoff_packets WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
        (project_id, limit, offset),
    ).fetchall()
    return {
        "items": [
            {
                "packet_id": row[0],
                "state": row[1],
                "objective_summary": row[2],
                "created_at": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_handoff_packet(conn, project_id: int, packet_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT packet_json FROM handoff_packets WHERE project_id=? AND packet_id=?",
        (project_id, packet_id),
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def update_handoff_packet(conn, project_id: int, packet_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    packet = get_handoff_packet(conn, project_id, packet_id)
    if not packet:
        return None
    meta = packet.setdefault("meta", {})
    current_state = str(meta.get("state") or "draft")
    next_state = updates.get("state")
    if next_state is not None:
        next_state = str(next_state)
        allowed = PACKET_TRANSITIONS.get(current_state, set())
        if next_state != current_state and next_state not in allowed:
            raise ValueError(f"invalid_state_transition:{current_state}->{next_state}")
        meta["state"] = next_state
    if "approved_by" in updates:
        meta["approved_by"] = updates.get("approved_by")
    if "delegation_target" in updates:
        meta["delegation_target"] = updates.get("delegation_target")
    if "notes" in updates and isinstance(updates.get("notes"), list):
        packet["notes"] = updates.get("notes")
    meta["updated_at"] = updates.get("updated_at") or _now_iso()
    return save_handoff_packet(conn, project_id, packet, commit=False)


def _module_for_file(conn, project_id: int, path: str) -> str | None:
    row = conn.execute(
        "SELECT module FROM analysis_file_insights WHERE project_id=? AND path=?",
        (project_id, path),
    ).fetchone()
    if row and row[0]:
        return str(row[0])
    row = conn.execute(
        "SELECT module FROM symbols WHERE project_id=? AND file_path=? AND module IS NOT NULL LIMIT 1",
        (project_id, path),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _decisions_touching_files(conn, project_id: int, files: list[str]) -> list[tuple[int, str, str, str]]:
    if not files:
        return []
    placeholders = ",".join("?" * len(files))
    rows = conn.execute(
        f"""
        SELECT DISTINCT d.id, d.title, d.status, dr.ref_value
        FROM decisions d
        JOIN decision_refs dr ON dr.decision_id = d.id AND dr.ref_type='file'
        WHERE d.project_id=? AND dr.ref_value IN ({placeholders})
        ORDER BY d.id ASC
        """,
        (project_id, *files),
    ).fetchall()
    return [(int(r[0]), str(r[1] or ""), str(r[2] or "proposed"), str(r[3])) for r in rows]


def _file_risk_signals(conn, project_id: int, path: str) -> dict[str, Any] | None:
    risk_row = conn.execute(
        "SELECT id, severity, kind, rationale, score FROM risks WHERE project_id=? AND area=? ORDER BY score DESC, id DESC LIMIT 1",
        (project_id, path),
    ).fetchone()
    debt_row = conn.execute(
        "SELECT cognitive_debt FROM analysis_file_insights WHERE project_id=? AND path=?",
        (project_id, path),
    ).fetchone()
    debt = float(debt_row[0]) if debt_row and debt_row[0] is not None else 0.0
    has_risk = risk_row is not None
    if not has_risk and debt < 70:
        return None
    return {
        "risk_id": int(risk_row[0]) if has_risk else None,
        "severity": str(risk_row[1]) if has_risk else ("high" if debt >= 80 else "medium"),
        "kind": str(risk_row[2]) if has_risk else "cognitive_debt",
        "rationale": str(risk_row[3]) if has_risk and risk_row[3] else None,
        "risk_score": int(risk_row[4] or 0) if has_risk else None,
        "cognitive_debt": round(debt, 2) if debt else None,
    }


def _estimate_size(touched_count: int) -> str:
    if touched_count <= 2:
        return "small"
    if touched_count <= 6:
        return "medium"
    return "large"


def _stable_review_id(packet_id: str, touched_files: list[str], generated_at: str) -> str:
    payload = json.dumps({"packet_id": packet_id, "touched_files": sorted(touched_files), "generated_at": generated_at}, sort_keys=True)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"review_{packet_id}_{digest}"


def build_handoff_review_summary(
    conn,
    project_id: int,
    packet: dict[str, Any],
    proposed_changes: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    meta = packet.get("meta") or {}
    packet_id = str(meta.get("packet_id") or "")
    if not packet_id:
        raise ValueError("packet_id_required")

    declared_scope = list(dict.fromkeys((packet.get("scope") or {}).get("declared_files") or []))
    declared_scope_set = set(declared_scope)
    do_not_touch = list((packet.get("do_not_touch") or []))
    boundary_targets = {str(item.get("target")): item for item in do_not_touch if item.get("target")}
    acknowledged_dark_areas = {
        str(item.get("area"))
        for item in (packet.get("risk_dark_zones") or [])
        if item.get("area")
    }

    touched_files = list(dict.fromkeys([str(f) for f in (proposed_changes.get("touched_files") or []) if f]))
    generated_at = generated_at or _now_iso()

    review_evidence: list[dict[str, Any]] = []
    for item in (packet.get("evidence_index") or []):
        _append_evidence(review_evidence, item)

    # scope_check
    out_of_scope = [f for f in touched_files if f not in declared_scope]
    boundary_violations = []
    for touched in touched_files:
        for target, boundary in boundary_targets.items():
            if touched == target or touched.startswith(target.rstrip("/") + "/"):
                boundary_violations.append({
                    "target": target,
                    "touched_file": touched,
                    "reason": boundary.get("reason") or "Hard boundary touched.",
                    "severity": boundary.get("severity") or "hard_boundary",
                })
                _append_evidence(review_evidence, _evidence_item(f"boundary:{target}", "boundary", target, target))
                _append_evidence(review_evidence, _evidence_item(f"file:{touched}", "file", touched, touched))
                break

    if not touched_files:
        scope_summary = "No proposed changes were supplied; nothing to compare against declared scope."
    elif out_of_scope:
        scope_summary = (
            f"{len(out_of_scope)} of {len(touched_files)} touched file(s) are out of declared scope."
        )
    else:
        scope_summary = f"All {len(touched_files)} touched file(s) stayed within declared scope."

    scope_check = {
        "declared_scope": declared_scope,
        "touched_files": touched_files,
        "out_of_scope_touches": out_of_scope,
        "boundary_violations": boundary_violations,
        "summary": scope_summary,
    }

    # decision_conflicts: a decision's linked file was touched but that file is not in the declared write scope
    decision_conflicts: list[dict[str, Any]] = []
    seen_conflict_ids: set[int] = set()
    for decision_id, title, status, ref_value in _decisions_touching_files(conn, project_id, touched_files):
        if ref_value in declared_scope_set:
            continue
        is_hard_target = ref_value in boundary_targets
        severity = "high" if status in {"accepted", "resolved"} else "medium"
        if decision_id in seen_conflict_ids:
            conflict = next(item for item in decision_conflicts if item["decision_id"] == decision_id)
            if ref_value not in conflict["touched_targets"]:
                conflict["touched_targets"].append(ref_value)
            ev_id = f"file:{ref_value}"
            if ev_id not in conflict["evidence"]:
                conflict["evidence"].append(ev_id)
            _append_evidence(review_evidence, _evidence_item(ev_id, "file", ref_value, ref_value))
            continue
        seen_conflict_ids.add(decision_id)
        decision_conflicts.append({
            "decision_id": decision_id,
            "title": title,
            "status": status,
            "severity": severity,
            "summary": (
                f"Touched file '{ref_value}' is linked to accepted decision '{title}' that was not declared as in scope for this packet."
                if status in {"accepted", "resolved"}
                else f"Touched file '{ref_value}' is linked to decision '{title}' (status: {status})."
            ),
            "touched_targets": [ref_value],
            "evidence": [f"decision:{decision_id}", f"file:{ref_value}"],
        })
        _append_evidence(review_evidence, _evidence_item(f"decision:{decision_id}", "decision", title, decision_id))
        _append_evidence(review_evidence, _evidence_item(f"file:{ref_value}", "file", ref_value, ref_value))

    # blast_radius
    impacted_modules: list[str] = []
    for touched in touched_files:
        module = _module_for_file(conn, project_id, touched)
        if module and module not in impacted_modules:
            impacted_modules.append(module)
    blast_radius = {
        "impacted_modules": impacted_modules,
        "touched_file_count": len(touched_files),
        "estimated_size": _estimate_size(len(touched_files)),
        "impact_summary": (
            f"Touched {len(touched_files)} file(s) across {len(impacted_modules)} module(s)."
            if touched_files
            else "No changes proposed."
        ),
    }

    # dark_zone_entry
    dark_zone_entry: list[dict[str, Any]] = []
    for touched in touched_files:
        signals = _file_risk_signals(conn, project_id, touched)
        if signals is None:
            continue
        expected = touched in acknowledged_dark_areas
        reason_parts = []
        if signals.get("kind"):
            reason_parts.append(f"kind={signals['kind']}")
        if signals.get("severity"):
            reason_parts.append(f"severity={signals['severity']}")
        if signals.get("cognitive_debt") is not None:
            reason_parts.append(f"cognitive_debt={signals['cognitive_debt']}")
        reason_prefix = "Acknowledged dark zone touched" if expected else "Unexpected dark zone entry"
        dark_zone_entry.append({
            "area": touched,
            "expected": expected,
            "reason": f"{reason_prefix} ({', '.join(reason_parts) or 'risk signal present'}).",
            "evidence": [f"file:{touched}"] + ([f"risk:{signals['risk_id']}"] if signals.get("risk_id") is not None else []),
        })
        _append_evidence(review_evidence, _evidence_item(f"file:{touched}", "file", touched, touched))
        if signals.get("risk_id") is not None:
            _append_evidence(review_evidence, _evidence_item(f"risk:{signals['risk_id']}", "risk", f"{signals['kind']} in {touched}", signals["risk_id"]))

    # unresolved_questions: carry over blocking/unresolved from packet
    unresolved_questions: list[dict[str, Any]] = []
    for question in (packet.get("questions_to_clarify") or []):
        if question.get("resolution") is None:
            unresolved_questions.append({
                "question": question.get("question"),
                "priority": question.get("priority") or "medium",
                "blocking": bool(question.get("blocking")),
                "derived_from": question.get("derived_from") or [],
            })

    # verdict
    hard_violations = (
        bool(out_of_scope)
        or bool(boundary_violations)
        or any(c["severity"] == "high" for c in decision_conflicts)
        or any(not entry.get("expected") for entry in dark_zone_entry)
    )
    soft_signals = any(c["severity"] == "medium" for c in decision_conflicts) or any(q.get("blocking") for q in unresolved_questions)

    if hard_violations:
        verdict = "changes_requested"
        confidence = "high"
        result_summary = "Proposed change violated declared scope, hard boundaries, or entered unexpected dark zones."
    elif unresolved_questions or soft_signals:
        verdict = "needs_human_review"
        confidence = "medium"
        result_summary = "Proposed change stayed in scope but exposes acknowledged risks or leaves blocking questions open."
    else:
        verdict = "accepted"
        confidence = "high" if touched_files else "medium"
        result_summary = "Proposed change stayed within declared scope with no detected violations."

    return {
        "meta": {
            "review_id": _stable_review_id(packet_id, touched_files, generated_at),
            "packet_id": packet_id,
            "review_state": "generated",
            "generated_at": generated_at,
        },
        "result": {
            "summary": result_summary,
            "verdict": verdict,
            "confidence": confidence,
        },
        "scope_check": scope_check,
        "decision_conflicts": decision_conflicts,
        "blast_radius": blast_radius,
        "dark_zone_entry": dark_zone_entry,
        "unresolved_questions": unresolved_questions,
        "review_evidence": review_evidence,
    }


def save_handoff_review_summary(
    conn,
    project_id: int,
    packet_id: str,
    review_summary: dict[str, Any],
    commit: bool = True,
) -> dict[str, Any]:
    meta = review_summary.get("meta") or {}
    review_state = str(meta.get("review_state") or "generated")
    if review_state not in REVIEW_STATES:
        raise ValueError("invalid_review_state")
    meta_packet_id = meta.get("packet_id")
    if meta_packet_id and str(meta_packet_id) != packet_id:
        raise ValueError("review_packet_id_mismatch")
    conn.execute(
        """
        INSERT INTO handoff_review_summaries(project_id, packet_id, review_state, review_json, created_at, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(project_id, packet_id) DO UPDATE SET
            review_state=excluded.review_state,
            review_json=excluded.review_json,
            updated_at=excluded.updated_at
        """,
        (
            project_id,
            packet_id,
            review_state,
            json.dumps(review_summary, sort_keys=True),
            (review_summary.get("meta") or {}).get("generated_at"),
            (review_summary.get("meta") or {}).get("generated_at"),
        ),
    )
    if commit:
        conn.commit()
    return review_summary


MCP_CONSUMABLE_STATES = {"approved_for_handoff", "delegated"}


def format_handoff_packet_for_mcp(packet: dict[str, Any]) -> dict[str, Any]:
    meta = packet.get("meta") or {}
    state = str(meta.get("state") or "draft")
    constraints = packet.get("constraints") or []
    risks = packet.get("risk_dark_zones") or []
    questions = packet.get("questions_to_clarify") or []
    acceptance = packet.get("acceptance_criteria") or []
    agent_consumable = packet.get("agent_consumable_packet") or {}

    warnings: list[str] = []
    agent_ready = state in MCP_CONSUMABLE_STATES
    if not agent_ready:
        warnings.append("not_ready_for_consumption")
    if any(q.get("blocking") and q.get("resolution") is None for q in questions):
        warnings.append("unresolved_blocking_questions")

    return {
        "meta": {
            "packet_id": meta.get("packet_id"),
            "state": state,
            "packet_version": meta.get("packet_version"),
            "updated_at": meta.get("updated_at"),
            "delegation_target": meta.get("delegation_target"),
        },
        "agent_ready": agent_ready,
        "warnings": warnings,
        "objective": packet.get("objective") or {},
        "agent_consumable_packet": agent_consumable,
        "constraints_summary": [str(item.get("summary")) for item in constraints if item.get("summary")],
        "risk_summary": [
            f"{item.get('kind')} in {item.get('area')}: {item.get('why_it_matters')}"
            for item in risks
            if item.get("area")
        ],
        "questions_to_clarify": [
            {
                "question": q.get("question"),
                "priority": q.get("priority") or "medium",
                "blocking": bool(q.get("blocking")),
            }
            for q in questions
        ],
        "acceptance_criteria": [item.get("summary") if isinstance(item, dict) else str(item) for item in acceptance],
    }


def list_mcp_handoff_packets(conn, project_id: int, states: set[str] | None = None, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT packet_id, state, objective_summary, updated_at FROM handoff_packets WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT ?",
        (project_id, max(1, min(limit, 200))),
    ).fetchall()
    items = [
        {
            "packet_id": row[0],
            "state": row[1],
            "objective_summary": row[2],
            "updated_at": row[3],
        }
        for row in rows
    ]
    if states:
        items = [item for item in items if item["state"] in states]
    return items


def get_handoff_review_summary(conn, project_id: int, packet_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT review_json FROM handoff_review_summaries WHERE project_id=? AND packet_id=?",
        (project_id, packet_id),
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0])
