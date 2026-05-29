# Cuaderno Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 1 of the cuaderno conversacional — a new sidebar page where the user types a question, an LLM compositor reads code via tool calls, and a structured "educational frame" renders with text, code blocks, citations, display-only widget glimpses, side panel, history overlay, and "I got this / I didn't" markers.

**Architecture:** Three layers. Frontend `CuadernoPage` posts the user's question to a new `POST /api/cuaderno/ask` endpoint, then receives a structured `Frame` JSON via SSE streaming. Backend `Compositor` runs an Anthropic Claude agentic loop with structured tool calls into the `Anchor System` (file reads, symbols DB queries, git commands). Sessions persist in `.copyclip/cuaderno-sessions.db` (SQLite). Visual + interaction is a 1:1 port of the prototype at `docs/superpowers/specs/2026-05-28-cuaderno-prototype/`.

**Tech Stack:**
- Backend: Python 3.10+, `anthropic` SDK (NEW dep), `sqlite3`, the existing `BaseHTTPRequestHandler` server, the existing `intelligence.db` for symbols access.
- Frontend: React 18 + TypeScript + Vite + `vite-plugin-singlefile` (existing). Ports prototype JSX → TSX. No new build deps.
- LLM: Anthropic Claude (provider already configured via `copyclip start` onboarding). Phase 1 uses Sonnet by default; model selection is config-driven so it can be swapped without code change.

---

## File structure

### Backend — new files

- `src/copyclip/intelligence/cuaderno/__init__.py` — package marker, exports
- `src/copyclip/intelligence/cuaderno/schema.py` — dataclasses: `Citation`, `Block` variants, `Widget` variants, `Frame`, `ToolCall`, `Question`, `Session`
- `src/copyclip/intelligence/cuaderno/anchor.py` — implements each tool call function; pure, no LLM
- `src/copyclip/intelligence/cuaderno/tool_catalog.py` — builds Anthropic-format tool definitions
- `src/copyclip/intelligence/cuaderno/compositor.py` — agentic loop: LLM ↔ tools, returns final `Frame`
- `src/copyclip/intelligence/cuaderno/persistence.py` — SQLite save/load of sessions + questions

### Backend — modified files

- `src/copyclip/intelligence/server.py` — add 3 routes (ask, list sessions, get session). Pattern follows existing routes.
- `src/copyclip/intelligence/db.py` — add `init_cuaderno_schema()` migration for new tables
- `pyproject.toml` — add `anthropic>=0.39` to dependencies

### Frontend — new files

- `frontend/src/pages/CuadernoPage.tsx` — top-level container; owns session state, API calls
- `frontend/src/components/cuaderno/Cuaderno.tsx` — surface shell (port of `cuaderno.jsx`)
- `frontend/src/components/cuaderno/Composer.tsx` — input pill
- `frontend/src/components/cuaderno/SidePanel.tsx` — citation viewer (port of `SidePanel` in prototype)
- `frontend/src/components/cuaderno/HistoryOverlay.tsx` — session history modal
- `frontend/src/components/cuaderno/GotItMarkers.tsx` — got/didn't buttons
- `frontend/src/components/cuaderno/frames/FrameEmpty.tsx` — first-visit frame (port of `FrameEmpty`)
- `frontend/src/components/cuaderno/frames/FrameMidStream.tsx` — streaming/tool-call frame (port of `FrameMidStream`)
- `frontend/src/components/cuaderno/frames/FrameDynamic.tsx` — renders any `Frame` from API by walking `Block[]`
- `frontend/src/components/cuaderno/widgets/GraphSubset.tsx` — port of widget
- `frontend/src/components/cuaderno/widgets/SequenceDiagram.tsx` — port of widget
- `frontend/src/components/cuaderno/widgets/CallersTree.tsx` — port of widget
- `frontend/src/styles/cuaderno.css` — port of prototype's `styles.css`
- `frontend/src/api/cuaderno.ts` — typed wrapper for cuaderno endpoints + SSE handling

### Frontend — modified files

- `frontend/src/App.tsx` — add `'cuaderno'` page id + route
- `frontend/src/components/Sidebar.tsx` — add `cuaderno` to a group (top of "Project Memory")
- `frontend/src/types/api.ts` — add `Frame`, `Block`, `Widget`, `Citation`, `CuadernoSession` types
- `frontend/src/index.css` (or wherever global styles live) — import `cuaderno.css`

### Tests

- `tests/test_cuaderno_schema.py` — JSON round-trip for all Block/Widget kinds
- `tests/test_cuaderno_anchor.py` — each tool function against a known fixture
- `tests/test_cuaderno_tool_catalog.py` — assertions on the Anthropic tool definitions
- `tests/test_cuaderno_compositor.py` — agentic loop with a stub Anthropic client
- `tests/test_cuaderno_persistence.py` — session save/restore
- `tests/test_cuaderno_endpoint.py` — HTTP integration test for `/api/cuaderno/ask`

---

## Phase A — Backend foundation

### Task 1: Add anthropic SDK dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

Find the `dependencies = [...]` block in `pyproject.toml`. Add the line `"anthropic>=0.39",` immediately after the existing `"psutil>=5.9",` line.

- [ ] **Step 2: Install editable**

Run: `python -m pip install -e .`
Expected: `Successfully installed anthropic-x.y.z ...` (or "Requirement already satisfied" — both fine).

- [ ] **Step 3: Verify import**

Run: `python -c "import anthropic; print(anthropic.__version__)"`
Expected: A version string like `0.39.0` or higher.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add anthropic SDK for cuaderno compositor"
```

---

### Task 2: Cuaderno schema dataclasses

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/__init__.py`
- Create: `src/copyclip/intelligence/cuaderno/schema.py`
- Test: `tests/test_cuaderno_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_schema.py
from copyclip.intelligence.cuaderno.schema import (
    Citation, Block, Widget, Frame, frame_to_dict, frame_from_dict,
)


def test_path_citation_round_trip():
    c = Citation(path="src/foo.py", line_start=10, line_end=20)
    d = c.to_dict()
    assert d == {"kind": "path", "path": "src/foo.py", "line_start": 10, "line_end": 20}
    assert Citation.from_dict(d) == c


def test_commit_citation_round_trip():
    c = Citation(commit="a0dae63")
    assert c.to_dict() == {"kind": "commit", "commit": "a0dae63"}
    assert Citation.from_dict({"kind": "commit", "commit": "a0dae63"}) == c


def test_frame_round_trip_full():
    f = Frame(
        question="what does this project do?",
        blocks=[
            Block.lead("CopyClip is a personal tool."),
            Block.paragraph("Three subsystems compose its core."),
            Block.ordered_list([
                {"head": "Analyzer", "desc": "Parses the repo.",
                 "citation": Citation(path="src/foo.py", line_start=1, line_end=50).to_dict()},
            ]),
            Block.code_block(code="def f(): pass", language="python",
                             citation=Citation(path="x.py", line_start=1).to_dict()),
            Block.ascii_block(text="A -> B"),
            Block.citation(citation=Citation(path="x.py").to_dict()),
            Block.citation_stack(items=[
                {"citation": Citation(path="a.py").to_dict(), "note": "fix"},
            ]),
            Block.callout(kicker="key point", text="explanation",
                          citations=[Citation(commit="abc1234").to_dict()]),
            Block.widget(widget=Widget.graph_subset(
                nodes=[{"id": "a", "label": "analyzer.py", "you": False}],
                edges=[],
            ).to_dict()),
            Block.followups(items=[
                {"label": "the analyzer", "question": "explore the analyzer"},
            ]),
        ],
    )
    d = frame_to_dict(f)
    f2 = frame_from_dict(d)
    assert frame_to_dict(f2) == d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'copyclip.intelligence.cuaderno'`.

- [ ] **Step 3: Create __init__.py**

Create `src/copyclip/intelligence/cuaderno/__init__.py` with content:

```python
"""Cuaderno — conversational LLM-tutor surface (Phase 1).

See docs/superpowers/specs/2026-05-28-copyclip-cuaderno-conversacional-design.md
"""
```

- [ ] **Step 4: Implement schema**

Create `src/copyclip/intelligence/cuaderno/schema.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Citation:
    path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    commit: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        if self.commit:
            return {"kind": "commit", "commit": self.commit}
        d: dict[str, Any] = {"kind": "path", "path": self.path}
        if self.line_start is not None:
            d["line_start"] = self.line_start
        if self.line_end is not None:
            d["line_end"] = self.line_end
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Citation":
        if d.get("kind") == "commit":
            return Citation(commit=d["commit"])
        return Citation(
            path=d.get("path"),
            line_start=d.get("line_start"),
            line_end=d.get("line_end"),
        )


@dataclass(frozen=True)
class Widget:
    """A display-only widget glimpse inside a frame block."""
    kind: str  # 'graph_subset' | 'sequence_diagram' | 'callers_tree'
    data: dict[str, Any]

    @staticmethod
    def graph_subset(nodes: list[dict], edges: list[dict]) -> "Widget":
        return Widget(kind="graph_subset", data={"nodes": nodes, "edges": edges})

    @staticmethod
    def sequence_diagram(actors: list[str], steps: list[dict]) -> "Widget":
        return Widget(kind="sequence_diagram", data={"actors": actors, "steps": steps})

    @staticmethod
    def callers_tree(root: str, callers: list[dict]) -> "Widget":
        return Widget(kind="callers_tree", data={"root": root, "callers": callers})

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Widget":
        kind = d["kind"]
        data = {k: v for k, v in d.items() if k != "kind"}
        return Widget(kind=kind, data=data)


@dataclass(frozen=True)
class Block:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def lead(text: str) -> "Block":
        return Block(kind="lead", data={"text": text})

    @staticmethod
    def paragraph(text: str) -> "Block":
        return Block(kind="paragraph", data={"text": text})

    @staticmethod
    def ordered_list(items: list[dict]) -> "Block":
        return Block(kind="ordered_list", data={"items": items})

    @staticmethod
    def code_block(code: str, language: str, citation: Optional[dict] = None) -> "Block":
        d: dict[str, Any] = {"code": code, "language": language}
        if citation is not None:
            d["citation"] = citation
        return Block(kind="code_block", data=d)

    @staticmethod
    def ascii_block(text: str) -> "Block":
        return Block(kind="ascii_block", data={"text": text})

    @staticmethod
    def citation(citation: dict) -> "Block":
        return Block(kind="citation", data={"citation": citation})

    @staticmethod
    def citation_stack(items: list[dict]) -> "Block":
        return Block(kind="citation_stack", data={"items": items})

    @staticmethod
    def callout(kicker: str, text: str, citations: Optional[list[dict]] = None) -> "Block":
        d: dict[str, Any] = {"kicker": kicker, "text": text}
        if citations is not None:
            d["citations"] = citations
        return Block(kind="callout", data=d)

    @staticmethod
    def widget(widget: dict) -> "Block":
        return Block(kind="widget", data={"widget": widget})

    @staticmethod
    def followups(items: list[dict]) -> "Block":
        return Block(kind="followups", data={"items": items})

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Block":
        kind = d["kind"]
        data = {k: v for k, v in d.items() if k != "kind"}
        return Block(kind=kind, data=data)


@dataclass
class Frame:
    question: str
    blocks: list[Block]


def frame_to_dict(f: Frame) -> dict[str, Any]:
    return {"question": f.question, "blocks": [b.to_dict() for b in f.blocks]}


def frame_from_dict(d: dict[str, Any]) -> Frame:
    return Frame(
        question=d["question"],
        blocks=[Block.from_dict(b) for b in d["blocks"]],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_schema.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/__init__.py src/copyclip/intelligence/cuaderno/schema.py tests/test_cuaderno_schema.py
git commit -m "feat(cuaderno): Frame/Block/Widget/Citation schema with JSON round-trip"
```

---

### Task 3: Cuaderno DB schema migration

