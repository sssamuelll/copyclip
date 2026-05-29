import json
import socket
import tempfile
import threading
import time
from pathlib import Path
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


def test_providers_endpoint_lists_providers_and_current(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    td = tempfile.mkdtemp(prefix="cuaderno-prov-")
    root = str(Path(td).absolute())
    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('cuaderno_provider','deepseek')")
    conn.commit(); conn.close()

    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start(); _wait_port(port)

    with request.urlopen(f"http://127.0.0.1:{port}/api/cuaderno/providers", timeout=10) as r:
        body = json.loads(r.read().decode("utf-8"))

    assert body["current"]["provider"] == "deepseek"
    names = {p["name"] for p in body["providers"]}
    assert {"anthropic", "openai", "deepseek"} <= names
    ds = next(p for p in body["providers"] if p["name"] == "deepseek")
    assert ds["key_configured"] is True
    assert ds["default_model"] == "deepseek-chat"
