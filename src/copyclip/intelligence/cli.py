import argparse
import json
import os

from .analyzer import analyze
from .db import connect, init_schema
from .server import run_server


COMMANDS = {"analyze", "serve", "start", "decision", "report"}


def maybe_handle(argv) -> bool:
    if len(argv) < 2 or argv[1] not in COMMANDS:
        return False

    cmd = argv[1]
    if cmd == "analyze":
        p = argparse.ArgumentParser("copyclip analyze")
        p.add_argument("--path", default=".")
        p.add_argument("--json", action="store_true", dest="as_json")
        args = p.parse_args(argv[2:])
        res = analyze(args.path)
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
        run_server(args.path, args.port)
        return True

    if cmd == "start":
        p = argparse.ArgumentParser("copyclip start")
        p.add_argument("--path", default=".")
        p.add_argument("--port", type=int, default=4310, help="CopyClip service port (frontend + API)")
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        res = analyze(root)
        print(f"[INFO] Indexed {res['files']} files, {res['commits']} commits, {res['issues']} issues")
        if res.get("git_stats"):
            gs = res["git_stats"]
            print(f"[INFO] Git: {gs['git_size_kb']}KB, {gs['branches_count']} branches, {gs['tags_count']} tags")
        
        print(f"[INFO] Open CopyClip dashboard: http://127.0.0.1:{args.port}")

        run_server(root, args.port)
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
        print("# CopyClip Project Report")
        print(f"- Files indexed: {files}")
        print(f"- Commits indexed: {commits}")
        print(f"- Modules mapped: {modules}")
        print(f"- Risks detected: {risks}")
        print(f"- Decisions tracked: {decisions}")
        return True

    return False
