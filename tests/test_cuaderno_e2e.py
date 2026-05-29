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


def _post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = request.Request(url, method="POST", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_e2e_example_A_compositor_returns_valid_frame():
    """A scripted run that walks the compositor through tool_use → tool_result →
    final Frame JSON, and verifies the HTTP response."""
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

    # Scripted Anthropic responses
    tool_use_response = {
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", "id": "t1", "name": "read_file",
             "input": {"path": "README.md"}},
        ],
    }
    final_response = {
        "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": json.dumps({
                "question": "what does this project do?",
                "blocks": [
                    {"kind": "lead", "text": "CopyClip is a personal tool."},
                    {"kind": "paragraph", "text": "It reads its README."},
                    {"kind": "citation",
                     "citation": {"kind": "path", "path": "README.md", "line_start": 1, "line_end": 1}},
                ],
            })},
        ],
    }

    with patch(
        "copyclip.intelligence.cuaderno.anthropic_client.AnthropicAdapter"
    ) as MockAdapter:
        sequence = [tool_use_response, final_response]
        def _create(**kwargs):
            return sequence.pop(0)
        MockAdapter.return_value.messages_create.side_effect = _create

        status, body = _post(
            f"http://127.0.0.1:{port}/api/cuaderno/ask",
            {"question": "what does this project do?"},
        )

    assert status == 200
    frame = body["frame"]
    assert frame["question"] == "what does this project do?"
    kinds = [b["kind"] for b in frame["blocks"]]
    assert "lead" in kinds
    assert "citation" in kinds
