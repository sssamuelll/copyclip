import json
import time
from datetime import datetime, timezone


def publish_event(ctx, kind: str, data: dict):
    with ctx.events_lock:
        ev = {
            "id": ctx.next_event_id["value"],
            "kind": kind,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        ctx.next_event_id["value"] += 1
        ctx.events.append(ev)
        if len(ctx.events) > 500:
            del ctx.events[: len(ctx.events) - 500]
        ctx.events_lock.notify_all()


def handle_events_get(handler, ctx, parsed):
    from urllib.parse import parse_qs

    q = parse_qs(parsed.query or "")
    try:
        cursor = int(q.get("cursor", ["0"])[0])
    except Exception:
        cursor = 0

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    def write_event(ev):
        payload = json.dumps(ev)
        handler.wfile.write(f"id: {ev['id']}\nevent: {ev['kind']}\ndata: {payload}\n\n".encode("utf-8"))
        handler.wfile.flush()

    write_event(
        {
            "id": cursor,
            "kind": "connected",
            "data": {"cursor": cursor},
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )

    with ctx.events_lock:
        backlog = [e for e in ctx.events if e["id"] > cursor]
    for ev in backlog:
        write_event(ev)
        cursor = ev["id"]

    deadline = time.time() + 30
    while time.time() < deadline:
        with ctx.events_lock:
            updates = [e for e in ctx.events if e["id"] > cursor]
            if not updates:
                ctx.events_lock.wait(timeout=2)
                updates = [e for e in ctx.events if e["id"] > cursor]
        for ev in updates:
            write_event(ev)
            cursor = ev["id"]
