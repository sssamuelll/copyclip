"""Cognitive debt remediation engine.

Given a debt breakdown from :func:`build_debt_breakdown`, produce a prioritized
list of concrete remediation candidates with evidence-backed targets. Follows
the "remediation hooks" section of ``docs/COGNITIVE_DEBT_CONTRACT.md``:
candidates do not mutate the breakdown, each candidate references the factors
it would reduce, and ``expected_impact`` is always framed as an estimate.
"""

from __future__ import annotations

from typing import Any


REMEDIATION_ACTION_TYPES = {
    "read_this_first",
    "review_this_recent_change",
    "link_or_resolve_decision",
    "add_documentation_invariants",
    "inspect_tests_or_test_gaps",
    "refactor_or_simplify",
    "clarify_ownership",
}

# Minimum normalized contribution (0-100) for a factor to trigger its template.
# High contribution → candidate is worth surfacing; low contribution → noise.
_FACTOR_ACTIVATION_FLOOR = {
    "agent_authored_ratio": 40.0,
    "review_staleness": 40.0,
    "decision_gap": 60.0,
    "test_evidence_gap": 60.0,
    "churn_pressure": 40.0,
    "ownership_ambiguity": 40.0,
    "blast_radius": 60.0,
    "novelty_recency": 50.0,
}


def _factor_map(breakdown: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["factor_id"]: f for f in (breakdown.get("factor_breakdown") or [])}


def _is_factor_active(factor_map: dict[str, dict[str, Any]], factor_id: str) -> bool:
    factor = factor_map.get(factor_id)
    if not factor or not factor.get("signal_available"):
        return False
    value = factor.get("normalized_contribution") or 0.0
    return value >= _FACTOR_ACTIVATION_FLOOR.get(factor_id, 50.0)


