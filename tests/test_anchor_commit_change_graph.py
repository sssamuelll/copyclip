"""The commit change graph (comprehension strategy ⑤, council-corrected).

`get_commit_change_graph` is the honest residue of "the plan, reassembled". The
roster council (2026-06-12) found that calling a commit's changed-file set "the
plan" lies in the noun: `file_changes` witnesses an EDIT set, "plan" asserts an
INTENT set, and `symbol_edges` is HEAD-state — so a drawn line proves "A calls B
AT HEAD", never "this wiring belonged to that burst". The reframe makes the
COMMIT the subject: "commit X (AI-attributed) changed these files; at HEAD here is
the cited call graph among them." Every claim witnessed; the human reassembles the
intent themselves.

Honesty invariants under test:
  - every edge carries as_of="head" (the link is at HEAD, not proven at the burst)
  - the unlinked bin distinguishes `not_indexed` (no symbols at all — deleted /
    non-code / unparsed) from `no_edge_in_index` (has symbols, none link here),
    and NEVER claims "no structural link exists"
  - coverage counts (changed vs indexed) so an empty graph reads as "index
    incomplete", not "files unrelated"
  - the file= resolution only ever lands on an AI-attributed commit
"""
import sqlite3

from copyclip.intelligence.cuaderno.anchor import get_commit_change_graph
from copyclip.intelligence.db import init_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    cur = conn.execute("INSERT INTO projects(root_path,name) VALUES('/p','P')")
    return conn, int(cur.lastrowid)


def _sym(conn, pid, name, file, ls, le=None, kind="function"):
    cur = conn.execute(
        "INSERT INTO symbols(project_id,name,kind,file_path,line_start,line_end) "
        "VALUES(?,?,?,?,?,?)", (pid, name, kind, file, ls, le or ls + 2))
    return int(cur.lastrowid)


def _calls(conn, pid, frm, to):
    conn.execute(
        "INSERT INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) "
        "VALUES(?,?,?,'calls')", (pid, frm, to))


def _commit(conn, pid, sha, date, ai, message="m"):
    conn.execute(
        "INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) "
        "VALUES(?,?,?,?,?,?)", (pid, sha, "S", date, message, 1 if ai else 0))


def _changed(conn, pid, sha, *files):
    for f in files:
        conn.execute(
            "INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) "
            "VALUES(?,?,?,0,0)", (pid, sha, f))


def test_linked_files_carry_cited_head_edges():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py", "src/b.py")
    fa = _sym(conn, pid, "fa", "src/a.py", 10)
    fb = _sym(conn, pid, "fb", "src/b.py", 20)
    _calls(conn, pid, fa, fb)
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1")
    assert out["resolved_via"] == "commit"
    assert out["commit"]["sha"] == "c1" and out["commit"]["ai_attributed"] is True
    assert set(out["linked"]) == {"src/a.py", "src/b.py"}
    assert out["co_changed_unlinked"] == []
    assert len(out["edges"]) == 1
    e = out["edges"][0]
    assert e["from_file"] == "src/a.py" and e["from_symbol"] == "fa" and e["from_line"] == 10
    assert e["to_file"] == "src/b.py" and e["to_symbol"] == "fb" and e["to_line"] == 20
    assert e["as_of"] == "head"
    assert out["kind"] == "static_change_graph"


def test_unlinked_with_symbols_is_no_edge_in_index():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py", "src/b.py", "src/c.py")
    fa = _sym(conn, pid, "fa", "src/a.py", 10)
    fb = _sym(conn, pid, "fb", "src/b.py", 20)
    _sym(conn, pid, "fc", "src/c.py", 1)  # has a symbol, no edge to a/b
    _calls(conn, pid, fa, fb)
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1")
    assert set(out["linked"]) == {"src/a.py", "src/b.py"}
    assert out["co_changed_unlinked"] == [{"file_path": "src/c.py", "reason": "no_edge_in_index"}]


def test_unlinked_without_symbols_is_not_indexed():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py", "src/b.py", "README.md")
    fa = _sym(conn, pid, "fa", "src/a.py", 10)
    fb = _sym(conn, pid, "fb", "src/b.py", 20)
    _calls(conn, pid, fa, fb)  # README.md has NO symbols at all
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1")
    assert out["co_changed_unlinked"] == [{"file_path": "README.md", "reason": "not_indexed"}]


