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
from copyclip.intelligence.cuaderno.schema import Frame, Block, frame_to_dict

# AnthropicAdapter is constructed by the route before compose_frame runs.
# Tests stub compose_frame so the client is never actually used, but the
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


def _post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="POST", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _setup_server():
    td = tempfile.mkdtemp(prefix="cuaderno-test-")
    root = str(Path(td).absolute())
    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    conn.commit()
    conn.close()
    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start()
    _wait_port(port)
    return root, port


def test_post_ask_returns_frame_when_compositor_is_stubbed():
    root, port = _setup_server()
    stub_frame = Frame(
        question="hello",
        blocks=[Block.lead("CopyClip is a tool.")],
    )

    def fake_compose_frame(**kwargs):
        return stub_frame

    with patch(
        "copyclip.intelligence.cuaderno.compositor.compose_frame",
        side_effect=fake_compose_frame,
    ):
        status, body = _post_json(
            f"http://127.0.0.1:{port}/api/cuaderno/ask",
            {"question": "hello"},
        )

    assert status == 200
    assert "session_id" in body
    assert body["position"] == 1
    assert body["frame"]["question"] == "hello"
    assert body["frame"]["blocks"][0]["kind"] == "lead"


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
    stub_frame_1 = Frame(question="q1", blocks=[Block.lead("a")])
    stub_frame_2 = Frame(question="q2", blocks=[Block.lead("b")])
    responses = [stub_frame_1, stub_frame_2]

    def fake_compose_frame(**kwargs):
        return responses.pop(0)

    with patch(
        "copyclip.intelligence.cuaderno.compositor.compose_frame",
        side_effect=fake_compose_frame,
    ):
        _, b1 = _post_json(f"http://127.0.0.1:{port}/api/cuaderno/ask",
                           {"question": "q1"})
        sid = b1["session_id"]
        _post_json(f"http://127.0.0.1:{port}/api/cuaderno/ask",
                   {"question": "q2", "session_id": sid})

    status, body = _get_json(f"http://127.0.0.1:{port}/api/cuaderno/sessions/{sid}")
    assert status == 200
    assert body["session_id"] == sid
    assert [q["question"] for q in body["questions"]] == ["q1", "q2"]
    assert [q["position"] for q in body["questions"]] == [1, 2]