def _recent_commits_for_file(conn, project_id: int, path: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.sha, c.author, c.date, c.message
        FROM file_changes fc
        JOIN commits c ON c.sha = fc.commit_sha AND c.project_id = fc.project_id
        WHERE fc.project_id=? AND fc.file_path=?
        ORDER BY c.date DESC
        LIMIT ?
        """,
        (project_id, path, limit),
    ).fetchall()
    return [
        {"sha": str(r[0]), "author": str(r[1] or ""), "date": str(r[2] or ""), "message": str(r[3] or "")}
        for r in rows
        if r[0]
    ]


def _agent_vs_human_commits(commits: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    agent_markers = ("claude", "bot", "copilot", "gpt", "codegen", "agent")
    agents: list[dict[str, Any]] = []
    humans: list[dict[str, Any]] = []
    for commit in commits:
        author = (commit.get("author") or "").lower()
        if any(marker in author for marker in agent_markers):
            agents.append(commit)
        else:
            humans.append(commit)
    return agents, humans


def _target_for_scope(meta: dict[str, Any]) -> dict[str, Any]:
    scope = meta.get("scope_kind")
    scope_id = meta.get("scope_id")
    if scope == "file":
        return {"kind": "file", "id": scope_id}
    if scope == "module":
        return {"kind": "module", "id": scope_id, "module": scope_id}
    return {"kind": "project", "id": scope_id}


def _estimate_impact(factor_map: dict[str, dict[str, Any]], factor_ids: list[str], reduction: float) -> float:
    delta = 0.0
    for fid in factor_ids:
        factor = factor_map.get(fid)
        if not factor or not factor.get("signal_available"):
            continue
        delta += factor["weight"] * (factor["normalized_contribution"] or 0.0) * reduction
    return round(-delta, 2)


def _candidate_for_human_review(factor_map, target, evidence_ids, agent_commits) -> dict[str, Any] | None:
    if not _is_factor_active(factor_map, "agent_authored_ratio") and not _is_factor_active(factor_map, "review_staleness"):
        return None
    delta = _estimate_impact(factor_map, ["agent_authored_ratio", "review_staleness"], reduction=0.5)
    commit_evidence = [f"commit:{c['sha']}" for c in agent_commits[:3]]
    return {
        "id": "human_review_recent_changes",
        "action_type": "review_this_recent_change",
        "label": "Human-review the recent agent-authored changes to restore continuity",
        "target": target,
        "reduces_factors": ["agent_authored_ratio", "review_staleness"],
        "expected_impact": {"score_delta": delta, "confidence": "medium"},
        "rationale": "Human review of recent non-human commits is the cheapest single reduction for drift and staleness.",
        "evidence": evidence_ids + commit_evidence,
    }


def _candidate_for_link_decision(factor_map, target) -> dict[str, Any] | None:
    if not _is_factor_active(factor_map, "decision_gap"):
        return None
    delta = _estimate_impact(factor_map, ["decision_gap"], reduction=0.8)
    return {
        "id": "link_or_propose_decision",
        "action_type": "link_or_resolve_decision",
        "label": "Link an accepted decision to this area or propose one if none applies",
        "target": target,
        "reduces_factors": ["decision_gap"],
        "expected_impact": {"score_delta": delta, "confidence": "medium"},
        "rationale": "An anchored decision turns an unexplained area into a documented constraint, which collapses the decision gap almost fully.",
        "evidence": [f"{target['kind']}:{target.get('id') or target.get('module')}"],
    }


def _candidate_for_add_test(factor_map, target, module) -> dict[str, Any] | None:
    if not _is_factor_active(factor_map, "test_evidence_gap"):
        return None
    delta = _estimate_impact(factor_map, ["test_evidence_gap"], reduction=0.9)
    module_label = module or target.get("module") or target.get("id") or "scope"
    return {
        "id": "add_targeted_test",
        "action_type": "inspect_tests_or_test_gaps",
        "label": f"Add at least one targeted test for {module_label}",
        "target": target if target.get("kind") != "file" else {"kind": "module", "id": module_label, "module": module_label},
        "reduces_factors": ["test_evidence_gap"],
        "expected_impact": {"score_delta": delta, "confidence": "medium"},
        "rationale": "A single deterministic test against the module's critical path dramatically reduces the test evidence gap.",
        "evidence": [f"module:{module_label}"],
    }


def _candidate_for_churn_note(factor_map, target, commits) -> dict[str, Any] | None:
    active = _is_factor_active(factor_map, "churn_pressure") or _is_factor_active(factor_map, "novelty_recency")
    if not active:
        return None
    delta = _estimate_impact(factor_map, ["churn_pressure", "novelty_recency"], reduction=0.3)
    commit_evidence = [f"commit:{c['sha']}" for c in commits[:3]]
    return {
        "id": "capture_churn_in_decision_note",
        "action_type": "add_documentation_invariants",
        "label": "Summarize the recent churn pattern in a decision or invariant note",
        "target": target,
        "reduces_factors": ["churn_pressure", "novelty_recency"],
        "expected_impact": {"score_delta": delta, "confidence": "low"},
        "rationale": "Writing down what the churn was for converts churn into acknowledged decisions, lowering uncertainty.",
        "evidence": [f"{target['kind']}:{target.get('id') or target.get('module')}"] + commit_evidence,
    }


def _candidate_for_ownership(factor_map, target) -> dict[str, Any] | None:
    if not _is_factor_active(factor_map, "ownership_ambiguity"):
        return None
    delta = _estimate_impact(factor_map, ["ownership_ambiguity"], reduction=0.5)
    return {
        "id": "clarify_ownership",
        "action_type": "clarify_ownership",
        "label": "Name a primary reviewer or owner for this area",
        "target": target,
        "reduces_factors": ["ownership_ambiguity"],
        "expected_impact": {"score_delta": delta, "confidence": "low"},
        "rationale": "Assigning a primary reviewer turns ambient co-authorship into a clear escalation path.",
        "evidence": [f"{target['kind']}:{target.get('id') or target.get('module')}"],
    }


def _candidate_for_blast_radius(factor_map, target) -> dict[str, Any] | None:
    if not _is_factor_active(factor_map, "blast_radius"):
        return None
    delta = _estimate_impact(factor_map, ["blast_radius"], reduction=0.3)
    return {
        "id": "isolate_blast_radius",
        "action_type": "refactor_or_simplify",
        "label": "Isolate side effects so the module's blast radius shrinks",
        "target": target,
        "reduces_factors": ["blast_radius"],
        "expected_impact": {"score_delta": delta, "confidence": "low"},
        "rationale": "High fan-out areas cascade small changes into wide impact; tightening boundaries is a slow but compounding win.",
        "evidence": [f"{target['kind']}:{target.get('id') or target.get('module')}"],
    }


def _candidate_for_read_anchor(factor_map, target, human_commits, last_human_ts) -> dict[str, Any] | None:
    if not human_commits:
        return None
    if not (_is_factor_active(factor_map, "agent_authored_ratio") or _is_factor_active(factor_map, "review_staleness")):
        return None
    delta = _estimate_impact(factor_map, ["agent_authored_ratio", "review_staleness"], reduction=0.2)
    first_human = human_commits[0]
    return {
        "id": "read_last_human_anchor",
        "action_type": "read_this_first",
        "label": f"Read the last human-authored anchor commit ({first_human['sha'][:7]})",
        "target": target,
        "reduces_factors": ["agent_authored_ratio", "review_staleness"],
        "expected_impact": {"score_delta": delta, "confidence": "low"},
        "rationale": "Re-anchoring on the last human-authored version of this area is the fastest context-restore step.",
        "evidence": [f"{target['kind']}:{target.get('id') or target.get('module')}", f"commit:{first_human['sha']}"],
    }


def _read_first_sequence(target, human_commits, agent_commits, breakdown) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1. last human-authored commit — restores continuity
    if human_commits:
        commit = human_commits[0]
        item_id = f"commit:{commit['sha']}"
        if item_id not in seen:
            items.append({
                "id": item_id,
                "kind": "commit",
                "sha": commit["sha"],
                "author_kind": "human",
                "reason": "Re-anchor on the last human-authored change to reset mental model.",
            })
            seen.add(item_id)

    # 2. up to two recent agent-authored commits worth reviewing
    for commit in agent_commits[:2]:
        item_id = f"commit:{commit['sha']}"
        if item_id not in seen:
            items.append({
                "id": item_id,
                "kind": "commit",
                "sha": commit["sha"],
                "author_kind": "agent",
                "reason": "Review recent agent-authored change to verify intent alignment.",
            })
            seen.add(item_id)

    # 3. linked decisions (if any) so the human rechecks constraints
    decision_factor = next((f for f in breakdown.get("factor_breakdown") or [] if f["factor_id"] == "decision_gap"), None)
    if decision_factor and decision_factor.get("signal_available"):
        for decision_id in (decision_factor.get("raw_signal") or {}).get("linked_decisions") or []:
            item_id = f"decision:{decision_id}"
            if item_id not in seen:
                items.append({
                    "id": item_id,
                    "kind": "decision",
                    "decision_id": decision_id,
                    "reason": "Re-read the decision anchoring this area before making changes.",
                })
                seen.add(item_id)

    # 4. the target file / module itself for direct inspection
    target_id = f"{target['kind']}:{target.get('id') or target.get('module')}"
    if target_id not in seen:
        items.append({
            "id": target_id,
            "kind": target["kind"],
            "reason": "Inspect the target in its current state before proposing changes.",
        })
        seen.add(target_id)

    return items


def _total_impact_with_diminishing_returns(candidates: list[dict[str, Any]]) -> float:
    # Order candidates by |score_delta| descending; each subsequent candidate
    # contributes at a decaying factor so the total impact stays realistic.
    ordered = sorted(candidates, key=lambda c: c["expected_impact"]["score_delta"])
    total = 0.0
    decay = 1.0
    for candidate in ordered:
        total += candidate["expected_impact"]["score_delta"] * decay
        decay *= 0.7
    return round(total, 2)


def build_remediation_plan(conn, project_id: int, breakdown: dict[str, Any]) -> dict[str, Any]:
    """Produce an ordered list of remediation candidates and a read_first sequence for a breakdown."""
    meta = dict(breakdown.get("meta") or {})
    factor_map = _factor_map(breakdown)
    target = _target_for_scope(meta)
    scope_kind = meta.get("scope_kind")
    scope_id = meta.get("scope_id")

    # Gather scope-dependent context
    commits: list[dict[str, Any]] = []
    module_for_file = None
    last_human_ts = None
    if scope_kind == "file" and scope_id:
        commits = _recent_commits_for_file(conn, project_id, scope_id)
        row = conn.execute(
            "SELECT module, last_human_ts FROM analysis_file_insights WHERE project_id=? AND path=?",
            (project_id, scope_id),
        ).fetchone()
        if row:
            module_for_file = row[0]
            last_human_ts = row[1]
    elif scope_kind == "module":
        file_rows = conn.execute(
            "SELECT path FROM analysis_file_insights WHERE project_id=? AND module=?",
            (project_id, scope_id),
        ).fetchall()
        for file_row in file_rows:
            commits.extend(_recent_commits_for_file(conn, project_id, file_row[0], limit=2))

    agent_commits, human_commits = _agent_vs_human_commits(commits)

    scope_evidence_ids = [f"{target['kind']}:{target.get('id') or target.get('module')}"]

    candidates: list[dict[str, Any]] = []
    for builder, args in [
        (_candidate_for_human_review, (factor_map, target, scope_evidence_ids, agent_commits)),
        (_candidate_for_link_decision, (factor_map, target)),
        (_candidate_for_add_test, (factor_map, target, module_for_file)),
        (_candidate_for_churn_note, (factor_map, target, commits)),
        (_candidate_for_ownership, (factor_map, target)),
        (_candidate_for_blast_radius, (factor_map, target)),
        (_candidate_for_read_anchor, (factor_map, target, human_commits, last_human_ts)),
    ]:
        candidate = builder(*args)
        if candidate is not None:
            candidates.append(candidate)

    # Dedupe by (action_type, target kind/id) keeping the first (highest-impact by construction).
    seen_keys: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate["action_type"], candidate["target"].get("kind", ""), str(candidate["target"].get("id") or candidate["target"].get("module", "")))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(candidate)

    # Rank by |expected score reduction| descending (most negative score_delta first).
    deduped.sort(key=lambda c: c["expected_impact"]["score_delta"])
    deduped = deduped[:6]

    # Compute top factors (available + positive contribution) ordered by weighted_contribution desc
    ranked_factors = sorted(
        [f for f in (breakdown.get("factor_breakdown") or []) if f.get("signal_available") and (f.get("weighted_contribution") or 0) > 0],
        key=lambda f: f["weighted_contribution"],
        reverse=True,
    )
    top_factor_ids = [f["factor_id"] for f in ranked_factors[:3]]

    read_first = _read_first_sequence(target, human_commits, agent_commits, breakdown)

    total_delta = _total_impact_with_diminishing_returns(deduped) if deduped else 0.0
    confidence_labels = [c["expected_impact"]["confidence"] for c in deduped]
    confidence = (
        "low"
        if not confidence_labels or "low" in confidence_labels and "medium" not in confidence_labels
        else ("high" if confidence_labels and all(c == "high" for c in confidence_labels) else "medium")
    )

    plan = {
        "meta": {
            "project": meta.get("project"),
            "generated_at": meta.get("generated_at"),
            "contract_version": meta.get("contract_version"),
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "score": (breakdown.get("score") or {}).get("value"),
            "severity": (breakdown.get("score") or {}).get("severity"),
        },
        "top_factors": top_factor_ids,
        "remediation_candidates": deduped,
        "read_first": read_first,
        "expected_total_impact": {"score_delta": total_delta, "confidence": confidence},
        "notes": [],
    }

    if not deduped:
        plan["notes"].append({
            "kind": "no_action_needed",
            "message": "No factor exceeded its activation floor; current debt is within acceptable bounds.",
        })

    return plan
