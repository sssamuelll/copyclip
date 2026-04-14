import hashlib
import json
import os
import re
import subprocess
import time
from fnmatch import fnmatch
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from .db import connect, init_schema
from .tree_sitter_parser import extract_symbols, SUPPORTED_LANGUAGES, ExtractionResult
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

DRIFT_THRESHOLDS = {
    "decision_alignment_low": 55.0,
    "architecture_cohesion_high": 18.0,
    "risk_concentration_high": 65.0,
}
DRIFT_CALIBRATION_VERSION = "v1.1"

AGENT_SIGNATURES = ["cursor", "windsurf", "agent", "github-actions", "bot"]


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
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "cpp",
        ".hpp": "cpp",
        ".rs": "rust",
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
    parts = [p for p in rel.split("/") if p]
    if len(parts) <= 1:
        return "root"

    # Treat common source roots as container folders rather than meaningful modules.
    if parts[0] in {"src", "lib"} and len(parts) > 2:
        parts = parts[1:]

    if len(parts) == 2:
        return parts[0] if parts[0] in {"api", "utils"} else parts[1]

    return "/".join(parts[:-1])


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
        "SELECT path, module, imports_json, complexity, COALESCE(cognitive_debt,0) FROM analysis_file_insights WHERE project_id=?",
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
            "cognitive_debt": float(row[4] or 0),
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
                            "cognitive_debt": float(cached.get("cognitive_debt") or 0),
                        }
                        reused_insight = True
                        skipped_parse_files += 1

            if (not reused_insight) and language in SUPPORTED_LANGUAGES and st_size < 300_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    extraction = extract_symbols(content, language)
                    cscore = extraction.complexity
                    imports = sorted(set(imp.target for imp in extraction.imports))
                    complexity_by_file[rel] = cscore
                    for t in imports:
                        dep_edges.add((mod, t))
                    stage_mask |= STAGE_IMPORT_GRAPH | STAGE_RISK_SIGNALS
                    next_insights[rel] = {
                        "module": mod,
                        "imports": imports,
                        "complexity": cscore,
                        "cognitive_debt": 0.0,
                    }
                    # Store extraction for symbol resolution pass
                    if not hasattr(analyze, '_file_extractions'):
                        analyze._file_extractions = {}
                    analyze._file_extractions[rel] = (mod, extraction)
                except Exception:
                    pass
            elif (not reused_insight) and language in {"python", "javascript", "typescript"} and st_size < 300_000:
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
                        "cognitive_debt": 0.0,
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

    # --- Symbol resolution pass ---
    file_extractions = getattr(analyze, '_file_extractions', {})
    if file_extractions:
        # Clear previous symbols for this project
        conn.execute("DELETE FROM symbol_edges WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM symbols WHERE project_id=?", (project_id,))

        # Insert all symbol definitions
        symbol_id_map = {}  # (file_path, name, kind) -> symbol_id
        global_symbols = {}  # (module, name) -> symbol_id (for cross-file resolution)

        for rel, (mod, extraction) in file_extractions.items():
            for sym in extraction.definitions:
                cursor = conn.execute(
                    "INSERT OR REPLACE INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) VALUES(?,?,?,?,?,?,?,?)",
                    (project_id, sym.name, sym.kind, rel, sym.line_start, sym.line_end, None, mod),
                )
                sid = cursor.lastrowid
                symbol_id_map[(rel, sym.name, sym.kind)] = sid
                global_symbols[(mod, sym.name)] = sid

        # Resolve parent_symbol_id for methods
        for rel, (mod, extraction) in file_extractions.items():
            for sym in extraction.definitions:
                if sym.parent:
                    parent_id = symbol_id_map.get((rel, sym.parent, "class"))
                    child_id = symbol_id_map.get((rel, sym.name, sym.kind))
                    if parent_id and child_id:
                        conn.execute("UPDATE symbols SET parent_symbol_id=? WHERE id=?", (parent_id, child_id))
                        conn.execute(
                            "INSERT OR IGNORE INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
                            (project_id, parent_id, child_id, "contains"),
                        )

        # Build import map for cross-file call resolution
        # Maps (file_path, imported_name) -> source_module
        import_map = {}
        for rel, (mod, extraction) in file_extractions.items():
            for imp in extraction.imports:
                import_map[(rel, imp.target)] = imp.target

        # Resolve calls
        for rel, (mod, extraction) in file_extractions.items():
            for call in extraction.calls:
                # Try to find the callee symbol
                callee_base = call.callee.split(".")[0]  # handle obj.method -> obj
                callee_name = call.callee.split(".")[-1] if "." in call.callee else call.callee

                # Look in same file first
                callee_id = symbol_id_map.get((rel, callee_name, "function")) or \
                            symbol_id_map.get((rel, callee_name, "method"))

                # Look in imported modules
                if not callee_id:
                    for (r, imp_name), src_mod in import_map.items():
                        if r == rel and imp_name == callee_base:
                            callee_id = global_symbols.get((src_mod, callee_name))
                            if callee_id:
                                break

                # Look globally as fallback
                if not callee_id:
                    for (m, n), sid in global_symbols.items():
                        if n == callee_name:
                            callee_id = sid
                            break

                if callee_id:
                    caller_id = symbol_id_map.get((rel, call.caller, "function")) or \
                                symbol_id_map.get((rel, call.caller, "method"))
                    if caller_id:
                        conn.execute(
                            "INSERT OR IGNORE INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
                            (project_id, caller_id, callee_id, "calls"),
                        )

        # Resolve inheritance
        for rel, (mod, extraction) in file_extractions.items():
            for inh in extraction.inheritance:
                child_id = symbol_id_map.get((rel, inh.child, "class")) or \
                           symbol_id_map.get((rel, inh.child, "struct"))
                parent_id = None
                # Look in same file
                parent_id = symbol_id_map.get((rel, inh.parent, "class")) or \
                            symbol_id_map.get((rel, inh.parent, "trait")) or \
                            symbol_id_map.get((rel, inh.parent, "interface"))
                # Look globally
                if not parent_id:
                    for (m, n), sid in global_symbols.items():
                        if n == inh.parent:
                            parent_id = sid
                            break
                if child_id and parent_id:
                    conn.execute(
                        "INSERT OR IGNORE INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
                        (project_id, child_id, parent_id, "inherits"),
                    )

        # Clean up
        analyze._file_extractions = {}

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

    # Cognitive debt scoring (CCIA module-2):
    # Score = (Agent_Lines / Total_Lines) * 100 * TimeSinceLastHumanReviewFactor
    # Agent lines detected by author signatures from git blame.
    now_ts = time.time()
    debt_values = []
    blame_candidates = {p for p, _ in churn.most_common(25)}

    for rel, ins in next_insights.items():
        _check_canceled()
        if not rel:
            continue

        # Keep analysis fast: only recompute blame for churn-active files.
        if rel not in blame_candidates:
            ins["cognitive_debt"] = float(ins.get("cognitive_debt") or 0.0)
            debt_values.append(float(ins.get("cognitive_debt") or 0.0))
            continue

        blame = _safe_git(root, ["blame", "--line-porcelain", "--", rel])
        if not blame:
            ins["cognitive_debt"] = float(ins.get("cognitive_debt") or 0.0)
            debt_values.append(float(ins.get("cognitive_debt") or 0.0))
            continue

        total_lines = 0
        agent_lines = 0
        current_author = ""
        current_author_time = 0
        last_human_ts = 0

        for bline in blame.splitlines():
            if bline.startswith("author "):
                current_author = (bline[7:] or "").strip().lower()
            elif bline.startswith("author-time "):
                try:
                    current_author_time = int((bline.split(" ", 1)[1] or "0").strip())
                except Exception:
                    current_author_time = 0
            elif bline.startswith("\t"):
                total_lines += 1
                is_agent = any(sig in current_author for sig in AGENT_SIGNATURES)
                if is_agent:
                    agent_lines += 1
                else:
                    if current_author_time > last_human_ts:
                        last_human_ts = current_author_time

        if total_lines <= 0:
            score = 0.0
        else:
            ratio = agent_lines / float(total_lines)
            if last_human_ts > 0:
                days_since_human = max(0.0, (now_ts - float(last_human_ts)) / 86400.0)
            else:
                # If we cannot find human lines, treat as high review staleness.
                days_since_human = 120.0
            time_factor = 1.0 + min(1.5, days_since_human / 30.0)
            score = min(100.0, (ratio * 100.0) * time_factor)

        ins["cognitive_debt"] = round(float(score), 2)
        debt_values.append(ins["cognitive_debt"])

    avg_cognitive_debt = round((sum(debt_values) / max(1, len(debt_values))), 2)

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

    # intent drift risks (CCIA phase-2 bootstrap): code touched in areas linked to accepted/resolved decisions.
    decision_link_rows = conn.execute(
        """
        SELECT dl.decision_id, dl.link_type, dl.target_pattern, d.title, d.summary, d.status
        FROM decision_links dl
        JOIN decisions d ON d.id = dl.decision_id
        WHERE dl.project_id=? AND d.project_id=? AND d.status IN ('accepted','resolved')
        ORDER BY dl.id DESC
        """,
        (project_id, project_id),
    ).fetchall()

    decision_tokens = {}
    for r in decision_link_rows:
        did = int(r[0])
        if did in decision_tokens:
            continue
        dtext = f"{r[3] or ''} {r[4] or ''}".lower()
        decision_tokens[did] = set(re.findall(r"[a-zA-Z0-9_\-]{4,}", dtext))

    seen_intent_risk = set()
    for file_path, churn_score in churn.most_common(40):
        _check_canceled()
        if not file_path:
            continue

        for r in decision_link_rows:
            did = int(r[0])
            link_type = (r[1] or "").strip()
            target_pattern = (r[2] or "").strip()
            title = (r[3] or "").strip()

            matched = False
            if link_type == "file_glob" and target_pattern:
                matched = fnmatch(file_path, target_pattern)
            elif link_type == "module" and target_pattern:
                matched = file_path.startswith(f"{target_pattern}/") or file_path == target_pattern

            if not matched:
                continue

            # heuristic contradiction signal: file path lexemes not represented in the decision language.
            ftokens = set(re.findall(r"[a-zA-Z0-9_\-]{4,}", file_path.lower()))
            overlap = len(ftokens & decision_tokens.get(did, set()))
            novelty = max(0, len(ftokens) - overlap)

            score = min(100, 25 + churn_score * 5 + novelty * 4)
            sev = "high" if score >= 75 else ("med" if score >= 45 else "low")
            key = (did, file_path)
            if key in seen_intent_risk:
                continue
            seen_intent_risk.add(key)

            rationale = (
                f"File touches decision-linked intent surface (decision #{did}: {title}). "
                f"Churn={churn_score}, token_novelty={novelty}, lexical_overlap={overlap}."
            )
            conn.execute(
                "INSERT INTO risks(project_id,area,severity,kind,rationale,score) VALUES(?,?,?,?,?,?)",
                (project_id, file_path, sev, "intent_drift", rationale, score),
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
            "INSERT INTO analysis_file_insights(project_id,path,module,imports_json,complexity,cognitive_debt,updated_at) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (
                project_id,
                rel,
                ins.get("module") or "root",
                json.dumps(ins.get("imports") or []),
                int(ins.get("complexity") or 0),
                float(ins.get("cognitive_debt") or 0),
            ),
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
        "average_cognitive_debt": avg_cognitive_debt,
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

    # Story snapshots (longitudinal narrative substrate)
    focus_rows = conn.execute(
        "SELECT area, severity, kind, score FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 5",
        (project_id,),
    ).fetchall()
    focus_areas = [
        {
            "area": r[0],
            "severity": r[1],
            "kind": r[2],
            "score": int(r[3] or 0),
        }
        for r in focus_rows
    ]

    change_rows = conn.execute(
        "SELECT sha, author, date, message FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 6",
        (project_id,),
    ).fetchall()
    major_changes = [
        {
            "sha": r[0],
            "author": r[1],
            "date": r[2],
            "message": r[3],
        }
        for r in change_rows
    ]

    question_rows = conn.execute(
        "SELECT id, title, status FROM decisions WHERE project_id=? AND status IN ('proposed','unresolved') ORDER BY id DESC LIMIT 6",
        (project_id,),
    ).fetchall()
    open_questions = [
        {
            "decision_id": int(r[0]),
            "title": r[1],
            "status": r[2],
        }
        for r in question_rows
    ]

    story_snapshot_summary = {
        "files": indexed,
        "commits": commits,
        "risks": risk_count,
        "focus_count": len(focus_areas),
        "open_questions_count": len(open_questions),
    }

    conn.execute(
        """
        INSERT INTO story_snapshots(project_id, focus_areas_json, major_changes_json, open_questions_json, summary_json)
        VALUES(?,?,?,?,?)
        """,
        (
            project_id,
            json.dumps(focus_areas),
            json.dumps(major_changes),
            json.dumps(open_questions),
            json.dumps(story_snapshot_summary),
        ),
    )

    # Identity drift metrics snapshot (calibrated v1.1)
    decision_status_rows = conn.execute(
        "SELECT status, COUNT(*) FROM decisions WHERE project_id=? GROUP BY status",
        (project_id,),
    ).fetchall()
    status_counts = {str(r[0] or ""): int(r[1] or 0) for r in decision_status_rows}
    total_decisions = max(1, sum(status_counts.values()))
    aligned = status_counts.get("accepted", 0) + status_counts.get("resolved", 0)
    decision_alignment_score = round((aligned / total_decisions) * 100.0, 2)

    dep_count_row = conn.execute("SELECT COUNT(*) FROM dependencies WHERE project_id=?", (project_id,)).fetchone()
    mod_count_row = conn.execute("SELECT COUNT(*) FROM modules WHERE project_id=?", (project_id,)).fetchone()
    dep_count = int(dep_count_row[0] or 0) if dep_count_row else 0
    mod_count = max(1, int(mod_count_row[0] or 0) if mod_count_row else 0)
    architecture_cohesion_delta = round((dep_count / mod_count), 3)

    risk_rows = conn.execute(
        "SELECT score FROM risks WHERE project_id=? ORDER BY score DESC LIMIT 20",
        (project_id,),
    ).fetchall()
    risk_scores = [max(0, int(r[0] or 0)) for r in risk_rows]
    risk_total = sum(risk_scores)
    risk_top3 = sum(risk_scores[:3])
    risk_concentration_index = round((risk_top3 / max(1, risk_total)) * 100.0, 2)

    drift_causes = []
    if decision_alignment_score < DRIFT_THRESHOLDS["decision_alignment_low"]:
        drift_causes.append("Low decision alignment (many proposed/unresolved decisions)")
    if architecture_cohesion_delta > DRIFT_THRESHOLDS["architecture_cohesion_high"]:
        drift_causes.append("High dependency density per module")
    if risk_concentration_index > DRIFT_THRESHOLDS["risk_concentration_high"]:
        drift_causes.append("Risk concentration clustered in top hotspots")

    drift_level = "high" if len(drift_causes) >= 2 else ("med" if len(drift_causes) == 1 else "low")
    drift_summary = {
        "decision_alignment_score": decision_alignment_score,
        "architecture_cohesion_delta": architecture_cohesion_delta,
        "risk_concentration_index": risk_concentration_index,
        "drift_level": drift_level,
        "calibration_version": DRIFT_CALIBRATION_VERSION,
        "thresholds": DRIFT_THRESHOLDS,
        "qa": {
            "decision_count": total_decisions,
            "dependency_count": dep_count,
            "module_count": mod_count,
            "risk_sample_size": len(risk_scores),
            "risk_total": risk_total,
        },
    }

    conn.execute(
        """
        INSERT INTO identity_drift_snapshots(
            project_id,
            decision_alignment_score,
            architecture_cohesion_delta,
            risk_concentration_index,
            causes_json,
            summary_json
        )
        VALUES(?,?,?,?,?,?)
        """,
        (
            project_id,
            decision_alignment_score,
            architecture_cohesion_delta,
            risk_concentration_index,
            json.dumps(drift_causes),
            json.dumps(drift_summary),
        ),
    )

    # Project Storytelling (Async)
    story = await _generate_project_story(root, project_id, conn)
    conn.execute("UPDATE projects SET story=? WHERE id=?", (story, project_id))

    conn.commit()
    conn.close()

    if progress_cb:
        progress_cb(PHASE_COMPLETED, total_files, total_files, "analysis completed")

    return summary
