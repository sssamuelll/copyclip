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


def sse_response(handler, events) -> bool:
    """Stream JSON event dicts as text/event-stream.

    Writes SSE headers, then one `data: <json>\\n\\n` record per event with an
    explicit flush. Returns True if the stream completed, False if the client
    disconnected (in which case the events generator is closed so its finally
    can run — e.g. to persist a partial frame).
    """
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()
    for ev in events:
        try:
            handler.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            close = getattr(events, "close", None)
            if close is not None:
                close()
            return False
    return True
