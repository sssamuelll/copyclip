import argparse
import json
import os
import subprocess
import sys

from .analyzer import analyze
from .db import connect, init_schema
from .server import run_server


COMMANDS = {"analyze", "serve", "start", "decision", "report", "issue", "audit"}


def _use_color() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _info(msg: str) -> str:
    return f"{_c('INFO', '36')} {msg}"


def _ok(msg: str) -> str:
    return f"{_c('OK', '32')} {msg}"


def _warn(msg: str) -> str:
    return f"{_c('WARN', '33')} {msg}"


def _err(msg: str) -> str:
    return f"{_c('ERROR', '31')} {msg}"


def _link(url: str, label: str | None = None) -> str:
    label = label or url
    if not sys.stdout.isatty():
        return url
    # OSC 8 hyperlink (BEL-terminated; better compatibility across macOS terminals)
    return f"\033]8;;{url}\a{label}\033]8;;\a"


def _looks_like_project_folder(root: str) -> bool:
    markers = [
        ".git",
        "pyproject.toml",
        "package.json",
        "requirements.txt",
        "setup.py",
        "Pipfile",
        "Cargo.toml",
        "go.mod",
        "frontend",
        "src",
        "app",
    ]
    return any(os.path.exists(os.path.join(root, m)) for m in markers)