**Files:**
- Modify: `src/copyclip/intelligence/db.py`
- Test: `tests/test_cuaderno_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_persistence.py
import sqlite3
from copyclip.intelligence.db import init_cuaderno_schema


def test_init_cuaderno_schema_creates_tables():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)

    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "cuaderno_sessions" in tables
    assert "cuaderno_questions" in tables


def test_init_cuaderno_schema_is_idempotent():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)
    init_cuaderno_schema(conn)  # second call must not raise

    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "cuaderno_sessions" in tables


def test_cuaderno_questions_links_to_session():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)

    conn.execute(
        "INSERT INTO cuaderno_sessions(id, project_root, created_at) VALUES(?,?,?)",
        ("s1", "/tmp/proj", "2026-05-28T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO cuaderno_questions"
        "(session_id, position, question, frame_json, bookmarked, got_it, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("s1", 1, "what?", '{"question":"what?","blocks":[]}', 0, None, "2026-05-28T00:00:01Z"),
    )
    conn.commit()

    row = conn.execute(
        "SELECT session_id, position FROM cuaderno_questions WHERE session_id=?", ("s1",)
    ).fetchone()
    assert row == ("s1", 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_persistence.py -v`
Expected: FAIL with `ImportError: cannot import name 'init_cuaderno_schema' from 'copyclip.intelligence.db'`.

- [ ] **Step 3: Add the migration to db.py**

Open `src/copyclip/intelligence/db.py` and append at the end of the file:

```python
def init_cuaderno_schema(conn: sqlite3.Connection) -> None:
    """Create cuaderno session + question tables. Idempotent."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cuaderno_sessions (
            id           TEXT PRIMARY KEY,
            project_root TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            last_seen_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cuaderno_questions (
            id          INTEGER PRIMARY KEY,
            session_id  TEXT NOT NULL REFERENCES cuaderno_sessions(id) ON DELETE CASCADE,
            position    INTEGER NOT NULL,
            question    TEXT NOT NULL,
            frame_json  TEXT NOT NULL,
            bookmarked  INTEGER NOT NULL DEFAULT 0,
            got_it      TEXT,
            created_at  TEXT NOT NULL,
            UNIQUE(session_id, position)
        );

        CREATE INDEX IF NOT EXISTS cuaderno_questions_session
            ON cuaderno_questions(session_id, position);
        """
    )
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_persistence.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/db.py tests/test_cuaderno_persistence.py
git commit -m "feat(cuaderno): db schema for sessions and questions"
```

---

### Task 4: Persistence layer

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/persistence.py`
- Test: `tests/test_cuaderno_persistence.py` (extends Task 3's file)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_cuaderno_persistence.py`:

```python
import json
from copyclip.intelligence.cuaderno.persistence import (
    create_session, save_question, list_questions, get_question_by_position,
    set_bookmark, set_got_it,
)
from copyclip.intelligence.cuaderno.schema import Frame, Block, frame_to_dict


def _conn():
    conn = sqlite3.connect(":memory:")
    init_cuaderno_schema(conn)
    return conn


def test_create_session_returns_id_and_persists():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    assert isinstance(sid, str) and len(sid) > 0
    row = conn.execute(
        "SELECT project_root FROM cuaderno_sessions WHERE id=?", (sid,)
    ).fetchone()
    assert row[0] == "/tmp/proj"


def test_save_question_assigns_position_starting_at_1():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    frame = Frame(question="q1", blocks=[Block.lead("hi")])
    pos1 = save_question(conn, sid, "q1", frame)
    pos2 = save_question(conn, sid, "q2", Frame(question="q2", blocks=[]))
    assert pos1 == 1
    assert pos2 == 2


def test_list_questions_returns_in_order():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[]))
    save_question(conn, sid, "q2", Frame(question="q2", blocks=[]))
    rows = list_questions(conn, sid)
    assert [r["position"] for r in rows] == [1, 2]
    assert [r["question"] for r in rows] == ["q1", "q2"]


def test_get_question_by_position_reconstructs_frame():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[Block.lead("hello")]))
    q = get_question_by_position(conn, sid, 1)
    assert q is not None
    assert q["question"] == "q1"
    assert q["frame"]["blocks"][0]["kind"] == "lead"


def test_set_bookmark_and_got_it():
    conn = _conn()
    sid = create_session(conn, project_root="/tmp/proj")
    save_question(conn, sid, "q1", Frame(question="q1", blocks=[]))
    set_bookmark(conn, sid, 1, True)
    set_got_it(conn, sid, 1, "got")
    q = get_question_by_position(conn, sid, 1)
    assert q["bookmarked"] is True
    assert q["got_it"] == "got"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_persistence.py -v`
Expected: 5 new tests FAIL with `ModuleNotFoundError: ... cuaderno.persistence`.

- [ ] **Step 3: Implement persistence.py**

Create `src/copyclip/intelligence/cuaderno/persistence.py`:

```python
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from .schema import Frame, frame_to_dict, frame_from_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_session(conn: sqlite3.Connection, *, project_root: str) -> str:
    sid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO cuaderno_sessions(id, project_root, created_at, last_seen_at) "
        "VALUES(?,?,?,?)",
        (sid, project_root, _now(), _now()),
    )
    conn.commit()
    return sid


def save_question(
    conn: sqlite3.Connection, session_id: str, question: str, frame: Frame
) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(position), 0) FROM cuaderno_questions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    next_pos = int(row[0]) + 1
    conn.execute(
        "INSERT INTO cuaderno_questions"
        "(session_id, position, question, frame_json, bookmarked, got_it, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (session_id, next_pos, question, json.dumps(frame_to_dict(frame)), 0, None, _now()),
    )
    conn.execute(
        "UPDATE cuaderno_sessions SET last_seen_at=? WHERE id=?", (_now(), session_id)
    )
    conn.commit()
    return next_pos


def list_questions(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT position, question, frame_json, bookmarked, got_it, created_at "
        "FROM cuaderno_questions WHERE session_id=? ORDER BY position",
        (session_id,),
    ).fetchall()
    return [
        {
            "position": r[0],
            "question": r[1],
            "frame": json.loads(r[2]),
            "bookmarked": bool(r[3]),
            "got_it": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def get_question_by_position(
    conn: sqlite3.Connection, session_id: str, position: int
) -> Optional[dict]:
    row = conn.execute(
        "SELECT question, frame_json, bookmarked, got_it, created_at "
        "FROM cuaderno_questions WHERE session_id=? AND position=?",
        (session_id, position),
    ).fetchone()
    if not row:
        return None
    return {
        "position": position,
        "question": row[0],
        "frame": json.loads(row[1]),
        "bookmarked": bool(row[2]),
        "got_it": row[3],
        "created_at": row[4],
    }


def set_bookmark(
    conn: sqlite3.Connection, session_id: str, position: int, bookmarked: bool
) -> None:
    conn.execute(
        "UPDATE cuaderno_questions SET bookmarked=? WHERE session_id=? AND position=?",
        (1 if bookmarked else 0, session_id, position),
    )
    conn.commit()


def set_got_it(
    conn: sqlite3.Connection, session_id: str, position: int, value: Optional[str]
) -> None:
    """value: 'got' | 'didnt' | None to clear."""
    if value is not None and value not in {"got", "didnt"}:
        raise ValueError(f"got_it must be 'got', 'didnt', or None; got {value!r}")
    conn.execute(
        "UPDATE cuaderno_questions SET got_it=? WHERE session_id=? AND position=?",
        (value, session_id, position),
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_persistence.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/persistence.py tests/test_cuaderno_persistence.py
git commit -m "feat(cuaderno): persistence layer for sessions and questions"
```

---

## Phase B — Anchor System tool implementations

Each tool function is pure: takes structured args, returns structured data. The compositor calls them based on LLM tool_use blocks.

### Task 5: anchor.read_file

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/anchor.py`
- Test: `tests/test_cuaderno_anchor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_anchor.py
import tempfile
from pathlib import Path

from copyclip.intelligence.cuaderno.anchor import read_file


