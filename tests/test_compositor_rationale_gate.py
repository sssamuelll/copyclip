"""Harden ② — the compositor gate that makes the accepted_not_decided stamp
honest-by-construction instead of prompt-hope.

Junta + Axiom-0 (2026-06-12): get_rationale already computes the verdict
deterministically, but nothing ENFORCES that the model surfaces it — the stamp
lived only in the prompt. This gate closes that: a callout that cites a file
get_rationale ruled `accepted_not_decided` (the ledger is silent — there is no
recorded 'why') must carry the verbatim ACCEPTED_NOT_DECIDED constant, or the
compositor rejects the block.

It is a CITE∩CITE STRUCTURAL gate (Halberg): the witnessed verdict
(accepted_not_decided for file F) ∩ the witnessed citation (the callout cites F)
→ require the witnessed constant. It never reads the prose to judge whether a
'why' is fabricated (that would be INFER); it only requires the stamp's presence
when a silent-ledger file is cited. Serrano's caveat is acknowledged: it guards
accepted_not_decided only; 'recovered' files (which have a real decision to cite)
are intentionally left ungated.
"""
import sqlite3

from copyclip.intelligence.cuaderno.compositor import (
    rationale_stamp_violation, iter_compose_events,
)
from copyclip.intelligence.cuaderno.anchor import ACCEPTED_NOT_DECIDED
from copyclip.intelligence.db import init_schema


def _callout(text, paths):
    return {
        "kind": "callout", "kicker": "recovered decision", "text": text,
        "citations": [{"kind": "path", "path": p} for p in paths],
    }


# ---- the pure structural predicate ----

def test_callout_over_silent_file_without_stamp_is_rejected():
    block = _callout("this module exists to orchestrate the pipeline", ["src/a.py"])
    reason = rationale_stamp_violation(block, {"src/a.py"})
    assert reason is not None
    assert "accepted_not_decided" in reason


def test_callout_over_silent_file_with_verbatim_stamp_passes():
    block = _callout(f"{ACCEPTED_NOT_DECIDED} an AI burst shaped it", ["src/a.py"])
    assert rationale_stamp_violation(block, {"src/a.py"}) is None


def test_callout_citing_a_non_floor_file_passes():
    block = _callout("this exists because of decision #4", ["src/b.py"])
    assert rationale_stamp_violation(block, {"src/a.py"}) is None


def test_non_callout_block_is_not_gated():
    para = {"kind": "paragraph", "text": "src/a.py does the thing"}
    assert rationale_stamp_violation(para, {"src/a.py"}) is None


def test_empty_floor_passes():
    block = _callout("anything at all", ["src/a.py"])
    assert rationale_stamp_violation(block, set()) is None


def test_commit_only_citations_do_not_trigger():
    block = {"kind": "callout", "kicker": "k", "text": "no stamp here",
             "citations": [{"kind": "commit", "commit": "abc123"}]}
    assert rationale_stamp_violation(block, {"src/a.py"}) is None


def test_windows_path_in_citation_is_normalized():
    block = _callout("a fabricated why", ["src\\a.py"])
    assert rationale_stamp_violation(block, {"src/a.py"}) is not None


# ---- wired through the real compose loop ----

class _Stub:
    def __init__(self, turns):
        self._turns = list(turns)

    def messages_stream(self, **kwargs):
        for ev in self._turns.pop(0):
            yield ev


def _silent_conn():
    """A project whose file src/a.py has commits but NO decision → get_rationale
    rules it accepted_not_decided."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    pid = int(conn.execute(
        "INSERT INTO projects(root_path,name) VALUES('/p','P')").lastrowid)
    conn.execute("INSERT INTO commits(project_id,sha,author,date,message,ai_attributed) "
                 "VALUES(?,?,?,?,?,1)", (pid, "c1", "S", "2026-01-01 00:00:00 +0000", "m"))
    conn.execute("INSERT INTO file_changes(project_id,commit_sha,file_path,additions,deletions) "
                 "VALUES(?,?,?,0,0)", (pid, "c1", "src/a.py"))
    conn.commit()
    return conn, pid


def _turns_calling_rationale_then_callout(callout_text):
    rationale_inp = {"file": "src/a.py"}
    callout_inp = _callout(callout_text, ["src/a.py"])
    return [
        [  # round 0: model recovers the rationale
            {"type": "block_stop", "block": {"type": "tool_use", "id": "r1",
             "name": "get_rationale", "input": rationale_inp}},
            {"type": "message_stop", "stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "r1", "name": "get_rationale", "input": rationale_inp}]},
        ],
        [  # round 1 (closing): model emits the callout + finishes
            {"type": "block_stop", "block": {"type": "tool_use", "id": "b1",
             "name": "emit_block", "input": callout_inp}},
            {"type": "block_stop", "block": {"type": "tool_use", "id": "f",
             "name": "finish", "input": {}}},
            {"type": "message_stop", "stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "b1", "name": "emit_block", "input": callout_inp},
                {"type": "tool_use", "id": "f", "name": "finish", "input": {}}]},
        ],
    ]


def test_compose_rejects_fabricated_why_over_silent_file():
    conn, pid = _silent_conn()
    client = _Stub(_turns_calling_rationale_then_callout(
        "this module exists to coordinate the analysis pipeline"))
    events = list(iter_compose_events(
        client=client, question="why does src/a.py exist?",
        project_root="/p", project_id=pid, conn=conn, max_tool_rounds=2))
    callouts = [e for e in events if e["type"] == "block" and e["block"].get("kind") == "callout"]
    assert callouts == []  # the invented 'why' over a silent ledger was rejected


def test_compose_accepts_callout_carrying_the_verbatim_stamp():
    conn, pid = _silent_conn()
    client = _Stub(_turns_calling_rationale_then_callout(
        f"{ACCEPTED_NOT_DECIDED} an AI burst shaped it"))
    events = list(iter_compose_events(
        client=client, question="why does src/a.py exist?",
        project_root="/p", project_id=pid, conn=conn, max_tool_rounds=2))
    callouts = [e for e in events if e["type"] == "block" and e["block"].get("kind") == "callout"]
    assert len(callouts) == 1  # the stamped callout crossed the gate
