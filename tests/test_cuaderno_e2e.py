import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib import request

from copyclip.intelligence.db import connect, init_schema, init_cuaderno_schema
from copyclip.intelligence.server import run_server


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _wait_port(port, timeout_s=3.0):
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


def _post_sse(url, body, timeout=15):
    """POST and parse a text/event-stream response into a list of event dicts.

    Reads line-by-line and stops after the terminal event (frame or error) so
    the keep-alive connection doesn't cause a hang.
    """
    data = json.dumps(body).encode("utf-8")
    req = request.Request(url, method="POST", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as r:
        status = r.status
        ctype = r.headers.get("Content-Type", "")
        events = []
        for line in r:
            line = line.decode("utf-8").rstrip("\n").rstrip("\r")
            if line.startswith("data:"):
                ev = json.loads(line[len("data:"):].strip())
                events.append(ev)
                if ev.get("type") in ("frame", "error"):
                    break
    return status, ctype, events


def _stop(bid, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": bid, "name": name, "input": inp}}


def _content(bid, name, inp):
    return {"type": "tool_use", "id": bid, "name": name, "input": inp}


def _msg(reason, content):
    return {"type": "message_stop", "stop_reason": reason, "content": content}


def test_e2e_example_A_streams_frame_over_sse():
    """Full-stack: POST /api/cuaderno/ask drives the streaming compositor
    (messages_stream + emit_block) and returns an SSE stream whose terminal
    frame event carries the composed blocks."""
    td = tempfile.mkdtemp(prefix="cuaderno-e2e-")
    root = str(Path(td).absolute())
    (Path(td) / "README.md").write_text("# CopyClip", encoding="utf-8")
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

    lead = {"kind": "lead", "text": "CopyClip is a personal tool."}
    cite = {"kind": "citation",
            "citation": {"kind": "path", "path": "README.md", "line_start": 1, "line_end": 1}}
    turns = [
        [
            _stop("t1", "read_file", {"path": "README.md"}),
            _msg("tool_use", [_content("t1", "read_file", {"path": "README.md"})]),
        ],
        [
            _stop("b1", "emit_block", lead),
            _stop("b2", "emit_block", cite),
            _stop("f", "finish", {}),
            _msg("tool_use", [
                _content("b1", "emit_block", lead),
                _content("b2", "emit_block", cite),
                _content("f", "finish", {}),
            ]),
        ],
    ]

    def _stream(**kwargs):
        for ev in turns.pop(0):
            yield ev

    with patch(
        "copyclip.intelligence.cuaderno.anthropic_client.AnthropicAdapter"
    ) as MockAdapter:
        MockAdapter.return_value.messages_stream.side_effect = _stream
        status, ctype, events = _post_sse(
            f"http://127.0.0.1:{port}/api/cuaderno/ask",
            {"question": "what does this project do?"},
        )

    assert status == 200
    assert "text/event-stream" in ctype
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert "tool" in types
    assert "block" in types
    frame_ev = next(e for e in events if e["type"] == "frame")
    kinds = [b["kind"] for b in frame_ev["frame"]["blocks"]]
    assert "lead" in kinds
    assert "citation" in kinds
    assert frame_ev["position"] == 1
