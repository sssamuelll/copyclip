"""Live end-to-end validation of the emit_block protocol against a REAL LLM.

This is the automated form of the manual T15 check: does the chosen provider
(DeepSeek by default) actually drive the agentic emit_block/finish protocol —
reading evidence, then emitting distinct, valid, *cited* blocks — over the real
SSE endpoint?

It is gated, not mocked. It hits a paid API, so it only runs when you have
opted in by setting the provider's key. With no key it skips cleanly, so a
normal `pytest` run (and CI without secrets) never touches the network.

Run it:

    # DeepSeek (default)
    $env:DEEPSEEK_API_KEY = "sk-..."          # PowerShell
    pytest tests/test_cuaderno_live_e2e.py -v -s

    # Another provider
    $env:CUADERNO_LIVE_PROVIDER = "anthropic"
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    pytest tests/test_cuaderno_live_e2e.py -v -s

What it asserts (the wedge — anti-invention):
  * the stream is real SSE and opens with a `meta` event;
  * NO terminal `error` event — i.e. the model could drive emit_block;
  * the model used a read tool (evidence phase ran);
  * at least one `block` event arrived (answer came via emit_block, not free text);
  * the terminal `frame` is at position 1 and every block is a known, renderable kind;
  * at least one block carries a citation — the model grounded its answer in the file.
"""

import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request

import pytest

from copyclip.intelligence.db import connect, init_schema, init_cuaderno_schema
from copyclip.intelligence.server import run_server
from copyclip.intelligence.cuaderno.provider import DEFAULT_MODELS
from copyclip.intelligence.cuaderno.schema import validate_block_dict
from copyclip.llm.provider_config import PROVIDERS


LIVE_PROVIDER = os.environ.get("CUADERNO_LIVE_PROVIDER", "deepseek").strip().lower()
_KEY_ENV = PROVIDERS[LIVE_PROVIDER].api_key_env if LIVE_PROVIDER in PROVIDERS else None
_HAS_KEY = bool(_KEY_ENV and (os.environ.get(_KEY_ENV) or "").strip())

pytestmark = pytest.mark.skipif(
    not _HAS_KEY,
    reason=(
        f"live e2e: set {_KEY_ENV or 'the provider key'} "
        f"(provider={LIVE_PROVIDER}) to run the real emit_block validation"
    ),
)


# A small, self-contained project the model must READ to answer correctly.
APP_PY = '''\
def greet(name):
    """Return a friendly greeting for the given name."""
    return f"Hello, {name}! Welcome to CopyClip."


def farewell(name):
    """Return a parting message."""
    return f"Goodbye, {name}."
'''


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
    raise RuntimeError("server did not start")


def _post_sse(url, body, timeout=120):
    """POST and parse a text/event-stream response into a list of event dicts.

    Stops after the terminal event (frame or error) so the keep-alive
    connection doesn't hang. Live model + tool rounds can take a while, hence
    the generous timeout.
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


def _has_citation(block: dict) -> bool:
    """True if the block grounds the answer in a source (the anti-invention bar)."""
    kind = block.get("kind")
    if kind in ("citation", "citation_stack"):
        return True
    if "citation" in block or "citations" in block:
        return True
    # citation_stack stores its refs under "items"; a lone citation may too.
    if kind == "citation_stack" and block.get("items"):
        return True
    return False


def test_live_emit_block_protocol_over_sse():
    td = tempfile.mkdtemp(prefix="cuaderno-live-")
    root = str(Path(td).absolute())
    (Path(td) / "README.md").write_text("# CopyClip\nA personal code-comprehension tool.\n",
                                         encoding="utf-8")
    (Path(td) / "app.py").write_text(APP_PY, encoding="utf-8")

    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "live-e2e"))
    conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('cuaderno_provider',?)",
                 (LIVE_PROVIDER,))
    conn.commit()
    conn.close()

    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start()
    _wait_port(port)

    question = (
        "What does the function `greet` in app.py do, and on which line is it "
        "defined? Cite the file and lines."
    )
    status, ctype, events = _post_sse(
        f"http://127.0.0.1:{port}/api/cuaderno/ask",
        {"question": question},
    )

    model = DEFAULT_MODELS.get(LIVE_PROVIDER, "?")
    print(f"\n[live e2e] provider={LIVE_PROVIDER} model={model} events={len(events)}")
    for e in events:
        if e["type"] == "tool":
            print(f"  tool  {e['name']}({e.get('args','')}) -> {e['state']} {e.get('ms')}ms")
        elif e["type"] == "block":
            print(f"  block {e['block'].get('kind')}")
        elif e["type"] == "error":
            print(f"  ERROR {e.get('message')}")

    # --- transport ---
    assert status == 200
    assert "text/event-stream" in ctype
    assert events and events[0]["type"] == "meta" and "session_id" in events[0]

    # --- the protocol did not collapse ---
    err = next((e for e in events if e["type"] == "error"), None)
    assert err is None, (
        f"{LIVE_PROVIDER} could not drive emit_block; terminal error: "
        f"{err and err.get('message')}"
    )

    # --- evidence phase ran (model read the file before answering) ---
    tool_events = [e for e in events if e["type"] == "tool"]
    assert any(e.get("state") == "done" for e in tool_events), (
        "no successful read tool — model answered without consulting the project"
    )

    # --- answer arrived as emit_block stream, not free text ---
    block_events = [e for e in events if e["type"] == "block"]
    assert block_events, "no block events — provider did not use emit_block"

    # --- terminal frame: position 1, every block renderable ---
    frame_ev = next((e for e in events if e["type"] == "frame"), None)
    assert frame_ev is not None, "no terminal frame event"
    assert frame_ev["position"] == 1
    blocks = frame_ev["frame"]["blocks"]
    assert blocks, "frame carried zero blocks"
    for b in blocks:
        reason = validate_block_dict(b)
        assert reason is None, f"unrenderable block in frame: {reason} ({b!r})"

    # --- the wedge: the answer is grounded in a citation ---
    assert any(_has_citation(b) for b in blocks), (
        "no citation in the answer — anti-invention bar not met. Blocks: "
        + ", ".join(b.get("kind", "?") for b in blocks)
    )
