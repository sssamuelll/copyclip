from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional


def _safe_resolve(project_root: str, rel_path: str) -> Optional[Path]:
    """Resolve a project-relative path; return None if it escapes the root."""
    root = Path(project_root).resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def read_file(
    project_root: str,
    path: str,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
) -> dict[str, Any]:
    """Read a project file with optional line range. Returns POSIX-style path."""
    resolved = _safe_resolve(project_root, path)
    if resolved is None:
        return {"error": "path_outside_root"}
    if not resolved.exists() or not resolved.is_file():
        return {"error": "file_not_found", "path": path}
    try:
        raw = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": "read_failed", "path": path, "detail": str(exc)}
    lines = raw.splitlines()
    if line_start is None and line_end is None:
        sliced = list(enumerate(lines, start=1))
    else:
        start = max(1, int(line_start or 1))
        end = min(len(lines), int(line_end or len(lines)))
        sliced = [(i + 1, lines[i]) for i in range(start - 1, end)]
    return {
        "path": path,
        "lines": [{"n": n, "text": text} for n, text in sliced],
    }


# Directories that only add noise when orienting in a project tree.
_NOISE_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".copyclip", ".next", ".turbo", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "target", "coverage", ".idea", ".vscode",
})


def list_dir(project_root: str, path: str = ".", limit: int = 200) -> dict[str, Any]:
    """List a project-relative directory's entries (dirs first, then files,
    alpha within each). Skips noise dirs. Use this to orient before reading."""
    resolved = _safe_resolve(project_root, path)
    if resolved is None:
        return {"error": "path_outside_root"}
    if not resolved.exists() or not resolved.is_dir():
        return {"error": "not_a_directory", "path": path}
    dirs: list[str] = []
    files: list[str] = []
    try:
        for entry in resolved.iterdir():
            name = entry.name
            if entry.is_dir():
                if name in _NOISE_DIRS:
                    continue
                dirs.append(name)
            else:
                files.append(name)
    except OSError as exc:
        return {"error": "read_failed", "path": path, "detail": str(exc)}
    entries = (
        [{"name": n, "type": "dir"} for n in sorted(dirs)]
        + [{"name": n, "type": "file"} for n in sorted(files)]
    )
    return {"path": path, "entries": entries[: max(1, int(limit or 200))]}