def test_resolves_commit_by_sha_prefix():
    conn, pid = _conn()
    _commit(conn, pid, "abc123def456", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "abc123def456", "src/a.py", "src/b.py")
    fa = _sym(conn, pid, "fa", "src/a.py", 1)
    fb = _sym(conn, pid, "fb", "src/b.py", 1)
    _calls(conn, pid, fa, fb)
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="abc123")
    assert out["resolved_via"] == "commit"
    assert out["commit"]["sha"] == "abc123def456"


def test_file_resolution_picks_most_recent_ai_commit():
    conn, pid = _conn()
    _commit(conn, pid, "old", "2026-01-01 10:00:00 +0000", ai=True)
    _commit(conn, pid, "new", "2026-03-01 10:00:00 +0000", ai=True)
    _commit(conn, pid, "human", "2026-04-01 10:00:00 +0000", ai=False)  # newer but NOT ai
    _changed(conn, pid, "old", "src/a.py", "src/b.py")
    _changed(conn, pid, "new", "src/a.py", "src/d.py")
    _changed(conn, pid, "human", "src/a.py")
    conn.commit()

    out = get_commit_change_graph(conn, pid, file="src/a.py")
    assert out["resolved_via"] == "file"
    assert out["commit"]["sha"] == "new"  # most recent AI commit, human commit ignored


def test_commit_takes_precedence_when_both_passed():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _commit(conn, pid, "c2", "2026-02-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py", "src/b.py")
    _changed(conn, pid, "c2", "src/x.py", "src/y.py")
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1", file="src/x.py")
    assert out["commit"]["sha"] == "c1"


def test_neither_arg_returns_note_no_crash():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py")
    conn.commit()

    out = get_commit_change_graph(conn, pid)
    assert out["commit"] is None
    assert out["resolved_via"] is None
    assert out["linked"] == [] and out["edges"] == [] and out["co_changed_unlinked"] == []
    assert "note" in out


def test_file_with_no_ai_commit_returns_note():
    conn, pid = _conn()
    _commit(conn, pid, "human", "2026-01-01 10:00:00 +0000", ai=False)
    _changed(conn, pid, "human", "src/a.py")
    conn.commit()

    out = get_commit_change_graph(conn, pid, file="src/a.py")
    assert out["commit"] is None
    assert "note" in out


def test_coverage_counts():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py", "src/b.py", "README.md")
    _sym(conn, pid, "fa", "src/a.py", 1)
    _sym(conn, pid, "fb", "src/b.py", 1)
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1")
    assert out["changed_file_count"] == 3
    assert out["indexed_file_count"] == 2  # README.md has no symbols


def test_single_file_commit_has_no_edges():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/solo.py")
    _sym(conn, pid, "fsolo", "src/solo.py", 1)
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1")
    assert out["linked"] == [] and out["edges"] == []
    assert out["co_changed_unlinked"] == [{"file_path": "src/solo.py", "reason": "no_edge_in_index"}]
    assert out["changed_file_count"] == 1


def test_deletion_commit_is_all_not_indexed():
    """A teardown burst (the 24-file '203ea885c0' analog): changed files no longer
    have symbols in the index, so the graph is empty and every file is honestly
    `not_indexed` — never 'no structural link exists'."""
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/gone1.py", "src/gone2.py")  # no symbols inserted
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1")
    assert out["linked"] == [] and out["edges"] == []
    assert out["indexed_file_count"] == 0
    reasons = {u["file_path"]: u["reason"] for u in out["co_changed_unlinked"]}
    assert reasons == {"src/gone1.py": "not_indexed", "src/gone2.py": "not_indexed"}


def test_max_files_truncates_and_flags():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    files = [f"src/f{i}.py" for i in range(5)]
    _changed(conn, pid, "c1", *files)
    for i, f in enumerate(files):
        _sym(conn, pid, f"s{i}", f, 1)  # symbols but no inter-file edges
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="c1", max_files=2)
    assert out["truncated"] is True
    assert len(out["linked"]) + len(out["co_changed_unlinked"]) == 2


def test_unknown_commit_returns_note():
    conn, pid = _conn()
    _commit(conn, pid, "c1", "2026-01-01 10:00:00 +0000", ai=True)
    _changed(conn, pid, "c1", "src/a.py")
    conn.commit()

    out = get_commit_change_graph(conn, pid, commit="ZZZ")
    assert out["commit"] is None
    assert "note" in out
