import argparse
import json
import os
import subprocess

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
            print(f"[INFO] Indexed {res['files']} files and {res['commits']} commits")
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
        p.add_argument("--port", type=int, default=4310, help="Backend intelligence API/dashboard port")
        p.add_argument("--frontend-port", type=int, default=5173, help="Frontend dev server port")
        p.add_argument("--no-frontend", action="store_true", help="Do not auto-start frontend dev server")
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        res = analyze(root)
        print(f"[INFO] Indexed {res['files']} files and {res['commits']} commits")

        frontend_url = f"http://127.0.0.1:{args.frontend_port}"
        backend_url = f"http://127.0.0.1:{args.port}"

        if not args.no_frontend:
            frontend_dir = os.path.join(root, "frontend")
            if os.path.isdir(frontend_dir):
                try:
                    subprocess.Popen(
                        ["npm", "run", "dev", "--", "--port", str(args.frontend_port)],
                        cwd=frontend_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    print(f"[INFO] Frontend dev server starting at {frontend_url}")
                except Exception as e:
                    print(f"[WARN] Could not start frontend dev server: {e}")
                    print(f"[INFO] Start it manually: cd frontend && npm run dev -- --port {args.frontend_port}")
            else:
                print("[WARN] No frontend/ directory found in this project.")

        print(f"[INFO] Open frontend: {frontend_url}")
        print(f"[INFO] Backend dashboard/API: {backend_url}")
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
