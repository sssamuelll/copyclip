"""Cognitive debt factor breakdowns.

Implements the v1 contract defined in ``docs/COGNITIVE_DEBT_CONTRACT.md``.

The entry point is :func:`build_debt_breakdown`, which returns the full
contract shape for a file, module, or project. Each factor is computed
independently; missing signals lower ``signal_coverage``/``confidence`` but do
not push the score toward zero (the factor weight is removed from the
denominator instead).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable


CONTRACT_VERSION = "v1"

COGNITIVE_DEBT_FACTORS: list[dict[str, Any]] = [
    {"id": "churn_pressure", "label": "Churn pressure", "weight": 0.18},
    {"id": "agent_authored_ratio", "label": "Agent-authored ratio", "weight": 0.22},
    {"id": "review_staleness", "label": "Review staleness", "weight": 0.15},
    {"id": "test_evidence_gap", "label": "Test evidence gap", "weight": 0.12},
    {"id": "decision_gap", "label": "Decision gap", "weight": 0.13},
    {"id": "ownership_ambiguity", "label": "Ownership ambiguity", "weight": 0.08},
    {"id": "blast_radius", "label": "Blast radius", "weight": 0.07},
    {"id": "novelty_recency", "label": "Novelty recency", "weight": 0.05},
]

FACTOR_WEIGHT = {f["id"]: f["weight"] for f in COGNITIVE_DEBT_FACTORS}
FACTOR_LABEL = {f["id"]: f["label"] for f in COGNITIVE_DEBT_FACTORS}

SEVERITY_BUCKETS = [
    ("critical", 75.0),
    ("high", 50.0),
    ("medium", 25.0),
    ("low", 0.0),
]

CHURN_NORMALIZATION_UNIT = 10  # each change contributes 10 points, cap at 100
STALENESS_CAP_DAYS = 60.0
TEST_PATH_MARKERS = ("tests/", "test_", "_test", "/tests/", "spec/", "__tests__/")


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _severity_for(value: float) -> str:
    for label, minimum in SEVERITY_BUCKETS:
        if value >= minimum:
            return label
    return "low"


def _confidence_for(signal_coverage: float) -> str:
    if signal_coverage >= 0.85:
        return "high"
    if signal_coverage >= 0.6:
        return "medium"
    return "low"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _append_evidence(index: list[dict[str, Any]], item: dict[str, Any]) -> None:
    if not any(existing["id"] == item["id"] for existing in index):
        index.append(item)


def _file_insight(conn, project_id: int, path: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT module, complexity, cognitive_debt, agent_line_ratio, last_human_ts FROM analysis_file_insights WHERE project_id=? AND path=?",
        (project_id, path),
    ).fetchone()
    if not row:
        return None
    return {
        "module": row[0],
        "complexity": row[1],
        "cognitive_debt": row[2],
        "agent_line_ratio": row[3],
        "last_human_ts": row[4],
    }


def _files_in_module(conn, project_id: int, module: str) -> list[str]:
    seen: list[str] = []
    for row in conn.execute(
        "SELECT path FROM analysis_file_insights WHERE project_id=? AND module=? ORDER BY path",
        (project_id, module),
    ).fetchall():
        if row[0] and row[0] not in seen:
            seen.append(row[0])
    return seen


def _all_modules(conn, project_id: int) -> list[str]:
    seen: list[str] = []
    for row in conn.execute(
        "SELECT DISTINCT module FROM analysis_file_insights WHERE project_id=? AND module IS NOT NULL ORDER BY module",
        (project_id,),
    ).fetchall():
        if row[0] and row[0] not in seen:
            seen.append(row[0])
    return seen


def _churn_count(conn, project_id: int, path: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM file_changes WHERE project_id=? AND file_path=?",
        (project_id, path),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _authors_for_file(conn, project_id: int, path: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT c.author
        FROM file_changes fc
        JOIN commits c ON c.sha = fc.commit_sha AND c.project_id = fc.project_id
        WHERE fc.project_id=? AND fc.file_path=? AND c.author IS NOT NULL AND c.author != ''
        """,
        (project_id, path),
    ).fetchall()
    return [str(r[0]) for r in rows if r[0]]