def grep_symbols(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    file: Optional[str] = None,
    module: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    where = ["project_id = ?"]
    params: list[Any] = [project_id]
    if name:
        where.append("name = ?")
        params.append(name)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if file:
        where.append("file_path = ?")
        params.append(file.replace("\\", "/"))
    if module:
        where.append("module = ?")
        params.append(module)
    params.append(min(int(limit or 50), 200))

    sql = (
        "SELECT name, kind, file_path, line_start, line_end, module "
        "FROM symbols WHERE " + " AND ".join(where) +
        " ORDER BY file_path, line_start LIMIT ?"
    )
    rows = conn.execute(sql, params).fetchall()
    return {
        "symbols": [
            {
                "name": r[0],
                "kind": r[1],
                "file_path": r[2],
                "line_start": r[3],
                "line_end": r[4],
                "module": r[5],
            }
            for r in rows
        ]
    }


def get_callers(
    conn: sqlite3.Connection, project_id: int, symbol_name: str
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.name, s.kind, s.file_path, s.line_start
        FROM symbol_edges e
        JOIN symbols s_to ON e.to_symbol_id = s_to.id
        JOIN symbols s    ON e.from_symbol_id = s.id
        WHERE e.project_id=? AND s_to.name=? AND e.edge_type='calls'
        ORDER BY s.file_path, s.line_start
        """,
        (project_id, symbol_name),
    ).fetchall()
    return {
        "callers": [
            {"name": r[0], "kind": r[1], "file_path": r[2], "line_start": r[3]}
            for r in rows
        ]
    }


def get_callees(
    conn: sqlite3.Connection, project_id: int, symbol_name: str
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.name, s.kind, s.file_path, s.line_start
        FROM symbol_edges e
        JOIN symbols s_from ON e.from_symbol_id = s_from.id
        JOIN symbols s      ON e.to_symbol_id = s.id
        WHERE e.project_id=? AND s_from.name=? AND e.edge_type='calls'
        ORDER BY s.file_path, s.line_start
        """,
        (project_id, symbol_name),
    ).fetchall()
    return {
        "callees": [
            {"name": r[0], "kind": r[1], "file_path": r[2], "line_start": r[3]}
            for r in rows
        ]
    }


def get_decisions(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    status: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Read the decision-ledger (decisions table). Optionally filter by status.
    Absorbs the Decisions/Planning pages: the data is the ledger, cited by id."""
    where = ["project_id = ?"]
    params: list[Any] = [project_id]
    if status:
        where.append("status = ?")
        params.append(status)
    params.append(min(int(limit or 50), 200))
    sql = (
        "SELECT id, title, summary, status, confidence, source_type, created_at, resolved_at "
        "FROM decisions WHERE " + " AND ".join(where) +
        " ORDER BY id DESC LIMIT ?"
    )
    rows = conn.execute(sql, params).fetchall()
    return {
        "decisions": [
            {
                "id": r[0],
                "title": r[1],
                "summary": r[2],
                "status": r[3],
                "confidence": r[4],
                "source_type": r[5],
                "created_at": r[6],
                "resolved_at": r[7],
            }
            for r in rows
        ]
    }


def get_risks(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    kind: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Read the risk signals (risks table), highest score first. Each row is a
    deterministic heuristic over real git data, citable by `area` (file path) —
    absorbs the Risks page as cited callout blocks, never fabricated severity."""
    where = ["project_id = ?"]
    params: list[Any] = [project_id]
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if severity:
        where.append("severity = ?")
        params.append(severity)
    params.append(min(int(limit or 50), 200))
    sql = (
        "SELECT area, severity, kind, rationale, score, created_at "
        "FROM risks WHERE " + " AND ".join(where) +
        " ORDER BY score DESC, area ASC LIMIT ?"
    )
    rows = conn.execute(sql, params).fetchall()
    return {
        "risks": [
            {
                "area": r[0],
                # `area` is a file path; expose it as file_path too so the
                # honesty ledger harvests it as tool-evidenced (citable).
                "file_path": r[0],
                "severity": r[1],
                "kind": r[2],
                "rationale": r[3],
                "score": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]
    }


def get_last_contact(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Read the Pulso 'Last contact' readings — files an AI burst last shaped that
    the human has NOT returned to, longest gap first. Reads the persisted
    `pulso_last_contact_days` (never the dead blame column). Silent files (no AI
    burst, or the human already returned) are absent, not zero. Each row is
    citable by `file_path`.

    Recency only: this proves elapsed time since the human's last touch, NOT that
    the human understands the code. A timestamp cannot witness comprehension."""
    from ..pulso import build_last_contact

    rows = conn.execute(
        "SELECT path, pulso_last_contact_days FROM analysis_file_insights "
        "WHERE project_id = ? AND pulso_last_contact_days IS NOT NULL "
        "ORDER BY pulso_last_contact_days DESC, path ASC LIMIT ?",
        (project_id, min(int(limit or 20), 200)),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for path, days in rows:
        detail = build_last_contact(conn, project_id, path)
        items.append({
            "file_path": path,
            "last_contact_days": days,
            "ai_burst_days": detail["ai_burst_days"] if detail else None,
            "never_human_touched": detail["never_human_touched"] if detail else None,
        })
    return {"last_contact": items}


def _parse_json_or_none(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def get_story_snapshots(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Read narrative snapshots (story_snapshots) newest-first — the connective
    tissue between bursts. If analysis hasn't run there are none; say so
    explicitly (never invent a narrative — degrade to git_log)."""
    rows = conn.execute(
        "SELECT generated_at, focus_areas_json, major_changes_json, "
        "open_questions_json, summary_json FROM story_snapshots "
        "WHERE project_id=? ORDER BY id DESC LIMIT ?",
        (project_id, min(int(limit or 5), 50)),
    ).fetchall()
    if not rows:
        return {
            "snapshots": [],
            "note": "no story snapshots yet — run `copyclip analyze`, or use git_log for raw history.",
        }
    return {
        "snapshots": [
            {
                "generated_at": r[0],
                "focus_areas": _parse_json_or_none(r[1]),
                "major_changes": _parse_json_or_none(r[2]),
                "open_questions": _parse_json_or_none(r[3]),
                "summary": _parse_json_or_none(r[4]),
            }
            for r in rows
        ]
    }


def get_reverse_dependents(
    conn: sqlite3.Connection,
    project_id: int,
    path: str,
) -> dict[str, Any]:
    """Modules transitively impacted if `path` changes (reverse-dependents).
    Resolves path→module (most specific prefix wins), then walks `dependencies`
    upward. The target is excluded from its own impact set. Cycle-safe."""
    norm = path.replace("\\", "/")
    row = conn.execute(
        "SELECT name FROM modules WHERE project_id=? AND ? LIKE path_prefix || '%' "
        "ORDER BY LENGTH(path_prefix) DESC LIMIT 1",
        (project_id, norm),
    ).fetchone()
    if not row:
        return {"target_module": "unknown", "impacted_modules": []}
    target_module = row[0]
    dependents: set[str] = set()
    to_visit = [target_module]
    visited: set[str] = set()
    while to_visit:
        curr = to_visit.pop()
        if curr in visited:
            continue
        visited.add(curr)
        rows = conn.execute(
            "SELECT from_module FROM dependencies WHERE project_id=? AND to_module=?",
            (project_id, curr),
        ).fetchall()
        for (frm,) in rows:
            dependents.add(frm)
            to_visit.append(frm)
    dependents.discard(target_module)
    return {"target_module": target_module, "impacted_modules": sorted(dependents)}


def _run_git(project_root: str, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def git_log(
    project_root: str, path: Optional[str] = None, limit: int = 20
) -> dict[str, Any]:
    args = ["log", f"-n{int(limit)}", "--pretty=format:%H%x09%an%x09%ai%x09%s"]
    if path:
        args += ["--", path]
    code, out, err = _run_git(project_root, *args)
    if code != 0:
        return {"error": "git_failed", "detail": err.strip()}
    commits = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            sha, author, when, msg = parts
            commits.append(
                {"commit": sha[:12], "author": author, "when": when, "message": msg}
            )
    return {"commits": commits}


def git_blame(
    project_root: str, path: str, line_start: int, line_end: int
) -> dict[str, Any]:
    code, out, err = _run_git(
        project_root,
        "blame",
        f"-L{int(line_start)},{int(line_end)}",
        "--porcelain",
        "--",
        path,
    )
    if code != 0:
        return {"error": "git_failed", "detail": err.strip()}
    blame_entries: list[dict[str, Any]] = []
    # Git's --porcelain emits the full header (author, author-time, ...) only
    # the FIRST time a SHA appears. Subsequent occurrences of the same SHA
    # emit only the SHA-line + `\tcontent`. Cache per-SHA so reappearances
    # restore the correct author/when.
    sha_meta: dict[str, dict[str, Optional[str]]] = {}
    current_sha: Optional[str] = None
    for line in out.splitlines():
        if not line:
            continue
        if line.startswith("\t"):
            meta = sha_meta.get(current_sha or "", {})
            blame_entries.append(
                {
                    "commit": (current_sha or "")[:12],
                    "author": meta.get("author"),
                    "when": meta.get("when"),
                }
            )
            continue
        head = line.split(" ", 1)[0]
        if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
            current_sha = head
            sha_meta.setdefault(current_sha, {"author": None, "when": None})
        elif line.startswith("author ") and current_sha is not None:
            sha_meta[current_sha]["author"] = line[7:]
        elif line.startswith("author-time ") and current_sha is not None:
            sha_meta[current_sha]["when"] = line[len("author-time "):]
    return {"blame": blame_entries}


def git_diff(project_root: str, commit_sha: str, path: Optional[str] = None) -> dict[str, Any]:
    args = ["show", "--pretty=format:%H%n%an%n%ai%n%s", "--no-color", commit_sha]
    if path:
        args += ["--", path]
    code, out, err = _run_git(project_root, *args)
    if code != 0:
        return {"error": "git_failed", "detail": err.strip()}
    return {"diff": out}


def git_archaeology(
    project_root: str,
    conn: sqlite3.Connection,
    project_id: int,
    file: str,
    limit: int = 12,
) -> dict[str, Any]:
    """A file's commit history crossed with the decisions that reference it
    (decision_refs). The commit↔decision correlation that no git_* tool alone
    has — connects 'what changed here' to 'which decision you made about it'."""
    norm = file.replace("\\", "/")
    code, out, _ = _run_git(
        project_root, "log",
        "--pretty=format:%H%x09%an%x09%ad%x09%s", "--date=iso",
        f"-n{int(limit)}", "--", norm,
    )
    commits: list[dict[str, Any]] = []
    if code == 0:
        for line in out.splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                sha, author, date, message = parts
                commits.append({"sha": sha, "author": author, "date": date, "message": message})

    rows = conn.execute(
        """
        SELECT d.id, d.title, d.status, d.source_type, dr.ref_type, dr.ref_value
        FROM decisions d
        LEFT JOIN decision_refs dr ON dr.decision_id = d.id
        WHERE d.project_id=?
        ORDER BY d.id DESC
        """,
        (project_id,),
    ).fetchall()
    related: dict[int, dict[str, Any]] = {}
    for did, title, status, source_type, ref_type, ref_value in rows:
        ref_value = ref_value or ""
        match = (
            (ref_type == "file" and ref_value == norm)
            or (ref_type == "commit" and ref_value and any(c["sha"].startswith(ref_value) for c in commits))
            or (ref_type == "doc" and norm.lower() in ref_value.lower())
        )
        if match:
            entry = related.setdefault(did, {
                "id": did, "title": title, "status": status,
                "source_type": source_type, "matched_refs": [],
            })
            entry["matched_refs"].append({"ref_type": ref_type, "ref_value": ref_value})
    return {"file": norm, "commits": commits, "related_decisions": list(related.values())}


def _rank_and_cap(
    nodes: set[str],
    edges: list[tuple[str, str, int]],
    node_file: dict[str, str],
    focus: set[str],
    max_nodes: int,
    max_edges: int,
) -> dict[str, Any]:
    """Shared ego-graph finishing: focus nodes rank first (never pruned out for a
    higher-degree neighbor), then degree DESC then name ASC; edges pruned to
    surviving nodes, then capped by weight DESC. Each node carries its citation
    file from node_file."""
    degree: dict[str, int] = {}
    for f, t, w in edges:
        degree[f] = degree.get(f, 0) + 1
        degree[t] = degree.get(t, 0) + 1
    ranked = sorted(nodes, key=lambda m: (m not in focus, -degree.get(m, 0), m))
    truncated = len(ranked) > max_nodes
    keep = set(ranked[:max_nodes])
    pruned = [(f, t, w) for (f, t, w) in edges if f in keep and t in keep]
    pruned.sort(key=lambda e: (-e[2], e[0], e[1]))
    if len(pruned) > max_edges:
        truncated = True
        pruned = pruned[:max_edges]
    return {
        "modules": [{"name": m, "file_path": node_file[m]} for m in sorted(keep)],
        "edges": [{"from": f, "to": t, "weight": w} for (f, t, w) in pruned],
        "truncated": truncated,
    }


def _module_citation_files(
    conn: sqlite3.Connection, project_id: int
) -> dict[str, str]:
    """Per module, the file it cites. A module is a SET; its citation must be a
    chosen representative, and the honest representative is the module's MAX-debt
    file — so the fog painted on the node is re-derivable by opening the very file
    the node cites (one referent). When no file in the module has been analyzed,
    fall back to MIN(file_path) (the prior, arbitrary-but-stable representative)
    and let _attach_debt mark the score as a typed unknown."""
    rows = conn.execute(
        """
        SELECT DISTINCT s.module, s.file_path, afi.cognitive_debt
        FROM symbols s
        LEFT JOIN analysis_file_insights afi
          ON afi.project_id = s.project_id AND afi.path = s.file_path
        WHERE s.project_id=? AND s.module IS NOT NULL
        """,
        (project_id,),
    ).fetchall()
    by_mod: dict[str, list[tuple[str, Optional[float]]]] = {}
    for module, file_path, debt in rows:
        by_mod.setdefault(module, []).append((file_path, debt))
    citation: dict[str, str] = {}
    for module, files in by_mod.items():
        analyzed = [(fp, d) for fp, d in files if d is not None]
        if analyzed:
            # highest debt wins; ties broken by path for determinism
            citation[module] = sorted(analyzed, key=lambda x: (-x[1], x[0]))[0][0]
        else:
            citation[module] = min(fp for fp, _ in files)
    return citation


def _directory_graph(
    conn: sqlite3.Connection, project_id: int, max_nodes: int, max_edges: int
) -> dict[str, Any]:
    """Whole-project overview at DIRECTORY granularity: a node is a module
    (a directory), the right altitude for 'show me the project'."""
    rows = conn.execute(
        """
        SELECT s1.module, s2.module, COUNT(*) AS weight
        FROM symbol_edges e
        JOIN symbols s1 ON e.from_symbol_id = s1.id
        JOIN symbols s2 ON e.to_symbol_id = s2.id
        WHERE e.project_id=? AND s1.module IS NOT NULL AND s2.module IS NOT NULL
              AND s1.module != s2.module
        GROUP BY s1.module, s2.module
        """,
        (project_id,),
    ).fetchall()
    files = _module_citation_files(conn, project_id)
    nodes = set(files)
    edges = [(f, t, w) for (f, t, w) in rows if f in nodes and t in nodes]
    return _rank_and_cap(nodes, edges, files, set(), max_nodes, max_edges)


def _file_graph(
    conn: sqlite3.Connection, project_id: int, scope: str, max_nodes: int, max_edges: int
) -> dict[str, Any]:
    """Focused ego graph at FILE granularity: a node is a file, cited as itself,
    so the thing the user names ('the analyzer' = analyzer.py) is a node — not a
    directory it dissolves into. The focus resolves by file path OR symbol name,
    so 'around X' works whether X is a file or a function the user remembers."""
    rows = conn.execute(
        """
        SELECT s1.file_path, s2.file_path, COUNT(*) AS weight
        FROM symbol_edges e
        JOIN symbols s1 ON e.from_symbol_id = s1.id
        JOIN symbols s2 ON e.to_symbol_id = s2.id
        WHERE e.project_id=? AND s1.file_path IS NOT NULL AND s2.file_path IS NOT NULL
              AND s1.file_path != s2.file_path
        GROUP BY s1.file_path, s2.file_path
        """,
        (project_id,),
    ).fetchall()
    focus = {
        fp
        for (fp,) in conn.execute(
            "SELECT DISTINCT file_path FROM symbols "
            "WHERE project_id=? AND file_path IS NOT NULL "
            "AND (file_path LIKE ? OR name LIKE ?)",
            (project_id, f"%{scope}%", f"%{scope}%"),
        )
    }
    if not focus:
        return {"modules": [], "edges": [], "truncated": False}
    edges = [(f, t, w) for (f, t, w) in rows if f in focus or t in focus]
    nodes = set(focus)
    for f, t, w in edges:
        nodes.add(f)
        nodes.add(t)
    node_file = {n: n for n in nodes}  # a file node cites itself, never a sibling
    return _rank_and_cap(nodes, edges, node_file, focus, max_nodes, max_edges)


def _attach_debt(
    conn: sqlite3.Connection, project_id: int, result: dict[str, Any]
) -> dict[str, Any]:
    """Attach each node's `heat` from analysis_file_insights, keyed by the node's
    own citation file (file_path). Heat is the live composite (maintenance
    pressure: churn/decisions/tests), re-derivable from the same row the node
    cites — one referent, one query. A file with no analysis row gets a TYPED
    UNKNOWN (None), never 0: absence of measurement must never read as low heat."""
    modules = result.get("modules") or []
    if not modules:
        return result
    debt = dict(
        conn.execute(
            "SELECT path, cognitive_debt FROM analysis_file_insights WHERE project_id=?",
            (project_id,),
        ).fetchall()
    )
    for m in modules:
        m["heat"] = debt.get(m["file_path"])
    return result


def get_module_graph(
    conn: sqlite3.Connection,
    project_id: int,
    scope: str = "",
    max_modules: int = 50,
    max_edges: int = 80,
) -> dict[str, Any]:
    """Dependency topology aggregated from symbol_edges; nodes map to real files
    (citations) and stdlib/external targets never appear.

    Granularity follows intent: an empty `scope` returns the WHOLE PROJECT at
    DIRECTORY granularity (a node is a module/folder — the right altitude for an
    overview). A non-empty `scope` is a FOCUS that drops to FILE granularity — it
    returns the file the user named (resolved by file path OR symbol name) as a
    node cited as itself, PLUS its direct-import neighbors (an ego graph, radius
    1). This is what makes 'the graph around analyzer.py' nameable: the file is a
    node, not a directory it dissolves into."""
    if scope:
        result = _file_graph(conn, project_id, scope, max_modules, max_edges)
    else:
        result = _directory_graph(conn, project_id, max_modules, max_edges)
    return _attach_debt(conn, project_id, result)


def find_tests(project_root: str, symbol_name: str) -> dict[str, Any]:
    """Scan tests/ directory for files mentioning the symbol name."""
    root = Path(project_root).resolve()
    tests_dir = root / "tests"
    if not tests_dir.exists() or not tests_dir.is_dir():
        return {"tests": []}
    pattern = re.compile(r"\b" + re.escape(symbol_name) + r"\b")
    results: list[dict[str, Any]] = []
    for fp in tests_dir.rglob("*.py"):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = []
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append({"line": i, "text": line.rstrip()})
        if matches:
            rel = str(fp.relative_to(root)).replace("\\", "/")
            results.append({"file_path": rel, "matches": matches[:5]})
    return {"tests": results}


def get_reacquaintance_briefing(
    project_root: str,
    mode: str = "last_seen",
    window: str = "7d",
    checkpoint: Optional[str] = None,
) -> dict[str, Any]:
    """Re-entry briefing — what to re-read to reconnect to your intention after
    a gap between bursts. Wraps the reacquaintance engine and trims the heavy
    evidence_index so the briefing fits the tutor's context window (decision A2).
    Lazy import: the engine pulls in mempalace/analysis machinery we don't want
    loaded for the lighter tools."""
    from ..reacquaintance import build_reacquaintance_briefing

    briefing = build_reacquaintance_briefing(
        project_root, baseline_mode=mode, window=window, checkpoint_name=checkpoint
    )
    if isinstance(briefing, dict):
        briefing.pop("evidence_index", None)
    return briefing
