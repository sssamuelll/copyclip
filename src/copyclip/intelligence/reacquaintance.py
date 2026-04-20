import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import (
    connect,
    init_schema,
    get_or_create_project,
    get_reentry_baseline,
    get_active_decisions,
    record_project_visit,
    create_reentry_checkpoint,
)
from .cognitive_debt import quick_debt_signal


def _safe_json(value: str | None, default: Any):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence_item(ref_id: str, type_: str, label: str, ref: str):
    return {"id": ref_id, "type": type_, "label": label, "ref": ref}


def _append_evidence(index: dict[str, dict], item: dict):
    index[item["id"]] = item


def _score_change(commit_dt, baseline_dt, churn, risk_score, decision_links):
    recency = 100
    if commit_dt and baseline_dt:
        delta_hours = max(0.0, (commit_dt - baseline_dt).total_seconds() / 3600.0)
        recency = max(0, min(100, int(100 - min(delta_hours, 96) / 96 * 50)))
    churn_score = min(100, churn * 25)
    risk_link_score = min(100, risk_score)
    decision_link_score = min(100, decision_links * 30)
    breadth_score = min(100, max(churn * 15, risk_score // 2))
    return round(
        0.30 * recency
        + 0.25 * churn_score
        + 0.20 * risk_link_score
        + 0.15 * decision_link_score
        + 0.10 * breadth_score,
        2,
    )


def _score_read_first(change_score, risk_score, decision_score, target: str, debt_score: float = 0.0):
    payoff = min(100, max(change_score, risk_score, decision_score, debt_score))
    brevity = 85 if Path(target).suffix in {".md", ".toml", ".py", ".ts", ".tsx", ".js"} else 60
    return round(
        0.20 * change_score
        + 0.20 * payoff
        + 0.20 * risk_score
        + 0.15 * decision_score
        + 0.15 * debt_score
        + 0.10 * brevity,
        2,
    )


def _estimate_minutes(target: str) -> int:
    suffix = Path(target).suffix
    if suffix in {".toml", ".md", ".json"}:
        return 2
    if suffix in {".py", ".ts", ".tsx", ".js"}:
        return 4
    return 5


def record_reacquaintance_visit(project_root: str, visit_kind: str = "reacquaintance_open", source: str = "local") -> None:
    root = str(Path(project_root).resolve())
    conn = connect(root)
    try:
        init_schema(conn)
        project_id = get_or_create_project(conn, root)
        latest = conn.execute(
            """
            SELECT visited_at
            FROM project_visits
            WHERE project_id=? AND visit_kind IN ('reacquaintance_api', 'reacquaintance_cli', 'reacquaintance_open')
            ORDER BY visited_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        latest_dt = _parse_dt(latest[0]) if latest else None
        now_dt = datetime.now(timezone.utc)
        if latest_dt and (now_dt - latest_dt).total_seconds() < 30 * 60:
            return
        record_project_visit(conn, project_id, visit_kind=visit_kind, source=source)
    finally:
        conn.close()


def save_reentry_checkpoint(project_root: str, name: str, notes: str | None = None) -> int:
    root = str(Path(project_root).resolve())
    conn = connect(root)
    try:
        init_schema(conn)
        project_id = get_or_create_project(conn, root)
        return create_reentry_checkpoint(conn, project_id, name=name, notes=notes)
    finally:
        conn.close()


def build_reacquaintance_briefing(
    project_root: str,
    baseline_mode: str = "last_seen",
    window: str = "7d",
    checkpoint_name: str | None = None,
):
    root = str(Path(project_root).resolve())
    conn = connect(root)
    init_schema(conn)

    row = conn.execute("SELECT id, name, story FROM projects WHERE root_path=?", (root,)).fetchone()
    evidence_index: dict[str, dict] = {}
    fallback_notes: list[str] = []

    if not row:
        conn.close()
        return {
            "meta": {
                "project": Path(root).name,
                "generated_at": _iso_now(),
                "briefing_version": "v1",
                "baseline_mode": baseline_mode,
                "baseline_label": "unavailable",
                "baseline_started_at": None,
                "baseline_available": False,
                "confidence": "low",
            },
            "project_refresher": {"summary": "Project has not been analyzed yet.", "confidence": "low", "why_now": "No project record found.", "evidence": []},
            "top_changes": [],
            "read_first": [],
            "relevant_decisions": [],
            "top_risk": None,
            "open_questions": [],
            "evidence_index": [],
            "fallback_notes": ["No project record found yet. Run copyclip analyze first."],
        }

    pid = int(row[0])
    project_name = row[1] or Path(root).name
    story = row[2] or ""

    baseline = get_reentry_baseline(conn, pid, mode=baseline_mode, window=window, checkpoint_name=checkpoint_name)
    baseline_label = baseline.get("label")
    baseline_started_at = baseline.get("started_at")
    baseline_dt = _parse_dt(baseline_started_at)
    effective_mode = baseline.get("mode", baseline_mode)
    if effective_mode != baseline_mode:
        fallback_notes.append(f"No {baseline_mode} baseline found; fell back to {effective_mode}.")

    story_row = conn.execute(
        "SELECT focus_areas_json, major_changes_json, open_questions_json, summary_json FROM story_snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
        (pid,),
    ).fetchone()
    latest_story_snapshot = {
        "focus_areas": _safe_json(story_row[0], []) if story_row else [],
        "major_changes": _safe_json(story_row[1], []) if story_row else [],
        "open_questions": _safe_json(story_row[2], []) if story_row else [],
        "summary": _safe_json(story_row[3], {}) if story_row else {},
    }

    if story:
        _append_evidence(evidence_index, _evidence_item("project.story", "story", "Project story", "projects.story"))
    elif latest_story_snapshot["summary"]:
        story = f"Project has {latest_story_snapshot['summary'].get('files', 0)} files, {latest_story_snapshot['summary'].get('commits', 0)} commits, and {latest_story_snapshot['summary'].get('risks', 0)} active risks."
        _append_evidence(evidence_index, _evidence_item("snapshot:latest", "snapshot", "Latest story snapshot", "story_snapshots.latest"))
        fallback_notes.append("No project story found; used latest story snapshot summary.")
    else:
        story = f"{project_name} has been analyzed locally. Use the sections below to recover context."
        fallback_notes.append("No narrative story found; used a factual refresher fallback.")

    project_refresher = {
        "summary": story,
        "confidence": "high" if row[2] else ("medium" if latest_story_snapshot["summary"] else "low"),
        "why_now": "This briefing highlights recent work and the most relevant next reads for re-entry.",
        "evidence": [e for e in ["project.story" if row[2] else None, "snapshot:latest" if latest_story_snapshot["summary"] else None] if e],
    }

    commit_rows = conn.execute(
        "SELECT sha, author, date, message FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 50",
        (pid,),
    ).fetchall()
    file_change_rows = conn.execute(
        "SELECT file_path, COUNT(*) AS c FROM file_changes WHERE project_id=? GROUP BY file_path ORDER BY c DESC",
        (pid,),
    ).fetchall()
    commit_file_rows = conn.execute(
        """
        SELECT commit_sha, file_path, COUNT(*) AS c
        FROM file_changes
        WHERE project_id=?
        GROUP BY commit_sha, file_path
        ORDER BY commit_sha, c DESC, file_path ASC
        """,
        (pid,),
    ).fetchall()
    risk_rows = conn.execute(
        "SELECT area, severity, kind, rationale, score, created_at FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 50",
        (pid,),
    ).fetchall()
    decision_rows = conn.execute(
        "SELECT id, title, summary, status, created_at FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 50",
        (pid,),
    ).fetchall()
    active_decisions = get_active_decisions(root)

    churn_by_file = {r[0]: int(r[1] or 0) for r in file_change_rows}
    files_by_commit: dict[str, list[dict[str, int | str]]] = defaultdict(list)
    for commit_sha, file_path, count in commit_file_rows:
        if commit_sha and file_path:
            files_by_commit[str(commit_sha)].append({"file_path": str(file_path), "count": int(count or 0)})
    risk_by_area = {}
    for r in risk_rows:
        risk_by_area.setdefault(r[0], []).append({
            "severity": r[1],
            "kind": r[2],
            "rationale": r[3],
            "score": int(r[4] or 0),
            "created_at": r[5],
        })

    decision_links_by_target = defaultdict(list)
    for d in active_decisions:
        for link in d.get("links", []):
            target = link.get("target_pattern")
            if target:
                decision_links_by_target[target].append(d)
    unresolved_decisions = [
        {"id": int(r[0]), "title": r[1], "summary": r[2] or "", "status": r[3], "created_at": r[4]}
        for r in decision_rows if r[3] in {"proposed", "unresolved"}
    ]
    for d in unresolved_decisions:
        link_rows = conn.execute(
            "SELECT target_pattern FROM decision_links WHERE project_id=? AND decision_id=? ORDER BY id DESC",
            (pid, d["id"]),
        ).fetchall()
        d["links"] = [lr[0] for lr in link_rows]
        for target in d["links"]:
            decision_links_by_target[target].append(d)

    top_changes = []
    for r in commit_rows:
        commit_sha = str(r[0])
        commit_dt = _parse_dt(r[2])
        if baseline_dt and commit_dt and commit_dt < baseline_dt:
            continue
        related_targets = [item["file_path"] for item in files_by_commit.get(commit_sha, []) if item.get("file_path")]
        candidate_target = None
        best_tuple = (-1, -1, -1)
        for item in files_by_commit.get(commit_sha, []):
            target = str(item["file_path"])
            commit_local_count = int(item["count"])
            global_churn = churn_by_file.get(target, 0)
            risk_score = max((x["score"] for x in risk_by_area.get(target, [])), default=0)
            if (risk_score, commit_local_count, global_churn) > best_tuple:
                best_tuple = (risk_score, commit_local_count, global_churn)
                candidate_target = target
        candidate_target = candidate_target or (related_targets[0] if related_targets else None)
        target_churn = churn_by_file.get(candidate_target, 0) if candidate_target else 0
        target_risk = max((x["score"] for x in risk_by_area.get(candidate_target, [])), default=0) if candidate_target else 0
        target_decisions = len(decision_links_by_target.get(candidate_target, [])) if candidate_target else 0
        score = _score_change(commit_dt, baseline_dt, target_churn, target_risk, target_decisions)
        evidence = [f"commit:{commit_sha}"]
        _append_evidence(evidence_index, _evidence_item(f"commit:{commit_sha}", "commit", r[3], commit_sha))
        if candidate_target:
            evidence.append(f"file:{candidate_target}")
            _append_evidence(evidence_index, _evidence_item(f"file:{candidate_target}", "file", candidate_target, candidate_target))
        top_changes.append({
            "title": r[3],
            "importance": score,
            "summary": f"Recent commit by {r[1]} affecting re-entry-relevant areas.",
            "change_kind": "recent_commit",
            "primary_area": candidate_target or "repository",
            "evidence": evidence,
            "why_selected": [x for x in ["recent_change", "broad_impact" if target_churn > 1 else None, "risk_linked" if target_risk else None, "decision_linked" if target_decisions else None] if x],
        })
    top_changes.sort(key=lambda x: x["importance"], reverse=True)
    top_changes = top_changes[:5]
    if not top_changes and latest_story_snapshot["major_changes"]:
        for item in latest_story_snapshot["major_changes"][:3]:
            sha = item.get("sha", "unknown")
            msg = item.get("message", "Recent change")
            _append_evidence(evidence_index, _evidence_item(f"commit:{sha}", "commit", msg, sha))
            top_changes.append({
                "title": msg,
                "importance": 60,
                "summary": "Recovered from latest story snapshot.",
                "change_kind": "story_snapshot",
                "primary_area": "repository",
                "evidence": [f"commit:{sha}"],
                "why_selected": ["story_snapshot_fallback"],
            })
        fallback_notes.append("No direct recent commit evidence exceeded the baseline; used latest story snapshot major changes.")

    candidates = sorted(set(list(churn_by_file.keys()) + list(risk_by_area.keys()) + list(decision_links_by_target.keys())))
    read_first = []
    for target in candidates:
        churn = churn_by_file.get(target, 0)
        risk_score = max((x["score"] for x in risk_by_area.get(target, [])), default=0)
        decision_score = min(100, len(decision_links_by_target.get(target, [])) * 30)
        matching_change = next((c for c in top_changes if c["primary_area"] == target), None)
        change_score = matching_change["importance"] if matching_change else min(100, churn * 20)
        debt_signal = quick_debt_signal(conn, pid, target)
        debt_score = float(debt_signal["value"]) if debt_signal else 0.0
        score = _score_read_first(change_score, risk_score, decision_score, target, debt_score=debt_score)
        evidence = [f"file:{target}"]
        _append_evidence(evidence_index, _evidence_item(f"file:{target}", "file", target, target))
        if risk_score:
            top_r = max(risk_by_area.get(target, []), key=lambda x: x["score"])
            rid = f"risk:{target}:{top_r['kind']}"
            _append_evidence(evidence_index, _evidence_item(rid, "risk", f"{top_r['kind']} in {target}", target))
            evidence.append(rid)
        if decision_links_by_target.get(target):
            for d in decision_links_by_target[target][:2]:
                did = f"decision:{d['id']}"
                _append_evidence(evidence_index, _evidence_item(did, "decision", d["title"], str(d["id"])))
                evidence.append(did)
        reason = "High recent signal for re-entry based on churn, risk, and decision overlap."
        if debt_signal and debt_signal["severity"] in {"high", "critical"}:
            reason = f"Dark zone ({debt_signal['severity']} cognitive debt) with recent signal; re-anchor before making changes."
        read_first.append({
            "rank": 0,
            "target_type": "file",
            "target": target,
            "score": score,
            "reason": reason,
            "expected_payoff": "Should quickly restore context for the current area of change.",
            "estimated_minutes": _estimate_minutes(target),
            "evidence": evidence,
            "debt_signal": debt_signal,
        })
    read_first.sort(key=lambda x: x["score"], reverse=True)
    read_first = read_first[:3]
    for idx, item in enumerate(read_first, start=1):
        item["rank"] = idx

    relevant_decisions = []
    changed_areas = {c["primary_area"] for c in top_changes}
    read_targets = {r["target"] for r in read_first}
    for d in active_decisions + unresolved_decisions:
        links = d.get("links") or []
        normalized_links = [link.get("target_pattern") if isinstance(link, dict) else link for link in links]
        overlap = sum(1 for link in normalized_links if link in changed_areas or link in read_targets)
        risk_overlap = sum(1 for link in normalized_links if link in risk_by_area)
        unresolved_weight = 20 if d.get("status") in {"proposed", "unresolved"} else 0
        score = round(min(100, 40 * max(1, overlap) + 15 * risk_overlap + unresolved_weight), 2)
        if overlap == 0 and risk_overlap == 0 and d.get("status") not in {"proposed", "unresolved"}:
            continue
        did = f"decision:{d['id']}"
        _append_evidence(evidence_index, _evidence_item(did, "decision", d["title"], str(d["id"])))
        evidence = [did]
        relevant_decisions.append({
            "id": d["id"],
            "title": d["title"],
            "status": d["status"],
            "relevance_score": score,
            "why_now": "Linked to current changed or risky areas." if overlap or risk_overlap else "Unresolved decision likely to affect re-entry understanding.",
            "evidence": evidence,
        })
    relevant_decisions.sort(key=lambda x: x["relevance_score"], reverse=True)
    relevant_decisions = relevant_decisions[:3]

    top_risk = None
    if risk_rows:
        r = risk_rows[0]
        rid = f"risk:{r[0]}:{r[2]}"
        _append_evidence(evidence_index, _evidence_item(rid, "risk", f"{r[2]} in {r[0]}", r[0]))
        _append_evidence(evidence_index, _evidence_item(f"file:{r[0]}", "file", r[0], r[0]))
        top_risk = {
            "area": r[0],
            "severity": r[1],
            "kind": r[2],
            "score": int(r[4] or 0),
            "summary": r[3] or "Top current risk for this project.",
            "recommended_first_action": f"Read {read_first[0]['target']} first." if read_first else f"Inspect {r[0]} first.",
            "evidence": [rid, f"file:{r[0]}"] if r[0] else [rid],
        }
    else:
        fallback_notes.append("No risk rows available for this project yet; omitted top_risk.")

    open_questions = []
    for d in unresolved_decisions[:3]:
        did = f"decision:{d['id']}"
        _append_evidence(evidence_index, _evidence_item(did, "decision", d["title"], str(d["id"])))
        open_questions.append({
            "question": d["title"],
            "priority": "medium",
            "derived_from": [did],
            "next_step": "Inspect the linked area and decide whether this should move forward.",
        })
    if not open_questions and latest_story_snapshot["open_questions"]:
        for q in latest_story_snapshot["open_questions"][:2]:
            qid = f"decision:{q.get('decision_id', 'unknown')}"
            _append_evidence(evidence_index, _evidence_item(qid, "decision", q.get("title", "Open question"), str(q.get("decision_id", "unknown"))))
            open_questions.append({
                "question": q.get("title", "Open question"),
                "priority": "medium",
                "derived_from": [qid],
                "next_step": "Review the latest story snapshot and linked decision context.",
            })
        fallback_notes.append("Used latest story snapshot to recover open questions.")

    confidence = "high"
    if fallback_notes:
        confidence = "medium"
    if not row[2] and not top_changes:
        confidence = "low"

    briefing = {
        "meta": {
            "project": project_name,
            "generated_at": _iso_now(),
            "briefing_version": "v1",
            "baseline_mode": effective_mode,
            "baseline_label": baseline_label,
            "baseline_started_at": baseline_started_at,
            "baseline_available": bool(baseline.get("available")),
            "confidence": confidence,
        },
        "project_refresher": project_refresher,
        "top_changes": top_changes,
        "read_first": read_first,
        "relevant_decisions": relevant_decisions,
        "top_risk": top_risk,
        "open_questions": open_questions,
        "evidence_index": list(evidence_index.values()),
        "fallback_notes": fallback_notes,
    }
    conn.close()
    return briefing
