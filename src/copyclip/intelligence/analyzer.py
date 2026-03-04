import hashlib
import os
import subprocess
from pathlib import Path
from typing import Dict, List

from .db import connect, init_schema


def _lang_from_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".md": "markdown",
        ".json": "json",
        ".css": "css",
        ".html": "html",
    }.get(ext, "other")


def _hash_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_git(project_root: str, args: List[str]) -> str:
    try:
        out = subprocess.check_output(["git", "-C", project_root, *args], text=True)
        return out.strip()
    except Exception:
        return ""


def analyze(project_root: str) -> Dict[str, int]:
    root = os.path.abspath(project_root)
    conn = connect(root)
    init_schema(conn)

    name = os.path.basename(root)
    conn.execute(
        "INSERT INTO projects(root_path,name,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(root_path) DO UPDATE SET name=excluded.name, updated_at=CURRENT_TIMESTAMP",
        (root, name),
    )
    project_id = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0]

    # full refresh for v1 skeleton
    conn.execute("DELETE FROM files WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM commits WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM file_changes WHERE project_id=?", (project_id,))

    ignored_dirs = {".git", ".venv", "node_modules", ".copyclip", "dist", "build", "__pycache__"}
    indexed = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            p = Path(base) / f
            rel = str(p.relative_to(root))
            try:
                st = p.stat()
                if st.st_size > 2_000_000:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
                    (project_id, rel, _lang_from_ext(rel), st.st_size, st.st_mtime, _hash_file(p)),
                )
                indexed += 1
            except Exception:
                continue

    log = _safe_git(root, ["log", "--pretty=format:%H|%an|%ad|%s", "--date=iso", "-n", "200"])
    commits = 0
    if log:
        for line in log.splitlines():
            try:
                sha, author, date, msg = line.split("|", 3)
                conn.execute(
                    "INSERT OR REPLACE INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)",
                    (project_id, sha, author, date, msg),
                )
                commits += 1
            except ValueError:
                continue

    conn.commit()
    conn.close()
    return {"files": indexed, "commits": commits}
