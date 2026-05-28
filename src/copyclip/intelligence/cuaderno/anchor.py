from __future__ import annotations

import os
import sqlite3
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
    params.append(int(limit))

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
