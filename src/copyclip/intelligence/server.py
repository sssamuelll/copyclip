import asyncio
import json
import os
import re
import sqlite3
import sys
import threading
import uuid
import subprocess
from fnmatch import fnmatch
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .context_bundle_builder import build_context_bundle
from .cognitive_debt import build_debt_breakdown, severity_to_fog
from .debt_remediation import build_remediation_plan
from .handoff import (
    build_handoff_packet,
    build_handoff_review_summary,
    get_handoff_packet,
    get_handoff_review_summary,
    list_handoff_packets,
    save_handoff_packet,
    save_handoff_review_summary,
    update_handoff_packet,
)
from .db import connect, init_schema, init_cuaderno_schema
from .playground import (
    MarimoNotInstalledError,
    PlaygroundError,
    PlaygroundLaunchRequest,
    StubMarimoRunner,
    launch_playground,
)
from .reacquaintance import build_reacquaintance_briefing, record_reacquaintance_visit
from .server_context import ServerContext
from .server_events import handle_events_get, publish_event as publish_event_impl
from .server_helpers import json_response, pagination, parse_dt, project_id, read_json_body, sse_response, with_meta as add_meta
from .server_routes_core import handle_health_get, handle_settings_get, handle_settings_post
from .phases import (
    PHASE_COMPLETED,
    PHASE_DISCOVERY,
    PHASE_ERROR,
    PHASE_GIT_HISTORY,
    PHASE_IMPORT_GRAPH,
    PHASE_METADATA_HASH,
    PHASE_RISK_SIGNALS,
    PHASE_SNAPSHOTS,
)


def _load_ui_html() -> str:
    ui_path = Path(__file__).resolve().parent / "ui" / "index.html"
    if ui_path.exists():
        return ui_path.read_text(encoding="utf-8")
    return "<html><body><h1>CopyClip UI not found</h1></body></html>"


_HTML = _load_ui_html()


# Back-compat shim for existing tests and callers that import the old helper.
def _project_id(conn: sqlite3.Connection, root: str):
    return project_id(conn, root)


