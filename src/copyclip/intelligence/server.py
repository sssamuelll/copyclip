import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import connect, init_schema


_HTML = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>CopyClip Intelligence</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 24px; background:#0b0f14; color:#e6edf3; }
    .grid { display:grid; grid-template-columns: repeat(3, minmax(180px,1fr)); gap:16px; }
    .card { background:#161b22; border:1px solid #30363d; border-radius:12px; padding:16px; }
    h1,h2 { margin:0 0 12px 0; }
    .muted { color:#8b949e; }
    ul { margin:8px 0 0 18px; }
    code { color:#79c0ff; }
  </style>
</head>
<body>
  <h1>CopyClip Project Intelligence</h1>
  <p class='muted'>Human control plane (v1 skeleton)</p>
  <div class='grid'>
    <div class='card'><h2>Files</h2><div id='files'>-</div></div>
    <div class='card'><h2>Commits</h2><div id='commits'>-</div></div>
    <div class='card'><h2>Decisions</h2><div id='decisions'>-</div></div>
  </div>
  <div class='card' style='margin-top:16px'>
    <h2>Recent Changes</h2>
    <ul id='changes'></ul>
  </div>
<script>
async function load(){
  const o = await fetch('/api/overview').then(r=>r.json());
  document.getElementById('files').textContent = o.files;
  document.getElementById('commits').textContent = o.commits;
  document.getElementById('decisions').textContent = o.decisions;
  const c = await fetch('/api/changes').then(r=>r.json());
  const ul = document.getElementById('changes'); ul.innerHTML='';
  c.items.forEach(it=>{ const li=document.createElement('li'); li.textContent = `${it.sha.slice(0,7)} — ${it.message}`; ul.appendChild(li); });
}
load();
</script>
</body>
</html>
"""


def _project_id(conn: sqlite3.Connection, root: str):
    row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
    return row[0] if row else None


def run_server(project_root: str, port: int = 4310) -> None:
    root = os.path.abspath(project_root)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, payload, code=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            init_schema(conn)
            pid = _project_id(conn, root)

            if parsed.path == "/":
                body = _HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/overview":
                if not pid:
                    self._json({"files": 0, "commits": 0, "decisions": 0})
                    return
                files = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
                commits = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
                decisions = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
                self._json({"files": files, "commits": commits, "decisions": decisions})
                return

            if parsed.path == "/api/changes":
                if not pid:
                    self._json({"items": []})
                    return
                rows = conn.execute(
                    "SELECT sha, message, date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 20", (pid,)
                ).fetchall()
                self._json({"items": [{"sha": r[0], "message": r[1], "date": r[2]} for r in rows]})
                return

            self._json({"error": "not_found"}, 404)

        def do_POST(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            init_schema(conn)
            pid = _project_id(conn, root)
            if not pid:
                self._json({"error": "run_analyze_first"}, 400)
                return

            if parsed.path == "/api/decisions":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                title = (data.get("title") or "").strip()
                summary = (data.get("summary") or "").strip()
                if not title:
                    self._json({"error": "title_required"}, 400)
                    return
                cur = conn.execute(
                    "INSERT INTO decisions(project_id,title,summary,status,source_type) VALUES(?,?,?,?,?)",
                    (pid, title, summary, "proposed", "manual"),
                )
                conn.commit()
                self._json({"id": cur.lastrowid, "ok": True})
                return

            self._json({"error": "not_found"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[INFO] CopyClip Intelligence running at http://127.0.0.1:{port}")
    print("[INFO] Press Ctrl+C to stop")
    server.serve_forever()
