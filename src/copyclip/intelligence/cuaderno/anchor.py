from __future__ import annotations

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


def get_module_graph(
    conn: sqlite3.Connection,
    project_id: int,
    scope: str = "",
    max_modules: int = 50,
    max_edges: int = 80,
) -> dict[str, Any]:
    """Module-level topology aggregated from symbol_edges — both endpoints live
    in the symbols.module namespace, so every node maps to a real file (citation)
    and stdlib/external import targets never appear.

    `scope` is a FOCUS, not an induced-subgraph filter: it selects the modules
    matching the substring — by module name OR by a backing file path, so
    'analyzer' resolves the module whose file is analyzer.py even when that module
    is named after the parent directory — and returns them PLUS their direct
    neighbors and the edges incident to the focus (an ego graph, radius 1). This
    is what answers 'the graph around X'; an empty scope returns the whole
    project. Deterministic caps: focus modules rank first (never pruned out for a
    higher-degree neighbor), then degree DESC then name ASC; edges pruned to
    surviving nodes, then capped by weight DESC."""
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
    files = dict(
        conn.execute(
            "SELECT module, MIN(file_path) FROM symbols "
            "WHERE project_id=? AND module IS NOT NULL GROUP BY module",
            (project_id,),
        ).fetchall()
    )
    all_mods = set(files)

    focus: set[str] = set()
    if scope:
        focus = {m for m in all_mods if scope in m}
        # Resolve via backing file paths too: a file like analyzer.py lives in a
        # module named after its parent directory, so a name-only match misses it.
        for (m,) in conn.execute(
            "SELECT DISTINCT module FROM symbols "
            "WHERE project_id=? AND module IS NOT NULL AND file_path LIKE ?",
            (project_id, f"%{scope}%"),
        ):
            if m in all_mods:
                focus.add(m)
        if not focus:
            return {"modules": [], "edges": [], "truncated": False}
        # Ego graph: edges incident to a focus module, plus the nodes they reach.
        edges = [(f, t, w) for (f, t, w) in rows if f in focus or t in focus]
        nodes = set(focus)
        for f, t, w in edges:
            nodes.add(f)
            nodes.add(t)
        nodes &= all_mods
    else:
        nodes = set(all_mods)
        edges = [(f, t, w) for (f, t, w) in rows if f in nodes and t in nodes]

    degree: dict[str, int] = {}
    for f, t, w in edges:
        degree[f] = degree.get(f, 0) + 1
        degree[t] = degree.get(t, 0) + 1
    ranked = sorted(nodes, key=lambda m: (m not in focus, -degree.get(m, 0), m))
    truncated = len(ranked) > max_modules
    keep = set(ranked[:max_modules])
    pruned = [(f, t, w) for (f, t, w) in edges if f in keep and t in keep]
    pruned.sort(key=lambda e: (-e[2], e[0], e[1]))
    if len(pruned) > max_edges:
        truncated = True
        pruned = pruned[:max_edges]
    return {
        "modules": [{"name": m, "file_path": files[m]} for m in sorted(keep)],
        "edges": [{"from": f, "to": t, "weight": w} for (f, t, w) in pruned],
        "truncated": truncated,
    }


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