def maybe_handle(argv) -> bool:
    if len(argv) < 2 or argv[1] not in COMMANDS:
        return False

    cmd = argv[1]
    if cmd == "analyze":
        import asyncio
        p = argparse.ArgumentParser("copyclip analyze")
        p.add_argument("--path", default=".")
        p.add_argument("--json", action="store_true", dest="as_json")
        args = p.parse_args(argv[2:])
        res = asyncio.run(analyze(args.path))
        if args.as_json:
            print(json.dumps(res))
        else:
            print(_ok(f"Indexed {res['files']} files, {res['commits']} commits, {res['issues']} issues"))
            if res.get("git_stats"):
                gs = res["git_stats"]
                print(_info(f"Git: {gs['git_size_kb']}KB, {gs['branches_count']} branches, {gs['tags_count']} tags"))
        return True

    if cmd == "serve":
        p = argparse.ArgumentParser("copyclip serve")
        p.add_argument("--path", default=".")
        p.add_argument("--port", type=int, default=4310)
        args = p.parse_args(argv[2:])
        try:
            run_server(args.path, args.port)
        except KeyboardInterrupt:
            print("\n" + _info("Stopped."))
        except OSError as e:
            print(_err(f"Could not start server on port {args.port}: {e}"))
        return True

    if cmd == "start":
        import asyncio
        p = argparse.ArgumentParser("copyclip start")
        p.add_argument("--path", default=".")
        p.add_argument("--port", type=int, default=4310, help="CopyClip service port (frontend + API)")
        p.add_argument("--open", dest="open_browser", action=argparse.BooleanOptionalAction, default=True,
                       help="Auto-open dashboard in browser (default: on)")
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        if not _looks_like_project_folder(root):
            print(_err(f"'{root}' does not look like a project folder."))
            print(_info("Run from a repo/project directory (expected markers like .git, src, package.json, pyproject.toml)."))
            return True

        res = asyncio.run(analyze(root))
        print(_ok(f"Indexed {res['files']} files, {res['commits']} commits, {res['issues']} issues"))
        if res.get("git_stats"):
            gs = res["git_stats"]
            print(_info(f"Git: {gs['git_size_kb']}KB, {gs['branches_count']} branches, {gs['tags_count']} tags"))

        dash_url = f"http://127.0.0.1:{args.port}"
        if args.open_browser:
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", dash_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(_info(f"Opening dashboard in browser: {dash_url}"))
            except Exception:
                pass

        try:
            run_server(root, args.port)
        except KeyboardInterrupt:
            print("\n" + _info("Stopped."))
        except OSError as e:
            print(_err(f"Could not start server on port {args.port}: {e}"))
        return True

    if cmd == "decision":
        p = argparse.ArgumentParser("copyclip decision")
        sub = p.add_subparsers(dest="action", required=True)

        add = sub.add_parser("add")
        add.add_argument("--path", default=".")
        add.add_argument("--title", required=True)
        add.add_argument("--summary", default="")

        ls = sub.add_parser("list")
        ls.add_argument("--path", default=".")

        resolve = sub.add_parser("resolve")
        resolve.add_argument("id", type=int)
        resolve.add_argument("--path", default=".")

        link = sub.add_parser("link")
        link.add_argument("id", type=int)
        link.add_argument("--path", default=".")
        link.add_argument("--type", dest="link_type", choices=["file_glob", "module"], default="file_glob")
        link.add_argument("--target", required=True, help="Glob or module name to anchor this decision to")

        args = p.parse_args(argv[2:])
        root = os.path.abspath(args.path)
        conn = connect(root)
        init_schema(conn)
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            print("[ERROR] Run 'copyclip analyze' first")
            return True
        pid = row[0]

        if args.action == "add":
            cur = conn.execute(
                "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
                (pid, args.title, args.summary, "proposed", "manual"),
            )
            conn.commit()
            print(f"[INFO] Decision added #{cur.lastrowid}")
            return True

        if args.action == "list":
            rows = conn.execute(
                "SELECT id,title,status,created_at FROM decisions WHERE project_id=? ORDER BY id DESC", (pid,)
            ).fetchall()
            if not rows:
                print("[INFO] No decisions")
                return True
            for r in rows:
                print(f"#{r[0]} [{r[2]}] {r[1]} ({r[3]})")
            return True

        if args.action == "resolve":
            conn.execute(
                "UPDATE decisions SET status='resolved', resolved_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=?",
                (args.id, pid),
            )
            conn.commit()
            print(f"[INFO] Decision #{args.id} resolved")
            return True

        if args.action == "link":
            did_row = conn.execute("SELECT id, title FROM decisions WHERE id=? AND project_id=?", (args.id, pid)).fetchone()
            if not did_row:
                print(f"[ERROR] Decision #{args.id} not found")
                return True
            conn.execute(
                "INSERT OR IGNORE INTO decision_links(project_id,decision_id,link_type,target_pattern) VALUES(?,?,?,?)",
                (pid, args.id, args.link_type, args.target),
            )
            conn.execute(
                "INSERT INTO decision_history(decision_id,action,from_status,to_status,note) VALUES(?,?,?,?,?)",
                (args.id, "link_added", None, None, f"{args.link_type}: {args.target}"),
            )
            conn.commit()
            print(f"[INFO] Linked Decision #{args.id} ({did_row['title']}) -> {args.link_type}:{args.target}")
            return True

    if cmd == "report":
        p = argparse.ArgumentParser("copyclip report")
        p.add_argument("--path", default=".")
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        conn = connect(root)
        init_schema(conn)
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            print("[ERROR] Run 'copyclip analyze' first")
            return True
        pid = row[0]
        files = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
        commits = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
        decisions = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
        modules = conn.execute("SELECT COUNT(*) FROM modules WHERE project_id=?", (pid,)).fetchone()[0]
        risks = conn.execute("SELECT COUNT(*) FROM risks WHERE project_id=?", (pid,)).fetchone()[0]
        print(f"# CopyClip Project Report")
        print(f"- Files indexed: {files}")
        print(f"- Commits indexed: {commits}")
        print(f"- Modules mapped: {modules}")
        print(f"- Risks detected: {risks}")
        print(f"- Decisions tracked: {decisions}")
        return True

    if cmd == "audit":
        p = argparse.ArgumentParser("copyclip audit")
        p.add_argument("--path", default=".")
        p.add_argument("--json", action="store_true", dest="as_json")
        p.add_argument("--limit", type=int, default=20)
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        conn = connect(root)
        init_schema(conn)
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            print("[ERROR] Run 'copyclip analyze' first")
            return True
        pid = row[0]

        link_count = conn.execute("SELECT COUNT(*) FROM decision_links WHERE project_id=?", (pid,)).fetchone()[0]
        decision_count = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
        intent_risks = conn.execute(
            """
            SELECT area, severity, score, rationale, created_at
            FROM risks
            WHERE project_id=? AND kind='intent_drift'
            ORDER BY score DESC, id DESC
            LIMIT ?
            """,
            (pid, max(1, min(args.limit, 200))),
        ).fetchall()

        unresolved = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE project_id=? AND status IN ('proposed','unresolved')",
            (pid,),
        ).fetchone()[0]

        payload = {
            "decision_links": int(link_count),
            "decisions_total": int(decision_count),
            "decisions_unresolved": int(unresolved),
            "intent_drift_risks": [
                {
                    "area": r[0],
                    "severity": r[1],
                    "score": int(r[2] or 0),
                    "rationale": r[3] or "",
                    "created_at": r[4],
                }
                for r in intent_risks
            ],
        }

        if args.as_json:
            print(json.dumps(payload))
            return True

        print(_ok("Intent Audit"))
        print(_info(f"Decision links: {payload['decision_links']} | Decisions: {payload['decisions_total']} | Unresolved: {payload['decisions_unresolved']}"))
        if not payload["intent_drift_risks"]:
            print(_ok("No intent-drift risks detected."))
            return True

        print(_warn(f"Detected {len(payload['intent_drift_risks'])} intent-drift risk signals:"))
        for i, r in enumerate(payload["intent_drift_risks"], start=1):
            print(f"{i:02d}. [{r['severity']}] score={r['score']} area={r['area']}")
            if r.get("rationale"):
                print(f"    ↳ {r['rationale'][:180]}")
        return True

    if cmd == "issue":
        import asyncio
        import re
        from ..reader import read_files_concurrently
        from ..minimizer import minimize_content
        from ..clipboard import ClipboardManager
        from .db import get_active_decisions

        p = argparse.ArgumentParser("copyclip issue")
        p.add_argument("id", help="GitHub Issue ID/Number")
        p.add_argument("--path", default=".")
        p.add_argument("--minimize", choices=["basic", "aggressive", "structural"], default="basic")
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        conn = connect(root)
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            print("[ERROR] Run 'copyclip analyze' first")
            return True
        pid = row[0]

        issue = conn.execute(
            "SELECT title, body, author, url FROM issues WHERE project_id=? AND external_id=?",
            (pid, args.id),
        ).fetchone()

        if not issue:
            print(f"[ERROR] Issue #{args.id} not found in database. Run 'copyclip analyze' to refresh.")
            return True

        # Heuristic to find relevant files
        relevant_files = set()
        body = (issue["body"] or "").lower()
        title = issue["title"].lower()

        # 1. Look for file-like paths in body
        for match in re.finditer(r"([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]+)", body):
            path = match.group(1).strip("./")
            if os.path.exists(os.path.join(root, path)):
                relevant_files.add(path)

        # 2. Look for files changed in commits mentioning this issue ID
        crows = conn.execute(
            "SELECT file_path FROM file_changes WHERE project_id=? AND commit_sha IN (SELECT sha FROM commits WHERE project_id=? AND (message LIKE ? OR message LIKE ?))",
            (pid, pid, f"%#{args.id}%", f"%issue {args.id}%"),
        ).fetchall()
        for r in crows:
            p_rel = r[0]
            if os.path.exists(os.path.join(root, p_rel)):
                relevant_files.add(p_rel)

        if not relevant_files:
            print("[WARN] No relevant files found automatically. Using all indexed files (limit 5).")
            frows = conn.execute("SELECT path FROM files WHERE project_id=? LIMIT 5", (pid,)).fetchall()
            relevant_files = {r[0] for r in frows}

        print(f"[INFO] Found {len(relevant_files)} relevant files for Issue #{args.id}")

        # Read and minimize
        files_data = asyncio.run(read_files_concurrently(list(relevant_files), root, no_progress=True))

        prompt_parts = []

        # Decisions header
        decs = get_active_decisions(root)
        if decs:
            prompt_parts.append("# PROJECT RULES & DECISIONS")
            for d in decs:
                prompt_parts.append(f"## {d['title']}\n{d['summary']}")

        # Issue Header
        prompt_parts.append(f"# ISSUE: #{args.id} {issue['title']}")
        prompt_parts.append(f"Source: {issue['url']}\nReported by: {issue['author']}")
        prompt_parts.append(f"## Description\n{issue['body']}")

        # Code Context
        prompt_parts.append("# RELEVANT CODE")
        for path, content in files_data.items():
            _, ext = os.path.splitext(path)
            minimized = minimize_content(content, ext.lstrip("."), args.minimize)
            prompt_parts.append(f"### {path}\n```\n{minimized}\n```")

        prompt_parts.append("\n# TASK\nPlease analyze the issue above and the provided code context. Propose a solution or a fix.")

        final_prompt = "\n\n".join(prompt_parts)
        if ClipboardManager().copy(final_prompt):
            print(f"[SUCCESS] Prompt for Issue #{args.id} copied to clipboard!")
        else:
            print("[ERROR] Failed to copy to clipboard")

        return True

        return False