def _earliest_commit_ts_for_file(conn, project_id: int, path: str) -> float | None:
    row = conn.execute(
        """
        SELECT MIN(c.date)
        FROM file_changes fc
        JOIN commits c ON c.sha = fc.commit_sha AND c.project_id = fc.project_id
        WHERE fc.project_id=? AND fc.file_path=?
        """,
        (project_id, path),
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        dt = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.timestamp()


def _decision_links_for_file(conn, project_id: int, path: str) -> list[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT d.id
        FROM decisions d
        LEFT JOIN decision_refs dr ON dr.decision_id = d.id AND dr.ref_type='file'
        LEFT JOIN decision_links dl ON dl.decision_id = d.id AND dl.project_id = d.project_id AND dl.link_type='file'
        WHERE d.project_id=? AND d.status IN ('accepted', 'resolved')
          AND (dr.ref_value=? OR dl.target_pattern=?)
        """,
        (project_id, path, path),
    ).fetchall()
    return [int(r[0]) for r in rows if r[0] is not None]


def _module_has_tests(conn, project_id: int, module: str, files: Iterable[str]) -> bool:
    for path in files:
        lowered = path.lower()
        if any(marker in lowered for marker in TEST_PATH_MARKERS):
            return True
    if not module:
        return False
    row = conn.execute(
        "SELECT COUNT(*) FROM files WHERE project_id=? AND path LIKE ?",
        (project_id, f"%tests/%{module.replace('.', '/')}%"),
    ).fetchone()
    return bool(row and row[0])


def _module_fan_out(conn, project_id: int, module: str) -> int:
    row = conn.execute(
        "SELECT SUM(LENGTH(imports_json) - LENGTH(REPLACE(imports_json, ',', ''))) FROM analysis_file_insights WHERE project_id=? AND module=?",
        (project_id, module),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _factor_item(
    factor_id: str,
    *,
    normalized: float | None,
    raw_signal: Any,
    available: bool,
    rationale: str,
    evidence: list[str],
) -> dict[str, Any]:
    weight = FACTOR_WEIGHT[factor_id]
    contribution = 0.0
    if available and normalized is not None:
        contribution = round(weight * _clamp(normalized), 4)
    return {
        "factor_id": factor_id,
        "label": FACTOR_LABEL[factor_id],
        "weight": weight,
        "raw_signal": raw_signal,
        "normalized_contribution": round(_clamp(normalized or 0.0), 2) if available else None,
        "weighted_contribution": contribution,
        "signal_available": available,
        "rationale": rationale,
        "evidence": evidence,
    }


def _build_file_factors(conn, project_id: int, path: str, *, lookback_days: int, now_ts: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    insight = _file_insight(conn, project_id, path)
    if insight is None:
        insight = {"module": None, "complexity": None, "cognitive_debt": None, "agent_line_ratio": None, "last_human_ts": None}

    evidence_index: list[dict[str, Any]] = []
    _append_evidence(evidence_index, {"id": f"file:{path}", "type": "file", "label": path, "ref": path})
    module = insight.get("module")
    if module:
        _append_evidence(evidence_index, {"id": f"module:{module}", "type": "module", "label": module, "ref": module})

    factors: list[dict[str, Any]] = []

    # churn_pressure
    churn_count = _churn_count(conn, project_id, path)
    churn_normalized = _clamp(churn_count * CHURN_NORMALIZATION_UNIT)
    factors.append(_factor_item(
        "churn_pressure",
        normalized=churn_normalized,
        raw_signal={"changes": churn_count, "lookback_days": lookback_days},
        available=True,
        rationale=f"{churn_count} recorded change(s) for this file.",
        evidence=[f"file:{path}"],
    ))

    # agent_authored_ratio
    agent_ratio = insight.get("agent_line_ratio")
    if agent_ratio is not None:
        agent_pct = _clamp(float(agent_ratio) * 100.0)
        factors.append(_factor_item(
            "agent_authored_ratio",
            normalized=agent_pct,
            raw_signal={"agent_line_ratio": round(float(agent_ratio), 4)},
            available=True,
            rationale=f"{agent_pct:.1f}% of current lines are agent-authored.",
            evidence=[f"file:{path}", "blame:agent"],
        ))
        _append_evidence(evidence_index, {"id": "blame:agent", "type": "blame", "label": "agent-authored lines", "ref": "blame:agent"})
    else:
        factors.append(_factor_item(
            "agent_authored_ratio",
            normalized=None,
            raw_signal={"agent_line_ratio": None},
            available=False,
            rationale="No blame data available for this file.",
            evidence=[],
        ))

    # review_staleness
    last_human_ts = insight.get("last_human_ts")
    if last_human_ts is not None and last_human_ts > 0:
        days_since = max(0.0, (now_ts - float(last_human_ts)) / 86400.0)
        normalized = _clamp((days_since / STALENESS_CAP_DAYS) * 100.0)
        factors.append(_factor_item(
            "review_staleness",
            normalized=normalized,
            raw_signal={"days_since_human": round(days_since, 1), "last_human_ts": float(last_human_ts)},
            available=True,
            rationale=f"Last human-authored line was {days_since:.1f} day(s) ago.",
            evidence=[f"file:{path}", "blame:human"],
        ))
        _append_evidence(evidence_index, {"id": "blame:human", "type": "blame", "label": "human-authored lines", "ref": "blame:human"})
    else:
        factors.append(_factor_item(
            "review_staleness",
            normalized=None,
            raw_signal={"last_human_ts": None},
            available=False,
            rationale="No human-authored line found in blame.",
            evidence=[],
        ))

    # test_evidence_gap
    siblings = _files_in_module(conn, project_id, module) if module else [path]
    has_tests = _module_has_tests(conn, project_id, module or "", siblings)
    factors.append(_factor_item(
        "test_evidence_gap",
        normalized=0.0 if has_tests else 100.0,
        raw_signal={"module": module, "module_has_tests": has_tests},
        available=True,
        rationale=(
            "Module has associated test files." if has_tests else "No test files were detected for this module."
        ),
        evidence=[f"module:{module}"] if module else [f"file:{path}"],
    ))

    # decision_gap
    decisions = _decision_links_for_file(conn, project_id, path)
    decision_coverage = 1.0 if decisions else 0.0
    factors.append(_factor_item(
        "decision_gap",
        normalized=(1.0 - decision_coverage) * 100.0,
        raw_signal={"linked_decisions": decisions},
        available=True,
        rationale=(
            f"File is linked to {len(decisions)} accepted/resolved decision(s)." if decisions else "No accepted decision is linked to this file."
        ),
        evidence=[f"file:{path}"] + [f"decision:{d}" for d in decisions],
    ))
    for d in decisions:
        _append_evidence(evidence_index, {"id": f"decision:{d}", "type": "decision", "label": f"decision {d}", "ref": d})

    # ownership_ambiguity
    authors = _authors_for_file(conn, project_id, path)
    if churn_count == 0 and not authors:
        factors.append(_factor_item(
            "ownership_ambiguity",
            normalized=None,
            raw_signal={"distinct_authors": 0, "churn": 0},
            available=False,
            rationale="No churn history to derive ownership signal.",
            evidence=[],
        ))
    else:
        # 1 author → 0, 2 → 30, 3 → 55, 4 → 75, 5+ → 90
        mapping = {0: 100.0, 1: 0.0, 2: 30.0, 3: 55.0, 4: 75.0}
        normalized = mapping.get(len(authors), 90.0)
        factors.append(_factor_item(
            "ownership_ambiguity",
            normalized=normalized,
            raw_signal={"distinct_authors": len(authors)},
            available=True,
            rationale=f"File touched by {len(authors)} distinct author(s).",
            evidence=[f"file:{path}"],
        ))

    # blast_radius
    fan_out = _module_fan_out(conn, project_id, module) if module else 0
    module_files = len(siblings) if module else 1
    if module:
        normalized = _clamp(math.log2(max(1, fan_out)) * 10 + module_files * 2.0)
        factors.append(_factor_item(
            "blast_radius",
            normalized=normalized,
            raw_signal={"module_files": module_files, "module_fan_out_tokens": fan_out},
            available=True,
            rationale=f"Module has {module_files} file(s); import-graph breadth signal={fan_out}.",
            evidence=[f"module:{module}"],
        ))
    else:
        factors.append(_factor_item(
            "blast_radius",
            normalized=None,
            raw_signal={"module": None},
            available=False,
            rationale="File has no known module; blast radius cannot be estimated.",
            evidence=[],
        ))

    # novelty_recency
    earliest = _earliest_commit_ts_for_file(conn, project_id, path)
    if earliest is not None:
        age_days = max(0.0, (now_ts - earliest) / 86400.0)
        # younger files score higher; linearly decays over 180 days
        normalized = _clamp((1.0 - min(1.0, age_days / 180.0)) * 100.0)
        factors.append(_factor_item(
            "novelty_recency",
            normalized=normalized,
            raw_signal={"age_days": round(age_days, 1), "first_seen_ts": earliest},
            available=True,
            rationale=f"File first appeared in history {age_days:.0f} day(s) ago.",
            evidence=[f"file:{path}"],
        ))
    else:
        factors.append(_factor_item(
            "novelty_recency",
            normalized=None,
            raw_signal={"first_seen_ts": None},
            available=False,
            rationale="No commit history found for this file.",
            evidence=[],
        ))

    return factors, evidence_index


def _compose_score(factors: list[dict[str, Any]]) -> tuple[float, float]:
    available_weight = 0.0
    weighted_sum = 0.0
    for factor in factors:
        if not factor["signal_available"]:
            continue
        available_weight += factor["weight"]
        weighted_sum += factor["weighted_contribution"]
    if available_weight <= 0:
        return 0.0, 0.0
    normalized_score = _clamp(weighted_sum / available_weight, 0.0, 100.0)
    coverage = available_weight  # weights already sum to 1.0 for the full set
    return round(normalized_score, 2), round(coverage, 3)


def _breakdown_skeleton(scope_kind: str, scope_id: str, generated_at: str, project_name: str) -> dict[str, Any]:
    return {
        "meta": {
            "project": project_name,
            "generated_at": generated_at,
            "contract_version": CONTRACT_VERSION,
            "scope_kind": scope_kind,
            "scope_id": scope_id,
        },
        "score": {
            "value": 0.0,
            "severity": "low",
            "confidence": "low",
            "signal_coverage": 0.0,
        },
        "factor_breakdown": [],
        "evidence_index": [],
        "notes": [],
    }


def _project_name(conn, project_id: int) -> str:
    row = conn.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
    return str(row[0]) if row and row[0] else f"project-{project_id}"


def _aggregate_module_from_files(conn, project_id: int, module: str, files: list[str], generated_at: str, lookback_days: int, now_ts: float) -> dict[str, Any]:
    per_file_breakdowns = []
    combined_factors: dict[str, dict[str, Any]] = {}
    combined_evidence: list[dict[str, Any]] = []

    for path in files:
        factors, evidence_index = _build_file_factors(conn, project_id, path, lookback_days=lookback_days, now_ts=now_ts)
        file_score, _ = _compose_score(factors)
        per_file_breakdowns.append({"path": path, "score": file_score, "severity": _severity_for(file_score)})
        for ev in evidence_index:
            _append_evidence(combined_evidence, ev)
        for factor in factors:
            bucket = combined_factors.setdefault(factor["factor_id"], {
                "factor_id": factor["factor_id"],
                "label": factor["label"],
                "weight": factor["weight"],
                "raw_signal": {"per_file": []},
                "normalized_contribution": 0.0,
                "weighted_contribution": 0.0,
                "signal_available": False,
                "rationale": factor["rationale"],
                "evidence": list(factor["evidence"]),
                "_samples": 0,
                "_sum_normalized": 0.0,
            })
            bucket["raw_signal"]["per_file"].append({"path": path, "raw_signal": factor["raw_signal"], "available": factor["signal_available"]})
            if factor["signal_available"]:
                bucket["_samples"] += 1
                bucket["_sum_normalized"] += factor["normalized_contribution"] or 0.0
                bucket["signal_available"] = True
                for ev_id in factor["evidence"]:
                    if ev_id not in bucket["evidence"]:
                        bucket["evidence"].append(ev_id)

    factor_list = []
    for factor_id in FACTOR_WEIGHT:
        bucket = combined_factors.get(factor_id)
        if not bucket:
            factor_list.append(_factor_item(
                factor_id,
                normalized=None,
                raw_signal={"per_file": []},
                available=False,
                rationale="No file data for this factor in the module.",
                evidence=[],
            ))
            continue
        samples = bucket.pop("_samples")
        sum_norm = bucket.pop("_sum_normalized")
        if samples > 0:
            normalized = _clamp(sum_norm / samples)
            bucket["normalized_contribution"] = round(normalized, 2)
            bucket["weighted_contribution"] = round(bucket["weight"] * normalized, 4)
            bucket["rationale"] = f"Averaged across {samples} file(s) in the module."
        else:
            bucket["normalized_contribution"] = None
            bucket["weighted_contribution"] = 0.0
        factor_list.append(bucket)

    score_value, coverage = _compose_score(factor_list)
    breakdown = _breakdown_skeleton("module", module, generated_at, _project_name(conn, project_id))
    breakdown["score"] = {
        "value": score_value,
        "severity": _severity_for(score_value),
        "confidence": _confidence_for(coverage),
        "signal_coverage": coverage,
    }
    breakdown["factor_breakdown"] = factor_list
    breakdown["evidence_index"] = combined_evidence
    breakdown["notes"] = [{"kind": "module_file_scores", "items": per_file_breakdowns}]
    return breakdown


def build_debt_breakdown(
    conn,
    project_id: int,
    scope_kind: str,
    scope_id: str,
    *,
    lookback_days: int = 30,
    now_ts: float | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if scope_kind not in {"file", "module", "project"}:
        raise ValueError(f"unsupported scope_kind: {scope_kind}")
    if scope_kind in {"file", "module"} and not scope_id:
        raise ValueError("scope_id required for file and module scopes")

    now_ts = now_ts if now_ts is not None else _now_ts()
    generated_at = generated_at or datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    project_name = _project_name(conn, project_id)

    if scope_kind == "file":
        factors, evidence = _build_file_factors(conn, project_id, scope_id, lookback_days=lookback_days, now_ts=now_ts)
        score_value, coverage = _compose_score(factors)
        breakdown = _breakdown_skeleton("file", scope_id, generated_at, project_name)
        breakdown["score"] = {
            "value": score_value,
            "severity": _severity_for(score_value),
            "confidence": _confidence_for(coverage),
            "signal_coverage": coverage,
        }
        breakdown["factor_breakdown"] = factors
        breakdown["evidence_index"] = evidence
        return breakdown

    if scope_kind == "module":
        files = _files_in_module(conn, project_id, scope_id)
        if not files:
            raise ValueError(f"module_not_found:{scope_id}")
        return _aggregate_module_from_files(conn, project_id, scope_id, files, generated_at, lookback_days, now_ts)

    # project scope: mean of module scores + include per-module summary
    modules = _all_modules(conn, project_id)
    per_module_scores: list[dict[str, Any]] = []
    sum_score = 0.0
    total_weight = 0.0
    for module in modules:
        module_breakdown = build_debt_breakdown(
            conn,
            project_id,
            "module",
            module,
            lookback_days=lookback_days,
            now_ts=now_ts,
            generated_at=generated_at,
        )
        per_module_scores.append({
            "module": module,
            "score": module_breakdown["score"]["value"],
            "severity": module_breakdown["score"]["severity"],
        })
        weight = max(1, len(_files_in_module(conn, project_id, module)))
        sum_score += module_breakdown["score"]["value"] * weight
        total_weight += weight

    project_score = round(sum_score / total_weight, 2) if total_weight else 0.0
    breakdown = _breakdown_skeleton("project", project_name, generated_at, project_name)
    breakdown["score"] = {
        "value": project_score,
        "severity": _severity_for(project_score),
        "confidence": _confidence_for(1.0 if modules else 0.0),
        "signal_coverage": 1.0 if modules else 0.0,
    }
    # Project-level breakdown: surface factor-weight-only list so UI can still enumerate factors.
    breakdown["factor_breakdown"] = [
        {
            "factor_id": f["id"],
            "label": f["label"],
            "weight": f["weight"],
            "raw_signal": None,
            "normalized_contribution": None,
            "weighted_contribution": 0.0,
            "signal_available": False,
            "rationale": "Project scope does not compute per-factor breakdowns; see per-module.",
            "evidence": [],
        }
        for f in COGNITIVE_DEBT_FACTORS
    ]
    breakdown["notes"] = [{"kind": "module_scores", "items": per_module_scores}]
    return breakdown


def quick_debt_signal(conn, project_id: int, path: str) -> dict[str, Any] | None:
    """Return a cheap debt summary for ``path`` without running the full breakdown.

    Suitable for integration callers (Reacquaintance, Ask Project) that only need
    to know "is this file dark, and roughly why" to adjust prioritization.
    """
    row = conn.execute(
        "SELECT cognitive_debt, agent_line_ratio, last_human_ts FROM analysis_file_insights WHERE project_id=? AND path=?",
        (project_id, path),
    ).fetchone()
    if not row:
        return None
    value = float(row[0] or 0.0)
    agent_ratio = row[1]
    last_human_ts = row[2]
    primary_signal: str | None = None
    if agent_ratio is not None and float(agent_ratio) >= 0.5:
        primary_signal = "agent_authored_ratio"
    elif last_human_ts is None and value >= 40:
        primary_signal = "review_staleness"
    return {
        "value": round(value, 2),
        "severity": _severity_for(value),
        "primary_signal": primary_signal,
    }


def breakdown_fingerprint(breakdown: dict[str, Any]) -> str:
    """Deterministic fingerprint across scope + factor contributions (useful for caching / diffing)."""
    meta = breakdown.get("meta") or {}
    payload = {
        "scope_kind": meta.get("scope_kind"),
        "scope_id": meta.get("scope_id"),
        "generated_at": meta.get("generated_at"),
        "factors": sorted(
            [
                (f.get("factor_id"), f.get("weighted_contribution"), f.get("signal_available"))
                for f in breakdown.get("factor_breakdown") or []
            ]
        ),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
