"""The open-order nudge — the honest residue of the descent gate (Level 2 of the
cognitive-load doctrine, council-corrected 2026-06-12).

The design council found legibility is NOT structurally sealable: "never measure the
climber" + "never INFER" leave only grounding (already sealed by assess) and ONE
INFER-free move — do not OPEN with the wall. So `altitude_violation` rejects exactly
the one witnessed failure: a code-question answer whose FIRST block is a dense
`citation_stack` (>=3 items), with no plain lead before it. Block-KIND + item-count
only; it never reads a block's text and never judges whether a lead is "plain". It is
a NUDGE, not an invariant — it bans the FLOOD-greeting and nothing more; FLOAT and
the rest of legibility stay prompt-guided.
"""
from copyclip.intelligence.cuaderno.quality import altitude_violation
from copyclip.intelligence.cuaderno.schema import Block

CODE_Q = "how does assess work end to end?"


def _stack(n):
    return Block(kind="citation_stack", data={"items": [
        {"citation": {"kind": "path", "path": "a.py", "line_start": i}, "note": "x"}
        for i in range(1, n + 1)
    ]})


def test_opening_with_a_dense_stack_is_a_violation():
    reason = altitude_violation([_stack(3), Block.lead("ok")], CODE_Q)
    assert reason is not None and "wall" in reason


def test_short_opening_stack_passes():
    # 1-2 items is a terse reveal, not a wall.
    assert altitude_violation([_stack(2)], CODE_Q) is None


def test_lead_before_the_wall_passes():
    assert altitude_violation([Block.lead("assess seals grounding"), _stack(10)], CODE_Q) is None


def test_code_block_opener_passes():
    # The terse "here is the function" reveal — nothing hidden, descent reachable.
    blocks = [Block(kind="code_block", data={"code": "def f(): ...", "language": "python"})]
    assert altitude_violation(blocks, CODE_Q) is None


def test_callout_opener_passes():
    # A Risk/decision answer legitimately leads with a callout (the claim block).
    blocks = [Block.callout("risk", "high churn", [{"kind": "path", "path": "a.py"}])]
    assert altitude_violation(blocks, CODE_Q) is None


def test_non_code_question_passes():
    # Meta questions never require a descent shape.
    assert altitude_violation([_stack(5)], "what can i ask you?") is None


def test_empty_blocks_pass():
    assert altitude_violation([], CODE_Q) is None


# --- wired through the real compose loop ---

class _Stub:
    def __init__(self, turns):
        self._turns = list(turns)

    def messages_stream(self, **kwargs):
        for ev in self._turns.pop(0):
            yield ev


def _stop(bid, name, inp):
    return {"type": "block_stop",
            "block": {"type": "tool_use", "id": bid, "name": name, "input": inp}}


def _content(bid, name, inp):
    return {"type": "tool_use", "id": bid, "name": name, "input": inp}


def _msg(content):
    return {"type": "message_stop", "stop_reason": "tool_use", "content": content}


def test_compose_retries_when_a_code_answer_opens_with_the_wall(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    stack = {"kind": "citation_stack", "items": [
        {"citation": {"kind": "path", "path": "a.py", "line_start": 1}, "note": "x"},
        {"citation": {"kind": "path", "path": "a.py", "line_start": 2}, "note": "y"},
        {"citation": {"kind": "path", "path": "a.py", "line_start": 1}, "note": "z"},
    ]}
    lead = {"kind": "lead", "text": "f returns 1"}
    from copyclip.intelligence.cuaderno.compositor import iter_compose_events
    turns = [
        # round 0: open the file so grounding can pass
        [_stop("r", "read_file", {"path": "a.py"}),
         _msg([_content("r", "read_file", {"path": "a.py"})])],
        # round 1: OPEN WITH THE WALL (3-item stack) + finish -> grounding passes,
        # altitude fires
        [_stop("b", "emit_block", stack), _stop("f", "finish", {}),
         _msg([_content("b", "emit_block", stack), _content("f", "finish", {})])],
        # round 2 (the altitude retry round): lead first -> seal
        [_stop("b2", "emit_block", lead), _stop("f2", "finish", {}),
         _msg([_content("b2", "emit_block", lead), _content("f2", "finish", {})])],
    ]
    events = list(iter_compose_events(
        client=_Stub(turns), question="how does f work end to end?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=5))
    assert any(e["type"] == "reset" for e in events)  # the altitude retry fired
    frame = next(e["frame"] for e in events if e["type"] == "frame")
    assert frame["blocks"][0]["kind"] == "lead"  # re-emitted lead-first
