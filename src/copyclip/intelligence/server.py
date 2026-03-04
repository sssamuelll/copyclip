import asyncio
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

    events = []
    events_lock = threading.Condition()
    next_event_id = {"value": 1}

    def publish_event(kind: str, data: dict):
        with events_lock:
            ev = {
                "id": next_event_id["value"],
                "kind": kind,
                "data": data,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            next_event_id["value"] += 1
            events.append(ev)
            if len(events) > 500:
                del events[: len(events) - 500]
            events_lock.notify_all()

    def with_meta(payload: dict):
        payload.setdefault("meta", {})
        payload["meta"]["project"] = os.path.basename(root)
        payload["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
        return payload

    def _pagination(parsed):
        q = parse_qs(parsed.query or "")
        try:
            limit = max(1, min(int(q.get("limit", ["100"])[0]), 500))
        except Exception:
            limit = 100
        try:
            offset = max(0, int(q.get("offset", ["0"])[0]))
        except Exception:
            offset = 0
        return limit, offset

    def _parse_dt(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    def _evaluate_alerts(conn, pid):
        rules = conn.execute(
            "SELECT id,name,kind,severity,min_score,cooldown_min,enabled,last_triggered_at FROM alert_rules WHERE project_id=? AND enabled=1 ORDER BY id",
            (pid,),
        ).fetchall()
        risks = conn.execute(
            "SELECT area,severity,kind,rationale,score,created_at FROM risks WHERE project_id=? ORDER BY score DESC, id DESC",
            (pid,),
        ).fetchall()

        now = datetime.now(timezone.utc)
        fired = []
        for r in rules:
            rid, name, kind, severity, min_score, cooldown_min, enabled, last_t = r
            candidates = []
            for risk in risks:
                area, sev, knd, rationale, score, created_at = risk
                if kind and knd != kind:
                    continue
                if severity and sev != severity:
                    continue
                if int(score or 0) < int(min_score or 0):
                    continue
                candidates.append(risk)

            if not candidates:
                continue

            last_dt = _parse_dt(last_t)
            if last_dt is not None and (now - last_dt).total_seconds() < int(cooldown_min or 0) * 60:
                continue

            top = candidates[0]
            title = f"{name}: {top[0]}"
            detail = f"[{top[2]}/{top[1]}] score={top[4]} — {top[3]}"

            conn.execute(
                "INSERT INTO alert_events(project_id,rule_id,title,detail) VALUES(?,?,?,?)",
                (pid, rid, title, detail),
            )
            conn.execute(
                "UPDATE alert_rules SET last_triggered_at=? WHERE id=?",
                (now.isoformat(), rid),
            )
            fired.append({"rule": name, "title": title, "detail": detail})

        if fired:
            conn.commit()
        return fired

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

            if parsed.path == "/api/events":
                q = parse_qs(parsed.query or "")
                try:
                    cursor = int(q.get("cursor", ["0"])[0])
                except Exception:
                    cursor = 0

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                def write_event(ev):
                    payload = json.dumps(ev)
                    self.wfile.write(f"id: {ev['id']}\nevent: {ev['kind']}\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()

                # Initial hello event + backlog since cursor
                write_event({
                    "id": cursor,
                    "kind": "connected",
                    "data": {"cursor": cursor},
                    "ts": datetime.now(timezone.utc).isoformat(),
                })

                with events_lock:
                    backlog = [e for e in events if e["id"] > cursor]
                for ev in backlog:
                    write_event(ev)
                    cursor = ev["id"]

                # Stream updates for up to 30s per request
                deadline = time.time() + 30
                while time.time() < deadline:
                    with events_lock:
                        updates = [e for e in events if e["id"] > cursor]
                        if not updates:
                            events_lock.wait(timeout=2)
                            updates = [e for e in events if e["id"] > cursor]
                    for ev in updates:
                        write_event(ev)
                        cursor = ev["id"]
                return

            if parsed.path == "/api/overview":
                if not pid:
                    self._json(with_meta({"files": 0, "commits": 0, "decisions": 0, "modules": 0, "risks": 0, "issues": 0, "pulls": 0, "story": ""}))
                    return
                files = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
                commits = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
                decisions = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
                modules = conn.execute("SELECT COUNT(*) FROM modules WHERE project_id=?", (pid,)).fetchone()[0]
                risks = conn.execute("SELECT COUNT(*) FROM risks WHERE project_id=?", (pid,)).fetchone()[0]
                issues = conn.execute("SELECT COUNT(*) FROM issues WHERE project_id=?", (pid,)).fetchone()[0]
                pulls = conn.execute("SELECT COUNT(*) FROM pulls WHERE project_id=?", (pid,)).fetchone()[0]
                story = conn.execute("SELECT story FROM projects WHERE id=?", (pid,)).fetchone()[0]
                self._json(with_meta({
                    "files": files,
                    "commits": commits,
                    "decisions": decisions,
                    "modules": modules,
                    "risks": risks,
                    "issues": issues,
                    "pulls": pulls,
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
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                    return
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT path, size_bytes, language FROM files WHERE project_id=? ORDER BY path LIMIT ? OFFSET ?",
                    (pid, limit, offset),
                ).fetchall()
                self._json(with_meta({
                    "items": [{"path": r[0], "size": r[1], "language": r[2]} for r in rows],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }))
                return

            if parsed.path == "/api/impact":
                if not pid:
                    self._json(with_meta({"impacted_modules": []}))
                    return
                query = urlparse(self.path).query
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
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                    return
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT sha, author, message, date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT ? OFFSET ?",
                    (pid, limit, offset),
                ).fetchall()
                self._json(with_meta({
                    "items": [{"sha": r[0], "author": r[1], "message": r[2], "date": r[3]} for r in rows],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }))
                return

            if parsed.path == "/api/decisions":
                if not pid:
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                    return
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM decisions WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT id,title,summary,status,source_type,created_at FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (pid, limit, offset),
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
                        ],
                        "total": total,
                        "limit": limit,
                        "offset": offset,
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

            if parsed.path.startswith("/api/decisions/") and parsed.path.endswith("/history"):
                if not pid:
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
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
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM decision_history WHERE decision_id=?", (decision_id,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT id,action,from_status,to_status,note,created_at FROM decision_history WHERE decision_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (decision_id, limit, offset),
                ).fetchall()
                self._json(with_meta({
                    "items": [
                        {
                            "id": r[0],
                            "action": r[1],
                            "from_status": r[2],
                            "to_status": r[3],
                            "note": r[4],
                            "created_at": r[5],
                        }
                        for r in rows
                    ],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }))
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
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                    return
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM risks WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT area,severity,kind,rationale,score,created_at FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT ? OFFSET ?",
                    (pid, limit, offset),
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
                        ],
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                    })
                )
                return

            if parsed.path == "/api/issues":
                if not pid:
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                    return
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM issues WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT external_id,title,status,labels,author,url,source,created_at,updated_at FROM issues WHERE project_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (pid, limit, offset),
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
                        ],
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                    })
                )
                return

            if parsed.path == "/api/pulls":
                if not pid:
                    self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                    return
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM pulls WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT external_id,title,status,merged,labels,author,url,source,created_at,updated_at FROM pulls WHERE project_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (pid, limit, offset),
                ).fetchall()
                self._json(with_meta({
                    "items": [
                        {
                            "id": r[0],
                            "title": r[1],
                            "status": r[2],
                            "merged": bool(r[3]),
                            "labels": r[4].split(",") if r[4] else [],
                            "author": r[5],
                            "url": r[6],
                            "source": r[7],
                            "created_at": r[8],
                            "updated_at": r[9],
                        }
                        for r in rows
                    ],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }))
                return

            if parsed.path == "/api/risks/trends":
                if not pid:
                    self._json(with_meta({"latest": {}, "previous": {}, "delta": {}, "has_previous": False}))
                    return
                rows = conn.execute(
                    "SELECT summary_json, generated_at FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 2",
                    (pid,),
                ).fetchall()
                latest = json.loads(rows[0][0]) if rows else {}
                previous = json.loads(rows[1][0]) if len(rows) > 1 else {}
                latest_b = latest.get("risk_breakdown", {}) if isinstance(latest, dict) else {}
                prev_b = previous.get("risk_breakdown", {}) if isinstance(previous, dict) else {}
                keys = sorted(set(latest_b.keys()) | set(prev_b.keys()))
                delta = {k: int(latest_b.get(k, 0)) - int(prev_b.get(k, 0)) for k in keys}
                self._json(with_meta({
                    "latest": latest_b,
                    "previous": prev_b,
                    "delta": delta,
                    "has_previous": len(rows) > 1,
                }))
                return

            if parsed.path == "/api/alerts":
                if not pid:
                    self._json(with_meta({"fired": [], "events": []}))
                    return
                fired = _evaluate_alerts(conn, pid)
                limit, offset = _pagination(parsed)
                total = conn.execute("SELECT COUNT(*) FROM alert_events WHERE project_id=?", (pid,)).fetchone()[0]
                rows = conn.execute(
                    "SELECT id,rule_id,title,detail,created_at FROM alert_events WHERE project_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (pid, limit, offset),
                ).fetchall()
                self._json(with_meta({
                    "fired": fired,
                    "events": [
                        {"id": r[0], "rule_id": r[1], "title": r[2], "detail": r[3], "created_at": r[4]}
                        for r in rows
                    ],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }))
                return

            if parsed.path == "/api/alerts/rules":
                if not pid:
                    self._json(with_meta({"items": []}))
                    return
                rows = conn.execute(
                    "SELECT id,name,kind,severity,min_score,cooldown_min,enabled,last_triggered_at FROM alert_rules WHERE project_id=? ORDER BY id",
                    (pid,),
                ).fetchall()
                self._json(with_meta({
                    "items": [
                        {
                            "id": r[0],
                            "name": r[1],
                            "kind": r[2],
                            "severity": r[3],
                            "min_score": r[4],
                            "cooldown_min": r[5],
                            "enabled": bool(r[6]),
                            "last_triggered_at": r[7],
                        }
                        for r in rows
                    ]
                }))
                return

            if parsed.path == "/api/export/weekly":
                if not pid:
                    self._json(with_meta({"markdown": "# Weekly Brief\n\nNo data available.", "summary": {}}))
                    return
                q = parse_qs(parsed.query or "")
                try:
                    days = max(1, min(int(q.get("days", ["7"])[0]), 30))
                except Exception:
                    days = 7

                commits_count = conn.execute(
                    "SELECT COUNT(*) FROM commits WHERE project_id=? AND datetime(date) >= datetime('now', ?)",
                    (pid, f"-{days} days"),
                ).fetchone()[0]
                issues_count = conn.execute(
                    "SELECT COUNT(*) FROM issues WHERE project_id=? AND datetime(created_at) >= datetime('now', ?)",
                    (pid, f"-{days} days"),
                ).fetchone()[0]
                pulls_count = conn.execute(
                    "SELECT COUNT(*) FROM pulls WHERE project_id=? AND datetime(created_at) >= datetime('now', ?)",
                    (pid, f"-{days} days"),
                ).fetchone()[0]
                decisions_open = conn.execute(
                    "SELECT COUNT(*) FROM decisions WHERE project_id=? AND status != 'resolved'",
                    (pid,),
                ).fetchone()[0]

                top_risks = conn.execute(
                    "SELECT area,severity,kind,score,rationale FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 5",
                    (pid,),
                ).fetchall()
                recent_alerts = conn.execute(
                    "SELECT title,detail,created_at FROM alert_events WHERE project_id=? ORDER BY id DESC LIMIT 5",
                    (pid,),
                ).fetchall()
                recent_decisions = conn.execute(
                    "SELECT id,title,status,created_at FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 5",
                    (pid,),
                ).fetchall()

                md = []
                md.append("# Weekly Executive Brief")
                md.append("")
                md.append(f"Period: last {days} days")
                md.append("")
                md.append("## Summary")
                md.append(f"- Commits: {commits_count}")
                md.append(f"- New Issues: {issues_count}")
                md.append(f"- New PRs: {pulls_count}")
                md.append(f"- Open Decisions: {decisions_open}")
                md.append("")

                md.append("## Top Risks")
                if top_risks:
                    for r in top_risks:
                        md.append(f"- [{r[1]}/{r[2]}] {r[0]} (score {r[3]}): {r[4]}")
                else:
                    md.append("- No risks registered.")
                md.append("")

                md.append("## Recent Decisions")
                if recent_decisions:
                    for d in recent_decisions:
                        md.append(f"- #{d[0]} [{d[2]}] {d[1]} ({str(d[3])[:10]})")
                else:
                    md.append("- No recent decisions.")
                md.append("")

                md.append("## Recent Alerts")
                if recent_alerts:
                    for a in recent_alerts:
                        md.append(f"- {a[0]} ({str(a[2])[:19]}): {a[1]}")
                else:
                    md.append("- No alert activity.")

                summary = {
                    "days": days,
                    "commits": commits_count,
                    "issues": issues_count,
                    "pulls": pulls_count,
                    "open_decisions": decisions_open,
                    "top_risks_count": len(top_risks),
                    "recent_alerts_count": len(recent_alerts),
                }
                self._json(with_meta({"markdown": "\n".join(md), "summary": summary}))
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
                note = (data.get("note") or "").strip()
                allowed = {"proposed", "accepted", "unresolved", "resolved", "superseded"}
                if status not in allowed:
                    self._json({"error": "invalid_status", "allowed": sorted(allowed)}, 400)
                    return

                prev = conn.execute(
                    "SELECT status FROM decisions WHERE id=? AND project_id=?",
                    (decision_id, pid),
                ).fetchone()
                prev_status = prev[0] if prev else None

                # Quality gate: cannot resolve without evidence.
                if status == "resolved":
                    refs_count = conn.execute(
                        "SELECT COUNT(*) FROM decision_refs WHERE decision_id=?",
                        (decision_id,),
                    ).fetchone()[0]
                    has_note = len(note) >= 12
                    if refs_count == 0 and not has_note:
                        self._json(
                            {
                                "error": "quality_gate_blocked",
                                "message": "Resolution requires evidence: at least one ref or a meaningful note.",
                                "decision_id": decision_id,
                            },
                            409,
                        )
                        return

                conn.execute(
                    "UPDATE decisions SET status=?, resolved_at=CASE WHEN ?='resolved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=? AND project_id=?",
                    (status, status, decision_id, pid),
                )
                conn.execute(
                    "INSERT INTO decision_history(decision_id,action,from_status,to_status,note) VALUES(?,?,?,?,?)",
                    (decision_id, "status_change", prev_status, status, note or "status updated via API"),
                )
                conn.commit()
                publish_event("decision.status_changed", {"decision_id": decision_id, "from": prev_status, "to": status})
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

            if parsed.path == "/api/alerts/rules":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                name = (data.get("name") or "").strip()
                if not name:
                    self._json({"error": "name_required"}, 400)
                    return
                kind = (data.get("kind") or "").strip() or None
                severity = (data.get("severity") or "").strip() or None
                min_score = int(data.get("min_score") or 0)
                cooldown_min = int(data.get("cooldown_min") or 60)
                enabled = 1 if bool(data.get("enabled", True)) else 0
                conn.execute(
                    "INSERT OR REPLACE INTO alert_rules(project_id,name,kind,severity,min_score,cooldown_min,enabled,last_triggered_at) VALUES(?,?,?,?,?,?,?,NULL)",
                    (pid, name, kind, severity, min_score, cooldown_min, enabled),
                )
                conn.commit()
                self._json({"ok": True, "name": name})
                return

            if parsed.path == "/api/github/sync":
                from .analyzer import analyze
                try:
                    summary = asyncio.run(analyze(root))
                    publish_event("github.sync.completed", {"issues": summary.get("issues", 0), "pulls": summary.get("pulls", 0)})
                    self._json(with_meta({"ok": True, "summary": summary}))
                except Exception as e:
                    self._json({"error": "github_sync_failed", "message": str(e)}, 500)
                return

            if parsed.path == "/api/ask":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                question = (data.get("question") or "").strip()
                if not question:
                    self._json({"error": "question_required"}, 400)
                    return

                # Lightweight retrieval over indexed artifacts.
                terms = [t for t in re.findall(r"[a-zA-Z0-9_\-]{3,}", question.lower()) if t not in {"the", "and", "for", "with", "that", "this", "what", "how"}]

                evidence = []

                # Decisions
                for r in conn.execute(
                    "SELECT id,title,summary,status FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 200",
                    (pid,),
                ).fetchall():
                    text = f"{r[1]} {r[2] or ''} {r[3]}".lower()
                    score = sum(1 for t in terms if t in text)
                    if score > 0:
                        evidence.append({
                            "score": score + 2,
                            "type": "decision",
                            "id": r[0],
                            "title": r[1],
                            "snippet": (r[2] or "")[:240],
                        })

                # Risks
                for r in conn.execute(
                    "SELECT area,kind,rationale,score FROM risks WHERE project_id=? ORDER BY score DESC LIMIT 300",
                    (pid,),
                ).fetchall():
                    text = f"{r[0]} {r[1]} {r[2] or ''}".lower()
                    score = sum(1 for t in terms if t in text)
                    if score > 0:
                        evidence.append({
                            "score": score + 1,
                            "type": "risk",
                            "id": r[0],
                            "title": f"{r[0]} ({r[1]})",
                            "snippet": (r[2] or "")[:240],
                        })

                # Commits
                for r in conn.execute(
                    "SELECT sha,message,date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 300",
                    (pid,),
                ).fetchall():
                    text = f"{r[0]} {r[1] or ''}".lower()
                    score = sum(1 for t in terms if t in text)
                    if score > 0:
                        evidence.append({
                            "score": score,
                            "type": "commit",
                            "id": r[0],
                            "title": (r[1] or "")[:120],
                            "snippet": f"commit {r[0][:7]} on {(r[2] or '')[:10]}",
                        })

                # Prefer governance artifacts over raw activity noise.
                type_boost = {"decision": 1000, "risk": 500, "commit": 100}
                for e in evidence:
                    e["rank"] = type_boost.get(e["type"], 0) + e["score"]

                evidence.sort(key=lambda x: x["rank"], reverse=True)

                # Deduplicate by (type,id)
                seen = set()
                top = []
                for e in evidence:
                    k = (e["type"], e["id"])
                    if k in seen:
                        continue
                    seen.add(k)
                    top.append(e)
                    if len(top) >= 5:
                        break

                if not top:
                    self._json(with_meta({
                        "answer": "I don’t have enough indexed evidence to answer that yet. Re-run analyze or ask with more specific entities (module/file/decision).",
                        "citations": [],
                        "grounded": False,
                    }))
                    return

                citations = []
                lines = []
                for e in top:
                    if e["type"] == "decision":
                        citations.append({"type": "decision", "id": e["id"], "label": f"decision #{e['id']}"})
                        lines.append(f"Decision #{e['id']}: {e['title']}")
                    elif e["type"] == "risk":
                        citations.append({"type": "risk", "id": e["id"], "label": e["title"]})
                        lines.append(f"Risk signal: {e['title']}")
                    elif e["type"] == "commit":
                        citations.append({"type": "commit", "id": e["id"], "label": f"commit {e['id'][:7]}"})
                        lines.append(f"Recent commit: {e['title']}")

                answer = "Based on indexed project evidence, here are the strongest signals:\n- " + "\n- ".join(lines)

                # Strict grounding contract: no claim without citations.
                if not citations:
                    self._json({"error": "ungrounded_answer_blocked"}, 500)
                    return

                self._json(with_meta({
                    "answer": answer,
                    "citations": citations,
                    "grounded": True,
                }))
                return

            if parsed.path == "/api/assemble-context":
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
                    # Filter valid files securely
                    valid_files = []
                    root_path = Path(root).resolve()
                    for f in selected_files:
                        p = (root_path / f).resolve()
                        if p.is_relative_to(root_path) and p.exists() and p.is_file():
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
                            adv_res = asyncio.run(client.minimize_code_contextually(advisor_prompt, "text", "en"))
                            if adv_res and "OK" not in adv_res.upper():
                                warnings.append(adv_res.strip())
                        except:
                            pass

                final_context = "\n\n".join(prompt_parts)
                self._json({"context": final_context, "warnings": warnings})
                return

            if parsed.path == "/api/config":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                data = json.loads(raw.decode("utf-8"))
                for k, v in data.items():
                    conn.execute("INSERT INTO config(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
                conn.commit()
                self._json({"status": "ok"})
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
                conn.execute(
                    "INSERT INTO decision_history(decision_id,action,from_status,to_status,note) VALUES(?,?,?,?,?)",
                    (cur.lastrowid, "created", None, "proposed", "decision created"),
                )
                conn.commit()
                publish_event("decision.created", {"decision_id": cur.lastrowid, "title": title})
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
                conn.execute(
                    "INSERT INTO decision_history(decision_id,action,from_status,to_status,note) VALUES(?,?,?,?,?)",
                    (decision_id, "ref_added", None, None, f"{ref_type}: {ref_value}"),
                )
                conn.commit()
                publish_event("decision.ref_added", {"decision_id": decision_id, "ref_type": ref_type, "ref_value": ref_value})
                self._json({"ok": True, "decision_id": decision_id, "ref_type": ref_type, "ref_value": ref_value})
                return

            self._json({"error": "not_found"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[INFO] CopyClip Intelligence running at http://127.0.0.1:{port}")
    print("[INFO] Press Ctrl+C to stop")
    server.serve_forever()
