"""Regression tests for the retry path that 400'd on real providers.

Bug: a grounding/responsiveness retry re-invokes the model, but the terminal
assistant turn's `tool_use` blocks (emit_block/finish) were left unanswered —
illegal for both the OpenAI ("insufficient tool messages following tool_calls")
and Anthropic APIs. And on the error that followed, the turn was not persisted,
so the question + answer were silently lost.
"""

import copy

from copyclip.intelligence.cuaderno.compositor import iter_compose_events
from copyclip.intelligence.cuaderno.openai_client import _to_openai_request
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop


class RecordingStub(StubStream):
    """StubStream that snapshots (deep-copies) the messages list AS SENT on each
    call. The base StubStream stores the live reference, which the compositor
    mutates in place — so a post-hoc read shows the final state, not what each
    call actually transmitted. We need the per-call snapshot to verify the retry
    call's messages were API-valid."""

    def __init__(self, turns):
        super().__init__(turns)
        self.message_snapshots = []

    def messages_stream(self, **kwargs):
        self.message_snapshots.append(copy.deepcopy(kwargs.get("messages")))
        yield from super().messages_stream(**kwargs)


def _assert_openai_tool_calls_answered(oai_messages):
    """OpenAI's hard requirement: an assistant message with tool_calls must be
    immediately followed by one role:tool message per tool_call_id — the exact
    rule the 400 'insufficient tool messages following tool_calls' enforces."""
    for i, m in enumerate(oai_messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            ids = [tc["id"] for tc in m["tool_calls"]]
            window = oai_messages[i + 1 : i + 1 + len(ids)]
            answered = {t.get("tool_call_id") for t in window if t.get("role") == "tool"}
            missing = set(ids) - answered
            assert not missing, (
                f"assistant tool_calls {ids} not answered (missing {missing}); "
                f"would 400 on OpenAI. Following: {oai_messages[i + 1 : i + 2 + len(ids)]}")


def _ungrounded_turn(bid, fid, text):
    # Emits one paragraph (no content-bearing reads) + finish -> the cheap layer
    # seals 'ungrounded' for a code question, firing a grounding retry.
    return [
        _tool_stop(bid, "emit_block", {"kind": "paragraph", "text": text}),
        _tool_stop(fid, "finish", {}),
        _msg_stop("tool_use", [
            _content(bid, "emit_block", {"kind": "paragraph", "text": text}),
            _content(fid, "finish", {}),
        ]),
    ]


def test_grounding_retry_produces_api_valid_messages(tmp_path):
    client = RecordingStub([_ungrounded_turn("b1", "f1", "first ungrounded"),
                            _ungrounded_turn("b2", "f2", "second")])
    list(iter_compose_events(
        client=client, question="how does the compositor work?",
        project_root=str(tmp_path), project_id=1, conn=None, max_tool_rounds=8))
    # A grounding retry must have fired -> at least 2 model calls.
    assert len(client.message_snapshots) >= 2, "expected a retry (2 model calls)"
    # The messages AS SENT on the retry call must translate to a valid OpenAI
    # sequence (every assistant tool_call answered by a tool message).
    retry_messages = client.message_snapshots[1]
    oai, _ = _to_openai_request(None, None, retry_messages)
    _assert_openai_tool_calls_answered(oai)
