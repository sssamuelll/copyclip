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
