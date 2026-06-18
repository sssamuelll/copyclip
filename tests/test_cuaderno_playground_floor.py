"""Epic #139 — the deterministic playground floor.

A run-request that names a resolvable symbol must NOT seal off_target when the
model answers in grounded prose: the compositor constructs the playground widget
itself from the resolved function_ref. The model authors the words; the SYSTEM
guarantees the type.

Roster ruling (project memory: capability-not-configuration): a property the
system guarantees about a model's output must be enforced OUTSIDE the model. The
run-request -> playground gate was a plea to the model (1-in-6 on DeepSeek); this
floor makes the artifact type deterministic while keeping authorship the model's.
The 'never invent' invariant is preserved by construction: the widget is built
ONLY from a symbol that resolves against the symbols table, else it falls through
to today's honest off_target.
"""
import sqlite3
from pathlib import Path

from copyclip.intelligence.cuaderno.compositor import iter_compose_events
from copyclip.intelligence.cuaderno.judge import JudgeVerdict
from copyclip.intelligence.db import init_schema


class StubStream:
    """Scripted messages_stream, mirroring the AnthropicAdapter contract."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def messages_stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self._turns:
            raise RuntimeError("StubStream ran out of scripted turns")
        for ev in self._turns.pop(0):
            yield ev


def _tool_stop(block_id, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": block_id, "name": name, "input": inp}}


def _content(block_id, name, inp):
    return {"type": "tool_use", "id": block_id, "name": name, "input": inp}


def _msg_stop(stop_reason, content):
    return {"type": "message_stop", "stop_reason": stop_reason, "content": content}


def _seed_symbol_project(conn: sqlite3.Connection) -> int:
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", ("/proj", "test"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?", ("/proj",)).fetchone()[0])
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, "_module_from_relpath", "function",
         "src/copyclip/intelligence/analyzer.py", 152, 170, None, "copyclip/intelligence"),
    )
    conn.commit()
    return pid


def _grounded_prose_turn(bid: str, fid: str, text: str):
    return [
        _tool_stop(bid, "emit_block", {"kind": "lead", "text": text}),
        _tool_stop(fid, "finish", {}),
        _msg_stop("tool_use", [
            _content(bid, "emit_block", {"kind": "lead", "text": text}),
            _content(fid, "finish", {}),
        ]),
    ]


def test_run_request_prose_constructs_playground_floor(tmp_path: Path):
    """The DeepSeek failure trace: model reads, then composes grounded prose for a
    run-request; the judge flags it non-responsive every time. Today this seals
    off_target. The floor must instead construct the playground and seal answer."""
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_symbol_project(conn)

    read = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    prose1 = _grounded_prose_turn("b1", "f1", "Convierte una ruta relativa en el nombre del modulo que la contiene.")
    prose2 = _grounded_prose_turn("b2", "f2", "Colapsa contenedores estructurales como src y lib.")
    client = StubStream([read, prose1, prose2])

    # The judge keeps flagging the prose as non-responsive for a run-request.
    jv = JudgeVerdict("code_comprehension", True, False, True, "retry", None,
                      "give a runnable example, not a description", "describes, does not run")
    events = list(iter_compose_events(
        client=client,
        question="dame un ejemplo ejecutable de _module_from_relpath",
        project_root=str(tmp_path), project_id=pid, conn=conn,
        judge=lambda q, b, l: jv,
    ))

    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer", (
        f"the floor must seal answer (constructed the artifact), got {frame['status']!r}"
    )
    playgrounds = [
        b for b in frame["blocks"]
        if b.get("kind") == "widget" and b.get("widget", {}).get("kind") == "playground"
    ]
    assert len(playgrounds) == 1, "the floor must construct exactly one playground widget"
    fr = playgrounds[0]["widget"]["function_ref"]
    assert fr["name"] == "_module_from_relpath"
    assert fr["file"] == "src/copyclip/intelligence/analyzer.py"


def test_run_request_unresolvable_symbol_stays_off_target(tmp_path: Path):
    """Never invent: a run-request whose named symbol does NOT resolve against the
    symbols table must keep the honest off_target — the floor declines to build a
    widget it cannot ground (which would error at launch)."""
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_symbol_project(conn)  # seeds ONLY _module_from_relpath

    read = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    prose1 = _grounded_prose_turn("b1", "f1", "Una descripcion fundada del comportamiento.")
    prose2 = _grounded_prose_turn("b2", "f2", "Mas descripcion, todavia sin ejecutar nada.")
    client = StubStream([read, prose1, prose2])

    jv = JudgeVerdict("code_comprehension", True, False, True, "retry", None,
                      "give a runnable example, not a description", "describes, does not run")
    events = list(iter_compose_events(
        client=client,
        question="dame un ejemplo ejecutable de funcion_que_no_existe",
        project_root=str(tmp_path), project_id=pid, conn=conn,
        judge=lambda q, b, l: jv,
    ))

    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "off_target", "no resolvable symbol -> honest off_target stands"
    playgrounds = [
        b for b in frame["blocks"]
        if b.get("kind") == "widget" and b.get("widget", {}).get("kind") == "playground"
    ]
    assert playgrounds == [], "the floor must NOT invent a widget for an unresolvable symbol"


def _playgrounds(frame: dict) -> list:
    return [
        b for b in frame["blocks"]
        if b.get("kind") == "widget" and b.get("widget", {}).get("kind") == "playground"
    ]


def test_run_request_model_playground_off_target_is_upgraded(tmp_path: Path):
    """A run-request answered WITH a playground is responsive by definition. If the
    model itself emits the playground but the (weak) judge still flags off_target,
    the frame must seal answer — off_target on an artifact-bearing run-request is
    the judge mislabeling form as relevance (the category error the council named).
    Reclassify, don't relabel."""
    analyzer = tmp_path / "src" / "copyclip" / "intelligence" / "analyzer.py"
    analyzer.parent.mkdir(parents=True)
    analyzer.write_text("def _module_from_relpath(p):\n    return p.split('/')[0]\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_symbol_project(conn)

    pg_widget = {
        "kind": "widget",
        "widget": {
            "kind": "playground",
            "function_ref": {
                "file": "src/copyclip/intelligence/analyzer.py",
                "name": "_module_from_relpath", "line": 152,
            },
            "breadcrumb": "corre la funcion con ejemplos",
        },
    }
    read = [
        _tool_stop("r1", "read_file", {"path": "src/copyclip/intelligence/analyzer.py"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "src/copyclip/intelligence/analyzer.py"})]),
    ]
    # Grounded prose + the model's own playground, then finish.
    emit_pg = [
        _tool_stop("l1", "emit_block", {"kind": "lead", "text": "La funcion deriva el modulo de una ruta."}),
        _tool_stop("w1", "emit_block", pg_widget),
        _tool_stop("f", "finish", {}),
        _msg_stop("tool_use", [
            _content("l1", "emit_block", {"kind": "lead", "text": "La funcion deriva el modulo de una ruta."}),
            _content("w1", "emit_block", pg_widget),
            _content("f", "finish", {}),
        ]),
    ]
    client = StubStream([read, emit_pg, emit_pg])
    jv = JudgeVerdict("code_comprehension", True, False, True, "retry", None,
                      "redo", "judge mislabels an artifact-bearing answer")
    events = list(iter_compose_events(
        client=client,
        question="dame un ejemplo ejecutable de _module_from_relpath",
        project_root=str(tmp_path), project_id=pid, conn=conn,
        judge=lambda q, b, l: jv,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer", (
        f"a run-request frame containing a playground must seal answer, got {frame['status']!r}"
    )
    assert len(_playgrounds(frame)) == 1, "the model's own playground must survive (not duplicated)"


def test_run_request_budget_tail_constructs_playground_floor(tmp_path: Path):
    """DeepSeek's dominant trace: the model explores to budget exhaustion without
    a clean finish, the tail judges the grounded prose off_target. The floor must
    fire at the budget tail too (not only at the clean-finish judge seal)."""
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_symbol_project(conn)

    read = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    # Emits a grounded block but never finishes -> stays tool_use -> budget tail.
    emit_no_finish = [
        _tool_stop("b1", "emit_block", {"kind": "lead", "text": "Describe el comportamiento, fundado en el archivo."}),
        _msg_stop("tool_use", [_content("b1", "emit_block", {"kind": "lead", "text": "Describe el comportamiento, fundado en el archivo."})]),
    ]
    client = StubStream([read, emit_no_finish, emit_no_finish])
    jv = JudgeVerdict("code_comprehension", True, False, True, "retry", None,
                      "give a runnable example", "describes, does not run")
    events = list(iter_compose_events(
        client=client,
        question="dame un ejemplo ejecutable de _module_from_relpath",
        project_root=str(tmp_path), project_id=pid, conn=conn,
        judge=lambda q, b, l: jv, max_tool_rounds=3,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer", f"budget-tail off_target run-request must be floored, got {frame['status']!r}"
    pg = _playgrounds(frame)
    assert len(pg) == 1
    assert pg[0]["widget"]["function_ref"]["name"] == "_module_from_relpath"


def test_run_request_blank_fallback_constructs_playground_floor(tmp_path: Path):
    """The known 'never a blank screen' gap: the model explores and emits nothing,
    the budget exhausts to a fallback. For a run-request naming a resolvable
    symbol, the floor turns the blank into the runnable artifact."""
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = _seed_symbol_project(conn)

    read = [
        _tool_stop("r1", "read_file", {"path": "README.md"}),
        _msg_stop("tool_use", [_content("r1", "read_file", {"path": "README.md"})]),
    ]
    client = StubStream([read, read, read])  # explores, never composes
    events = list(iter_compose_events(
        client=client,
        question="dame un ejemplo ejecutable de _module_from_relpath",
        project_root=str(tmp_path), project_id=pid, conn=conn,
        max_tool_rounds=3,
    ))
    frame = next(e for e in events if e["type"] == "frame")["frame"]
    assert frame["status"] == "answer", f"blank fallback run-request must be floored, got {frame['status']!r}"
    pg = _playgrounds(frame)
    assert len(pg) == 1, "the floor must turn a blank into a playground"
    assert pg[0]["widget"]["function_ref"]["file"] == "src/copyclip/intelligence/analyzer.py"
    # The 'couldn't finish' fallback message must NOT survive alongside the artifact.
    leads = [b for b in frame["blocks"] if b.get("kind") == "paragraph"]
    assert leads == [], "fallback message must be dropped when the floor delivers the artifact"


# ---------------------------------------------------------------------------
# Task 9: floor emits real call descriptor + breadcrumb rename
# ---------------------------------------------------------------------------

from copyclip.intelligence.cuaderno.compositor import _construct_playground_floor


def test_floor_breadcrumb_is_step_through_spanish(tmp_path: Path):
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)
    block, reason = _construct_playground_floor(
        "ejecuta _module_from_relpath", conn, pid, ledger=None, emitted=[],
        project_root=str(tmp_path))
    assert reason is None
    w = block.to_dict()["widget"]
    assert w["breadcrumb"] == "Recorre _module_from_relpath paso a paso"


def test_floor_breadcrumb_is_step_through_english(tmp_path: Path):
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)
    block, reason = _construct_playground_floor(
        "run _module_from_relpath", conn, pid, ledger=None, emitted=[],
        project_root=str(tmp_path))
    assert reason is None
    w = block.to_dict()["widget"]
    assert w["breadcrumb"] == "Step through _module_from_relpath"


def test_floor_emits_real_call_descriptor(tmp_path: Path):
    # spec §6: the widget must carry a REAL call so the frontend renders the
    # actual invocation, not a fake placeholder. The floor seeds a bare call
    # (function_ref only) when it has no model-proposed args — the frontend's
    # editable free-text field then shows `name(...)` from the real ref.
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)
    block, reason = _construct_playground_floor(
        "run _module_from_relpath", conn, pid, ledger=None, emitted=[],
        project_root=str(tmp_path))
    assert reason is None
    w = block.to_dict()["widget"]
    assert w["call"]["function_ref"]["name"] == "_module_from_relpath"
    assert w["call"]["function_ref"]["file"] == "src/copyclip/intelligence/analyzer.py"


