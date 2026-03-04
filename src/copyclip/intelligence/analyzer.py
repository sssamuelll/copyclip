import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from .db import connect, init_schema


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
        out = subprocess.check_output(["git", "-C", project_root, *args], text=True)
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
                "INSERT INTO issues(project_id, external_id, title, body, status, labels, author, url, created_at, updated_at, source) "
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
                "INSERT INTO pulls(project_id, external_id, title, body, status, merged, labels, author, url, created_at, updated_at, source) "
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

async def analyze(project_root: str) -> Dict[str, int]:
    root = os.path.abspath(project_root)
    conn = connect(root)
    init_schema(conn)

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

    for table in ("files", "commits", "file_changes", "modules", "dependencies", "risks", "issues", "pulls"):
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

    for p, rel in _iter_repo_files(root):
        try:
            st = p.stat()
            if st.st_size > 2_000_000:
                continue
            language = _lang_from_ext(rel)
            conn.execute(
                "INSERT OR REPLACE INTO files(project_id,path,language,size_bytes,mtime,hash) VALUES(?,?,?,?,?,?)",
                (project_id, rel, language, st.st_size, st.st_mtime, _hash_file(p)),
            )
            indexed += 1
            repo_files.add(rel)

            mod = _module_from_relpath(rel)
            modules_seen[mod] += 1

            if language in {"python", "javascript", "typescript"} and st.st_size < 300_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    complexity_by_file[rel] = _complexity_score(content, language)
                    for t in _extract_import_targets(content, language):
                        dep_edges.add((mod, t))
                except Exception:
                    continue
        except Exception:
            continue

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

    log = _safe_git(root, ["log", "--pretty=format:%H|%an|%ad|%s", "--date=iso", "-n", "300"])
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

    churn = Counter()
    raw_changes = _safe_git(root, ["log", "--name-only", "--pretty=format:---%H", "-n", "200"])
    current_sha = None
    if raw_changes:
        for line in raw_changes.splitlines():
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

    risk_count = 0

    # churn risks
    for file_path, score in churn.most_common(10):
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

    summary = {
        "files": indexed,
        "commits": commits,
        "modules": len(modules_seen),
        "dependencies": len(dep_edges),
        "risks": risk_count,
        "issues": issue_count,
        "pulls": pull_count,
        "git_stats": git_stats,
    }

    risk_breakdown_rows = conn.execute(
        "SELECT kind, COUNT(*) FROM risks WHERE project_id=? GROUP BY kind",
        (project_id,),
    ).fetchall()
    risk_breakdown = {r[0]: r[1] for r in risk_breakdown_rows}

    conn.execute(
        "INSERT INTO snapshots(project_id, summary_json) VALUES(?,?)",
        (project_id, json.dumps({**summary, "risk_breakdown": risk_breakdown})),
    )

    # Project Storytelling (Async)
    story = await _generate_project_story(root, project_id, conn)
    conn.execute("UPDATE projects SET story=? WHERE id=?", (story, project_id))

    conn.commit()
    conn.close()
    return summary
