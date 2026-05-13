"""Contract tests for the unified /api/cognitive-load endpoint.

The endpoint used to compute its own proxy score inline. After unification it
must serve the v1 factor-model score from ``build_debt_breakdown`` while
preserving the legacy fields the frontend already consumes.
"""

import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request

from copyclip.intelligence import cognitive_debt
from copyclip.intelligence.cognitive_debt import build_debt_breakdown
from copyclip.intelligence.db import connect, init_schema
from copyclip.intelligence.server import run_server

from tests.fixtures.cog_debt_fixtures import STABLE_NOW_TS, seed_mixed_debt_project


SEVERITY_TO_FOG = {"critical": "high", "high": "high", "medium": "med", "low": "low"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(port: int, timeout_s: float = 3.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start in time")


def _get_json(url: str):
    with request.urlopen(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _start_server_with_seed(tmp_path: Path, monkeypatch, seed_fn) -> tuple[int, int]:
    monkeypatch.setattr(cognitive_debt, "_now_ts", lambda: STABLE_NOW_TS)
    root_path = str(tmp_path)
    conn = connect(root_path)
    init_schema(conn)
    pid = seed_fn(conn, root_path)
    conn.close()
    port = _free_port()
    th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
    th.start()
    _wait_port(port)
    return pid, port


def test_cognitive_load_score_equals_factor_model_for_each_module(tmp_path, monkeypatch):
    pid, port = _start_server_with_seed(tmp_path, monkeypatch, seed_mixed_debt_project)
    payload = _get_json(f"http://127.0.0.1:{port}/api/cognitive-load")
    items = payload["items"]
    assert items, "mixed_debt fixture should produce at least one module item"

    conn = connect(str(tmp_path))
    try:
        for item in items:
            module = item["module"]
            breakdown = build_debt_breakdown(conn, pid, "module", module)
            assert item["cognitive_debt_score"] == breakdown["score"]["value"], (
                f"score mismatch for module {module}: "
                f"endpoint={item['cognitive_debt_score']} factor_model={breakdown['score']['value']}"
            )
            assert item["severity"] == breakdown["score"]["severity"], (
                f"severity mismatch for module {module}"
            )
    finally:
        conn.close()


def test_cognitive_load_reaches_high_or_critical_on_mixed_fixture(tmp_path, monkeypatch):
    _, port = _start_server_with_seed(tmp_path, monkeypatch, seed_mixed_debt_project)
    payload = _get_json(f"http://127.0.0.1:{port}/api/cognitive-load")
    severities = {item["severity"] for item in payload["items"]}
    assert severities & {"high", "critical"}, (
        f"expected at least one high/critical module on the mixed_debt fixture, got {severities}"
    )


def test_cognitive_load_fog_level_maps_from_severity(tmp_path, monkeypatch):
    _, port = _start_server_with_seed(tmp_path, monkeypatch, seed_mixed_debt_project)
    payload = _get_json(f"http://127.0.0.1:{port}/api/cognitive-load")
    for item in payload["items"]:
        expected_fog = SEVERITY_TO_FOG[item["severity"]]
        assert item["fog_level"] == expected_fog, (
            f"module {item['module']}: severity={item['severity']} -> "
            f"expected fog={expected_fog}, got {item['fog_level']}"
        )
        assert item["fog_level"] in {"low", "med", "high"}


def test_cognitive_load_preserves_legacy_fields(tmp_path, monkeypatch):
    _, port = _start_server_with_seed(tmp_path, monkeypatch, seed_mixed_debt_project)
    payload = _get_json(f"http://127.0.0.1:{port}/api/cognitive-load")
    assert payload["items"], "fixture must yield items"
    for item in payload["items"]:
        for key in ("module", "files", "churn", "avg_complexity", "decision_linked",
                    "cognitive_debt_score", "fog_level", "severity"):
            assert key in item, f"missing legacy/new field {key} on item {item}"
        assert isinstance(item["files"], int) and item["files"] >= 1
        assert isinstance(item["churn"], int)
        assert isinstance(item["avg_complexity"], (int, float))
        assert isinstance(item["decision_linked"], bool)
        assert item["severity"] in {"low", "medium", "high", "critical"}


def test_cognitive_load_returns_empty_when_no_project(tmp_path, monkeypatch):
    monkeypatch.setattr(cognitive_debt, "_now_ts", lambda: STABLE_NOW_TS)
    root_path = str(tmp_path)
    conn = connect(root_path)
    init_schema(conn)
    conn.close()
    port = _free_port()
    th = threading.Thread(target=run_server, args=(root_path, port), daemon=True)
    th.start()
    _wait_port(port)
    payload = _get_json(f"http://127.0.0.1:{port}/api/cognitive-load")
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["last_review_at"] is None


def test_cognitive_load_does_not_use_legacy_proxy_formula(tmp_path, monkeypatch):
    """Sanity check: at least one module on the mixed fixture should diverge from
    the legacy proxy. The legacy formula would put copyclip.mcp around the
    medium band (debt~churn+complexity, capped/decayed by the decision link),
    whereas the factor model lands it firmly in high/critical territory.
    """
    pid, port = _start_server_with_seed(tmp_path, monkeypatch, seed_mixed_debt_project)
    payload = _get_json(f"http://127.0.0.1:{port}/api/cognitive-load")
    mcp_items = [it for it in payload["items"] if it["module"] == "copyclip.mcp"]
    assert mcp_items, "expected copyclip.mcp in the mixed_debt fixture"
    mcp = mcp_items[0]
    assert mcp["severity"] in {"high", "critical"}, (
        f"factor model must mark copyclip.mcp as high/critical (got {mcp['severity']})"
    )
