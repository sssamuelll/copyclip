"""GET /api/cuaderno/entry-cue — the entry cue wired to session-open.

The cue is the proactive launching point (pulso.build_entry_cue): the single
most-overdue AI burst the human has NOT returned to. The route must be pure
exposición — it reads, it never records. Reading the cue is not returning to
the file, so unlike /api/reacquaintance it must NOT write a project visit.
"""
import json
import socket
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request

from copyclip.intelligence.db import connect, init_schema, init_cuaderno_schema
from copyclip.intelligence.server import run_server


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


def _get_json(url, timeout=10):
    with request.urlopen(url, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S +0000")


def _setup_server(*, with_cue_data: bool):
    td = tempfile.mkdtemp(prefix="entry-cue-test-")
    root = str(Path(td).absolute())
    conn = connect(root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "test"))
    pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0]

    if with_cue_data:
        now = datetime.now(timezone.utc)
        # Snapshot row selects the candidate; updated_at 20d old -> stale=True.
        conn.execute(
            "INSERT INTO analysis_file_insights"
            "(project_id, path, module, pulso_last_contact_days, updated_at) "
            "VALUES(?,?,?,?,?)",
            (pid, "src/cold.py", "m", 100,
             (now - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")),
        )
        # Live verification: human commit, then an AI burst after -> hasn't been back.
        conn.execute(
            "INSERT INTO commits(project_id, sha, author, date, message, ai_attributed) "
            "VALUES(?,?,?,?,?,?)",
            (pid, "h-cold", "S", _iso(now - timedelta(days=120)), "m", 0))
        conn.execute(
            "INSERT INTO commits(project_id, sha, author, date, message, ai_attributed) "
            "VALUES(?,?,?,?,?,?)",
            (pid, "ai-cold", "S", _iso(now - timedelta(days=60)), "m", 1))
        for sha in ("h-cold", "ai-cold"):
            conn.execute(
                "INSERT INTO file_changes(project_id, commit_sha, file_path, additions, deletions) "
                "VALUES(?,?,?,0,0)", (pid, sha, "src/cold.py"))

    conn.commit()
    conn.close()
    port = _free_port()
    th = threading.Thread(target=run_server, args=(root, port), daemon=True)
    th.start()
    _wait_port(port)
    return root, port


def test_entry_cue_route_returns_the_live_cue():
    root, port = _setup_server(with_cue_data=True)
    status, payload = _get_json(f"http://127.0.0.1:{port}/api/cuaderno/entry-cue")
    assert status == 200
    cue = payload["entry_cue"]
    assert cue is not None
    assert cue["file_path"] == "src/cold.py"
    assert cue["ai_burst_days"] >= 59
    assert cue["last_contact_source"] == "git"
    assert cue["never_human_touched"] is False
    # snapshot is 20d old (> stale_after_days=14) -> the claim must be hedged
    assert cue["stale"] is True
    assert cue["analyzed_age_days"] >= 19


def test_entry_cue_route_is_silent_when_nothing_to_surface():
    root, port = _setup_server(with_cue_data=False)
    status, payload = _get_json(f"http://127.0.0.1:{port}/api/cuaderno/entry-cue")
    assert status == 200
    assert payload == {"entry_cue": None}


def test_entry_cue_route_never_records_a_visit():
    # Reading the cue is not returning to the file: unlike /api/reacquaintance
    # (server.py records a reacquaintance_api visit), this GET must write nothing.
    root, port = _setup_server(with_cue_data=True)
    _get_json(f"http://127.0.0.1:{port}/api/cuaderno/entry-cue")
    conn = connect(root)
    try:
        count = conn.execute("SELECT COUNT(*) FROM project_visits").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
