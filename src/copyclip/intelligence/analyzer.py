import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from .db import connect, init_schema
from .phases import (
    PHASE_COMPLETED,
    PHASE_DISCOVERY,
    PHASE_GIT_HISTORY,
    PHASE_IMPORT_GRAPH,
    PHASE_METADATA_HASH,
    PHASE_RISK_SIGNALS,
    PHASE_SNAPSHOTS,
)

STAGE_METADATA_HASH = 1
STAGE_IMPORT_GRAPH = 2
STAGE_RISK_SIGNALS = 4


class AnalysisCanceled(Exception):
    pass


# Brief: _generate_project_story

async def _generate_project_story(root: str, project_id: int, conn) -> str:
    from ..llm_client import LLMClientFactory
    from ..llm.config import load_config
    from ..llm.provider_config import resolve_provider, ProviderConfigError
    
    # 1. Gather Context
    readme = ""
    for rname in ["README.md", "readme.md", "README.txt"]:
        rp = Path(root) / rname
        if rp.exists():
            readme = rp.read_text(encoding="utf-8", errors="ignore")[:3000]
            break
            
    modules = [r[0] for r in conn.execute("SELECT name FROM modules WHERE project_id=? LIMIT 20", (project_id,)).fetchall()]
    decisions = [f"- {r[0]}: {r[1]}" for r in conn.execute("SELECT title, summary FROM decisions WHERE project_id=? AND status='accepted' LIMIT 5", (project_id,)).fetchall()]
    
    prompt = f"""
    You are a principal software architect. Summarize this project into a high-level narrative.
    
    README Extract:
    {readme}
    
    Identified Modules:
    {', '.join(modules)}
    
    Key Architectural Decisions:
    {chr(10).join(decisions)}
    
    Instructions:
    - Write 2-3 concise paragraphs.
    - Explain the "soul" of the project: what problem it solves and how it is structured.
    - Mention major tech/patterns found.
    - Be professional, narrative, and highly useful for a new developer.
    """
    
    # 2. Call LLM
    try:
        cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
        cli_p = os.getenv("COPYCLIP_LLM_PROVIDER")
        prov = resolve_provider(cli_p, cfg)
        
        client = LLMClientFactory.create(
            prov["name"],
            api_key=prov.get("api_key"),
            model=prov.get("model"),
            endpoint=prov.get("base_url"),
            timeout=30,
            extra_headers=prov.get("extra_headers"),
        )
        story = await client.minimize_code_contextually(prompt, "markdown", "en")
        return story
    except Exception:
        return "No narrative story generated yet. Run 'copyclip analyze' with an LLM provider configured."


# Brief: _lang_from_ext

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


# Brief: _hash_file

def _hash_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# Brief: _safe_git

def _safe_git(project_root: str, args: List[str]) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", project_root, *args],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return ""


# Brief: _module_from_relpath

