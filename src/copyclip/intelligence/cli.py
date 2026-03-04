import argparse
import json
import os

from .analyzer import analyze
from .db import connect, init_schema
from .server import run_server


COMMANDS = {"analyze", "serve", "start", "decision", "report", "issue"}


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
            print(f"[INFO] Indexed {res['files']} files, {res['commits']} commits, {res['issues']} issues")
            if res.get("git_stats"):
                gs = res["git_stats"]
                print(f"[INFO] Git: {gs['git_size_kb']}KB, {gs['branches_count']} branches, {gs['tags_count']} tags")
        return True

    if cmd == "serve":
        p = argparse.ArgumentParser("copyclip serve")
        p.add_argument("--path", default=".")
        p.add_argument("--port", type=int, default=4310)
        args = p.parse_args(argv[2:])
        try:
            run_server(args.path, args.port)
        except KeyboardInterrupt:
            print("\n[INFO] Stopped.")
        except OSError as e:
            print(f"[ERROR] Could not start server on port {args.port}: {e}")
        return True

    if cmd == "start":
        import asyncio
        p = argparse.ArgumentParser("copyclip start")
        p.add_argument("--path", default=".")
        p.add_argument("--port", type=int, default=4310, help="CopyClip service port (frontend + API)")
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        res = asyncio.run(analyze(root))
        print(f"[INFO] Indexed {res['files']} files, {res['commits']} commits, {res['issues']} issues")
        if res.get("git_stats"):
            gs = res["git_stats"]
            print(f"[INFO] Git: {gs['git_size_kb']}KB, {gs['branches_count']} branches, {gs['tags_count']} tags")
        
        print(f"[INFO] Open CopyClip dashboard: http://127.0.0.1:{args.port}")

        try:
            run_server(root, args.port)
        except KeyboardInterrupt:
            print("\n[INFO] Stopped.")
        except OSError as e:
            print(f"[ERROR] Could not start server on port {args.port}: {e}")
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

