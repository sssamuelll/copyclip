import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .db import connect, init_schema


_HTML = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>CopyClip Intelligence</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 24px; background:#0b0f14; color:#e6edf3; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(180px,1fr)); gap:16px; }
    .card { background:#161b22; border:1px solid #30363d; border-radius:12px; padding:16px; }
    h1,h2 { margin:0 0 12px 0; }
    .muted { color:#8b949e; }
    ul { margin:8px 0 0 18px; }
    .two { display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-top:16px; }
    .sev-high { color:#ff7b72; }
    .sev-med { color:#d29922; }
    .sev-low { color:#3fb950; }
  </style>
</head>
<body>
  <h1>CopyClip Project Intelligence</h1>
  <p class='muted'>Human control plane — architecture, decisions, and risk awareness.</p>

  <div class='grid'>
    <div class='card'><h2>Files</h2><div id='files'>-</div></div>
    <div class='card'><h2>Commits</h2><div id='commits'>-</div></div>
    <div class='card'><h2>Modules</h2><div id='modules'>-</div></div>
    <div class='card'><h2>Risks</h2><div id='riskCount'>-</div></div>
  </div>

  <div class='two'>
    <div class='card'>
      <h2>Recent Changes</h2>
      <ul id='changes'></ul>
    </div>
    <div class='card'>
      <h2>Decisions</h2>
      <ul id='decisions'></ul>
    </div>
  </div>

  <div class='two'>
    <div class='card'>
      <h2>Architecture Edges</h2>
      <ul id='arch'></ul>
    </div>
    <div class='card'>
      <h2>Top Risks</h2>
      <ul id='risks'></ul>
    </div>
  </div>

<script>
function li(text, cls=''){ const x=document.createElement('li'); x.textContent=text; if(cls)x.className=cls; return x; }

async function load(){
  const o = await fetch('/api/overview').then(r=>r.json());
  document.getElementById('files').textContent = o.files;
  document.getElementById('commits').textContent = o.commits;
  document.getElementById('modules').textContent = o.modules;
  document.getElementById('riskCount').textContent = o.risks;

  const changes = await fetch('/api/changes').then(r=>r.json());
  const ch = document.getElementById('changes'); ch.innerHTML='';
  changes.items.slice(0,12).forEach(it=> ch.appendChild(li(`${it.sha.slice(0,7)} — ${it.message}`)) );

  const dec = await fetch('/api/decisions').then(r=>r.json());
  const dl = document.getElementById('decisions'); dl.innerHTML='';
  if(!dec.items.length) dl.appendChild(li('No decisions yet (use copyclip decision add)', 'muted'));
  dec.items.forEach(it=> dl.appendChild(li(`#${it.id} [${it.status}] ${it.title}`)) );

  const arch = await fetch('/api/architecture/graph').then(r=>r.json());
  const al = document.getElementById('arch'); al.innerHTML='';
  arch.edges.slice(0,20).forEach(e=> al.appendChild(li(`${e.from} → ${e.to}`)) );

  const risks = await fetch('/api/risks').then(r=>r.json());
  const rl = document.getElementById('risks'); rl.innerHTML='';
  risks.items.slice(0,15).forEach(r => {
    const cls = r.severity === 'high' ? 'sev-high' : (r.severity === 'med' ? 'sev-med' : 'sev-low');
    rl.appendChild(li(`[${r.severity}] ${r.area} — ${r.rationale}`, cls));
  });
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
                    self._json({"files": 0, "commits": 0, "decisions": 0, "modules": 0, "risks": 0})
                    return
                files = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
                commits = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
                decisions = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
                modules = conn.execute("SELECT COUNT(*) FROM modules WHERE project_id=?", (pid,)).fetchone()[0]
                risks = conn.execute("SELECT COUNT(*) FROM risks WHERE project_id=?", (pid,)).fetchone()[0]
                self._json({
                    "files": files,
                    "commits": commits,
                    "decisions": decisions,
                    "modules": modules,
                    "risks": risks,
                })
                return

            if parsed.path == "/api/changes":
                if not pid:
                    self._json({"items": []})
                    return
                rows = conn.execute(
                    "SELECT sha, message, date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 50", (pid,)
                ).fetchall()
                self._json({"items": [{"sha": r[0], "message": r[1], "date": r[2]} for r in rows]})
                return

            if parsed.path == "/api/decisions":
                if not pid:
                    self._json({"items": []})
                    return
                rows = conn.execute(
                    "SELECT id,title,summary,status,created_at FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 100",
                    (pid,),
                ).fetchall()
                self._json(
                    {
                        "items": [
                            {
                                "id": r[0],
                                "title": r[1],
                                "summary": r[2],
                                "status": r[3],
                                "created_at": r[4],
                            }
                            for r in rows
                        ]
                    }
                )
                return

            if parsed.path == "/api/architecture/graph":
                if not pid:
                    self._json({"nodes": [], "edges": []})
                    return
                nodes = [
                    {"name": r[0]}
                    for r in conn.execute("SELECT name FROM modules WHERE project_id=? ORDER BY name", (pid,)).fetchall()
                ]
                edges = [
                    {"from": r[0], "to": r[1], "type": r[2]}
                    for r in conn.execute(
                        "SELECT from_module,to_module,edge_type FROM dependencies WHERE project_id=? ORDER BY id LIMIT 800",
                        (pid,),
                    ).fetchall()
                ]
                self._json({"nodes": nodes, "edges": edges})
                return

            if parsed.path == "/api/risks":
                if not pid:
                    self._json({"items": []})
                    return
                rows = conn.execute(
                    "SELECT area,severity,kind,rationale,score,created_at FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 100",
                    (pid,),
                ).fetchall()
                self._json(
                    {
                        "items": [
                            {
                                "area": r[0],
                                "severity": r[1],
                                "kind": r[2],
                                "rationale": r[3],
                                "score": r[4],
                                "created_at": r[5],
                            }
                            for r in rows
                        ]
                    }
                )
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
