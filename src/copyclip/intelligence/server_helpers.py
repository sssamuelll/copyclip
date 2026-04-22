import json
import sqlite3
from datetime import datetime, timezone
from urllib.parse import parse_qs


def json_response(handler, payload, code=200):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def project_id(conn: sqlite3.Connection, root: str):
    row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
    return row[0] if row else None


def with_meta(root: str, payload: dict):
    payload.setdefault("meta", {})
    payload["meta"]["project"] = __import__("os").path.basename(root)
    payload["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def pagination(parsed):
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


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8"))
