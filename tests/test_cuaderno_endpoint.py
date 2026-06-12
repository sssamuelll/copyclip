import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib import request
from urllib.error import HTTPError

from copyclip.intelligence.db import connect, init_schema, init_cuaderno_schema
from copyclip.intelligence.server import run_server
from copyclip.intelligence.cuaderno.schema import Block

# AnthropicAdapter is constructed by the route before the compositor runs.
# Tests stub iter_compose_events so the client is never actually used, but the
# adapter init demands an API key. Provide a placeholder so the route can
# proceed to the patched compositor.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-placeholder-key")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_port(port, timeout_s=3.0):
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"server did not start on {port}")


def _post_sse(url, payload, timeout=15):
    """POST and parse a text/event-stream response into (status, events list).

    Reads line-by-line and stops after the terminal event (frame or error) so
    the keep-alive connection doesn't cause a hang.
    """
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="POST", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as r:
        status = r.status
        events = []
        for line in r:
            line = line.decode("utf-8").rstrip("\n").rstrip("\r")
            if line.startswith("data:"):
                ev = json.loads(line[len("data:"):].strip())
                events.append(ev)
                if ev.get("type") in ("frame", "error"):
                    break
    return status, events


def _post_json(url, payload, timeout=10):
    """POST expecting a plain JSON response (used for error-path tests)."""
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="POST", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _setup_server():
    td = tempfile.mkdtemp(prefix="cuaderno-test-")
    root = str(Path(td).absolute())
    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('cuaderno_provider','anthropic')")
    conn.commit()
    conn.close()
    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start()
    _wait_port(port)
    return root, port


def test_post_ask_returns_frame_when_compositor_is_stubbed():
    root, port = _setup_server()
    stub_block = Block.lead("CopyClip is a tool.")

    def fake_iter_compose_events(**kwargs):
        yield {"type": "block", "block": stub_block.to_dict()}
        yield {"type": "frame", "frame": {"question": "hello",
                                          "blocks": [stub_block.to_dict()]}}

    with patch(
        "copyclip.intelligence.cuaderno.ask_stream.iter_compose_events",
        side_effect=fake_iter_compose_events,
    ):
        status, events = _post_sse(
            f"http://127.0.0.1:{port}/api/cuaderno/ask",
            {"question": "hello"},
        )

    assert status == 200
    meta = next(e for e in events if e["type"] == "meta")
    assert "session_id" in meta
    frame_ev = next(e for e in events if e["type"] == "frame")
    assert frame_ev["position"] == 1
    assert frame_ev["frame"]["question"] == "hello"
    assert frame_ev["frame"]["blocks"][0]["kind"] == "lead"


def test_post_ask_rejects_missing_question():
    _, port = _setup_server()
    try:
        _post_json(
            f"http://127.0.0.1:{port}/api/cuaderno/ask", {}
        )
        assert False, "expected HTTPError"
    except HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read().decode("utf-8"))
        assert body["error"] == "question_required"


def _get_json(url):
    with request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_get_session_returns_questions_in_order():
    root, port = _setup_server()
    stubs = [
        [Block.lead("a")],
        [Block.lead("b")],
    ]

    def fake_iter_compose_events(question, **kwargs):
        blks = stubs.pop(0)
        for b in blks:
            yield {"type": "block", "block": b.to_dict()}
        yield {"type": "frame", "frame": {"question": question,
                                          "blocks": [b.to_dict() for b in blks]}}

    with patch(
        "copyclip.intelligence.cuaderno.ask_stream.iter_compose_events",
        side_effect=fake_iter_compose_events,
    ):
        _, evs1 = _post_sse(f"http://127.0.0.1:{port}/api/cuaderno/ask",
                            {"question": "q1"})
        sid = next(e for e in evs1 if e["type"] == "meta")["session_id"]
        _post_sse(f"http://127.0.0.1:{port}/api/cuaderno/ask",
                  {"question": "q2", "session_id": sid})

    status, body = _get_json(f"http://127.0.0.1:{port}/api/cuaderno/sessions/{sid}")
    assert status == 200
    assert body["session_id"] == sid
    assert [q["question"] for q in body["questions"]] == ["q1", "q2"]
    assert [q["position"] for q in body["questions"]] == [1, 2]


def _patch_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="PATCH", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_patch_bookmark_and_gotit():
    root, port = _setup_server()
    stub_block = Block.lead("hi")

    def fake_iter_compose_events(question, **kwargs):
        yield {"type": "block", "block": stub_block.to_dict()}
        yield {"type": "frame", "frame": {"question": question,
                                          "blocks": [stub_block.to_dict()]}}

    with patch(
        "copyclip.intelligence.cuaderno.ask_stream.iter_compose_events",
        side_effect=fake_iter_compose_events,
    ):
        _, evs = _post_sse(f"http://127.0.0.1:{port}/api/cuaderno/ask",
                           {"question": "q1"})
    sid = next(e for e in evs if e["type"] == "meta")["session_id"]

    status, _ = _patch_json(
        f"http://127.0.0.1:{port}/api/cuaderno/sessions/{sid}/questions/1",
        {"bookmarked": True, "answer_check": "answers"},
    )
    assert status == 200

    _, session = _get_json(f"http://127.0.0.1:{port}/api/cuaderno/sessions/{sid}")
    q1 = session["questions"][0]
    assert q1["bookmarked"] is True
    assert q1["answer_check"] == "answers"
