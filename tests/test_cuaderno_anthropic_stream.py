from copyclip.intelligence.cuaderno.anthropic_client import (
    AnthropicAdapter, _normalize_block,
)


class _Blk:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _StopEvent:
    type = "content_block_stop"
    def __init__(self, block):
        self.content_block = block


class _OtherEvent:
    type = "content_block_delta"  # should be ignored by messages_stream


class _FakeStreamCtx:
    def __init__(self, events, final):
        self._events = events
        self._final = final
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def __iter__(self):
        return iter(self._events)
    def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, ctx):
        self._ctx = ctx
    def stream(self, **kwargs):
        return self._ctx


class _FakeRawClient:
    def __init__(self, ctx):
        self.messages = _FakeMessages(ctx)


def test_normalize_block_text_and_tool_use():
    assert _normalize_block(_Blk(type="text", text="hi")) == {"type": "text", "text": "hi"}
    assert _normalize_block(
        _Blk(type="tool_use", id="t1", name="read_file", input={"path": "x"})
    ) == {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}}


def test_messages_stream_yields_block_stops_then_message_stop():
    tool_blk = _Blk(type="tool_use", id="b1", name="emit_block",
                    input={"kind": "lead", "text": "hi"})
    final = _Blk(stop_reason="tool_use", content=[tool_blk])
    ctx = _FakeStreamCtx([_StopEvent(tool_blk), _OtherEvent()], final)
    adapter = AnthropicAdapter(raw_client=_FakeRawClient(ctx))

    events = list(adapter.messages_stream(model="m", messages=[], max_tokens=10))
    assert events[0] == {
        "type": "block_stop",
        "block": {"type": "tool_use", "id": "b1", "name": "emit_block",
                  "input": {"kind": "lead", "text": "hi"}},
    }
    assert events[-1] == {
        "type": "message_stop",
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": "b1", "name": "emit_block",
                     "input": {"kind": "lead", "text": "hi"}}],
    }