# ---------------------------------------------------------------------------
# ORCHESTRATION Fix 7: the floor must DECLINE a doomed bare-floor widget — a
# method-without-ctor or an arity>0 function with no proposed args would render
# `name()` and TypeError / fall back. Don't emit a widget we KNOW is doomed.
# ---------------------------------------------------------------------------


def _seed_arity0_function(conn: sqlite3.Connection, root: str, tmp_path: Path) -> int:
    """Seed a project whose run-target is an arity-0 function with REAL source on
    disk (so the floor can read its signature and emit a non-doomed `name()`)."""
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0])
    src = tmp_path / "src" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def boot():\n    return 1\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, "boot", "function", "src/pkg/mod.py", 1, 2, None, "pkg"),
    )
    conn.commit()
    return pid


def _seed_arity_n_function(conn: sqlite3.Connection, root: str, tmp_path: Path) -> int:
    """Seed an arity-1 function WITH real source so the floor reads arity>0."""
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0])
    src = tmp_path / "src" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def needs_arg(rel):\n    return rel.upper()\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, "needs_arg", "function", "src/pkg/mod.py", 1, 2, None, "pkg"),
    )
    conn.commit()
    return pid


def test_floor_proposes_widget_for_arity0_function(tmp_path: Path):
    """An arity-0 function's `name()` floor is NOT doomed — the floor proceeds."""
    root = str(tmp_path)
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_arity0_function(conn, root, tmp_path)
    block, reason = _construct_playground_floor(
        "run boot", conn, pid, ledger=None, emitted=[], project_root=root)
    assert reason is None, f"arity-0 floor must be offered; declined with {reason!r}"
    assert block is not None
    assert block.to_dict()["widget"]["call"]["function_ref"]["name"] == "boot"