def test_read_file_returns_lines_with_numbers(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = read_file(str(tmp_path), "src/foo.py")
    assert out["path"] == "src/foo.py"
    assert out["lines"] == [
        {"n": 1, "text": "a"},
        {"n": 2, "text": "b"},
        {"n": 3, "text": "c"},
        {"n": 4, "text": "d"},
        {"n": 5, "text": "e"},
    ]


def test_read_file_with_line_range_slices(tmp_path: Path):
    (tmp_path / "x.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = read_file(str(tmp_path), "x.py", line_start=2, line_end=4)
    assert [r["n"] for r in out["lines"]] == [2, 3, 4]
    assert [r["text"] for r in out["lines"]] == ["b", "c", "d"]


def test_read_file_rejects_path_escaping_root(tmp_path: Path):
    (tmp_path / "x.py").write_text("hi", encoding="utf-8")
    out = read_file(str(tmp_path), "../etc/passwd")
    assert out == {"error": "path_outside_root"}


def test_read_file_missing(tmp_path: Path):
    out = read_file(str(tmp_path), "nope.py")
    assert out == {"error": "file_not_found", "path": "nope.py"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_anchor.py -v`
Expected: FAIL with `ModuleNotFoundError: ... anchor`.

- [ ] **Step 3: Implement read_file**

Create `src/copyclip/intelligence/cuaderno/anchor.py`:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional


def _safe_resolve(project_root: str, rel_path: str) -> Optional[Path]:
    """Resolve a project-relative path; return None if it escapes the root."""
    root = Path(project_root).resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def read_file(
    project_root: str,
    path: str,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
) -> dict[str, Any]:
    """Read a project file with optional line range. Returns POSIX-style path."""
    resolved = _safe_resolve(project_root, path)
    if resolved is None:
        return {"error": "path_outside_root"}
    if not resolved.exists() or not resolved.is_file():
        return {"error": "file_not_found", "path": path}
    try:
        raw = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": "read_failed", "path": path, "detail": str(exc)}
    lines = raw.splitlines()
    if line_start is None and line_end is None:
        sliced = list(enumerate(lines, start=1))
    else:
        start = max(1, int(line_start or 1))
        end = min(len(lines), int(line_end or len(lines)))
        sliced = [(i + 1, lines[i]) for i in range(start - 1, end)]
    return {
        "path": path,
        "lines": [{"n": n, "text": text} for n, text in sliced],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_anchor.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anchor.py tests/test_cuaderno_anchor.py
git commit -m "feat(cuaderno): anchor.read_file tool"
```

---

### Task 6: anchor.grep_symbols

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/anchor.py`
- Test: append to `tests/test_cuaderno_anchor.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_cuaderno_anchor.py`:

```python
import sqlite3
from copyclip.intelligence.db import init_schema
from copyclip.intelligence.cuaderno.anchor import grep_symbols


def _seed_symbols(conn, project_id, rows):
    for r in rows:
        conn.execute(
            "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (project_id, r["name"], r["kind"], r["file_path"],
             r.get("line_start", 1), r.get("line_end", 10),
             None, r.get("module", "x")),
        )
    conn.commit()


def test_grep_symbols_by_name(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_symbols(conn, pid, [
        {"name": "foo", "kind": "function", "file_path": "src/a.py"},
        {"name": "foo", "kind": "method", "file_path": "src/b.py"},
        {"name": "bar", "kind": "function", "file_path": "src/c.py"},
    ])

    out = grep_symbols(conn, pid, name="foo")
    assert sorted(r["file_path"] for r in out["symbols"]) == ["src/a.py", "src/b.py"]


def test_grep_symbols_by_kind(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_symbols(conn, pid, [
        {"name": "x", "kind": "class", "file_path": "src/a.py"},
        {"name": "y", "kind": "function", "file_path": "src/b.py"},
    ])

    out = grep_symbols(conn, pid, kind="class")
    assert [r["name"] for r in out["symbols"]] == ["x"]


def test_grep_symbols_limit(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_symbols(conn, pid, [
        {"name": f"sym{i}", "kind": "function", "file_path": f"src/{i}.py"} for i in range(20)
    ])

    out = grep_symbols(conn, pid, limit=5)
    assert len(out["symbols"]) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_anchor.py::test_grep_symbols_by_name -v`
Expected: FAIL with `ImportError: cannot import name 'grep_symbols' from 'copyclip.intelligence.cuaderno.anchor'`.

- [ ] **Step 3: Implement grep_symbols**

Append to `src/copyclip/intelligence/cuaderno/anchor.py`:

```python
import sqlite3


def grep_symbols(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    file: Optional[str] = None,
    module: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    where = ["project_id = ?"]
    params: list[Any] = [project_id]
    if name:
        where.append("name = ?")
        params.append(name)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if file:
        where.append("file_path = ?")
        params.append(file.replace("\\", "/"))
    if module:
        where.append("module = ?")
        params.append(module)
    params.append(int(limit))

    sql = (
        "SELECT name, kind, file_path, line_start, line_end, module "
        "FROM symbols WHERE " + " AND ".join(where) +
        " ORDER BY file_path, line_start LIMIT ?"
    )
    rows = conn.execute(sql, params).fetchall()
    return {
        "symbols": [
            {
                "name": r[0],
                "kind": r[1],
                "file_path": r[2],
                "line_start": r[3],
                "line_end": r[4],
                "module": r[5],
            }
            for r in rows
        ]
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_anchor.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anchor.py tests/test_cuaderno_anchor.py
git commit -m "feat(cuaderno): anchor.grep_symbols tool"
```

---

### Task 7: anchor.get_callers and get_callees

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/anchor.py`
- Test: append to `tests/test_cuaderno_anchor.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_cuaderno_anchor.py`:

```python
from copyclip.intelligence.cuaderno.anchor import get_callers, get_callees


def _seed_edges(conn, pid, edges):
    """edges: list of (caller_name, callee_name, kind)"""
    name_to_id = {}
    for name, kind in {(e[0], "function") for e in edges} | {(e[1], "function") for e in edges}:
        if name not in name_to_id:
            cur = conn.execute(
                "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (pid, name, kind, f"src/{name}.py", 1, 5, None, "x"),
            )
            name_to_id[name] = cur.lastrowid
    for caller, callee, edge_kind in edges:
        conn.execute(
            "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
            "VALUES(?,?,?,?)",
            (pid, name_to_id[caller], name_to_id[callee], edge_kind),
        )
    conn.commit()
    return name_to_id


def test_get_callers_returns_call_sites(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_edges(conn, pid, [("foo", "bar", "calls"), ("baz", "bar", "calls")])

    out = get_callers(conn, pid, "bar")
    assert sorted(c["name"] for c in out["callers"]) == ["baz", "foo"]


def test_get_callees_returns_outgoing_calls(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO projects(root_path,name) VALUES(?,?)", (str(tmp_path), "t"))
    pid = int(conn.execute("SELECT id FROM projects").fetchone()[0])
    _seed_edges(conn, pid, [("foo", "bar", "calls"), ("foo", "baz", "calls")])

    out = get_callees(conn, pid, "foo")
    assert sorted(c["name"] for c in out["callees"]) == ["bar", "baz"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_anchor.py::test_get_callers_returns_call_sites -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement get_callers and get_callees**

Append to `src/copyclip/intelligence/cuaderno/anchor.py`:

```python
def get_callers(
    conn: sqlite3.Connection, project_id: int, symbol_name: str
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.name, s.kind, s.file_path, s.line_start
        FROM symbol_edges e
        JOIN symbols s_to ON e.to_symbol_id = s_to.id
        JOIN symbols s    ON e.from_symbol_id = s.id
        WHERE e.project_id=? AND s_to.name=? AND e.edge_type='calls'
        ORDER BY s.file_path, s.line_start
        """,
        (project_id, symbol_name),
    ).fetchall()
    return {
        "callers": [
            {"name": r[0], "kind": r[1], "file_path": r[2], "line_start": r[3]}
            for r in rows
        ]
    }


def get_callees(
    conn: sqlite3.Connection, project_id: int, symbol_name: str
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.name, s.kind, s.file_path, s.line_start
        FROM symbol_edges e
        JOIN symbols s_from ON e.from_symbol_id = s_from.id
        JOIN symbols s      ON e.to_symbol_id = s.id
        WHERE e.project_id=? AND s_from.name=? AND e.edge_type='calls'
        ORDER BY s.file_path, s.line_start
        """,
        (project_id, symbol_name),
    ).fetchall()
    return {
        "callees": [
            {"name": r[0], "kind": r[1], "file_path": r[2], "line_start": r[3]}
            for r in rows
        ]
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_anchor.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anchor.py tests/test_cuaderno_anchor.py
git commit -m "feat(cuaderno): anchor.get_callers + get_callees tools"
```

---

### Task 8: anchor git_log / git_blame / git_diff

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/anchor.py`
- Test: append to `tests/test_cuaderno_anchor.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_cuaderno_anchor.py`:

```python
import subprocess
from copyclip.intelligence.cuaderno.anchor import git_log, git_blame, git_diff


def _git(cwd: Path, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_git_log_returns_commits(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name",  "t")
    (tmp_path / "a.txt").write_text("1")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    (tmp_path / "a.txt").write_text("2")
    _git(tmp_path, "commit", "-am", "second")

    out = git_log(str(tmp_path), limit=10)
    msgs = [c["message"] for c in out["commits"]]
    assert "first" in msgs and "second" in msgs


def test_git_blame_returns_sha_for_lines(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name",  "t")
    (tmp_path / "a.txt").write_text("line1\nline2\nline3\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "init")

    out = git_blame(str(tmp_path), "a.txt", line_start=1, line_end=3)
    assert all(len(b["commit"]) >= 7 for b in out["blame"])
    assert len(out["blame"]) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_anchor.py::test_git_log_returns_commits -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement git tools**

Append to `src/copyclip/intelligence/cuaderno/anchor.py`:

```python
import subprocess


def _run_git(project_root: str, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def git_log(
    project_root: str, path: Optional[str] = None, limit: int = 20
) -> dict[str, Any]:
    args = ["log", f"-n{int(limit)}", "--pretty=format:%H%x09%an%x09%ai%x09%s"]
    if path:
        args += ["--", path]
    code, out, err = _run_git(project_root, *args)
    if code != 0:
        return {"error": "git_failed", "detail": err.strip()}
    commits = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            sha, author, when, msg = parts
            commits.append(
                {"commit": sha[:12], "author": author, "when": when, "message": msg}
            )
    return {"commits": commits}


def git_blame(
    project_root: str, path: str, line_start: int, line_end: int
) -> dict[str, Any]:
    code, out, err = _run_git(
        project_root,
        "blame",
        f"-L{int(line_start)},{int(line_end)}",
        "--porcelain",
        "--",
        path,
    )
    if code != 0:
        return {"error": "git_failed", "detail": err.strip()}
    blame_entries: list[dict[str, Any]] = []
    current_sha = None
    current_author = None
    current_when = None
    for line in out.splitlines():
        if not line:
            continue
        if line.startswith("\t"):
            blame_entries.append(
                {
                    "commit": (current_sha or "")[:12],
                    "author": current_author,
                    "when": current_when,
                }
            )
            continue
        head = line.split(" ", 1)[0]
        if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
            current_sha = head
        elif line.startswith("author "):
            current_author = line[7:]
        elif line.startswith("author-time "):
            current_when = line[len("author-time "):]
    return {"blame": blame_entries}


def git_diff(project_root: str, commit_sha: str, path: Optional[str] = None) -> dict[str, Any]:
    args = ["show", "--pretty=format:%H%n%an%n%ai%n%s", "--no-color", commit_sha]
    if path:
        args += ["--", path]
    code, out, err = _run_git(project_root, *args)
    if code != 0:
        return {"error": "git_failed", "detail": err.strip()}
    return {"diff": out}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_anchor.py -v`
Expected: PASS, all tests including the 2 new git ones.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anchor.py tests/test_cuaderno_anchor.py
git commit -m "feat(cuaderno): anchor.git_log + git_blame + git_diff tools"
```

---

### Task 9: anchor.find_tests

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/anchor.py`
- Test: append to `tests/test_cuaderno_anchor.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_cuaderno_anchor.py`:

```python
from copyclip.intelligence.cuaderno.anchor import find_tests


def test_find_tests_scans_tests_dir_for_symbol_name(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_foo_does_x():\n    foo()\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_b.py").write_text(
        "def test_bar():\n    pass\n", encoding="utf-8"
    )

    out = find_tests(str(tmp_path), "foo")
    assert sorted(t["file_path"] for t in out["tests"]) == ["tests/test_a.py"]
    assert out["tests"][0]["matches"][0]["line"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_anchor.py::test_find_tests_scans_tests_dir_for_symbol_name -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement find_tests**

Append to `src/copyclip/intelligence/cuaderno/anchor.py`:

```python
import re


def find_tests(project_root: str, symbol_name: str) -> dict[str, Any]:
    """Scan tests/ directory for files mentioning the symbol name."""
    root = Path(project_root).resolve()
    tests_dir = root / "tests"
    if not tests_dir.exists() or not tests_dir.is_dir():
        return {"tests": []}
    pattern = re.compile(r"\b" + re.escape(symbol_name) + r"\b")
    results: list[dict[str, Any]] = []
    for fp in tests_dir.rglob("*.py"):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = []
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append({"line": i, "text": line.rstrip()})
        if matches:
            rel = str(fp.relative_to(root)).replace("\\", "/")
            results.append({"file_path": rel, "matches": matches[:5]})
    return {"tests": results}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_anchor.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anchor.py tests/test_cuaderno_anchor.py
git commit -m "feat(cuaderno): anchor.find_tests tool"
```

---

### Task 10: Tool catalog (Anthropic format)

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/tool_catalog.py`
- Test: `tests/test_cuaderno_tool_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_tool_catalog.py
from copyclip.intelligence.cuaderno.tool_catalog import build_tool_definitions, dispatch_tool


def test_tool_definitions_include_all_tools():
    tools = build_tool_definitions()
    names = {t["name"] for t in tools}
    assert names == {
        "read_file", "grep_symbols", "get_callers", "get_callees",
        "git_log", "git_blame", "git_diff", "find_tests",
    }


def test_tool_definitions_have_anthropic_shape():
    tools = build_tool_definitions()
    for t in tools:
        assert "name" in t and "description" in t and "input_schema" in t
        assert t["input_schema"]["type"] == "object"
        assert "properties" in t["input_schema"]


def test_dispatch_unknown_tool_returns_error():
    out = dispatch_tool("nope", {}, project_root="/tmp", project_id=1, conn=None)
    assert out == {"error": "unknown_tool", "name": "nope"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_tool_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement tool_catalog.py**

Create `src/copyclip/intelligence/cuaderno/tool_catalog.py`:

```python
from __future__ import annotations

import sqlite3
from typing import Any

from . import anchor


def build_tool_definitions() -> list[dict[str, Any]]:
    """Return Anthropic-format tool definitions for the cuaderno compositor."""
    return [
        {
            "name": "read_file",
            "description": "Read a project-relative file. Returns lines numbered from 1. Optionally slice by line range.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project-relative path (POSIX). Cannot escape root."},
                    "line_start": {"type": "integer", "description": "1-based start line (inclusive). Optional."},
                    "line_end":   {"type": "integer", "description": "1-based end line (inclusive). Optional."},
                },
                "required": ["path"],
            },
        },
        {
            "name": "grep_symbols",
            "description": "Query the symbols index. Filter by any combination of name, kind, file, module.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "kind":   {"type": "string", "description": "function | method | class | etc."},
                    "file":   {"type": "string", "description": "Exact project-relative path."},
                    "module": {"type": "string", "description": "Slash-style module path (analyzer's stored format)."},
                    "limit":  {"type": "integer", "default": 50},
                },
            },
        },
        {
            "name": "get_callers",
            "description": "List call sites of a symbol by name.",
            "input_schema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "get_callees",
            "description": "List symbols that a given symbol calls.",
            "input_schema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "git_log",
            "description": "Recent commits. Optionally filter by path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path":  {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "git_blame",
            "description": "Per-line blame for a file slice. Returns commit + author + timestamp per line.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string"},
                    "line_start": {"type": "integer"},
                    "line_end":   {"type": "integer"},
                },
                "required": ["path", "line_start", "line_end"],
            },
        },
        {
            "name": "git_diff",
            "description": "Show the diff of a commit. Optionally restrict to a path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "commit_sha": {"type": "string"},
                    "path":       {"type": "string"},
                },
                "required": ["commit_sha"],
            },
        },
        {
            "name": "find_tests",
            "description": "Scan the tests/ directory for files mentioning a symbol name (word-boundary match).",
            "input_schema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    ]


def dispatch_tool(
    name: str,
    args: dict[str, Any],
    *,
    project_root: str,
    project_id: int,
    conn: sqlite3.Connection | None,
) -> dict[str, Any]:
    """Execute a tool by name with the provided args + ambient project context."""
    if name == "read_file":
        return anchor.read_file(project_root, args["path"], args.get("line_start"), args.get("line_end"))
    if name == "grep_symbols":
        return anchor.grep_symbols(
            conn, project_id,
            name=args.get("name"), kind=args.get("kind"),
            file=args.get("file"), module=args.get("module"),
            limit=args.get("limit", 50),
        )
    if name == "get_callers":
        return anchor.get_callers(conn, project_id, args["symbol"])
    if name == "get_callees":
        return anchor.get_callees(conn, project_id, args["symbol"])
    if name == "git_log":
        return anchor.git_log(project_root, args.get("path"), args.get("limit", 20))
    if name == "git_blame":
        return anchor.git_blame(project_root, args["path"], args["line_start"], args["line_end"])
    if name == "git_diff":
        return anchor.git_diff(project_root, args["commit_sha"], args.get("path"))
    if name == "find_tests":
        return anchor.find_tests(project_root, args["symbol"])
    return {"error": "unknown_tool", "name": name}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_tool_catalog.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/tool_catalog.py tests/test_cuaderno_tool_catalog.py
git commit -m "feat(cuaderno): tool catalog + dispatcher for anchor system"
```

---

## Phase C — LLM Compositor

### Task 11: System prompt + compositor scaffolding

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/compositor.py`
- Create: `src/copyclip/intelligence/cuaderno/prompts.py`
- Test: `tests/test_cuaderno_compositor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_compositor.py
from copyclip.intelligence.cuaderno.compositor import compose_frame
from copyclip.intelligence.cuaderno.schema import Frame, frame_from_dict


class StubAnthropic:
    """Stub client that returns canned responses based on the request shape."""

    def __init__(self, scripted_responses):
        self._scripted = list(scripted_responses)
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._scripted:
            raise RuntimeError("StubAnthropic ran out of scripted responses")
        return self._scripted.pop(0)


def _final_response(frame_json_str):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": frame_json_str}],
    }


def test_compose_frame_returns_parsed_frame_when_llm_returns_no_tool_calls(tmp_path):
    frame_dict = {
        "question": "what does this project do?",
        "blocks": [{"kind": "lead", "text": "CopyClip is a tool."}],
    }
    import json
    client = StubAnthropic([_final_response(json.dumps(frame_dict))])

    frame = compose_frame(
        client=client,
        question="what does this project do?",
        project_root=str(tmp_path),
        project_id=1,
        conn=None,
        max_tool_rounds=3,
    )
    assert isinstance(frame, Frame)
    assert frame.question == "what does this project do?"
    assert frame.blocks[0].kind == "lead"


def test_compose_frame_executes_tool_call_then_finishes(tmp_path):
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")

    tool_use_response = {
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", "id": "t1", "name": "read_file",
             "input": {"path": "README.md"}},
        ],
    }
    final = _final_response(
        '{"question":"q","blocks":[{"kind":"paragraph","text":"answer."}]}'
    )
    client = StubAnthropic([tool_use_response, final])

    frame = compose_frame(
        client=client, question="q",
        project_root=str(tmp_path), project_id=1, conn=None,
        max_tool_rounds=3,
    )
    assert frame.blocks[0].kind == "paragraph"
    # Second call must have included tool_result for t1
    second = client.calls[1]
    messages = second["messages"]
    found_tool_result = any(
        any(block.get("type") == "tool_result" and block.get("tool_use_id") == "t1"
            for block in (m["content"] if isinstance(m["content"], list) else []))
        for m in messages
    )
    assert found_tool_result


def test_compose_frame_caps_tool_rounds(tmp_path):
    tool_use_response = {
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", "id": "t", "name": "read_file",
             "input": {"path": "x.py"}},
        ],
    }
    # Never resolves — keep returning tool_use
    client = StubAnthropic([tool_use_response] * 5)

    frame = compose_frame(
        client=client, question="q",
        project_root=str(tmp_path), project_id=1, conn=None,
        max_tool_rounds=2,
    )
    # Cap reached — compositor returns a fallback frame
    assert frame.blocks[0].kind in {"paragraph", "callout"}
    assert "tool" in frame.blocks[0].data.get("text", "").lower() or \
           "limit" in frame.blocks[0].data.get("text", "").lower() or \
           "couldn't finish" in frame.blocks[0].data.get("text", "").lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_compositor.py -v`
Expected: FAIL with `ModuleNotFoundError: ... compositor`.

- [ ] **Step 3: Create prompts.py with the system prompt**

Create `src/copyclip/intelligence/cuaderno/prompts.py`:

```python
SYSTEM_PROMPT = """\
You are the cuaderno — a tutor that helps a single developer understand
their own AI-generated codebase. The user is an archaeologist of their own
output: they wrote the code with AI assistance, but do not remember the
detail-level decisions. Your job is to recover the deliberation that was
delegated, anchored to real evidence in the code.

## Hard rules

1. NEVER invent. Every claim you make must be anchored to evidence the user
   can verify: a file path with line range, a commit SHA, a test name.
2. Use the provided tools to read the code. Do not guess paths or contents.
3. The user's project has been analyzed: there is a symbols index, a git
   history, a set of tests. Query them via tools before composing the answer.
4. If the evidence is insufficient or contradictory, say so explicitly in
   the answer. Do not fabricate to fill gaps.

## Your output

When you have enough evidence, return a SINGLE text block containing JSON
that conforms to the Frame schema below. No prose around the JSON.

### Frame schema

```
{
  "question": "<the user's question, echoed>",
  "blocks": [<Block>, ...]
}
```

### Block kinds (use the ones that fit; do not invent new kinds)

- {"kind": "lead", "text": "<italic display line; one sentence, the answer's thesis>"}
- {"kind": "paragraph", "text": "<body paragraph; serif>"}
- {"kind": "ordered_list", "items": [{"head": "...", "desc": "...", "citation": <Citation>?}, ...]}
- {"kind": "code_block", "code": "<verbatim code>", "language": "python|typescript|...", "citation": <Citation>?}
- {"kind": "ascii_block", "text": "<preformatted ascii diagram>"}
- {"kind": "citation", "citation": <Citation>}
- {"kind": "citation_stack", "items": [{"citation": <Citation>, "note": "..."}, ...]}
- {"kind": "callout", "kicker": "key point | recovered decision | explicit commitment | ...",
   "text": "<body of the callout>", "citations": [<Citation>, ...]?}
- {"kind": "widget", "widget": <Widget>}
- {"kind": "followups", "items": [{"label": "the analyzer", "question": "explore the analyzer"}, ...]}

### Citation shape

- File: {"kind": "path", "path": "src/...", "line_start": 10, "line_end": 20}
  (line_start/line_end optional)
- Commit: {"kind": "commit", "commit": "<short sha>"}

### Widget kinds (display-only in Phase 1)

- {"kind": "graph_subset", "nodes": [{"id": "...", "label": "...", "you": <bool>?}, ...],
   "edges": [{"from": "<id>", "to": "<id>", "label": "..."}, ...]}
- {"kind": "sequence_diagram", "actors": ["A", "B"], "steps": [{"from": 0, "to": 1, "label": "..."}, ...]}
- {"kind": "callers_tree", "root": "symbol_name",
   "callers": [{"citation": <Citation>, "note": "..."}, ...]}

## Tone

Editorial, plain, never hyped. The user knows what a function is — explain
what they do not remember deciding, not what they already know. One short
lead. Then paragraphs and citations. Conclude with 2-4 follow-up questions
that go deeper, expressed as actions ("walk me through X", "show the commit
that...").
"""
```

- [ ] **Step 4: Implement compositor.py**

Create `src/copyclip/intelligence/cuaderno/compositor.py`:

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .prompts import SYSTEM_PROMPT
from .schema import Block, Frame, frame_from_dict
from .tool_catalog import build_tool_definitions, dispatch_tool


def _fallback_frame(question: str, reason: str) -> Frame:
    return Frame(
        question=question,
        blocks=[
            Block.paragraph(
                f"I couldn't finish this turn — {reason}. Try rephrasing, or "
                "ask a narrower question (a specific file, function, or commit)."
            ),
        ],
    )


def compose_frame(
    *,
    client: Any,
    question: str,
    project_root: str,
    project_id: int,
    conn: Optional[sqlite3.Connection],
    model: str = "claude-sonnet-4-6",
    max_tool_rounds: int = 8,
    max_tokens: int = 8192,
) -> Frame:
    """Run the agentic loop. Returns a Frame; falls back gracefully on cap or parse failure."""
    tools = build_tool_definitions()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": question},
    ]

    for _ in range(max_tool_rounds):
        resp = client.messages_create(
            model=model,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
            max_tokens=max_tokens,
        )

        stop_reason = resp.get("stop_reason")
        content = resp.get("content", [])

        # Echo assistant turn into conversation
        messages.append({"role": "assistant", "content": content})

        if stop_reason != "tool_use":
            # Extract the final text block and parse as Frame JSON
            text_chunks = [b["text"] for b in content if b.get("type") == "text"]
            raw = "".join(text_chunks).strip()
            # Strip ```json fences if the model added them
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            try:
                data = json.loads(raw)
                return frame_from_dict(data)
            except (json.JSONDecodeError, KeyError) as exc:
                return _fallback_frame(
                    question, f"model output was not valid Frame JSON ({exc})"
                )

        # Tool-use turn: execute every tool_use block, append a single user
        # message with all tool_result blocks before looping.
        tool_results: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            result = dispatch_tool(
                block["name"], block.get("input", {}) or {},
                project_root=project_root, project_id=project_id, conn=conn,
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return _fallback_frame(question, "tool-call budget exhausted")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_compositor.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/compositor.py src/copyclip/intelligence/cuaderno/prompts.py tests/test_cuaderno_compositor.py
git commit -m "feat(cuaderno): system prompt + compositor agentic loop"
```

---

### Task 12: Anthropic client adapter

The compositor uses a `client.messages_create(...)` interface. Wrap the real `anthropic` SDK to match.

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/anthropic_client.py`
- Test: `tests/test_cuaderno_anthropic_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_anthropic_client.py
from copyclip.intelligence.cuaderno.anthropic_client import AnthropicAdapter


class FakeRawClient:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.last_kwargs = kwargs
            return self.outer._response

    @property
    def messages(self):
        return self._Messages(self)


class _FakeBlockText:
    type = "text"
    text = "the answer"


class _FakeBlockToolUse:
    type = "tool_use"
    id = "t1"
    name = "read_file"
    input = {"path": "x.py"}


class _FakeResponse:
    def __init__(self, blocks, stop_reason):
        self.content = blocks
        self.stop_reason = stop_reason


def test_adapter_returns_text_response_as_dict():
    raw = FakeRawClient(_FakeResponse([_FakeBlockText()], "end_turn"))
    adapter = AnthropicAdapter(raw_client=raw)
    out = adapter.messages_create(model="m", system="sys", tools=[], messages=[], max_tokens=10)
    assert out["stop_reason"] == "end_turn"
    assert out["content"] == [{"type": "text", "text": "the answer"}]


def test_adapter_returns_tool_use_blocks():
    raw = FakeRawClient(_FakeResponse([_FakeBlockToolUse()], "tool_use"))
    adapter = AnthropicAdapter(raw_client=raw)
    out = adapter.messages_create(model="m", system="sys", tools=[], messages=[], max_tokens=10)
    assert out["stop_reason"] == "tool_use"
    assert out["content"][0]["type"] == "tool_use"
    assert out["content"][0]["name"] == "read_file"
    assert out["content"][0]["input"] == {"path": "x.py"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_anthropic_client.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the adapter**

Create `src/copyclip/intelligence/cuaderno/anthropic_client.py`:

```python
from __future__ import annotations

import os
from typing import Any, Optional


class AnthropicAdapter:
    """Normalizes the anthropic SDK response into the dict shape compose_frame expects."""

    def __init__(self, raw_client: Optional[Any] = None, api_key: Optional[str] = None):
        if raw_client is not None:
            self._client = raw_client
        else:
            import anthropic
            key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not configured. Run `copyclip start` to onboard, "
                    "or export the env var."
                )
            self._client = anthropic.Anthropic(api_key=key)

    def messages_create(self, **kwargs) -> dict[str, Any]:
        resp = self._client.messages.create(**kwargs)
        content = []
        for block in resp.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input or {},
                })
        return {"stop_reason": resp.stop_reason, "content": content}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cuaderno_anthropic_client.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/anthropic_client.py tests/test_cuaderno_anthropic_client.py
git commit -m "feat(cuaderno): anthropic SDK adapter"
```

---

## Phase D — HTTP endpoints

### Task 13: POST /api/cuaderno/ask

**Files:**
- Modify: `src/copyclip/intelligence/server.py` — append a new route block
- Test: `tests/test_cuaderno_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cuaderno_endpoint.py
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
from copyclip.intelligence.cuaderno.schema import Frame, Block, frame_to_dict


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
    status, body = _post_json(
        f"http://127.0.0.1:{port}/api/cuaderno/ask", {}
    )
    assert status == 400
    assert body["error"] == "question_required"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cuaderno_endpoint.py -v`
Expected: FAIL with 404 from the server (route not implemented).

- [ ] **Step 3: Locate the `do_POST` block in server.py and add the route**

Find the existing `do_POST` method in `src/copyclip/intelligence/server.py`. After the LAST `if parsed.path == "/api/..."` block in `do_POST`, but BEFORE the final fallback `self._json({"error": "not_found"}, 404)`, insert the new route. Use the same pattern as adjacent routes.

```python
                if parsed.path == "/api/cuaderno/ask":
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    try:
                        data = json.loads(self.rfile.read(
                            int(self.headers.get("Content-Length", "0"))
                        ).decode("utf-8") or "{}")
                    except json.JSONDecodeError:
                        self._json({"error": "invalid_request"}, 400)
                        return
                    question = (data.get("question") or "").strip()
                    if not question:
                        self._json({"error": "question_required"}, 400)
                        return
                    session_id = data.get("session_id")
                    from .cuaderno import compositor as _compositor
                    from .cuaderno.anthropic_client import AnthropicAdapter
                    from .cuaderno.persistence import (
                        create_session, save_question,
                    )
                    from .cuaderno.schema import frame_to_dict
                    if not session_id:
                        session_id = create_session(conn, project_root=ctx.root)
                    try:
                        client = AnthropicAdapter()
                    except RuntimeError as exc:
                        self._json({"error": "llm_not_configured", "detail": str(exc)}, 503)
                        return
                    frame = _compositor.compose_frame(
                        client=client, question=question,
                        project_root=ctx.root, project_id=pid, conn=conn,
                    )
                    position = save_question(conn, session_id, question, frame)
                    self._json({
                        "session_id": session_id,
                        "position": position,
                        "frame": frame_to_dict(frame),
                    })
                    return
```

Insertion point: after the last route in the `do_POST` block, before the 404 fallback. Match the indentation of the surrounding routes (a single tab-stop more than the surrounding `if` cascade — examine an existing route to copy the indentation precisely).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_endpoint.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/server.py tests/test_cuaderno_endpoint.py
git commit -m "feat(cuaderno): POST /api/cuaderno/ask endpoint"
```

---

### Task 14: GET /api/cuaderno/sessions/:id

**Files:**
- Modify: `src/copyclip/intelligence/server.py`
- Test: append to `tests/test_cuaderno_endpoint.py`

- [ ] **Step 1: Append the failing test**

```python
def _get_json(url):
    with request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_get_session_returns_questions_in_order():
    root, port = _setup_server()
    # First ask to create a session
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_endpoint.py::test_get_session_returns_questions_in_order -v`
Expected: FAIL with 404.

- [ ] **Step 3: Add the GET route in do_GET**

Locate `do_GET` in `server.py`. Append a new `if parsed.path.startswith("/api/cuaderno/sessions/"):` block before the 404 fallback. Use this code:

```python
                if parsed.path.startswith("/api/cuaderno/sessions/"):
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    sid = parsed.path[len("/api/cuaderno/sessions/"):]
                    if not sid:
                        self._json({"error": "session_id_required"}, 400)
                        return
                    from .cuaderno.persistence import list_questions
                    questions = list_questions(conn, sid)
                    if not questions:
                        # session does not exist OR has no questions yet
                        row = conn.execute(
                            "SELECT id FROM cuaderno_sessions WHERE id=?", (sid,),
                        ).fetchone()
                        if not row:
                            self._json({"error": "session_not_found"}, 404)
                            return
                    self._json({"session_id": sid, "questions": questions})
                    return
```

Insert with the same indentation as the surrounding `if parsed.path ==` routes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_endpoint.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/server.py tests/test_cuaderno_endpoint.py
git commit -m "feat(cuaderno): GET /api/cuaderno/sessions/:id endpoint"
```

---

### Task 15: PATCH /api/cuaderno/sessions/:id/questions/:pos

For `bookmark` and `got_it` mutations.

**Files:**
- Modify: `src/copyclip/intelligence/server.py`
- Test: append to `tests/test_cuaderno_endpoint.py`

- [ ] **Step 1: Append the failing test**

```python
def _patch_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method="PATCH", data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_patch_bookmark_and_gotit():
    root, port = _setup_server()
    stub_frame = Frame(question="q1", blocks=[Block.lead("hi")])
    with patch(
        "copyclip.intelligence.cuaderno.compositor.compose_frame",
        return_value=stub_frame,
    ):
        _, b = _post_json(f"http://127.0.0.1:{port}/api/cuaderno/ask",
                          {"question": "q1"})
    sid = b["session_id"]

    status, _ = _patch_json(
        f"http://127.0.0.1:{port}/api/cuaderno/sessions/{sid}/questions/1",
        {"bookmarked": True, "got_it": "got"},
    )
    assert status == 200

    _, session = _get_json(f"http://127.0.0.1:{port}/api/cuaderno/sessions/{sid}")
    q1 = session["questions"][0]
    assert q1["bookmarked"] is True
    assert q1["got_it"] == "got"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cuaderno_endpoint.py::test_patch_bookmark_and_gotit -v`
Expected: FAIL with 404 or 405.

- [ ] **Step 3: Locate or add `do_PATCH` method in the Handler class**

If `do_PATCH` does not exist, add a new method on the Handler class:

```python
        def do_PATCH(self):
            try:
                parsed = urlparse(self.path)
                import re as _re
                m = _re.match(r"^/api/cuaderno/sessions/([^/]+)/questions/(\d+)$", parsed.path)
                if not m:
                    self._json({"error": "not_found"}, 404)
                    return
                if not pid:
                    self._json({"error": "no_project"}, 400)
                    return
                sid, pos = m.group(1), int(m.group(2))
                try:
                    data = json.loads(self.rfile.read(
                        int(self.headers.get("Content-Length", "0"))
                    ).decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._json({"error": "invalid_request"}, 400)
                    return
                from .cuaderno.persistence import set_bookmark, set_got_it
                if "bookmarked" in data:
                    set_bookmark(conn, sid, pos, bool(data["bookmarked"]))
                if "got_it" in data:
                    set_got_it(conn, sid, pos, data["got_it"])
                self._json({"ok": True})
            except Exception as exc:
                self._json({"error": "internal", "detail": str(exc)}, 500)
```

If `do_PATCH` already exists, add the cuaderno regex match block as the first check in it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cuaderno_endpoint.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/server.py tests/test_cuaderno_endpoint.py
git commit -m "feat(cuaderno): PATCH endpoint for bookmark + got_it markers"
```

---

## Phase E — Frontend port

The prototype's JSX is the reference. Each frontend task ports a piece into TSX and wires it.

### Task 16: TypeScript types for Frame / Block / Widget / Citation

**Files:**
- Modify: `frontend/src/types/api.ts` — append cuaderno types

- [ ] **Step 1: Append types**

Open `frontend/src/types/api.ts`. Append at the end:

```typescript
// --- Cuaderno -------------------------------------------------------------

export type PathCitation = {
  kind: 'path'
  path: string
  line_start?: number
  line_end?: number
}

export type CommitCitation = {
  kind: 'commit'
  commit: string
}

export type Citation = PathCitation | CommitCitation

export type GraphSubsetWidget = {
  kind: 'graph_subset'
  nodes: Array<{ id: string; label: string; you?: boolean }>
  edges: Array<{ from: string; to: string; label?: string }>
}

export type SequenceDiagramWidget = {
  kind: 'sequence_diagram'
  actors: string[]
  steps: Array<{ from: number; to: number; label: string }>
}

export type CallersTreeWidget = {
  kind: 'callers_tree'
  root: string
  callers: Array<{ citation: Citation; note?: string }>
}

export type Widget = GraphSubsetWidget | SequenceDiagramWidget | CallersTreeWidget

export type Block =
  | { kind: 'lead'; text: string }
  | { kind: 'paragraph'; text: string }
  | {
      kind: 'ordered_list'
      items: Array<{ head: string; desc: string; citation?: Citation }>
    }
  | { kind: 'code_block'; code: string; language: string; citation?: Citation }
  | { kind: 'ascii_block'; text: string }
  | { kind: 'citation'; citation: Citation }
  | {
      kind: 'citation_stack'
      items: Array<{ citation: Citation; note?: string }>
    }
  | { kind: 'callout'; kicker: string; text: string; citations?: Citation[] }
  | { kind: 'widget'; widget: Widget }
  | {
      kind: 'followups'
      items: Array<{ label: string; question: string }>
    }

export type Frame = {
  question: string
  blocks: Block[]
}

export type CuadernoAskResponse = {
  session_id: string
  position: number
  frame: Frame
}

export type CuadernoQuestion = {
  position: number
  question: string
  frame: Frame
  bookmarked: boolean
  got_it: 'got' | 'didnt' | null
  created_at: string
}

export type CuadernoSession = {
  session_id: string
  questions: CuadernoQuestion[]
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno-fe): TypeScript types for Frame/Block/Widget/Citation"
```

---

### Task 17: API client extension

**Files:**
- Create: `frontend/src/api/cuaderno.ts`

- [ ] **Step 1: Create the client**

Create `frontend/src/api/cuaderno.ts`:

```typescript
import type { CuadernoAskResponse, CuadernoSession } from '../types/api'

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`POST ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}

async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`PATCH ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`GET ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}

export const cuadernoApi = {
  ask(question: string, sessionId?: string) {
    return postJson<CuadernoAskResponse>('/api/cuaderno/ask', {
      question,
      session_id: sessionId,
    })
  },
  session(sessionId: string) {
    return getJson<CuadernoSession>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}`,
    )
  },
  patchQuestion(
    sessionId: string,
    position: number,
    fields: { bookmarked?: boolean; got_it?: 'got' | 'didnt' | null },
  ) {
    return patchJson<{ ok: boolean }>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}/questions/${position}`,
      fields,
    )
  },
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/cuaderno.ts
git commit -m "feat(cuaderno-fe): typed API client wrapper"
```

---

### Task 18: Port cuaderno.css

**Files:**
- Create: `frontend/src/styles/cuaderno.css`
- Modify: `frontend/src/index.css` (or main entry CSS — verify which is imported by App.tsx)

- [ ] **Step 1: Copy styles.css → cuaderno.css**

```bash
cp "docs/superpowers/specs/2026-05-28-cuaderno-prototype/styles.css" frontend/src/styles/cuaderno.css
```

If the `frontend/src/styles/` directory does not exist, create it first:

```bash
mkdir -p frontend/src/styles
cp "docs/superpowers/specs/2026-05-28-cuaderno-prototype/styles.css" frontend/src/styles/cuaderno.css
```

- [ ] **Step 2: Import in App.tsx**

Open `frontend/src/App.tsx` and add near the top, after the other imports:

```typescript
import './styles/cuaderno.css'
```

- [ ] **Step 3: Verify the dev build still compiles**

Run: `npm --prefix frontend run build`
Expected: `built in ...ms` with no errors. Bundle size grows by ~25 KB.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/cuaderno.css frontend/src/App.tsx
git commit -m "feat(cuaderno-fe): port styles.css from prototype"
```

---

### Task 19: GraphSubset widget component

**Files:**
- Create: `frontend/src/components/cuaderno/widgets/GraphSubset.tsx`

- [ ] **Step 1: Port the JSX**

Create `frontend/src/components/cuaderno/widgets/GraphSubset.tsx`. Source reference: `docs/superpowers/specs/2026-05-28-cuaderno-prototype/widgets.jsx` lines 73-113.

```tsx
import type { GraphSubsetWidget } from '../../../types/api'

type Props = { widget: GraphSubsetWidget }

export function GraphSubset({ widget }: Props) {
  const { nodes, edges } = widget
  // Positions: simple deterministic 2-column layout for Phase 1 display-only.
  // (Phase 2 will make this interactive; positions become dynamic.)
  const positioned = nodes.map((n, i) => ({
    ...n,
    x: 40 + (i % 3) * 160,
    y: 30 + Math.floor(i / 3) * 80,
  }))
  const byId = Object.fromEntries(positioned.map((n) => [n.id, n]))

  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · graph subset
        </span>
        <span>{`${nodes.length} nodes · ${edges.length} edges`}</span>
      </div>
      <div className="widget-body">
        <div className="graph">
          {edges.map((e, i) => {
            const a = byId[e.from]
            const b = byId[e.to]
            if (!a || !b) return null
            const dx = b.x - a.x
            const dy = b.y - a.y
            const len = Math.sqrt(dx * dx + dy * dy)
            const ang = (Math.atan2(dy, dx) * 180) / Math.PI
            return (
              <div
                key={i}
                className="gedge"
                style={{
                  left: a.x + 50,
                  top: a.y + 14,
                  width: len,
                  transform: `rotate(${ang}deg)`,
                }}
              />
            )
          })}
          {positioned.map((n) => (
            <div
              key={n.id}
              className={'gnode' + (n.you ? ' you' : '')}
              style={{ left: n.x, top: n.y }}
            >
              {n.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/widgets/GraphSubset.tsx
git commit -m "feat(cuaderno-fe): GraphSubset widget component"
```

---

### Task 20: SequenceDiagram widget

**Files:**
- Create: `frontend/src/components/cuaderno/widgets/SequenceDiagram.tsx`

- [ ] **Step 1: Port the JSX**

Source: `widgets.jsx` lines 12-45.

```tsx
import type { SequenceDiagramWidget } from '../../../types/api'

type Props = { widget: SequenceDiagramWidget }

export function SequenceDiagram({ widget }: Props) {
  const { actors, steps } = widget
  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · sequence
        </span>
        <span>{`${steps.length} calls`}</span>
      </div>
      <div className="widget-body">
        <div className="seq">
          {actors.map((a, i) => (
            <div className="col" key={`actor-${i}`}>
              <div className="who">{a}</div>
            </div>
          ))}
          {steps.map((s, stepIdx) => (
            <>
              {actors.map((_, ai) => {
                const inSpan =
                  ai >= Math.min(s.from, s.to) && ai < Math.max(s.from, s.to)
                const isStart = ai === s.from
                return (
                  <div className="lane" key={`step-${stepIdx}-lane-${ai}`}>
                    {inSpan ? (
                      <>
                        <div
                          className="step"
                          style={{ left: '0%', width: '100%' }}
                        />
                        {isStart ? (
                          <span className="stepNote" style={{ left: '8px' }}>
                            {s.label}
                          </span>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                )
              })}
            </>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/widgets/SequenceDiagram.tsx
git commit -m "feat(cuaderno-fe): SequenceDiagram widget component"
```

---

### Task 21: CallersTree widget

**Files:**
- Create: `frontend/src/components/cuaderno/widgets/CallersTree.tsx`

- [ ] **Step 1: Port the JSX**

Source: `widgets.jsx` lines 47-70.

```tsx
import type { CallersTreeWidget, Citation } from '../../../types/api'

type Props = {
  widget: CallersTreeWidget
  onOpenCitation: (c: Citation) => void
}

function citationLabel(c: Citation): string {
  if (c.kind === 'commit') return `commit ${c.commit}`
  const range = c.line_start
    ? `:${c.line_start}${c.line_end && c.line_end !== c.line_start ? `-${c.line_end}` : ''}`
    : ''
  return `${c.path}${range}`
}

export function CallersTree({ widget, onOpenCitation }: Props) {
  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · callers
        </span>
        <span>{`${widget.callers.length} sites`}</span>
      </div>
      <div className="widget-body tree">
        <div className="node">
          <span className="glyph">◇</span>
          <span className="name">{widget.root}</span>
        </div>
        {widget.callers.map((c, i) => (
          <div className="node indent" key={i}>
            <span className="glyph">└─</span>
            <button className="cite" onClick={() => onOpenCitation(c.citation)}>
              <span className="arrow">▸</span>
              <span>{citationLabel(c.citation)}</span>
            </button>
            {c.note ? (
              <span style={{ color: 'var(--ink-3)', marginLeft: 4 }}>{c.note}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/widgets/CallersTree.tsx
git commit -m "feat(cuaderno-fe): CallersTree widget component"
```

---

### Task 22: Composer + GotItMarkers + small components

**Files:**
- Create: `frontend/src/components/cuaderno/Composer.tsx`
- Create: `frontend/src/components/cuaderno/GotItMarkers.tsx`
- Create: `frontend/src/components/cuaderno/CitationChip.tsx`

- [ ] **Step 1: Composer.tsx**

Create `frontend/src/components/cuaderno/Composer.tsx`. Source: `cuaderno.jsx` lines 165-178.

```tsx
import { useState, type FormEvent } from 'react'

type Props = {
  onSubmit: (text: string) => void
  disabled?: boolean
  placeholder?: string
}

export function Composer({
  onSubmit,
  disabled,
  placeholder = 'ask whatever you want…',
}: Props) {
  const [value, setValue] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!value.trim()) return
    onSubmit(value)
    setValue('')
  }

  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={handleSubmit}>
        <span className="prefix">›</span>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          spellCheck={false}
        />
        <button className="send" type="submit" disabled={!value.trim() || disabled}>
          ↵
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 2: GotItMarkers.tsx**

Create `frontend/src/components/cuaderno/GotItMarkers.tsx`. Source: `cuaderno.jsx` lines 127-160.

```tsx
type Props = {
  value: 'got' | 'didnt' | null
  onSet: (v: 'got' | 'didnt') => void
}

export function GotItMarkers({ value, onSet }: Props) {
  if (value === null) {
    return (
      <div className="gotit">
        <span className="ask">does this answer the question?</span>
        <button className="gotit-btn" onClick={() => onSet('got')}>
          <span style={{ color: 'var(--accent-2)' }}>✓</span> I got this
        </button>
        <button className="gotit-btn" onClick={() => onSet('didnt')}>
          <span style={{ color: 'var(--accent)' }}>↻</span> I didn't
        </button>
      </div>
    )
  }
  if (value === 'got') {
    return (
      <div className="gotit">
        <button className="gotit-btn is-got">✓ marked: got this</button>
        <span className="gotit-msg">
          saved to <span style={{ color: 'var(--ink)' }}>this matters</span>. ask anything else when ready.
        </span>
      </div>
    )
  }
  return (
    <div className="gotit">
      <button className="gotit-btn is-didnt">↻ marked: didn't</button>
      <span className="gotit-msg">
        where did it break? try a follow-up below or rephrase.
      </span>
    </div>
  )
}
```

- [ ] **Step 3: CitationChip.tsx**

Create `frontend/src/components/cuaderno/CitationChip.tsx`:

```tsx
import type { Citation } from '../../types/api'

export function citationLabel(c: Citation): string {
  if (c.kind === 'commit') return `commit ${c.commit}`
  const range = c.line_start
    ? `:${c.line_start}${c.line_end && c.line_end !== c.line_start ? `-${c.line_end}` : ''}`
    : ''
  return `${c.path}${range}`
}

type Props = {
  citation: Citation
  block?: boolean
  onClick: (c: Citation) => void
}

export function CitationChip({ citation, block, onClick }: Props) {
  return (
    <button
      className={'cite' + (block ? ' cite-block' : '')}
      onClick={() => onClick(citation)}
    >
      <span className="arrow">▸</span>
      <span>{citationLabel(citation)}</span>
    </button>
  )
}
```

- [ ] **Step 4: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cuaderno/Composer.tsx frontend/src/components/cuaderno/GotItMarkers.tsx frontend/src/components/cuaderno/CitationChip.tsx
git commit -m "feat(cuaderno-fe): Composer + GotItMarkers + CitationChip"
```

---

### Task 23: SidePanel

**Files:**
- Create: `frontend/src/components/cuaderno/SidePanel.tsx`

- [ ] **Step 1: Port SidePanel**

Create `frontend/src/components/cuaderno/SidePanel.tsx`. Source: `cuaderno.jsx` lines 226-313.

Phase 1 of SidePanel: read the file via the existing `/api/files?path=` or `/api/module/source` (whatever's nearest in `api/client.ts`). If none exists, the simplest path is to add a small fetch to a new helper. For now, do a direct `fetch('/api/file/symbols?...')` is wrong (returns symbols, not contents). Use a new helper: see Step 2.

For Phase 1, the SidePanel fetches the file via a small endpoint added in Step 2 OR (if an existing endpoint already serves file contents, use that).

```tsx
import { useEffect, useState } from 'react'
import type { Citation } from '../../types/api'

type Props = {
  citation: Citation
  onClose: () => void
}

type FileSlice = {
  path: string
  lines: { n: number; text: string }[]
  blame?: { commit: string; author: string; when: string }
}

async function fetchFileSlice(c: Citation): Promise<FileSlice | null> {
  if (c.kind === 'commit') return null
  const params = new URLSearchParams({ path: c.path })
  if (c.line_start) params.set('line_start', String(c.line_start))
  if (c.line_end) params.set('line_end', String(c.line_end))
  const r = await fetch(`/api/cuaderno/file?${params.toString()}`)
  if (!r.ok) return null
  return await r.json()
}

export function SidePanel({ citation, onClose }: Props) {
  const [slice, setSlice] = useState<FileSlice | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    setLoading(true)
    fetchFileSlice(citation)
      .then(setSlice)
      .finally(() => setLoading(false))
  }, [citation])

  if (citation.kind === 'commit') {
    return (
      <>
        <div className="sidepanel-backdrop" onClick={onClose} />
        <div className="sidepanel">
          <div className="sidepanel-head">
            <div className="path">
              <span className="dim">commit</span>
              <span>{citation.commit}</span>
            </div>
            <button className="close" onClick={onClose}>esc</button>
          </div>
          <div className="sidepanel-body" style={{ padding: 24 }}>
            <p style={{ color: 'var(--ink-3)' }}>
              Commit detail view coming in Phase 1.5. For now, this confirms
              the citation: <code>{citation.commit}</code>.
            </p>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="sidepanel-backdrop" onClick={onClose} />
      <div className="sidepanel">
        <div className="sidepanel-head">
          <div className="path">
            <span className="dim">▸</span>
            <span>{citation.path}</span>
            {citation.line_start ? (
              <span className="dim">
                :{citation.line_start}
                {citation.line_end && citation.line_end !== citation.line_start
                  ? `-${citation.line_end}`
                  : ''}
              </span>
            ) : null}
          </div>
          <button className="close" onClick={onClose}>esc</button>
        </div>
        <div className="sidepanel-body">
          {loading ? (
            <div style={{ padding: 24, color: 'var(--ink-3)' }}>loading…</div>
          ) : !slice ? (
            <div style={{ padding: 24, color: 'var(--ink-3)' }}>
              could not load file.
            </div>
          ) : (
            <div className="file-code">
              {slice.lines.map((r) => (
                <div
                  key={r.n}
                  className={
                    'row' +
                    (citation.line_start &&
                    r.n >= citation.line_start &&
                    r.n <= (citation.line_end ?? citation.line_start)
                      ? ' hi'
                      : '')
                  }
                >
                  <div className="lno">{r.n}</div>
                  <div>{r.text || ' '}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        {slice?.blame ? (
          <div className="sidepanel-meta">
            <span className="pair">
              <b>blame </b>
              {slice.blame.commit}
            </span>
            <span className="pair">
              <b>by </b>
              {slice.blame.author}
            </span>
            <span className="pair">
              <b>on </b>
              {slice.blame.when}
            </span>
          </div>
        ) : null}
      </div>
    </>
  )
}
```

- [ ] **Step 2: Add a thin file-slice backend endpoint**

The SidePanel needs `GET /api/cuaderno/file?path=...&line_start=...&line_end=...`. Add it to `server.py`'s `do_GET`, after the existing cuaderno routes:

```python
                if parsed.path == "/api/cuaderno/file":
                    if not pid:
                        self._json({"error": "no_project"}, 400)
                        return
                    q = parse_qs(parsed.query or "")
                    file_path = (q.get("path", [""])[0] or "").strip()
                    if not file_path:
                        self._json({"error": "path_required"}, 400)
                        return
                    try:
                        ls_raw = q.get("line_start", [""])[0]
                        le_raw = q.get("line_end", [""])[0]
                        line_start = int(ls_raw) if ls_raw else None
                        line_end   = int(le_raw) if le_raw else None
                    except ValueError:
                        self._json({"error": "invalid_line_range"}, 400)
                        return
                    from .cuaderno.anchor import read_file
                    out = read_file(ctx.root, file_path, line_start, line_end)
                    if out.get("error"):
                        status = 404 if out["error"] == "file_not_found" else 400
                        self._json(out, status)
                        return
                    # Best-effort blame for the slice
                    if line_start and line_end:
                        from .cuaderno.anchor import git_blame
                        b = git_blame(ctx.root, file_path, line_start, line_end)
                        if b.get("blame"):
                            first = b["blame"][0]
                            out["blame"] = {
                                "commit": first.get("commit", ""),
                                "author": first.get("author", ""),
                                "when": first.get("when", ""),
                            }
                    self._json(out)
                    return
```

- [ ] **Step 3: Verify TS compiles + endpoint works**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/cuaderno/SidePanel.tsx src/copyclip/intelligence/server.py
git commit -m "feat(cuaderno): SidePanel + /api/cuaderno/file slice endpoint"
```

---

### Task 24: HistoryOverlay

**Files:**
- Create: `frontend/src/components/cuaderno/HistoryOverlay.tsx`

- [ ] **Step 1: Port HistoryOverlay**

Create `frontend/src/components/cuaderno/HistoryOverlay.tsx`. Source: `cuaderno.jsx` lines 183-220.

```tsx
import { useEffect } from 'react'
import type { CuadernoQuestion } from '../../types/api'

type Props = {
  questions: CuadernoQuestion[]
  activePosition: number | null
  onSelect: (position: number) => void
  onClose: () => void
}

export function HistoryOverlay({ questions, activePosition, onSelect, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <div className="history-back" onClick={onClose} />
      <div className="history">
        <div className="history-head">
          <span>session · this conversation</span>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 0,
              color: 'var(--ink-3)',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            esc
          </button>
        </div>
        <div className="history-list">
          {questions.map((q) => (
            <button
              key={q.position}
              className={
                'h-item' +
                (q.bookmarked ? ' bookmarked' : '') +
                (q.position === activePosition ? ' active' : '')
              }
              onClick={() => onSelect(q.position)}
            >
              <span className="num">{String(q.position).padStart(2, '0')}</span>
              <span className="q">{q.question}</span>
              <span className="when">{q.created_at}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/HistoryOverlay.tsx
git commit -m "feat(cuaderno-fe): HistoryOverlay component"
```

---

### Task 25: FrameDynamic — render Block[] from API

**Files:**
- Create: `frontend/src/components/cuaderno/frames/FrameDynamic.tsx`

- [ ] **Step 1: Port the dispatching renderer**

Create `frontend/src/components/cuaderno/frames/FrameDynamic.tsx`:

```tsx
import type { Block, Citation, Frame } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { GraphSubset } from '../widgets/GraphSubset'
import { SequenceDiagram } from '../widgets/SequenceDiagram'
import { CallersTree } from '../widgets/CallersTree'

type Props = {
  frame: Frame
  onOpenCitation: (c: Citation) => void
  onAsk: (question: string) => void
}

export function FrameDynamic({ frame, onOpenCitation, onAsk }: Props) {
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">{frame.question}</span>
      </div>
      {frame.blocks.map((b, i) => (
        <BlockRender
          key={i}
          block={b}
          onOpenCitation={onOpenCitation}
          onAsk={onAsk}
        />
      ))}
    </>
  )
}

function BlockRender({
  block,
  onOpenCitation,
  onAsk,
}: {
  block: Block
  onOpenCitation: (c: Citation) => void
  onAsk: (question: string) => void
}) {
  switch (block.kind) {
    case 'lead':
      return <p className="cua-lead">{block.text}</p>
    case 'paragraph':
      return <p className="cua-p">{block.text}</p>
    case 'ordered_list':
      return (
        <ol className="cua-list">
          {block.items.map((item, i) => (
            <li key={i}>
              <div>
                <div className="head">{item.head}</div>
                <div className="desc">{item.desc}</div>
                {item.citation ? (
                  <CitationChip citation={item.citation} block onClick={onOpenCitation} />
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )
    case 'code_block':
      return (
        <>
          {block.citation ? (
            <CitationChip citation={block.citation} block onClick={onOpenCitation} />
          ) : null}
          <pre className="code">
            {block.code.split('\n').map((l, i) => (
              <span className="ln" key={i}>
                {l || ' '}
                {'\n'}
              </span>
            ))}
          </pre>
        </>
      )
    case 'ascii_block':
      return <pre className="ascii">{block.text}</pre>
    case 'citation':
      return <CitationChip citation={block.citation} block onClick={onOpenCitation} />
    case 'citation_stack':
      return (
        <div className="cite-stack">
          {block.items.map((it, i) => (
            <a key={i} onClick={() => onOpenCitation(it.citation)}>
              <span className="arrow">▸</span>
              <span>
                {it.citation.kind === 'commit'
                  ? `commit ${it.citation.commit}`
                  : `${it.citation.path}${
                      it.citation.line_start
                        ? `:${it.citation.line_start}${
                            it.citation.line_end && it.citation.line_end !== it.citation.line_start
                              ? `-${it.citation.line_end}`
                              : ''
                          }`
                        : ''
                    }`}
              </span>
              {it.note ? (
                <span style={{ color: 'var(--ink-3)' }}>  {it.note}</span>
              ) : null}
            </a>
          ))}
        </div>
      )
    case 'callout':
      return (
        <div className="callout">
          <div className="kicker">{block.kicker}</div>
          <p>{block.text}</p>
          {block.citations
            ? block.citations.map((c, i) => (
                <div key={i} style={{ marginTop: i === 0 ? 8 : 4 }}>
                  <CitationChip citation={c} onClick={onOpenCitation} />
                </div>
              ))
            : null}
        </div>
      )
    case 'widget':
      switch (block.widget.kind) {
        case 'graph_subset':
          return <GraphSubset widget={block.widget} />
        case 'sequence_diagram':
          return <SequenceDiagram widget={block.widget} />
        case 'callers_tree':
          return (
            <CallersTree widget={block.widget} onOpenCitation={onOpenCitation} />
          )
      }
      return null
    case 'followups':
      return (
        <div className="followups">
          <div className="cap">go deeper</div>
          <div className="btns">
            {block.items.map((it, i) => (
              <button key={i} className="fu" onClick={() => onAsk(it.question)}>
                <span className="arr">↳</span> {it.label}
              </button>
            ))}
          </div>
        </div>
      )
  }
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/frames/FrameDynamic.tsx
git commit -m "feat(cuaderno-fe): FrameDynamic renders Block[] from API"
```

---

### Task 26: FrameEmpty + FrameMidStream

**Files:**
- Create: `frontend/src/components/cuaderno/frames/FrameEmpty.tsx`
- Create: `frontend/src/components/cuaderno/frames/FrameMidStream.tsx`

- [ ] **Step 1: FrameEmpty**

Create `frontend/src/components/cuaderno/frames/FrameEmpty.tsx`. Source: `frames.jsx` lines 32-61.

```tsx
type Props = { onAsk: (q: string) => void }

export function FrameEmpty({ onAsk }: Props) {
  return (
    <div className="empty">
      <h1 className="hi">
        First time in this project. <em>What interests you?</em>
      </h1>
      <p className="sub">
        Ask anything in your own words — broad ("what does this project do?"),
        relational ("how do X and Y connect?"), or atomic ("why is line 152
        written this way?"). Every answer is anchored to real code; nothing
        invented.
      </p>
      <div className="starters">
        <div className="cap">or start from here</div>
        <button
          className="starter"
          onClick={() => onAsk('what does this project do?')}
        >
          <span className="glyph">A</span>
          <span>what does this project do?</span>
          <span className="arr">→</span>
        </button>
        <button
          className="starter"
          onClick={() =>
            onAsk('how do the analyzer and the playground connect?')
          }
        >
          <span className="glyph">B</span>
          <span>how do the analyzer and the playground connect?</span>
          <span className="arr">→</span>
        </button>
        <button
          className="starter"
          onClick={() =>
            onAsk(
              'why does _module_from_relpath use slash instead of dot?',
            )
          }
        >
          <span className="glyph">C</span>
          <span>
            why does{' '}
            <code style={{ fontFamily: 'var(--font-mono)', fontStyle: 'normal', fontSize: '0.85em' }}>
              _module_from_relpath
            </code>{' '}
            use slash instead of dot?
          </span>
          <span className="arr">→</span>
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: FrameMidStream**

Create `frontend/src/components/cuaderno/frames/FrameMidStream.tsx`. Source: `frames.jsx` lines 64-91.

```tsx
type ToolState = 'queued' | 'running' | 'done'

type ToolRow = {
  state: ToolState
  name: string
  args: string
  ms: number | null
}

type Props = {
  question: string
  tools: ToolRow[]
  partial: string
}

export function FrameMidStream({ question, tools, partial }: Props) {
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">{question}</span>
      </div>
      <div className="toolcalls" aria-label="LLM tool calls">
        {tools.map((t, i) => (
          <div key={i} className={`row ${t.state}`}>
            <span className="tag">
              {t.state === 'done' ? '✓' : t.state === 'running' ? '◐' : '·'}
            </span>
            <span className="name">{t.name}</span>
            <span className="args">{t.args}</span>
            <span className="meta">
              {t.state === 'done'
                ? `${t.ms ?? 0} ms`
                : t.state === 'running'
                ? 'running…'
                : 'queued'}
            </span>
          </div>
        ))}
      </div>
      <p className="cua-lead">
        {partial}
        <span className="streaming-caret" />
      </p>
    </>
  )
}
```

- [ ] **Step 3: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/cuaderno/frames/FrameEmpty.tsx frontend/src/components/cuaderno/frames/FrameMidStream.tsx
git commit -m "feat(cuaderno-fe): FrameEmpty + FrameMidStream"
```

---

### Task 27: Cuaderno top-level component

**Files:**
- Create: `frontend/src/components/cuaderno/Cuaderno.tsx`

- [ ] **Step 1: Compose the surface**

Create `frontend/src/components/cuaderno/Cuaderno.tsx`. Source: `cuaderno.jsx` lines 21-223. This is the shell that owns the active frame + composer + side panel + history overlay.

```tsx
import { useState } from 'react'
import type { Citation, CuadernoQuestion } from '../../types/api'
import { Composer } from './Composer'
import { GotItMarkers } from './GotItMarkers'
import { SidePanel } from './SidePanel'
import { HistoryOverlay } from './HistoryOverlay'
import { FrameEmpty } from './frames/FrameEmpty'
import { FrameMidStream } from './frames/FrameMidStream'
import { FrameDynamic } from './frames/FrameDynamic'

type Props = {
  sessionLabel: string
  questionNumber: string
  questions: CuadernoQuestion[]
  activeQuestion: CuadernoQuestion | null
  isLoading: boolean
  partialText?: string
  toolCalls?: Array<{ state: 'queued' | 'running' | 'done'; name: string; args: string; ms: number | null }>
  onAsk: (question: string) => void
  onSelectFromHistory: (position: number) => void
  onSetGotIt: (position: number, value: 'got' | 'didnt') => void
}

export function Cuaderno({
  sessionLabel,
  questionNumber,
  questions,
  activeQuestion,
  isLoading,
  partialText = '',
  toolCalls = [],
  onAsk,
  onSelectFromHistory,
  onSetGotIt,
}: Props) {
  const [sidePanelFor, setSidePanelFor] = useState<Citation | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const scene: 'empty' | 'midstream' | 'frame' =
    isLoading ? 'midstream' : activeQuestion ? 'frame' : 'empty'

  return (
    <div className="cuaderno theme-light accent-sienna density-regular">
      <div className="cua-top">
        <div className="crumb">
          <span className="dot" />
          <span className="here">copyclip</span>
          <span className="sep">·</span>
          <span>cuaderno</span>
          <span className="sep">·</span>
          <span style={{ color: 'var(--ink-2)' }}>{sessionLabel}</span>
        </div>
        <div className="right">
          <span className="session">{questionNumber}</span>
          <button
            className="hamb"
            onClick={() => setHistoryOpen((h) => !h)}
            aria-label="session history"
          >
            ≡
          </button>
        </div>
      </div>

      <div className="cua-stage swap-fade">
        <div className="cua-frame-wrap">
          <div className="cua-frame" key={activeQuestion?.position ?? scene}>
            {scene === 'empty' && <FrameEmpty onAsk={onAsk} />}
            {scene === 'midstream' && (
              <FrameMidStream
                question={questions[questions.length - 1]?.question ?? '…'}
                tools={toolCalls}
                partial={partialText}
              />
            )}
            {scene === 'frame' && activeQuestion && (
              <>
                <FrameDynamic
                  frame={activeQuestion.frame}
                  onOpenCitation={setSidePanelFor}
                  onAsk={onAsk}
                />
                <GotItMarkers
                  value={activeQuestion.got_it}
                  onSet={(v) => onSetGotIt(activeQuestion.position, v)}
                />
              </>
            )}
          </div>
        </div>

        <Composer onSubmit={onAsk} disabled={isLoading} />

        {sidePanelFor && (
          <SidePanel citation={sidePanelFor} onClose={() => setSidePanelFor(null)} />
        )}

        {historyOpen && (
          <HistoryOverlay
            questions={questions}
            activePosition={activeQuestion?.position ?? null}
            onSelect={(p) => {
              setHistoryOpen(false)
              onSelectFromHistory(p)
            }}
            onClose={() => setHistoryOpen(false)}
          />
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/Cuaderno.tsx
git commit -m "feat(cuaderno-fe): Cuaderno surface composes all components"
```

---

### Task 28: CuadernoPage container with API integration

**Files:**
- Create: `frontend/src/pages/CuadernoPage.tsx`

- [ ] **Step 1: Create the page container**

Create `frontend/src/pages/CuadernoPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import type { CuadernoQuestion } from '../types/api'
import { Cuaderno } from '../components/cuaderno/Cuaderno'
import { cuadernoApi } from '../api/cuaderno'

const SESSION_STORAGE_KEY = 'copyclip.cuaderno.session_id'

export function CuadernoPage() {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem(SESSION_STORAGE_KEY),
  )
  const [questions, setQuestions] = useState<CuadernoQuestion[]>([])
  const [activePosition, setActivePosition] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activeQuestion = useMemo(
    () => questions.find((q) => q.position === activePosition) ?? null,
    [questions, activePosition],
  )

  // Restore session on mount
  useEffect(() => {
    if (!sessionId) return
    cuadernoApi
      .session(sessionId)
      .then((s) => {
        setQuestions(s.questions)
        if (s.questions.length > 0) {
          setActivePosition(s.questions[s.questions.length - 1].position)
        }
      })
      .catch(() => {
        // session is dead; clear and start fresh
        localStorage.removeItem(SESSION_STORAGE_KEY)
        setSessionId(null)
      })
  }, [sessionId])

  const onAsk = (question: string) => {
    setIsLoading(true)
    setError(null)
    cuadernoApi
      .ask(question, sessionId ?? undefined)
      .then((r) => {
        if (!sessionId) {
          setSessionId(r.session_id)
          localStorage.setItem(SESSION_STORAGE_KEY, r.session_id)
        }
        const newQ: CuadernoQuestion = {
          position: r.position,
          question,
          frame: r.frame,
          bookmarked: false,
          got_it: null,
          created_at: new Date().toISOString(),
        }
        setQuestions((prev) => [...prev, newQ])
        setActivePosition(r.position)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setIsLoading(false))
  }

  const onSelectFromHistory = (position: number) => {
    setActivePosition(position)
  }

  const onSetGotIt = (position: number, value: 'got' | 'didnt') => {
    if (!sessionId) return
    cuadernoApi
      .patchQuestion(sessionId, position, { got_it: value })
      .catch(() => {})
    setQuestions((prev) =>
      prev.map((q) => (q.position === position ? { ...q, got_it: value } : q)),
    )
  }

  const sessionLabel = sessionId
    ? `session ${sessionId.slice(0, 8)}`
    : 'new session'
  const questionNumber = activePosition
    ? `${String(activePosition).padStart(2, '0')} · q`
    : '· q'

  return (
    <>
      {error ? (
        <div style={{
          background: 'var(--accent-soft)',
          color: 'var(--accent-ink)',
          padding: '8px 16px',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
        }}>
          {error}
        </div>
      ) : null}
      <Cuaderno
        sessionLabel={sessionLabel}
        questionNumber={questionNumber}
        questions={questions}
        activeQuestion={activeQuestion}
        isLoading={isLoading}
        onAsk={onAsk}
        onSelectFromHistory={onSelectFromHistory}
        onSetGotIt={onSetGotIt}
      />
    </>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CuadernoPage.tsx
git commit -m "feat(cuaderno-fe): CuadernoPage container with session + API wiring"
```

---

### Task 29: Wire to App.tsx + Sidebar

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Add cuaderno to the Page type and routing**

Open `frontend/src/App.tsx`. Find the `type Page = 'reacquaintance' | ... | 'settings'` line (around line 25) and add `'cuaderno'` to the union:

```typescript
type Page = 'reacquaintance' | 'ask' | 'handoff' | 'debt-navigator' | 'atlas-3d' | 'timeline' | 'planning' | 'changes' | 'architecture' | 'impact' | 'risks' | 'context-builder' | 'decisions' | 'settings' | 'cuaderno'
```

Add the import near the other page imports:

```typescript
import { CuadernoPage } from './pages/CuadernoPage'
```

Add the route entry near the other `{page === '...' && <Page />}` lines (around line 108-121):

```typescript
            {page === 'cuaderno' && <CuadernoPage />}
```

- [ ] **Step 2: Add cuaderno to the sidebar**

Open `frontend/src/components/Sidebar.tsx`. Find the `GROUPS` array. Add `cuaderno` as the FIRST entry of the `'Project Memory'` group, before `'catch me up'`:

```typescript
const GROUPS = [
  {
    label: 'Project Memory',
    pages: [
      { id: 'cuaderno', label: 'cuaderno' },
      { id: 'reacquaintance', label: 'catch me up' },
      // ... rest unchanged
    ]
  },
  // ... rest unchanged
]
```

- [ ] **Step 3: Verify TS compiles**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat(cuaderno-fe): wire cuaderno page into routing + sidebar"
```

---

### Task 30: Deploy bundle + smoke verify

**Files:**
- Modify: `src/copyclip/intelligence/ui/index.html` (regenerated by build)

- [ ] **Step 1: Build and copy bundle**

Run:
```bash
npm --prefix frontend run build
cp frontend/dist/index.html src/copyclip/intelligence/ui/index.html
```

Expected: build completes, `ui/index.html` is updated. Size should be ~310-330 KB.

- [ ] **Step 2: Restart backend if it is running**

If the backend (`copyclip start` or `.copyclip-verify.py`) is currently running, stop it and restart so it reloads `_HTML`.

- [ ] **Step 3: Smoke verify the page loads**

Open `http://127.0.0.1:4310/` in a browser. Navigate to **cuaderno** in the sidebar. The empty frame should appear with the editorial-notebook styling: warm paper background, sienna accents, the three starter buttons.

If `ANTHROPIC_API_KEY` is set in env or in `.copyclip/config`, clicking a starter should:
1. Show the composer in a disabled state
2. Eventually replace the empty frame with a real `FrameDynamic` rendered from the LLM response
3. Citation chips inside the frame open the side panel

If the API key is missing, the backend returns 503 `llm_not_configured` — the error banner at the top of the page should show this.

- [ ] **Step 4: Commit the bundle**

```bash
git add src/copyclip/intelligence/ui/index.html
git commit -m "build(cuaderno): redeploy frontend bundle with cuaderno page"
```

---

### Task 31: End-to-end acceptance — Example A

**Files:**
- Test: `tests/test_cuaderno_e2e.py`

- [ ] **Step 1: Write the acceptance test**

This test exercises the full flow with a stubbed Anthropic client. It does NOT call the real Claude API — that would be flaky and expensive in CI. The point is to validate that the wiring from `POST /api/cuaderno/ask` through compose_frame → tool dispatch → persistence → response is end-to-end correct.

```python
# tests/test_cuaderno_e2e.py
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

    class StubAdapter:
        def __init__(self, *_, **__): pass
        def messages_create(self, **kwargs):
            return tool_use_response if not getattr(self, "_done", False) else final_response

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
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_cuaderno_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cuaderno_e2e.py
git commit -m "test(cuaderno): e2e acceptance for example A flow"
```

---

## Phase F — Polish

### Task 32: Streaming via SSE (deferred to v1.1 — gate first version on non-streaming)

For the initial Phase 1 ship, the `POST /api/cuaderno/ask` returns the full frame after the compositor completes. The mid-stream visualization (`FrameMidStream` showing tool calls running) is implemented but only renders for the brief moment between request initiation and response completion in the current design.

A follow-up task (not in this plan) will add SSE streaming to pump tool-call progress and partial text to the frontend during the agentic loop. The frontend already has the `FrameMidStream` component ready to receive that data.

This task is intentionally **postponed** to keep the Phase 1 critical path narrow.

---

### Task 33: README addition for cuaderno

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short cuaderno section**

Find the existing "What this is" section (or equivalent) in `README.md`. Add a short block immediately after it:

```markdown
## Cuaderno (Phase 1)

The cuaderno is the conversational surface where the user asks questions
about the codebase and receives interactive frames composed by an LLM tutor.
See `docs/superpowers/specs/2026-05-28-copyclip-cuaderno-conversacional-design.md`
for the design and `docs/superpowers/specs/2026-05-28-cuaderno-prototype/` for
the visual reference.

Phase 1 requires `ANTHROPIC_API_KEY` set in env or `.copyclip/config`. Run
`copyclip start` to onboard.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add cuaderno phase 1 section to README"
```

---

## Self-review notes

**Spec coverage check:**

- Surface (cuaderno crumb, question echo, frame, got-it markers, composer, history overlay, side panel) → covered by Tasks 23, 24, 26, 27 + the styles port (Task 18)
- Architecture (Surface → Compositor → Anchor System with tool calls) → Tasks 5-13
- Anchor System primitives (read_file, grep_symbols, get_callers, get_callees, git_log, git_blame, git_diff, find_tests) → Tasks 5-9
- `read_transcript` is explicitly out of scope for Phase 1 (transcript ingestion deferred) — NOT in the plan
- Phase 1 widgets (graph_subset, sequence_diagram, callers_tree as display-only) → Tasks 19-21
- Session persistence in SQLite → Tasks 3-4
- Phase 1 success criteria (visual match to prototype scenes, citation chips open side panel, follow-up buttons mutate frame, session resume from localStorage) → Task 30 smoke + Task 31 e2e
- Streaming (tool calls visible during running, partial text streaming) → **postponed** in Task 32 — first ship is non-streaming. Stated explicitly so it isn't surprise scope.

**Type consistency check:** all Block kinds in the backend `schema.py` match the frontend `types/api.ts` and the `FrameDynamic` switch. The system prompt enumerates the same kinds. Citation shape is consistent (`kind: 'path' | 'commit'`).

**Placeholder check:** no TBDs, no "implement later", no "add appropriate error handling". Every step has the actual code or command.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-28-cuaderno-phase-1.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

**Which approach?**
