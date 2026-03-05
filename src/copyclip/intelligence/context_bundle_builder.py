import re
from collections import defaultdict
from typing import Dict, List


def _terms(text: str) -> List[str]:
    return [
        t
        for t in re.findall(r"[a-zA-Z0-9_\-]{3,}", (text or "").lower())
        if t not in {"the", "and", "for", "with", "that", "this", "what", "how", "about"}
    ]


def build_context_bundle(conn, project_id: int, question: str, max_files: int = 20) -> Dict:
    """Build deterministic compact file bundle + explainable manifest.

    Selection signals:
    - direct term match in file path
    - high-risk files
    - high-churn files
    - decision refs to files
    """
    terms = _terms(question)

    scores = defaultdict(int)
    reasons = defaultdict(list)

    # Path/term matching from indexed files.
    for row in conn.execute("SELECT path FROM files WHERE project_id=?", (project_id,)).fetchall():
        path = row[0]
        path_l = (path or "").lower()
        hits = sum(1 for t in terms if t in path_l)
        if hits > 0:
            scores[path] += hits * 20
            reasons[path].append(f"term-match:{hits}")

    # Risk-driven selection.
    for row in conn.execute(
        "SELECT area, score, kind FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 60",
        (project_id,),
    ).fetchall():
        area, score, kind = row[0], int(row[1] or 0), row[2]
        if not area:
            continue
        scores[area] += min(score, 100)
        reasons[area].append(f"risk:{kind}:{score}")

    # Churn-driven selection.
    for row in conn.execute(
        "SELECT file_path, COUNT(*) AS c FROM file_changes WHERE project_id=? GROUP BY file_path ORDER BY c DESC LIMIT 60",
        (project_id,),
    ).fetchall():
        fpath, cnt = row[0], int(row[1] or 0)
        if not fpath:
            continue
        scores[fpath] += min(cnt * 8, 80)
        reasons[fpath].append(f"churn:{cnt}")

    # Decision references to files.
    for row in conn.execute(
        """
        SELECT dr.ref_value
        FROM decisions d
        JOIN decision_refs dr ON dr.decision_id = d.id
        WHERE d.project_id=? AND d.status IN ('accepted','resolved') AND dr.ref_type='file'
        ORDER BY d.id DESC
        LIMIT 60
        """,
        (project_id,),
    ).fetchall():
        fpath = row[0]
        if not fpath:
            continue
        scores[fpath] += 35
        reasons[fpath].append("decision-ref")

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    selected = [p for p, _ in ranked[: max(1, int(max_files or 20))]]

    manifest = [
        {
            "path": p,
            "score": int(scores[p]),
            "reasons": sorted(set(reasons[p])),
        }
        for p in selected
    ]

    return {
        "query_terms": terms,
        "selected_files": selected,
        "manifest": manifest,
        "total_candidates": len(ranked),
    }