def test_floor_declines_arity_n_function_with_no_args(tmp_path: Path):
    """An arity>0 function with no proposed args would render `name()` and
    TypeError — the floor must DECLINE rather than emit a doomed widget."""
    root = str(tmp_path)
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_arity_n_function(conn, root, tmp_path)
    block, reason = _construct_playground_floor(
        "run needs_arg", conn, pid, ledger=None, emitted=[], project_root=root)
    assert block is None, "an arity>0 bare floor must be declined (doomed `name()` call)"
    assert reason is not None and ("argument" in reason.lower() or "arity" in reason.lower())


def test_floor_declines_method_without_ctor(tmp_path: Path):
    """A method-without-inferable-ctor bare floor would TypeError — decline it."""
    root = str(tmp_path)
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (root, "t"))
    pid = int(conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()[0])
    src = tmp_path / "src" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("class Worker:\n    def run(self):\n        return 1\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (pid, "run", "method", "src/pkg/mod.py", 2, 3, None, "pkg"),
    )
    conn.commit()
    block, reason = _construct_playground_floor(
        "run run", conn, pid, ledger=None, emitted=[], project_root=root)
    assert block is None, "a method-without-ctor bare floor must be declined"
    assert reason is not None and ("ctor" in reason.lower() or "constructor" in reason.lower()
                                   or "method" in reason.lower())


def test_floor_proceeds_when_arity_unknown(tmp_path: Path):
    """When the source is not readable (arity unknown), the floor must NOT decline
    on arity grounds — it preserves the 'symbol resolves → offer the floor'
    behavior. (Only positively-doomed targets are declined.)"""
    (tmp_path / "README.md").write_text("# analyzer\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:"); init_schema(conn)
    pid = _seed_symbol_project(conn)  # file points at analyzer.py NOT in tmp_path
    block, reason = _construct_playground_floor(
        "run _module_from_relpath", conn, pid, ledger=None, emitted=[],
        project_root=str(tmp_path))
    assert reason is None, (
        f"arity-unknown floor must still be offered (symbol resolved); declined: {reason!r}"
    )
    assert block is not None
