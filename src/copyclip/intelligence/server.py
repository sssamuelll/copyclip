import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .db import connect, init_schema


def _load_ui_html() -> str:
    ui_path = Path(__file__).resolve().parent / "ui" / "index.html"
    if ui_path.exists():
        return ui_path.read_text(encoding="utf-8")
    return "<html><body><h1>CopyClip UI not found</h1></body></html>"


_HTML = _load_ui_html()


def _project_id(conn: sqlite3.Connection, root: str):
    row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
    return row[0] if row else None


def run_server(project_root: str, port: int = 4310) -> None:
    root = os.path.abspath(project_root)

    def with_meta(payload: dict):
        payload.setdefault("meta", {})
        payload["meta"]["project"] = os.path.basename(root)
        return payload

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
                    self._json(with_meta({"files": 0, "commits": 0, "decisions": 0, "modules": 0, "risks": 0, "issues": 0, "story": ""}))
                    return
                files = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
                commits = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
                decisions = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
                modules = conn.execute("SELECT COUNT(*) FROM modules WHERE project_id=?", (pid,)).fetchone()[0]
                risks = conn.execute("SELECT COUNT(*) FROM risks WHERE project_id=?", (pid,)).fetchone()[0]
                issues = conn.execute("SELECT COUNT(*) FROM issues WHERE project_id=?", (pid,)).fetchone()[0]
                story = conn.execute("SELECT story FROM projects WHERE id=?", (pid,)).fetchone()[0]
                self._json(with_meta({
                    "files": files,
                    "commits": commits,
                    "decisions": decisions,
                    "modules": modules,
                    "risks": risks,
                    "issues": issues,
                    "story": story or "",
                }))
                return

            if parsed.path == "/api/heatmap":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                # ... heatmap logic ...
                self._json(with_meta({"items": items}))
                return

            if parsed.path == "/api/agents/chat":
                from .agents import get_agent
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                
                agent_type = data.get("agent", "scout")
                message = data.get("message", "")
                
                if not message:
                    self._json({"error": "message_required"}, 400)
                    return
                
                import asyncio
                agent = get_agent(agent_type, root)
                response = asyncio.run(agent.chat(message))
                self._json(with_meta({"response": response, "agent": agent_type}))
                return

            if parsed.path == "/api/files":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                rows = conn.execute("SELECT path, size_bytes, language FROM files WHERE project_id=? ORDER BY path", (pid,)).fetchall()
                self._json(with_meta({"items": [{"path": r[0], "size": r[1], "language": r[2]} for r in rows]}))
                return

            if parsed.path == "/api/impact":
                if not pid:
                    self._json(with_meta({"impacted_modules": []}))
                    return
                query = urlparse(self.path).query
                from urllib.parse import parse_qs
                params = parse_qs(query)
                target_path = params.get("path", [""])[0]
                
                if not target_path:
                    self._json({"error": "path_required"}, 400)
                    return

                # 1. Find the module for this file
                row = conn.execute(
                    "SELECT name FROM modules WHERE project_id=? AND ? LIKE path_prefix || '%'",
                    (pid, target_path)
                ).fetchone()
                
                if not row:
                    self._json({"impacted_modules": [], "target_module": "unknown"})
                    return
                
                target_module = row[0]
                
                # 2. Find dependents (who depends on this module) - Upwards
                dependents = set()
                to_visit = [target_module]
                visited = set()
                while to_visit:
                    curr = to_visit.pop()
                    if curr in visited: continue
                    visited.add(curr)
                    rows = conn.execute(
                        "SELECT from_module FROM dependencies WHERE project_id=? AND to_module=?",
                        (pid, curr)
                    ).fetchall()
                    for r in rows:
                        dependents.add(r[0])
                        to_visit.append(r[0])

                self._json(with_meta({
                    "target_module": target_module,
                    "impacted_modules": list(dependents)
                }))
                return

            if parsed.path == "/api/changes":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                rows = conn.execute(
                    "SELECT sha, author, message, date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 200", (pid,)
                ).fetchall()
                self._json(with_meta({"items": [{"sha": r[0], "author": r[1], "message": r[2], "date": r[3]} for r in rows]}))
                return

            if parsed.path == "/api/decisions":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                rows = conn.execute(
                    "SELECT id,title,summary,status,source_type,created_at FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 200",
                    (pid,),
                ).fetchall()
                self._json(
                    with_meta({
                        "items": [
                            {
                                "id": r[0],
                                "title": r[1],
                                "summary": r[2],
                                "status": r[3],
                                "source_type": r[4],
                                "created_at": r[5],
                            }
                            for r in rows
                        ]
                    })
                )
                return

            if parsed.path.startswith("/api/decisions/") and parsed.path.endswith("/refs"):
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 4:
                    self._json({"error": "invalid_path"}, 400)
                    return
                try:
                    decision_id = int(parts[2])
                except Exception:
                    self._json({"error": "invalid_decision_id"}, 400)
                    return
                rows = conn.execute(
                    "SELECT ref_type, ref_value FROM decision_refs WHERE decision_id=? ORDER BY id DESC",
                    (decision_id,),
                ).fetchall()
                self._json(with_meta({"items": [{"ref_type": r[0], "ref_value": r[1]} for r in rows]}))
                return

            if parsed.path == "/api/architecture/graph":
                if not pid:
                    self._json(with_meta({"nodes": [], "edges": []}))
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
                self._json(with_meta({"nodes": nodes, "edges": edges}))
                return

            if parsed.path == "/api/risks":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                rows = conn.execute(
                    "SELECT area,severity,kind,rationale,score,created_at FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 100",
                    (pid,),
                ).fetchall()
                self._json(
                    with_meta({
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
                    })
                )
                return

            if parsed.path == "/api/issues":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                rows = conn.execute(
                    "SELECT external_id,title,status,labels,author,url,source,created_at,updated_at FROM issues WHERE project_id=? ORDER BY created_at DESC LIMIT 200",
                    (pid,),
                ).fetchall()
                self._json(
                    with_meta({
                        "items": [
                            {
                                "id": r[0],
                                "title": r[1],
                                "status": r[2],
                                "labels": r[3].split(",") if r[3] else [],
                                "author": r[4],
                                "url": r[5],
                                "source": r[6],
                                "created_at": r[7],
                                "updated_at": r[8],
                            }
                            for r in rows
                        ]
                    })
                )
                return

            self._json({"error": "not_found"}, 404)

        def do_PATCH(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            init_schema(conn)
            pid = _project_id(conn, root)
            if not pid:
                self._json({"error": "run_analyze_first"}, 400)
                return

            if parsed.path.startswith("/api/decisions/"):
                try:
                    decision_id = int(parsed.path.rsplit("/", 1)[-1])
                except Exception:
                    self._json({"error": "invalid_decision_id"}, 400)
                    return

                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                status = (data.get("status") or "").strip()
                allowed = {"proposed", "accepted", "unresolved", "resolved", "superseded"}
                if status not in allowed:
                    self._json({"error": "invalid_status", "allowed": sorted(allowed)}, 400)
                    return

                conn.execute(
                    "UPDATE decisions SET status=?, resolved_at=CASE WHEN ?='resolved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=? AND project_id=?",
                    (status, status, decision_id, pid),
                )
                conn.commit()
                self._json({"ok": True, "id": decision_id, "status": status})
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

            if parsed.path == "/api/assemble-context":
                import asyncio
                from ..reader import read_files_concurrently
                from ..minimizer import minimize_content
                from .db import get_active_decisions

                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                
                selected_files = data.get("files", [])
                selected_issues = data.get("issues", [])
                include_decisions = data.get("include_decisions", True)
                minimize_mode = data.get("minimize", "basic")

                prompt_parts = []
                
                # 1. Decisions
                if include_decisions:
                    decs = get_active_decisions(root)
                    if decs:
                        d_p = ["# PROJECT RULES & DECISIONS"]
                        for d in decs:
                            d_p.append(f"## {d['title']}\n{d['summary']}")
                        prompt_parts.append("\n\n".join(d_p))
                
                # 2. Issues
                if selected_issues:
                    for iid in selected_issues:
                        issue = conn.execute(
                            "SELECT external_id, title, body, author, url FROM issues WHERE project_id=? AND external_id=?",
                            (pid, str(iid))
                        ).fetchone()
                        if issue:
                            prompt_parts.append(f"# ISSUE: #{issue[0]} {issue[1]}\nAuthor: {issue[3]}\nURL: {issue[4]}\n\n{issue[2]}")
                
                # 3. Code
                if selected_files:
                    prompt_parts.append("# CODE CONTEXT")
                    # Filter valid files
                    valid_files = []
                    for f in selected_files:
                        if os.path.exists(os.path.join(root, f)):
                            valid_files.append(f)
                    
                    if valid_files:
                        files_data = asyncio.run(read_files_concurrently(valid_files, root, no_progress=True))
                        for path, content in files_data.items():
                            _, ext = os.path.splitext(path)
                            minimized = minimize_content(content, ext.lstrip("."), minimize_mode)
                            prompt_parts.append(f"### {path}\n```\n{minimized}\n```")
                
                # 4. Guardrail Check (Decision Advisor)
                warnings = []
                if include_decisions:
                    decs = get_active_decisions(root)
                    if decs and selected_files:
                        from ..llm_client import LLMClientFactory
                        from ..llm.config import load_config
                        from ..llm.provider_config import resolve_provider, ProviderConfigError
                        
                        try:
                            cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
                            cli_p = os.getenv("COPYCLIP_LLM_PROVIDER")
                            prov = resolve_provider(cli_p, cfg)
                            client = LLMClientFactory.create(
                                prov["name"],
                                api_key=prov.get("api_key"),
                                model=prov.get("model"),
                                endpoint=prov.get("base_url"),
                                timeout=15,
                            )
                            
                            advisor_prompt = f"""
                            Check if the current task/context assembly conflicts with project decisions.
                            
                            Current Context Assembly (Files): {", ".join(selected_files)}
                            Current Context Assembly (Issues): {", ".join(selected_issues)}
                            
                            Active Decisions:
                            {chr(10).join([f"- {d['title']}: {d['summary']}" for d in decs])}
                            
                            If there is a conflict or a risk, return a 1-sentence warning. If no conflict, return "OK".
                            """
                            adv_res = await client.minimize_code_contextually(advisor_prompt, "text", "en")
                            if adv_res and "OK" not in adv_res.upper():
                                warnings.append(adv_res.strip())
                        except:
                            pass

                final_context = "\n\n".join(prompt_parts)
                self._json({"context": final_context, "warnings": warnings})
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

            if parsed.path.startswith("/api/decisions/") and parsed.path.endswith("/refs"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 4:
                    self._json({"error": "invalid_path"}, 400)
                    return
                try:
                    decision_id = int(parts[2])
                except Exception:
                    self._json({"error": "invalid_decision_id"}, 400)
                    return

                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                ref_type = (data.get("ref_type") or "file").strip()
                ref_value = (data.get("ref_value") or "").strip()
                allowed = {"file", "commit", "doc"}
                if ref_type not in allowed:
                    self._json({"error": "invalid_ref_type", "allowed": sorted(allowed)}, 400)
                    return
                if not ref_value:
                    self._json({"error": "ref_value_required"}, 400)
                    return

                conn.execute(
                    "INSERT INTO decision_refs(decision_id,ref_type,ref_value) VALUES(?,?,?)",
                    (decision_id, ref_type, ref_value),
                )
                conn.commit()
                self._json({"ok": True, "decision_id": decision_id, "ref_type": ref_type, "ref_value": ref_value})
                return

            self._json({"error": "not_found"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[INFO] CopyClip Intelligence running at http://127.0.0.1:{port}")
    print("[INFO] Press Ctrl+C to stop")
    server.serve_forever()