def _module_from_relpath(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "root"
    if parts[0] in {"src", "app", "lib"} and len(parts) > 1:
        return parts[1]
    return parts[0]


# Brief: _extract_import_targets

def _extract_import_targets(content: str, language: str) -> Set[str]:
    targets: Set[str] = set()
    if language == "python":
        for m in re.finditer(r"(?m)^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)", content):
            base = m.group(1).split(".")[0]
            if base:
                targets.add(base)
    elif language in {"javascript", "typescript"}:
        for m in re.finditer(r"(?:from\s+['\"]([^'\"]+)['\"]|import\(['\"]([^'\"]+)['\"]\))", content):
            raw = m.group(1) or m.group(2) or ""
            if raw.startswith("."):
                cleaned = raw.strip("./")
                base = cleaned.split("/")[0] if cleaned else "root"
                if base:
                    targets.add(base)
            else:
                pkg = raw.split("/")[0]
                if pkg:
                    targets.add(pkg)
    return targets


# Brief: _iter_repo_files

def _iter_repo_files(root: str) -> Iterable[Tuple[Path, str]]:
    ignored_dirs = {".git", ".venv", "node_modules", ".copyclip", "dist", "build", "__pycache__"}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            p = Path(base) / f
            rel = str(p.relative_to(root))
            yield p, rel


# Brief: _is_test_path

def _is_test_path(rel: str) -> bool:
    low = rel.lower()
    return (
        "/tests/" in f"/{low}"
        or low.endswith("_test.py")
        or low.endswith(".test.ts")
        or low.endswith(".test.tsx")
        or low.endswith(".test.js")
        or low.endswith(".spec.ts")
        or low.endswith(".spec.tsx")
        or low.endswith(".spec.js")
    )


# Brief: _base_for_test_match

def _base_for_test_match(rel: str) -> str:
    name = Path(rel).name.lower()
    for suffix in ["_test.py", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js"]:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(rel).stem.lower()


# Brief: _complexity_score

def _complexity_score(content: str, language: str) -> int:
    if language not in {"python", "javascript", "typescript"}:
        return 0
    keyword_hits = len(re.findall(r"\b(if|elif|else|for|while|switch|case|catch|except|try)\b", content))
    fn_hits = len(re.findall(r"\b(def|function)\b|=>", content))
    return keyword_hits + fn_hits


# Brief: _is_dependency_impacted

def _is_dependency_impacted(changed_modules: Set[str], module_name: str, imports: List[str]) -> bool:
    if module_name in changed_modules:
        return True
    return any(str(t) in changed_modules for t in imports)


# Brief: _fetch_github_issues

def _fetch_github_issues(project_root: str, project_id: int, conn) -> int:
    try:
        cmd = [
            "gh",
            "issue",
            "list",
            "--limit",
            "200",
            "--json",
            "number,title,state,author,labels,url,createdAt,updatedAt,body",
            "--state",
            "all",
        ]
        out = subprocess.check_output(cmd, cwd=project_root, text=True, stderr=subprocess.DEVNULL)
        issues = json.loads(out)
        for issue in issues:
            conn.execute(
                "INSERT OR REPLACE INTO issues(project_id, external_id, title, body, status, labels, author, url, created_at, updated_at, source) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    str(issue.get("number")),
                    issue.get("title", ""),
                    issue.get("body", ""),
                    issue.get("state", ""),
                    ",".join([l.get("name", "") for l in issue.get("labels", []) if l.get("name")]),
                    issue.get("author", {}).get("login", "unknown") if issue.get("author") else "unknown",
                    issue.get("url", ""),
                    issue.get("createdAt", ""),
                    issue.get("updatedAt", ""),
                    "github",
                ),
            )
        return len(issues)
    except Exception:
        return 0


# Brief: _fetch_github_pull_requests

def _fetch_github_pull_requests(project_root: str, project_id: int, conn) -> int:
    try:
        cmd = [
            "gh",
            "pr",
            "list",
            "--limit",
            "200",
            "--json",
            "number,title,state,author,labels,url,createdAt,updatedAt,body,mergedAt",
            "--state",
            "all",
        ]
        out = subprocess.check_output(cmd, cwd=project_root, text=True, stderr=subprocess.DEVNULL)
        pulls = json.loads(out)
        for pr in pulls:
            conn.execute(
                "INSERT OR REPLACE INTO pulls(project_id, external_id, title, body, status, merged, labels, author, url, created_at, updated_at, source) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    str(pr.get("number")),
                    pr.get("title", ""),
                    pr.get("body", ""),
                    pr.get("state", ""),
                    1 if pr.get("mergedAt") else 0,
                    ",".join([l.get("name", "") for l in pr.get("labels", []) if l.get("name")]),
                    pr.get("author", {}).get("login", "unknown") if pr.get("author") else "unknown",
                    pr.get("url", ""),
                    pr.get("createdAt", ""),
                    pr.get("updatedAt", ""),
                    "github",
                ),
            )
        return len(pulls)
    except Exception:
        return 0


# Brief: _analyze_git_folder

def _analyze_git_folder(project_root: str, project_id: int, conn) -> Dict:
    git_dir = Path(project_root) / ".git"
    if not git_dir.exists():
        return {}

    # Size
    total_size = 0
    try:
        for p in git_dir.rglob("*"):
            if p.is_file():
                total_size += p.stat().st_size
    except Exception:
        pass

    # Branches & Tags
    branches = _safe_git(project_root, ["branch", "-a"]).splitlines()
    tags = _safe_git(project_root, ["tag"]).splitlines()

    stats = {
        "git_size_kb": total_size // 1024,
        "branches_count": len(branches),
        "tags_count": len(tags),
    }
    return stats


# Brief: analyze