def run_server(
    project_root: str,
    port: int = 4310,
    *,
    playground_runner=None,
) -> None:
    root = os.path.abspath(project_root)

    events = []
    events_lock = threading.Condition()
    next_event_id = {"value": 1}

    analysis_lock = threading.Lock()
    cancel_lock = threading.Lock()
    cancel_events = {}

    ctx = ServerContext(
        root=root,
        html=_HTML,
        events=events,
        events_lock=events_lock,
        next_event_id=next_event_id,
        analysis_lock=analysis_lock,
        cancel_lock=cancel_lock,
        cancel_events=cancel_events,
    )

    # Playground subprocess runner. Tests inject a Mock via the keyword arg.
    # Real implementation lands in src/copyclip/intelligence/marimo_runner.py
    # (issue #88). Contract: that module MUST expose either a class named
    # `MarimoRunner` instantiable with no args, OR a factory `create_runner()
    # -> MarimoRunner`. Update this block accordingly when #88 merges. The
    # StubMarimoRunner is the safety net so endpoint shape and the frontend
    # (#89) stay exercisable end-to-end until then.
    if playground_runner is None:
        try:
            from .marimo_runner import create_runner as _create_runner  # type: ignore[attr-defined]
            playground_runner = _create_runner()
        except ImportError:
            try:
                from .marimo_runner import MarimoRunner as _RealMarimoRunner  # type: ignore[attr-defined]
                playground_runner = _RealMarimoRunner()
            except ImportError:
                playground_runner = StubMarimoRunner()

    def with_meta(payload: dict):
        return add_meta(root, payload)

    def publish_event(kind: str, data: dict):
        return publish_event_impl(ctx, kind, data)

    def _count_project_files(base_root: str) -> int:
        ignored_dirs = {".git", ".venv", "node_modules", ".copyclip", "dist", "build", "__pycache__"}
        total = 0
        for base, dirs, files in os.walk(base_root):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            total += len(files)
        return total

    PHASE_ORDER = {
        PHASE_DISCOVERY: 10,
        PHASE_METADATA_HASH: 20,
        PHASE_IMPORT_GRAPH: 30,
        PHASE_GIT_HISTORY: 40,
        PHASE_RISK_SIGNALS: 50,
        PHASE_SNAPSHOTS: 60,
        PHASE_COMPLETED: 100,
        PHASE_ERROR: 999,
    }

    def _set_job_phase(job_id: str, phase: str, processed: int, total_local: int, message: str):
        conn_p = connect(root)
        init_schema(conn_p)
        row = conn_p.execute("SELECT phase FROM analysis_jobs WHERE id=?", (job_id,)).fetchone()
        current_phase = row[0] if row else None

        # Keep monotonic progression (except explicit error/completed handling).
        if (
            current_phase in PHASE_ORDER
            and phase in PHASE_ORDER
            and PHASE_ORDER[phase] < PHASE_ORDER[current_phase]
        ):
            conn_p.close()
            return

        conn_p.execute(
            "UPDATE analysis_jobs SET phase=?, processed=?, total=?, message=? WHERE id=?",
            (phase, int(processed or 0), int(total_local or 0), str(message or ""), job_id),
        )
        conn_p.commit()
        conn_p.close()

    def _job_payload(row):
        # row: id,status,phase,processed,total,message,checkpoint_cursor,checkpoint_every,started_at,finished_at
        processed = int(row[3] or 0)
        total = int(row[4] or 0)
        started_at = row[8]
        elapsed = None
        throughput = None
        eta_sec = None
        if started_at:
            st = parse_dt(started_at)
            if st:
                elapsed = max(0.0, (datetime.now(timezone.utc) - st).total_seconds())
                if elapsed > 0:
                    throughput = processed / elapsed
                    remaining = max(0, total - processed)
                    eta_sec = int(remaining / throughput) if throughput > 0 else None
        return {
            "id": row[0],
            "status": row[1],
            "phase": row[2],
            "processed": processed,
            "total": total,
            "message": row[5],
            "checkpoint_cursor": int(row[6] or 0),
            "checkpoint_every": int(row[7] or 0),
            "started_at": started_at,
            "finished_at": row[9],
            "throughput_fps": round(throughput, 2) if throughput is not None else None,
            "eta_sec": eta_sec,
        }

    def _start_analysis_job(pid: int, resume_from: int = 0, checkpoint_every: int = 500):
        job_id = str(uuid.uuid4())
        total = _count_project_files(root)
        cancel_event = threading.Event()
        conn_j = connect(root)
        init_schema(conn_j)
        conn_j.execute(
            "INSERT INTO analysis_jobs(id,project_id,status,phase,processed,total,message,checkpoint_cursor,checkpoint_every) VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, pid, "queued", "queued", int(resume_from or 0), total, "queued", int(resume_from or 0), int(checkpoint_every or 500)),
        )
        conn_j.commit()
        conn_j.close()
        with cancel_lock:
            cancel_events[job_id] = cancel_event

        def _runner():
            with analysis_lock:
                conn_r = connect(root)
                init_schema(conn_r)
                conn_r.execute(
                    "UPDATE analysis_jobs SET status='running', phase=?, processed=?, checkpoint_cursor=?, message=? WHERE id=?",
                    (PHASE_DISCOVERY, int(resume_from or 0), int(resume_from or 0), "analyzing project", job_id),
                )
                conn_r.commit()
                conn_r.close()
                publish_event("analyze.progress", {"job_id": job_id, "status": "running", "phase": "analyzing", "processed": int(resume_from or 0), "total": total})

                try:
                    from .analyzer import AnalysisCanceled, analyze

                    def _on_progress(phase, processed, total_local, message):
                        _set_job_phase(job_id, phase, int(processed or 0), int(total_local or 0), str(message or ""))
                        publish_event(
                            "analyze.progress",
                            {
                                "job_id": job_id,
                                "status": "running",
                                "phase": phase,
                                "processed": int(processed or 0),
                                "total": int(total_local or 0),
                                "message": str(message or ""),
                            },
                        )

                    def _on_checkpoint(cursor_value):
                        conn_cp = connect(root)
                        init_schema(conn_cp)
                        conn_cp.execute(
                            "UPDATE analysis_jobs SET checkpoint_cursor=? WHERE id=?",
                            (int(cursor_value or 0), job_id),
                        )
                        conn_cp.commit()
                        conn_cp.close()

                    summary = asyncio.run(
                        analyze(
                            root,
                            progress_cb=_on_progress,
                            start_cursor=int(resume_from or 0),
                            checkpoint_every=int(checkpoint_every or 500),
                            checkpoint_cb=_on_checkpoint,
                            should_cancel=cancel_event.is_set,
                        )
                    )
                    conn_d = connect(root)
                    init_schema(conn_d)
                    conn_d.execute(
                        "UPDATE analysis_jobs SET status='completed', phase=?, processed=?, total=?, checkpoint_cursor=?, message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                        (PHASE_COMPLETED, total, total, total, "analysis completed", job_id),
                    )
                    conn_d.commit()
                    conn_d.close()
                    publish_event("analyze.completed", {"job_id": job_id, "summary": summary})
                except AnalysisCanceled:
                    conn_c = connect(root)
                    init_schema(conn_c)
                    conn_c.execute(
                        "UPDATE analysis_jobs SET status='canceled', phase=?, message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                        (PHASE_ERROR, "analysis canceled by user", job_id),
                    )
                    conn_c.commit()
                    conn_c.close()
                    publish_event("analyze.canceled", {"job_id": job_id})
                except Exception as e:
                    conn_e = connect(root)
                    init_schema(conn_e)
                    conn_e.execute(
                        "UPDATE analysis_jobs SET status='failed', phase=?, message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                        (PHASE_ERROR, str(e), job_id),
                    )
                    conn_e.commit()
                    conn_e.close()
                    publish_event("analyze.failed", {"job_id": job_id, "error": str(e)})
                finally:
                    with cancel_lock:
                        cancel_events.pop(job_id, None)

        threading.Thread(target=_runner, daemon=True).start()
        return job_id

    # Boot-time schema initialization. Ensures all tables (including cuaderno_*)
    # exist before any HTTP handler runs, so GET/PATCH endpoints don't fail with
    # "no such table" if hit before the first POST.
    _boot_conn = connect(root)
    try:
        init_schema(_boot_conn)
        init_cuaderno_schema(_boot_conn)
    finally:
        _boot_conn.close()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, payload, code=200):
            json_response(self, payload, code=code)

        def do_GET(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            try:
                init_schema(conn)
                pid = project_id(conn, root)

                if parsed.path == "/api/playground":
                    items = playground_runner.list() if hasattr(playground_runner, "list") else []
                    self._json({"items": items})
                    return

                if parsed.path.startswith("/api/playground/") and parsed.path.endswith("/status"):
                    if not pid:
                        self._json({"error": "run_analyze_first"}, 400)
                        return
                    playground_id = parsed.path[len("/api/playground/"):-len("/status")]
                    if not playground_id or "/" in playground_id:
                        self._json({"error": "missing_playground_id"}, 400)
                        return
                    status = playground_runner.status(playground_id)
                    self._json({"status": status, "id": playground_id})
                    return

                if parsed.path == "/":
                    body = ctx.html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if parsed.path == "/api/events":
                    handle_events_get(self, ctx, parsed)
                    return

                if parsed.path == "/api/health":
                    handle_health_get(self, ctx)
                    return

                if parsed.path == "/api/reacquaintance":
                    q = parse_qs(parsed.query or "")
                    mode = (q.get("mode", ["last_seen"])[0] or "last_seen").strip()
                    window = (q.get("window", ["7d"])[0] or "7d").strip()
                    checkpoint = (q.get("checkpoint", [None])[0] or None)
                    payload = build_reacquaintance_briefing(root, baseline_mode=mode, window=window, checkpoint_name=checkpoint)
                    record_reacquaintance_visit(root, visit_kind="reacquaintance_api", source="server")
                    self._json(with_meta(payload))
                    return

                if parsed.path == "/api/cognitive-debt/breakdown":
                    if not pid:
                        self._json({"error": "project_not_indexed"}, 404)
                        return
                    q = parse_qs(parsed.query or "")
                    scope_kind = (q.get("scope", ["file"])[0] or "file").strip()
                    scope_id = (q.get("id", [""])[0] or "").strip()
                    if scope_kind not in {"file", "module", "project"}:
                        self._json({"error": "invalid_scope_kind"}, 400)
                        return
                    if scope_kind in {"file", "module"} and not scope_id:
                        self._json({"error": "scope_id_required"}, 400)
                        return
                    try:
                        breakdown = build_debt_breakdown(conn, pid, scope_kind, scope_id)
                    except ValueError as e:
                        msg = str(e)
                        if msg.startswith("module_not_found:"):
                            self._json({"error": "module_not_found", "module": msg.split(":", 1)[1]}, 404)
                            return
                        self._json({"error": msg}, 400)
                        return
                    self._json(with_meta({"breakdown": breakdown}))
                    return

                if parsed.path == "/api/cognitive-debt/remediation":
                    if not pid:
                        self._json({"error": "project_not_indexed"}, 404)
                        return
                    q = parse_qs(parsed.query or "")
                    scope_kind = (q.get("scope", ["file"])[0] or "file").strip()
                    scope_id = (q.get("id", [""])[0] or "").strip()
                    if scope_kind not in {"file", "module", "project"}:
                        self._json({"error": "invalid_scope_kind"}, 400)
                        return
                    if scope_kind in {"file", "module"} and not scope_id:
                        self._json({"error": "scope_id_required"}, 400)
                        return
                    try:
                        breakdown = build_debt_breakdown(conn, pid, scope_kind, scope_id)
                    except ValueError as e:
                        msg = str(e)
                        if msg.startswith("module_not_found:"):
                            self._json({"error": "module_not_found", "module": msg.split(":", 1)[1]}, 404)
                            return
                        self._json({"error": msg}, 400)
                        return
                    plan = build_remediation_plan(conn, pid, breakdown)
                    self._json(with_meta({"breakdown": breakdown, "plan": plan}))
                    return

                if parsed.path == "/api/cognitive-load":
                    # Serves the v1 factor-model score from build_debt_breakdown
                    # under the legacy field names. fog_level + decision_linked
                    # are kept for backward-compat; severity is the v1 vocab.
                    if not pid:
                        self._json(with_meta({"items": [], "total": 0, "last_review_at": None}))
                        return

                    last_snap = conn.execute(
                        "SELECT generated_at FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
                        (pid,),
                    ).fetchone()
                    last_review = last_snap[0] if last_snap else None

                    rows = conn.execute(
                        """
                        SELECT i.module, COALESCE(i.complexity,0) AS complexity,
                               COALESCE((SELECT COUNT(*) FROM file_changes fc WHERE fc.project_id=i.project_id AND fc.file_path=i.path),0) AS churn
                        FROM analysis_file_insights i
                        WHERE i.project_id=? AND i.module IS NOT NULL AND i.module != ''
                        """,
                        (pid,),
                    ).fetchall()

                    module_stats: dict[str, dict[str, int]] = {}
                    for r in rows:
                        module = r[0]
                        agg = module_stats.setdefault(module, {"files": 0, "complexity": 0, "churn": 0})
                        agg["files"] += 1
                        agg["complexity"] += int(r[1] or 0)
                        agg["churn"] += int(r[2] or 0)

                    decision_link_rows = conn.execute(
                        "SELECT link_type, target_pattern FROM decision_links WHERE project_id=?",
                        (pid,),
                    ).fetchall()

                    def _module_decision_linked(module: str) -> bool:
                        for lr in decision_link_rows:
                            ltype = (lr[0] or "").strip()
                            pattern = (lr[1] or "").strip()
                            if ltype == "module" and pattern == module:
                                return True
                            if ltype == "file_glob" and module in pattern:
                                return True
                        return False

                    items = []
                    for module, agg in module_stats.items():
                        try:
                            breakdown = build_debt_breakdown(conn, pid, "module", module)
                        except ValueError:
                            # Module visible in insights but no aggregate rows — skip rather than guess.
                            continue
                        files = max(1, int(agg["files"]))
                        severity = breakdown["score"]["severity"]
                        items.append({
                            "module": module,
                            "files": files,
                            "churn": int(agg["churn"]),
                            "avg_complexity": round(agg["complexity"] / files, 2),
                            "decision_linked": _module_decision_linked(module),
                            "cognitive_debt_score": breakdown["score"]["value"],
                            "severity": severity,
                            "fog_level": severity_to_fog(severity),
                        })

                    items.sort(key=lambda x: x["cognitive_debt_score"], reverse=True)
                    self._json(with_meta({
                        "items": items[:80],
                        "total": len(items),
                        "last_review_at": last_review,
                    }))
                    return

                if parsed.path == "/api/story/timeline":
                    if not pid:
                        self._json(with_meta({"items": [], "total": 0, "range_days": 30}))
                        return

                    q = parse_qs(parsed.query or "")
                    raw_range = (q.get("range", ["30d"])[0] or "30d").strip().lower()
                    m = re.match(r"^(\d+)(d)?$", raw_range)
                    range_days = int(m.group(1)) if m else 30
                    range_days = max(1, min(range_days, 365))

                    rows = conn.execute(
                        """
                        SELECT id, generated_at, focus_areas_json, major_changes_json, open_questions_json, summary_json
                        FROM story_snapshots
                        WHERE project_id=? AND datetime(generated_at) >= datetime('now', ?)
                        ORDER BY datetime(generated_at) DESC
                        LIMIT 200
                        """,
                        (pid, f"-{range_days} days"),
                    ).fetchall()

                    items = []
                    for r in rows:
                        try:
                            focus_areas = json.loads(r[2] or "[]")
                        except Exception:
                            focus_areas = []
                        try:
                            major_changes = json.loads(r[3] or "[]")
                        except Exception:
                            major_changes = []
                        try:
                            open_questions = json.loads(r[4] or "[]")
                        except Exception:
                            open_questions = []
                        try:
                            summary = json.loads(r[5] or "{}")
                        except Exception:
                            summary = {}

                        items.append(
                            {
                                "id": int(r[0]),
                                "generated_at": r[1],
                                "focus_areas": focus_areas,
                                "major_changes": major_changes,
                                "open_questions": open_questions,
                                "summary": summary,
                            }
                        )

                    self._json(with_meta({
                        "items": items,
                        "total": len(items),
                        "range_days": range_days,
                    }))
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

                    risk_rows = conn.execute(
                        "SELECT area, score FROM risks WHERE project_id=?",
                        (pid,),
                    ).fetchall()
                    risk_map = {r[0]: int(r[1] or 0) for r in risk_rows}

                    rows = conn.execute(
                        "SELECT path, size_bytes FROM files WHERE project_id=? ORDER BY size_bytes DESC LIMIT 500",
                        (pid,),
                    ).fetchall()
                    items = [
                        {
                            "path": r[0],
                            "size": int(r[1] or 0),
                            "score": int(risk_map.get(r[0], 0)),
                        }
                        for r in rows
                    ]
                    self._json(with_meta({"items": items}))
                    return

                if parsed.path == "/api/files":
                    if not pid:
                        self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                        return
                    limit, offset = pagination(parsed)
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

                if parsed.path == "/api/module/source":
                    if not pid:
                        self._json(with_meta({"module": "", "files": []}))
                        return
                    q = parse_qs(parsed.query or "")
                    module_name = (q.get("module", [""])[0] or "").strip()
                    if not module_name:
                        self._json(with_meta({"module": "", "files": []}))
                        return
                    rows = conn.execute(
                        "SELECT DISTINCT path FROM analysis_file_insights WHERE project_id=? AND module=? LIMIT 10",
                        (pid, module_name),
                    ).fetchall()
                    result_files = []
                    root_path = Path(root).resolve()
                    for (rel_path,) in rows:
                        fp = (root_path / rel_path).resolve()
                        if not fp.is_relative_to(root_path) or not fp.exists() or not fp.is_file():
                            continue
                        try:
                            raw = fp.read_bytes()
                            if b"\x00" in raw[:1024]:
                                continue  # skip binary
                            content = raw.decode("utf-8", errors="replace")
                            if len(content) > 102400:
                                content = content[:102400] + "\n// ... truncated (100KB limit)"
                            ext = fp.suffix.lstrip(".")
                            lang_map = {"py": "python", "js": "javascript", "ts": "javascript", "tsx": "javascript", "css": "css", "json": "javascript"}
                            result_files.append({"path": rel_path, "content": content, "language": lang_map.get(ext, "")})
                        except Exception:
                            continue
                    self._json(with_meta({"module": module_name, "files": result_files}))
                    return

                if parsed.path == "/api/module/symbols":
                    if not pid:
                        self._json(with_meta({"module": "", "symbols": []}))
                        return
                    q = parse_qs(parsed.query or "")
                    module_name = (q.get("module", [""])[0] or "").strip()
                    if not module_name:
                        self._json(with_meta({"module": "", "symbols": []}))
                        return
                    rows = conn.execute(
                        "SELECT id, name, kind, file_path, line_start, line_end, parent_symbol_id FROM symbols WHERE project_id=? AND module=? ORDER BY file_path, line_start",
                        (pid, module_name),
                    ).fetchall()
                    symbols = []
                    symbol_ids = {r[0] for r in rows}
                    for r in rows:
                        sid, name, kind, fpath, lstart, lend, parent_id = r
                        # Get methods (children)
                        methods = [row[0] for row in conn.execute(
                            "SELECT name FROM symbols WHERE parent_symbol_id=? AND project_id=?", (sid, pid)
                        ).fetchall()] if kind == "class" else []
                        # Get calls (outgoing)
                        calls = [row[0] for row in conn.execute(
                            "SELECT s.name FROM symbol_edges e JOIN symbols s ON e.to_symbol_id=s.id WHERE e.from_symbol_id=? AND e.edge_type='calls'", (sid,)
                        ).fetchall()]
                        # Get called_by (incoming)
                        called_by = [row[0] for row in conn.execute(
                            "SELECT s.name FROM symbol_edges e JOIN symbols s ON e.from_symbol_id=s.id WHERE e.to_symbol_id=? AND e.edge_type='calls'", (sid,)
                        ).fetchall()]
                        # Get inherits
                        inherits = [row[0] for row in conn.execute(
                            "SELECT s.name FROM symbol_edges e JOIN symbols s ON e.to_symbol_id=s.id WHERE e.from_symbol_id=? AND e.edge_type='inherits'", (sid,)
                        ).fetchall()]
                        symbols.append({
                            "name": name, "kind": kind, "file_path": fpath,
                            "line_start": lstart, "line_end": lend,
                            "methods": methods, "calls": calls,
                            "called_by": called_by, "inherits": inherits,
                        })
                    self._json(with_meta({"module": module_name, "symbols": symbols}))
                    return

                if parsed.path == "/api/context-bundle":
                    if not pid:
                        self._json(with_meta({"selected_files": [], "manifest": [], "total_candidates": 0}))
                        return
                    q = parse_qs(parsed.query or "")
                    question = (q.get("q", [""])[0] or "").strip()
                    try:
                        max_files = max(1, min(int((q.get("max_files", ["20"])[0])), 100))
                    except Exception:
                        max_files = 20
                    bundle = build_context_bundle(conn, pid, question, max_files=max_files)
                    self._json(with_meta(bundle))
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
                    limit, offset = pagination(parsed)
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

                if parsed.path == "/api/archaeology":
                    if not pid:
                        self._json(with_meta({"file": None, "commits": [], "related_decisions": []}))
                        return
                    params = parse_qs(parsed.query or "")
                    target_file = (params.get("file", [""])[0] or "").strip()
                    if not target_file:
                        self._json({"error": "file_required", "message": "Query param 'file' is required"}, 400)
                        return

                    commits = []
                    try:
                        proc = subprocess.run(
                            [
                                "git",
                                "log",
                                "--pretty=format:%H\t%an\t%ad\t%s",
                                "--date=iso",
                                "-n",
                                "12",
                                "--",
                                target_file,
                            ],
                            cwd=root,
                            capture_output=True,
                            text=True,
                            timeout=8,
                            check=False,
                        )
                        for line in (proc.stdout or "").splitlines():
                            parts = line.split("\t", 3)
                            if len(parts) != 4:
                                continue
                            sha, author, date, message = parts
                            commits.append({
                                "sha": sha,
                                "author": author,
                                "date": date,
                                "message": message,
                            })
                    except Exception:
                        commits = []

                    rows = conn.execute(
                        """
                        SELECT d.id, d.title, d.status, d.source_type, dr.ref_type, dr.ref_value
                        FROM decisions d
                        LEFT JOIN decision_refs dr ON dr.decision_id = d.id
                        WHERE d.project_id=?
                        ORDER BY d.id DESC
                        """,
                        (pid,),
                    ).fetchall()

                    related = {}
                    for r in rows:
                        did, title, status, source_type, ref_type, ref_value = r
                        match = False
                        ref_value = ref_value or ""
                        if ref_type == "file" and ref_value == target_file:
                            match = True
                        elif ref_type == "commit" and any(c["sha"].startswith(ref_value) for c in commits):
                            match = True
                        elif ref_type == "doc" and target_file.lower() in ref_value.lower():
                            match = True

                        if match:
                            if did not in related:
                                related[did] = {
                                    "id": did,
                                    "title": title,
                                    "status": status,
                                    "source_type": source_type,
                                    "matched_refs": [],
                                }
                            related[did]["matched_refs"].append({
                                "ref_type": ref_type,
                                "ref_value": ref_value,
                            })

                    self._json(with_meta({
                        "file": target_file,
                        "commits": commits,
                        "related_decisions": list(related.values()),
                    }))
                    return

                if parsed.path == "/api/handoff-packets":
                    if not pid:
                        self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                        return
                    limit, offset = pagination(parsed)
                    self._json(with_meta(list_handoff_packets(conn, pid, limit=limit, offset=offset)))
                    return

                if parsed.path.startswith("/api/handoff-packets/") and parsed.path.endswith("/review-summary"):
                    if not pid:
                        self._json({"error": "run_analyze_first"}, 400)
                        return
                    packet_id = parsed.path.split("/")[3]
                    review_summary = get_handoff_review_summary(conn, pid, packet_id)
                    if not review_summary:
                        self._json({"error": "review_summary_not_found"}, 404)
                        return
                    self._json(with_meta({"review_summary": review_summary}))
                    return

                if parsed.path.startswith("/api/handoff-packets/"):
                    if not pid:
                        self._json({"error": "run_analyze_first"}, 400)
                        return
                    packet_id = parsed.path.rsplit("/", 1)[-1]
                    packet = get_handoff_packet(conn, pid, packet_id)
                    if not packet:
                        self._json({"error": "handoff_packet_not_found"}, 404)
                        return
                    self._json(with_meta({"packet": packet}))
                    return

                if parsed.path == "/api/decisions":
                    if not pid:
                        self._json(with_meta({"items": [], "total": 0, "limit": 0, "offset": 0}))
                        return
                    limit, offset = pagination(parsed)
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

                if parsed.path.startswith("/api/decisions/") and parsed.path.endswith("/links"):
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
                        """
                        SELECT id, link_type, target_pattern, created_at
                        FROM decision_links
                        WHERE project_id=? AND decision_id=?
                        ORDER BY id DESC
                        """,
                        (pid, decision_id),
                    ).fetchall()
                    self._json(with_meta({
                        "items": [
                            {
                                "id": int(r[0]),
                                "link_type": r[1],
                                "target_pattern": r[2],
                                "created_at": r[3],
                            }
                            for r in rows
                        ]
                    }))
                    return

                if parsed.path == "/api/decision-links":
                    if not pid:
                        self._json(with_meta({"items": []}))
                        return
                    q = parse_qs(parsed.query or "")
                    path = (q.get("path", [""])[0] or "").strip()
                    module = (q.get("module", [""])[0] or "").strip()

                    rows = conn.execute(
                        """
                        SELECT dl.id, dl.decision_id, d.title, d.status, dl.link_type, dl.target_pattern, dl.created_at
                        FROM decision_links dl
                        JOIN decisions d ON d.id = dl.decision_id
                        WHERE dl.project_id=?
                        ORDER BY dl.id DESC
                        """,
                        (pid,),
                    ).fetchall()

                    items = []
                    for r in rows:
                        link_type = (r[4] or "").strip()
                        target_pattern = (r[5] or "").strip()
                        matched = False
                        if link_type == "file_glob" and path:
                            matched = fnmatch(path, target_pattern)
                        elif link_type == "module" and module:
                            matched = module == target_pattern

                        if path or module:
                            if not matched:
                                continue

                        items.append({
                            "id": int(r[0]),
                            "decision_id": int(r[1]),
                            "decision_title": r[2],
                            "decision_status": r[3],
                            "link_type": link_type,
                            "target_pattern": target_pattern,
                            "created_at": r[6],
                        })

                    self._json(with_meta({"items": items, "total": len(items)}))
                    return

                if parsed.path == "/api/intent/manifesto":
                    if not pid:
                        self._json(with_meta({"manifesto": "", "decisions": [], "constraints": []}))
                        return

                    drows = conn.execute(
                        """
                        SELECT id, title, summary, status
                        FROM decisions
                        WHERE project_id=? AND status IN ('accepted','resolved')
                        ORDER BY id DESC
                        LIMIT 80
                        """,
                        (pid,),
                    ).fetchall()

                    decisions = []
                    for dr in drows:
                        did = int(dr[0])
                        lrows = conn.execute(
                            "SELECT link_type, target_pattern FROM decision_links WHERE project_id=? AND decision_id=? ORDER BY id DESC",
                            (pid, did),
                        ).fetchall()
                        links = [{"link_type": lr[0], "target_pattern": lr[1]} for lr in lrows]
                        decisions.append({
                            "id": did,
                            "title": dr[1],
                            "summary": dr[2] or "",
                            "status": dr[3],
                            "links": links,
                        })

                    constraints = []
                    for d in decisions:
                        if d.get("links"):
                            link_txt = ", ".join([f"{l['link_type']}:{l['target_pattern']}" for l in d["links"][:8]])
                            constraints.append(f"Decision #{d['id']} applies to {link_txt}")
                        else:
                            constraints.append(f"Decision #{d['id']} has no explicit link patterns yet")

                    lines = ["## INTENT MANIFESTO", ""]
                    if decisions:
                        for d in decisions:
                            lines.append(f"### Decision #{d['id']}: {d['title']}")
                            if d.get("summary"):
                                lines.append(d["summary"])
                            if d.get("links"):
                                for l in d["links"][:10]:
                                    lines.append(f"- link: {l['link_type']} => {l['target_pattern']}")
                            lines.append("")
                    else:
                        lines.append("No active accepted/resolved decisions found.")

                    manifesto = "\n".join(lines).strip()
                    self._json(with_meta({
                        "manifesto": manifesto,
                        "decisions": decisions,
                        "constraints": constraints,
                    }))
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
                    limit, offset = pagination(parsed)
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

                if parsed.path == "/api/architecture/tree":
                    if not pid:
                        self._json(with_meta({"name": "root", "type": "folder", "path": "", "children": [], "file_count": 0, "avg_debt": 0}))
                        return

                    # Get all files with their metrics
                    rows = conn.execute(
                        """SELECT f.path, f.language, f.size_bytes,
                                  COALESCE(a.cognitive_debt, 0) as debt,
                                  (SELECT COUNT(*) FROM symbols s WHERE s.project_id=? AND s.file_path=f.path) as symbol_count
                           FROM files f
                           LEFT JOIN analysis_file_insights a ON a.project_id=f.project_id AND a.path=f.path
                           WHERE f.project_id=?
                           ORDER BY f.path""",
                        (pid, pid),
                    ).fetchall()

                    # Build nested tree from flat file paths
                    tree = {"name": "root", "type": "folder", "path": "", "children": [], "file_count": 0, "avg_debt": 0}

                    for fpath, lang, size_bytes, debt, sym_count in rows:
                        parts = fpath.split("/")
                        current = tree
                        # Navigate/create folder nodes
                        for i, part in enumerate(parts[:-1]):
                            folder_path = "/".join(parts[:i+1])
                            existing = None
                            for child in current["children"]:
                                if child["name"] == part and child["type"] == "folder":
                                    existing = child
                                    break
                            if not existing:
                                existing = {"name": part, "type": "folder", "path": folder_path, "children": [], "file_count": 0, "avg_debt": 0}
                                current["children"].append(existing)
                            current = existing
                        # Add file node
                        lines = 0
                        if size_bytes:
                            try:
                                fp = Path(root) / fpath
                                if fp.exists():
                                    lines = sum(1 for _ in open(fp, "rb"))
                            except Exception:
                                lines = max(1, size_bytes // 40)
                        current["children"].append({
                            "name": parts[-1], "type": "file", "path": fpath,
                            "lines": lines, "debt": round(debt, 1),
                            "symbol_count": sym_count or 0, "language": lang or "",
                        })

                    # Aggregate folder metrics (file_count, avg_debt) bottom-up
                    def _aggregate(node):
                        if node["type"] == "file":
                            return 1, node.get("debt", 0)
                        total_files = 0
                        total_debt = 0.0
                        for child in node.get("children", []):
                            fc, td = _aggregate(child)
                            total_files += fc
                            total_debt += td
                        node["file_count"] = total_files
                        node["avg_debt"] = round(total_debt / max(total_files, 1), 1)
                        return total_files, total_debt

                    _aggregate(tree)

                    # Collapse single-child folders (e.g. src/copyclip → src/copyclip)
                    def _collapse(node):
                        if node["type"] == "file":
                            return node
                        node["children"] = [_collapse(c) for c in node["children"]]
                        if len(node["children"]) == 1 and node["children"][0]["type"] == "folder" and node["name"] != "root":
                            child = node["children"][0]
                            child["name"] = node["name"] + "/" + child["name"]
                            return child
                        return node

                    tree = _collapse(tree)

                    self._json(with_meta(tree))
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
                    limit, offset = pagination(parsed)
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
                    limit, offset = pagination(parsed)
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
                    limit, offset = pagination(parsed)
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

                if parsed.path == "/api/analyze/status":
                    if not pid:
                        self._json(with_meta({"items": []}))
                        return
                    rows = conn.execute(
                        "SELECT id,status,phase,processed,total,message,checkpoint_cursor,checkpoint_every,started_at,finished_at FROM analysis_jobs WHERE project_id=? ORDER BY started_at DESC LIMIT 20",
                        (pid,),
                    ).fetchall()
                    self._json(with_meta({
                        "items": [_job_payload(r) for r in rows]
                    }))
                    return

                if parsed.path.startswith("/api/analyze/status/"):
                    if not pid:
                        self._json({"error": "run_analyze_first"}, 400)
                        return
                    job_id = parsed.path.rsplit("/", 1)[-1]
                    row = conn.execute(
                        "SELECT id,status,phase,processed,total,message,checkpoint_cursor,checkpoint_every,started_at,finished_at FROM analysis_jobs WHERE id=? AND project_id=?",
                        (job_id, pid),
                    ).fetchone()
                    if not row:
                        self._json({"error": "job_not_found"}, 404)
                        return
                    self._json(with_meta(_job_payload(row)))
                    return

                if parsed.path in {"/api/config", "/api/settings"}:
                    handle_settings_get(self, ctx, conn)
                    return

                if parsed.path == "/api/cuaderno/providers":
                    from .cuaderno.provider import (
                        provider_key_status, DEFAULT_MODELS, TOOL_INCAPABLE_MODELS,
                    )
                    status = provider_key_status()
                    cur_provider = None
                    cur_model = None
                    row = conn.execute(
                        "SELECT value FROM config WHERE key='cuaderno_provider'").fetchone()
                    if row:
                        cur_provider = row[0]
                    row = conn.execute(
                        "SELECT value FROM config WHERE key='cuaderno_model'").fetchone()
                    if row:
                        cur_model = row[0]
                    providers = [
                        {
                            "name": name,
                            "key_configured": configured,
                            "default_model": DEFAULT_MODELS.get(name),
                        }
                        for name, configured in status.items()
                    ]
                    self._json({
                        "providers": providers,
                        "tool_incapable_models": sorted(TOOL_INCAPABLE_MODELS),
                        "current": {"provider": cur_provider, "model": cur_model},
                    })
                    return

                if parsed.path == "/api/cuaderno/file":
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    q = parse_qs(parsed.query or "")
                    file_path = (q.get("path", [""])[0] or "").strip()
                    if not file_path:
                        self._json({"error": "path_required"}, 400)
                        return
                    try:
                        ls_raw = q.get("line_start", [""])[0]
                        le_raw = q.get("line_end", [""])[0]
                        line_start = int(ls_raw) if ls_raw else None
                        line_end   = int(le_raw) if le_raw else None
                    except ValueError:
                        self._json({"error": "invalid_line_range"}, 400)
                        return
                    from .cuaderno.anchor import read_file
                    out = read_file(ctx.root, file_path, line_start, line_end)
                    if out.get("error"):
                        status = 404 if out["error"] == "file_not_found" else 400
                        self._json(out, status)
                        return
                    # Best-effort blame for the slice
                    if line_start and line_end:
                        from .cuaderno.anchor import git_blame
                        b = git_blame(ctx.root, file_path, line_start, line_end)
                        if b.get("blame"):
                            first = b["blame"][0]
                            out["blame"] = {
                                "commit": first.get("commit", ""),
                                "author": first.get("author", ""),
                                "when": first.get("when", ""),
                            }
                    self._json(out)
                    return

                if parsed.path.startswith("/api/cuaderno/sessions/"):
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    sid = parsed.path[len("/api/cuaderno/sessions/"):]
                    if not sid:
                        self._json({"error": "session_id_required"}, 400)
                        return
                    from .cuaderno.persistence import list_questions
                    questions = list_questions(conn, sid)
                    if not questions:
                        # session does not exist OR has no questions yet
                        row = conn.execute(
                            "SELECT id FROM cuaderno_sessions WHERE id=?", (sid,),
                        ).fetchone()
                        if not row:
                            self._json({"error": "session_not_found"}, 404)
                            return
                    self._json({"session_id": sid, "questions": questions})
                    return

                self._json({"error": "not_found"}, 404)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        def do_PATCH(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            try:
                init_schema(conn)
                pid = project_id(conn, root)

                import re as _re
                _m = _re.match(
                    r"^/api/cuaderno/sessions/([^/]+)/questions/(\d+)$",
                    parsed.path,
                )
                if _m:
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    sid, pos = _m.group(1), int(_m.group(2))
                    try:
                        data = json.loads(self.rfile.read(
                            int(self.headers.get("Content-Length", "0"))
                        ).decode("utf-8") or "{}")
                    except json.JSONDecodeError:
                        self._json({"error": "invalid_request"}, 400)
                        return
                    from .cuaderno.persistence import set_bookmark, set_got_it
                    if "bookmarked" in data:
                        set_bookmark(conn, sid, pos, bool(data["bookmarked"]))
                    if "got_it" in data:
                        set_got_it(conn, sid, pos, data["got_it"])
                    self._json({"ok": True})
                    return

                if not pid:
                    self._json({"error": "run_analyze_first"}, 400)
                    return

                if parsed.path.startswith("/api/handoff-packets/"):
                    if not pid:
                        self._json({"error": "run_analyze_first"}, 400)
                        return
                    packet_id = parsed.path.rsplit("/", 1)[-1]
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    data = json.loads(raw.decode("utf-8"))
                    if str(data.get("state") or "") == "reviewed":
                        review_summary = get_handoff_review_summary(conn, pid, packet_id)
                        if not review_summary:
                            self._json({"error": "review_summary_required"}, 409)
                            return
                    try:
                        packet = update_handoff_packet(conn, pid, packet_id, data)
                        conn.commit()
                    except ValueError as e:
                        if str(e).startswith("invalid_state_transition:"):
                            self._json({"error": "invalid_state_transition", "detail": str(e)}, 409)
                            return
                        raise
                    if not packet:
                        self._json({"error": "handoff_packet_not_found"}, 404)
                        return
                    self._json(with_meta({"packet": packet}))
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
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        def do_DELETE(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            try:
                init_schema(conn)
                pid = project_id(conn, root)
                if not pid:
                    self._json({"error": "run_analyze_first"}, 400)
                    return

                if parsed.path.startswith("/api/playground/"):
                    playground_id = parsed.path[len("/api/playground/"):]
                    if not playground_id or "/" in playground_id:
                        self._json({"error": "missing_playground_id"}, 400)
                        return
                    ok = playground_runner.kill(playground_id)
                    if ok:
                        self._json({"ok": True, "id": playground_id})
                    else:
                        self._json({"error": "playground_not_found", "id": playground_id}, 404)
                    return

                self._json({"error": "not_found"}, 404)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        def do_POST(self):
            parsed = urlparse(self.path)
            conn = connect(root)
            try:
                init_schema(conn)
                pid = project_id(conn, root)
                if not pid:
                    self._json({"error": "run_analyze_first"}, 400)
                    return

                if parsed.path == "/api/playground/launch":
                    try:
                        data = read_json_body(self)
                    except (json.JSONDecodeError, ValueError) as e:
                        self._json(
                            {"error": "invalid_request", "message": f"malformed JSON body: {e}"},
                            400,
                        )
                        return
                    try:
                        req = PlaygroundLaunchRequest.from_dict(data)
                        response = launch_playground(req, root, conn, pid, playground_runner)
                        self._json(response.to_dict())
                    except PlaygroundError as e:
                        payload = {"error": e.error_code, "message": str(e)}
                        if isinstance(e, MarimoNotInstalledError):
                            payload["install_hint"] = "pip install copyclip[playground]"
                        self._json(payload, e.http_status)
                    return

                if parsed.path == "/api/handoff-packets":
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    data = json.loads(raw.decode("utf-8"))
                    task_prompt = (data.get("task_prompt") or "").strip()
                    if not task_prompt:
                        self._json({"error": "task_prompt_required"}, 400)
                        return
                    packet = build_handoff_packet(
                        conn,
                        pid,
                        task_prompt=task_prompt,
                        declared_files=[str(x) for x in (data.get("declared_files") or [])],
                        declared_modules=[str(x) for x in (data.get("declared_modules") or [])],
                        do_not_touch=data.get("do_not_touch") or [],
                        acceptance_criteria=[str(x) for x in (data.get("acceptance_criteria") or [])],
                        delegation_target=data.get("delegation_target"),
                        generated_at=data.get("generated_at"),
                    )
                    save_handoff_packet(conn, pid, packet)
                    self._json(with_meta({"packet": packet}))
                    return

                if parsed.path.startswith("/api/handoff-packets/") and parsed.path.endswith("/review-summary"):
                    packet_id = parsed.path.split("/")[3]
                    packet = get_handoff_packet(conn, pid, packet_id)
                    if not packet:
                        self._json({"error": "handoff_packet_not_found"}, 404)
                        return
                    packet_state = str(((packet.get("meta") or {}).get("state")) or "draft")
                    if packet_state not in {"change_received", "reviewed"}:
                        self._json({"error": "invalid_review_state_for_packet", "packet_state": packet_state}, 409)
                        return
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    data = json.loads(raw.decode("utf-8"))
                    generated_at = str(data.get("generated_at") or datetime.now(timezone.utc).isoformat())
                    proposed_changes = data.get("proposed_changes")
                    if isinstance(proposed_changes, dict):
                        review_summary = build_handoff_review_summary(
                            conn,
                            pid,
                            packet,
                            proposed_changes=proposed_changes,
                            generated_at=generated_at,
                        )
                        if data.get("review_state"):
                            review_summary["meta"]["review_state"] = str(data.get("review_state"))
                    else:
                        review_summary = {
                            "meta": {
                                "review_id": f"review_{packet_id}",
                                "packet_id": packet_id,
                                "review_state": str(data.get("review_state") or "generated"),
                                "generated_at": generated_at,
                            },
                            "result": data.get("result") or {},
                            "scope_check": data.get("scope_check") or {},
                            "decision_conflicts": data.get("decision_conflicts") or [],
                            "blast_radius": data.get("blast_radius") or {},
                            "dark_zone_entry": data.get("dark_zone_entry") or [],
                            "unresolved_questions": data.get("unresolved_questions") or [],
                            "review_evidence": data.get("review_evidence") or [],
                        }
                    try:
                        conn.execute("BEGIN")
                        save_handoff_review_summary(conn, pid, packet_id, review_summary, commit=False)
                        updated_packet = update_handoff_packet(conn, pid, packet_id, {"state": "reviewed"})
                        conn.commit()
                    except ValueError as e:
                        conn.rollback()
                        if str(e) == "invalid_review_state":
                            self._json({"error": "invalid_review_state"}, 400)
                            return
                        if str(e).startswith("invalid_state_transition:"):
                            self._json({"error": "invalid_state_transition", "detail": str(e)}, 409)
                            return
                        if str(e) == "review_packet_id_mismatch":
                            self._json({"error": "review_packet_id_mismatch"}, 400)
                            return
                        raise
                    self._json(with_meta({"review_summary": review_summary, "packet": updated_packet}))
                    return

                if parsed.path == "/api/analyze/start":
                    # prevent concurrent analyze jobs
                    running = conn.execute(
                        "SELECT id FROM analysis_jobs WHERE project_id=? AND status IN ('queued','running') ORDER BY started_at DESC LIMIT 1",
                        (pid,),
                    ).fetchone()
                    if running:
                        self._json(with_meta({"ok": True, "job_id": running[0], "already_running": True}))
                        return
                    job_id = _start_analysis_job(pid)
                    self._json(with_meta({"ok": True, "job_id": job_id, "already_running": False}))
                    return

                if parsed.path == "/api/analyze/resume":
                    running = conn.execute(
                        "SELECT id FROM analysis_jobs WHERE project_id=? AND status IN ('queued','running') ORDER BY started_at DESC LIMIT 1",
                        (pid,),
                    ).fetchone()
                    if running:
                        self._json(with_meta({"ok": True, "job_id": running[0], "already_running": True}))
                        return

                    last = conn.execute(
                        "SELECT checkpoint_cursor,total FROM analysis_jobs WHERE project_id=? AND status IN ('failed','queued','running','canceled') ORDER BY started_at DESC LIMIT 1",
                        (pid,),
                    ).fetchone()
                    if not last:
                        self._json({"error": "no_resumable_job"}, 404)
                        return

                    resume_from = int(last[0] or 0)
                    total = int(last[1] or 0)
                    if total > 0 and resume_from >= total:
                        self._json({"error": "resume_cursor_at_end"}, 409)
                        return

                    job_id = _start_analysis_job(pid, resume_from=resume_from)
                    self._json(with_meta({"ok": True, "job_id": job_id, "already_running": False, "resume_from": resume_from}))
                    return

                if parsed.path == "/api/analyze/cancel":
                    running = conn.execute(
                        "SELECT id,status FROM analysis_jobs WHERE project_id=? AND status IN ('queued','running') ORDER BY started_at DESC LIMIT 1",
                        (pid,),
                    ).fetchone()
                    if not running:
                        self._json({"error": "no_running_job"}, 404)
                        return

                    job_id = str(running[0])
                    with cancel_lock:
                        ev = cancel_events.get(job_id)
                        if ev:
                            ev.set()

                    conn.execute(
                        "UPDATE analysis_jobs SET message=? WHERE id=?",
                        ("cancel requested", job_id),
                    )
                    conn.commit()
                    publish_event("analyze.cancel_requested", {"job_id": job_id})
                    self._json(with_meta({"ok": True, "job_id": job_id, "cancel_requested": True}))
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

                if parsed.path == "/api/decision-advisor/check":
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    data = json.loads(raw.decode("utf-8"))

                    intent = (data.get("intent") or data.get("question") or "").strip()
                    selected_files = [str(f) for f in (data.get("files") or [])]
                    if not intent and not selected_files:
                        self._json({"error": "intent_or_files_required"}, 400)
                        return

                    tokens = [
                        t
                        for t in re.findall(r"[a-zA-Z0-9_\-]{3,}", intent.lower())
                        if t not in {"the", "and", "for", "with", "that", "this", "what", "how", "from", "into"}
                    ]
                    file_text = " ".join(selected_files).lower()

                    rows = conn.execute(
                        "SELECT id,title,summary,status FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 300",
                        (pid,),
                    ).fetchall()

                    conflicts = []
                    for r in rows:
                        did, title, summary, status = int(r[0]), (r[1] or ""), (r[2] or ""), (r[3] or "")
                        decision_text = f"{title} {summary} {status}".lower()
                        lexical_hits = [t for t in tokens if t in decision_text]

                        ref_rows = conn.execute(
                            "SELECT ref_type, ref_value FROM decision_refs WHERE decision_id=? ORDER BY id DESC LIMIT 20",
                            (did,),
                        ).fetchall()

                        ref_match = False
                        matched_refs = []
                        for rr in ref_rows:
                            rtype = rr[0] or ""
                            rval = (rr[1] or "")
                            rval_l = rval.lower()
                            if rtype == "file" and any(f == rval for f in selected_files):
                                ref_match = True
                                matched_refs.append({"ref_type": rtype, "ref_value": rval})
                            elif rtype == "file" and file_text and (rval_l in file_text or file_text in rval_l):
                                ref_match = True
                                matched_refs.append({"ref_type": rtype, "ref_value": rval})
                            elif rtype == "doc" and tokens and any(t in rval_l for t in tokens):
                                ref_match = True
                                matched_refs.append({"ref_type": rtype, "ref_value": rval})

                        signal = len(lexical_hits) + (2 if ref_match else 0)
                        if signal <= 0:
                            continue

                        # lightweight contradiction heuristic
                        negative_markers = ["avoid", "do not", "never", "deprecated", "forbid", "forbidden", "must not"]
                        positive_markers = ["introduce", "add", "enable", "migrate", "adopt", "use"]
                        intent_negative = any(m in intent.lower() for m in negative_markers)
                        decision_negative = any(m in decision_text for m in negative_markers)
                        contradiction = (intent_negative and not decision_negative) or (decision_negative and not intent_negative)

                        confidence = min(0.95, 0.4 + (0.08 * len(lexical_hits)) + (0.2 if ref_match else 0.0) + (0.1 if contradiction else 0.0))

                        if contradiction or signal >= 2:
                            why = (
                                f"Intent overlaps with decision #{did} on {', '.join(lexical_hits[:4])}."
                                + (" Referenced files/docs also overlap." if ref_match else "")
                            )
                            if contradiction:
                                why += " Direction markers appear inconsistent with the decision narrative."

                            conflicts.append({
                                "decision_id": did,
                                "title": title,
                                "status": status,
                                "why_conflict": why,
                                "confidence": round(confidence, 2),
                                "suggested_alternative": f"Align implementation with decision #{did} ({status}) or supersede it explicitly before proceeding.",
                                "matched_refs": matched_refs,
                            })

                    conflicts.sort(key=lambda c: (c.get("confidence", 0), c.get("decision_id", 0)), reverse=True)
                    conflicts = conflicts[:6]

                    self._json(with_meta({
                        "ok": True,
                        "conflicts": conflicts,
                        "has_conflicts": len(conflicts) > 0,
                        "intent": intent,
                        "checked_files": selected_files,
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
                    question = (data.get("question") or "").strip()

                    prompt_parts = []
                
                    # Auto-compact bundle when no explicit file list was provided.
                    compact_bundle = {"manifest": [], "selected_files": []}
                    if not selected_files:
                        issue_titles = []
                        for iid in selected_issues:
                            row_i = conn.execute(
                                "SELECT title FROM issues WHERE project_id=? AND external_id=?",
                                (pid, str(iid)),
                            ).fetchone()
                            if row_i and row_i[0]:
                                issue_titles.append(str(row_i[0]))
                        compact_query = question or " ".join(issue_titles)
                        compact_bundle = build_context_bundle(conn, pid, compact_query, max_files=25)
                        selected_files = compact_bundle.get("selected_files", [])

                    # 1. Intent Manifesto + Decisions
                    if include_decisions:
                        drows = conn.execute(
                            """
                            SELECT id, title, summary, status
                            FROM decisions
                            WHERE project_id=? AND status IN ('accepted','resolved')
                            ORDER BY id DESC
                            LIMIT 80
                            """,
                            (pid,),
                        ).fetchall()

                        if drows:
                            lines = ["## INTENT MANIFESTO", ""]
                            for dr in drows:
                                did = int(dr[0])
                                title = dr[1]
                                summary = dr[2] or ""
                                lines.append(f"### Decision #{did}: {title}")
                                if summary:
                                    lines.append(summary)
                                lrows = conn.execute(
                                    "SELECT link_type, target_pattern FROM decision_links WHERE project_id=? AND decision_id=? ORDER BY id DESC",
                                    (pid, did),
                                ).fetchall()
                                for lr in lrows[:10]:
                                    lines.append(f"- link: {lr[0]} => {lr[1]}")
                                lines.append("")
                            prompt_parts.append("\n".join(lines).strip())

                        # Keep legacy header for compatibility with existing prompts/tools.
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
                    self._json({
                        "context": final_context,
                        "warnings": warnings,
                        "bundle_manifest": compact_bundle.get("manifest", []),
                        "bundle_files": compact_bundle.get("selected_files", []),
                    })
                    return

                if parsed.path in {"/api/config", "/api/settings"}:
                    handle_settings_post(self, ctx, conn)
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

                if parsed.path.startswith("/api/decisions/") and parsed.path.endswith("/links"):
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
                    link_type = (data.get("link_type") or "file_glob").strip()
                    target_pattern = (data.get("target_pattern") or "").strip()
                    allowed = {"file_glob", "module"}
                    if link_type not in allowed:
                        self._json({"error": "invalid_link_type", "allowed": sorted(allowed)}, 400)
                        return
                    if not target_pattern:
                        self._json({"error": "target_pattern_required"}, 400)
                        return

                    conn.execute(
                        """
                        INSERT OR IGNORE INTO decision_links(project_id,decision_id,link_type,target_pattern)
                        VALUES(?,?,?,?)
                        """,
                        (pid, decision_id, link_type, target_pattern),
                    )
                    conn.execute(
                        "INSERT INTO decision_history(decision_id,action,from_status,to_status,note) VALUES(?,?,?,?,?)",
                        (decision_id, "link_added", None, None, f"{link_type}: {target_pattern}"),
                    )
                    conn.commit()
                    publish_event("decision.link_added", {"decision_id": decision_id, "link_type": link_type, "target_pattern": target_pattern})
                    self._json({"ok": True, "decision_id": decision_id, "link_type": link_type, "target_pattern": target_pattern})
                    return

                if parsed.path == "/api/cuaderno/ask":
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    try:
                        data = json.loads(self.rfile.read(
                            int(self.headers.get("Content-Length", "0"))
                        ).decode("utf-8") or "{}")
                    except json.JSONDecodeError:
                        self._json({"error": "invalid_request"}, 400)
                        return
                    question = (data.get("question") or "").strip()
                    if not question:
                        self._json({"error": "question_required"}, 400)
                        return
                    session_id = data.get("session_id")
                    from .cuaderno.ask_stream import iter_ask_events
                    from .cuaderno.persistence import create_session
                    from .cuaderno.provider import (
                        resolve_cuaderno_provider, build_cuaderno_client,
                        CuadernoProviderError,
                    )
                    if not session_id:
                        session_id = create_session(conn, project_root=ctx.root)
                    try:
                        resolved = resolve_cuaderno_provider(conn)
                    except CuadernoProviderError as exc:
                        self._json({"error": "llm_not_configured",
                                    "provider": exc.provider, "detail": str(exc)}, 503)
                        return
                    client = build_cuaderno_client(resolved)
                    from .cuaderno.provider import resolve_judge_model
                    from .cuaderno.judge import judge_answer
                    judge_overlay = None
                    try:
                        _jrow = conn.execute(
                            "SELECT value FROM config WHERE key=?",
                            ("cuaderno_judge_model",),
                        ).fetchone()
                        judge_overlay = _jrow[0] if _jrow and _jrow[0] else None
                    except Exception:
                        judge_overlay = None
                    judge_model = resolve_judge_model(
                        resolved["provider"], resolved["model"], judge_overlay)

                    def _judge(q, b, l):
                        return judge_answer(client=client, question=q, blocks=b, ledger=l, model=judge_model)

                    events = iter_ask_events(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                        session_id=session_id, model=resolved["model"],
                        judge=_judge,
                    )
                    sse_response(self, events)
                    return

                self._json({"error": "not_found"}, 404)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def _use_color() -> bool:
        return sys.stdout.isatty() and os.getenv("NO_COLOR") is None

    def _c(text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if _use_color() else text

    def _link(url: str, label: str | None = None) -> str:
        label = label or url
        if not sys.stdout.isatty():
            return url
        return f"\033]8;;{url}\a{label}\033]8;;\a"

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    actual_port = int(server.server_address[1])
    dash_url = f"http://127.0.0.1:{actual_port}"
    print(f"{_c('INFO', '36')} CopyClip Intelligence running at {_link(dash_url)}")
    print(f"{_c('INFO', '36')} Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{_c('INFO', '36')} Shutting down CopyClip Intelligence...")
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        server.server_close()
        # Kill any live Marimo playground subprocesses spawned during this
        # session. Falls through silently for the Stub runner (no method).
        kill_all = getattr(playground_runner, "kill_all", None)
        if callable(kill_all):
            try:
                kill_all()
            except Exception as exc:
                # Don't crash on the way out; do leave a breadcrumb so a
                # hung subprocess cleanup is debuggable instead of silently
                # lost.
                print(
                    f"{_c('WARN', '33')} playground_runner.kill_all() failed: {exc!r}"
                )
        print(f"{_c('OK', '32')} Bye.")