async def analyze(project_root: str, progress_cb=None, start_cursor: int = 0, checkpoint_every: int = 500, checkpoint_cb=None, should_cancel=None) -> Dict[str, int]:
    root = os.path.abspath(project_root)
    conn = connect(root)
    init_schema(conn)

    def _check_canceled():
        try:
            if callable(should_cancel) and should_cancel():
                raise AnalysisCanceled("analysis canceled")
        except AnalysisCanceled:
            raise
        except Exception:
            pass

    _check_canceled()

    name = os.path.basename(root)
    conn.execute(
        "INSERT INTO projects(root_path,name,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(root_path) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
        (root, name),
    )
    project_id = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0]

    # Seed default alert rules once per project.
    default_rules = [
        ("high-risk", None, "high", 70, 60),
        ("test-gap-spike", "test_gap", None, 50, 120),
        ("churn-spike", "churn", None, 70, 60),
    ]
    for name_r, kind_r, sev_r, score_r, cooldown_r in default_rules:
        conn.execute(
            "INSERT OR IGNORE INTO alert_rules(project_id,name,kind,severity,min_score,cooldown_min,enabled) VALUES(?,?,?,?,?,?,1)",
            (project_id, name_r, kind_r, sev_r, score_r, cooldown_r),
        )

    if int(start_cursor or 0) <= 0:
        for table in ("files", "commits", "file_changes", "modules", "dependencies", "risks", "issues", "pulls"):
            conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
    else:
        # Resume mode: keep already indexed files, rebuild downstream derived artifacts deterministically.
        for table in ("commits", "file_changes", "modules", "dependencies", "risks", "issues", "pulls"):
            conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))

    # GitHub Issues + PRs
    issue_count = _fetch_github_issues(root, project_id, conn)
    pull_count = _fetch_github_pull_requests(root, project_id, conn)

    # Git stats
    git_stats = _analyze_git_folder(root, project_id, conn)

    indexed = 0
    modules_seen: Counter = Counter()
    dep_edges: Set[Tuple[str, str]] = set()
    repo_files: Set[str] = set()
    complexity_by_file: Dict[str, int] = {}

    if int(start_cursor or 0) > 0:
        indexed = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (project_id,)).fetchone()[0]
        for r in conn.execute("SELECT name FROM modules WHERE project_id=?", (project_id,)).fetchall():
            modules_seen[r[0]] += 1
        for r in conn.execute(
            "SELECT from_module,to_module FROM dependencies WHERE project_id=?",
            (project_id,),
        ).fetchall():
            dep_edges.add((r[0], r[1]))
        for r in conn.execute("SELECT path FROM files WHERE project_id=?", (project_id,)).fetchall():
            repo_files.add(r[0])

    if progress_cb:
        progress_cb(PHASE_DISCOVERY, 0, 0, "discovering project files")

    discovered = sorted(list(_iter_repo_files(root)), key=lambda x: x[1])
    total_files = len(discovered)

    prev_state_rows = conn.execute(
        "SELECT path, hash, mtime, size_bytes, stage_mask FROM analysis_file_state WHERE project_id=?",
        (project_id,),
    ).fetchall()
    prev_state = {
        row[0]: {
            "hash": row[1],
            "mtime": float(row[2] or 0),
            "size_bytes": int(row[3] or 0),
            "stage_mask": int(row[4] or 0),
        }
        for row in prev_state_rows
    }
    prev_insight_rows = conn.execute(
        "SELECT path, module, imports_json, complexity FROM analysis_file_insights WHERE project_id=?",
        (project_id,),
    ).fetchall()
    prev_insights = {}
    for row in prev_insight_rows:
        imports = []
        if row[2]:
            try:
                imports = list(json.loads(row[2]))
            except Exception:
                imports = []
        prev_insights[row[0]] = {
            "module": row[1] or "root",
            "imports": imports,
            "complexity": int(row[3] or 0),
        }

    next_state = {}
    next_insights = {}
    changed_files = 0
    skipped_hash_files = 0
    skipped_parse_files = 0

    changed_modules: Set[str] = set()
    for p, rel in discovered:
        _check_canceled()
        try:
            st = p.stat()
            if st.st_size > 2_000_000:
                continue
            prev = prev_state.get(rel)
            is_unchanged_fast = bool(
                prev
                and abs(float(prev.get("mtime") or 0) - float(st.st_mtime)) < 1e-6
                and int(prev.get("size_bytes") or 0) == int(st.st_size)
                and prev.get("hash")
            )
            if not is_unchanged_fast:
                changed_modules.add(_module_from_relpath(rel))
        except Exception:
            continue

    if progress_cb:
        progress_cb(PHASE_METADATA_HASH, 0, total_files, "computing file metadata and hashes")

    workers = max(1, min(int(os.getenv("COPYCLIP_ANALYZE_WORKERS", "4") or 4), 16))

    queued = [
        (cursor, p, rel)
        for cursor, (p, rel) in enumerate(discovered)
        if not (int(start_cursor or 0) > 0 and cursor < int(start_cursor or 0))
    ]

    def _scan_item(item):
        cursor, p, rel = item
        try:
            st = p.stat()
            if st.st_size > 2_000_000:
                return {"skip": True, "cursor": cursor, "rel": rel}
            prev = prev_state.get(rel)
            is_unchanged = bool(
                prev
                and abs(float(prev.get("mtime") or 0) - float(st.st_mtime)) < 1e-6
                and int(prev.get("size_bytes") or 0) == int(st.st_size)
                and prev.get("hash")
            )
            if is_unchanged:
                file_hash = str(prev.get("hash"))
            else:
                file_hash = _hash_file(p)
            return {
                "skip": False,
                "cursor": cursor,
                "path": p,
                "rel": rel,
                "st_size": int(st.st_size),
                "st_mtime": float(st.st_mtime),
                "language": _lang_from_ext(rel),
                "is_unchanged": is_unchanged,
                "file_hash": file_hash,
            }
        except Exception:
            return {"skip": True, "cursor": cursor, "rel": rel}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        scanned_items = list(pool.map(_scan_item, queued))

    for scanned in scanned_items:
        _check_canceled()
        if scanned.get("skip"):
            continue
        try:
            p = scanned["path"]
            rel = scanned["rel"]
            st_size = int(scanned["st_size"])
            st_mtime = float(scanned["st_mtime"])
            language = scanned["language"]
            is_unchanged = bool(scanned["is_unchanged"])
            file_hash = scanned["file_hash"]

            if is_unchanged:
                skipped_hash_files += 1
            else:
                changed_files += 1

            conn.execute(
                "INSERT OR REPLACE INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
                (project_id, rel, language, st_size, st_mtime, file_hash),
            )

            stage_mask = int(prev.get("stage_mask") or 0) if prev else 0
            stage_mask |= STAGE_METADATA_HASH

            indexed += 1
            repo_files.add(rel)
            if checkpoint_cb and checkpoint_every > 0 and indexed % int(checkpoint_every) == 0:
                try:
                    checkpoint_cb(indexed)
                except Exception:
                    pass
            if progress_cb and indexed % 200 == 0:
                progress_cb(PHASE_METADATA_HASH, indexed, total_files, f"processed {indexed} files")

            mod = _module_from_relpath(rel)
            modules_seen[mod] += 1

            reused_insight = False
            if is_unchanged and (stage_mask & STAGE_IMPORT_GRAPH):
                cached = prev_insights.get(rel)
                if cached:
                    cached_mod = cached.get("module") or mod
                    cached_imports = [str(t) for t in (cached.get("imports") or [])]
                    dependency_impacted = _is_dependency_impacted(changed_modules, cached_mod, cached_imports)
                    if not dependency_impacted:
                        complexity_by_file[rel] = int(cached.get("complexity") or 0)
                        for t in cached_imports:
                            dep_edges.add((cached_mod, t))
                        next_insights[rel] = {
                            "module": cached_mod,
                            "imports": list(cached_imports),
                            "complexity": int(cached.get("complexity") or 0),
                        }
                        reused_insight = True
                        skipped_parse_files += 1

            if (not reused_insight) and language in {"python", "javascript", "typescript"} and st_size < 300_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    cscore = _complexity_score(content, language)
                    imports = sorted(_extract_import_targets(content, language))
                    complexity_by_file[rel] = cscore
                    for t in imports:
                        dep_edges.add((mod, t))
                    stage_mask |= STAGE_IMPORT_GRAPH | STAGE_RISK_SIGNALS
                    next_insights[rel] = {
                        "module": mod,
                        "imports": imports,
                        "complexity": cscore,
                    }
                except Exception:
                    pass

            next_state[rel] = {
                "hash": file_hash,
                "mtime": st_mtime,
                "size_bytes": st_size,
                "stage_mask": stage_mask,
            }
        except Exception:
            continue

    if progress_cb:
        progress_cb(PHASE_IMPORT_GRAPH, indexed, total_files, "building module and dependency graph")

    for module in modules_seen:
        conn.execute(
            "INSERT OR REPLACE INTO modules(project_id,name,path_prefix) VALUES(?,?,?)",
            (project_id, module, module),
        )

    for frm, to in sorted(dep_edges):
        if frm == to:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO dependencies(project_id,from_module,to_module,edge_type) VALUES(?,?,?,?)",
            (project_id, frm, to, "import"),
        )

    if progress_cb:
        progress_cb(PHASE_GIT_HISTORY, indexed, total_files, "collecting git history")

    log = _safe_git(root, ["log", "--pretty=format:%H|%an|%ad|%s", "--date=iso", "-n", "300"])
    commits = 0
    if log:
        for line in log.splitlines():
            _check_canceled()
            try:
                sha, author, date, msg = line.split("|", 3)
                conn.execute(
                    "INSERT OR REPLACE INTO commits(project_id,sha,author,date,message) VALUES(?,?,?,?,?)",
                    (project_id, sha, author, date, msg),
                )
                commits += 1
            except ValueError:
                continue

    churn = Counter()
    raw_changes = _safe_git(root, ["log", "--name-only", "--pretty=format:---%H", "-n", "200"])
    current_sha = None
    if raw_changes:
        for line in raw_changes.splitlines():
            _check_canceled()
            line = line.strip()
            if not line:
                continue
            if line.startswith("---"):
                current_sha = line[3:]
                continue
            churn[line] += 1
            conn.execute(
                "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) VALUES(?,?,?,?,?)",
                (project_id, current_sha, line, 0, 0),
            )

    if progress_cb:
        progress_cb(PHASE_RISK_SIGNALS, indexed, total_files, "computing risk signals")

    risk_count = 0

    # churn risks
    for file_path, score in churn.most_common(10):
        _check_canceled()
        sev = "high" if score >= 8 else ("med" if score >= 4 else "low")
        conn.execute(
            "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
            (
                project_id,
                file_path,
                sev,
                "churn",
                f"File changed {score} times in recent history",
                min(score * 10, 100),
            ),
        )
        risk_count += 1

    # test gap risks: changed non-test files without nearby tests
    test_bases = {_base_for_test_match(p) for p in repo_files if _is_test_path(p)}
    for file_path, score in churn.most_common(25):
        _check_canceled()
        if _is_test_path(file_path):
            continue
        base = _base_for_test_match(file_path)
        if base not in test_bases and score >= 3:
            sev = "high" if score >= 8 else ("med" if score >= 5 else "low")
            conn.execute(
                "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
                (
                    project_id,
                    file_path,
                    sev,
                    "test_gap",
                    "Frequent changes without matching test file signal",
                    min(20 + score * 8, 100),
                ),
            )
            risk_count += 1

    # complexity risks
    for file_path, cscore in sorted(complexity_by_file.items(), key=lambda x: x[1], reverse=True)[:10]:
        _check_canceled()
        if cscore < 18:
            continue
        sev = "high" if cscore >= 35 else ("med" if cscore >= 24 else "low")
        conn.execute(
            "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
            (
                project_id,
                file_path,
                sev,
                "complexity",
                f"Control-flow and function density indicates complexity ({cscore})",
                min(cscore * 2, 100),
            ),
        )
        risk_count += 1

    _check_canceled()

    # Persist incremental file-state snapshot for next run.
    conn.execute("DELETE FROM analysis_file_state WHERE project_id=?", (project_id,))
    for rel, stt in next_state.items():
        conn.execute(
            "INSERT INTO analysis_file_state(project_id,path,hash,mtime,size_bytes,last_processed_at,stage_mask) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP,?)",
            (project_id, rel, stt["hash"], stt["mtime"], stt["size_bytes"], int(stt["stage_mask"] or 0)),
        )

    conn.execute("DELETE FROM analysis_file_insights WHERE project_id=?", (project_id,))
    for rel, ins in next_insights.items():
        conn.execute(
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,updated_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)",
            (project_id, rel, ins.get("module") or "root", json.dumps(ins.get("imports") or []), int(ins.get("complexity") or 0)),
        )

    summary = {
        "files": indexed,
        "commits": commits,
        "modules": len(modules_seen),
        "dependencies": len(dep_edges),
        "risks": risk_count,
        "issues": issue_count,
        "pulls": pull_count,
        "changed_files": changed_files,
        "skipped_hash_files": skipped_hash_files,
        "skipped_parse_files": skipped_parse_files,
        "resume_start_cursor": int(start_cursor or 0),
        "git_stats": git_stats,
    }

    risk_breakdown_rows = conn.execute(
        "SELECT kind, COUNT(*) FROM risks WHERE project_id=? GROUP BY kind",
        (project_id,),
    ).fetchall()
    risk_breakdown = {r[0]: r[1] for r in risk_breakdown_rows}

    if progress_cb:
        progress_cb(PHASE_SNAPSHOTS, indexed, total_files, "writing snapshots and finalizing")

    conn.execute(
        "INSERT INTO snapshots(project_id, summary_json) VALUES(?,?)",
        (project_id, json.dumps({**summary, "risk_breakdown": risk_breakdown})),
    )

    # Project Storytelling (Async)
    story = await _generate_project_story(root, project_id, conn)
    conn.execute("UPDATE projects SET story=? WHERE id=?", (story, project_id))

    conn.commit()
    conn.close()

    if progress_cb:
        progress_cb(PHASE_COMPLETED, total_files, total_files, "analysis completed")

    return summary
