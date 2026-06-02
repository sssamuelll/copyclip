import json

from copyclip.intelligence.cuaderno.openai_client import (
    OpenAICompatAdapter, _to_openai_request,
)


# --- input translation -------------------------------------------------------

def test_to_openai_request_translates_system_tools_and_messages():
    system = "you are the cuaderno"
    tools = [{
        "name": "read_file",
        "description": "read a file",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }]
    messages = [
        {"role": "user", "content": "what does this do?"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "let me look"},
            {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "README.md"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "# Hello"},
        ]},
    ]
    oai_messages, oai_tools = _to_openai_request(system, tools, messages)

    assert oai_messages[0] == {"role": "system", "content": "you are the cuaderno"}
    assert oai_messages[1] == {"role": "user", "content": "what does this do?"}
    assert oai_messages[2]["role"] == "assistant"
    assert oai_messages[2]["content"] == "let me look"
    assert oai_messages[2]["tool_calls"] == [{
        "id": "t1", "type": "function",
        "function": {"name": "read_file", "arguments": json.dumps({"path": "README.md"})},
    }]
    assert oai_messages[3] == {"role": "tool", "tool_call_id": "t1", "content": "# Hello"}
    assert oai_tools == [{
        "type": "function",
        "function": {
            "name": "read_file", "description": "read a file",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    }]


# --- streaming output normalization -----------------------------------------

class _Fn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _TC:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = _Fn(name, arguments)


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class _Chunk:
    def __init__(self, choice):
        self.choices = [choice]


class _FakeChatCompletions:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._chunks)


class _FakeChat:
    def __init__(self, chunks):
        self.completions = _FakeChatCompletions(chunks)


class _FakeOpenAI:
    def __init__(self, chunks):
        self.chat = _FakeChat(chunks)


def _adapter(chunks):
    return OpenAICompatAdapter(raw_client=_FakeOpenAI(chunks))


def test_messages_stream_emits_a_block_per_completed_tool_call():
    # Two emit_block tool calls streamed as argument fragments, then a finish.
    chunks = [
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, id="c0", name="emit_block")]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, arguments='{"kind":"lead",')]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, arguments='"text":"hi"}')]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(1, id="c1", name="emit_block")]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(1, arguments='{"kind":"paragraph","text":"body"}')]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(2, id="c2", name="finish")]))),
        _Chunk(_Choice(_Delta(tool_calls=[_TC(2, arguments='{}')]))),
        _Chunk(_Choice(_Delta(), finish_reason="tool_calls")),
    ]
    events = list(_adapter(chunks).messages_stream(
        model="deepseek-chat", system="s", tools=[], messages=[], max_tokens=100))

    block_stops = [e for e in events if e["type"] == "block_stop"]
    assert [b["block"]["name"] for b in block_stops] == ["emit_block", "emit_block", "finish"]
    assert block_stops[0]["block"]["input"] == {"kind": "lead", "text": "hi"}
    assert block_stops[1]["block"]["input"] == {"kind": "paragraph", "text": "body"}
    assert block_stops[0]["block"]["id"] == "c0"

    msg_stop = events[-1]
    assert msg_stop["type"] == "message_stop"
    assert msg_stop["stop_reason"] == "tool_use"
    assert [b["name"] for b in msg_stop["content"]] == ["emit_block", "emit_block", "finish"]


def test_messages_stream_skips_malformed_arguments():
    chunks = [
        _Chunk(_Choice(_Delta(tool_calls=[_TC(0, id="c0", name="emit_block", arguments="{not json")]))),
        _Chunk(_Choice(_Delta(), finish_reason="tool_calls")),
    ]
    events = list(_adapter(chunks).messages_stream(
        model="deepseek-chat", messages=[], max_tokens=100))
    assert [e for e in events if e["type"] == "block_stop"] == []
    assert events[-1]["type"] == "message_stop"


def test_messages_stream_maps_stop_reason_stop_to_end_turn():
    chunks = [
        _Chunk(_Choice(_Delta(content="hello"), finish_reason="stop")),
    ]
    events = list(_adapter(chunks).messages_stream(
        model="deepseek-chat", messages=[], max_tokens=100))
    assert events[-1]["stop_reason"] == "end_turn"


def test_messages_create_forwards_timeout_to_sdk():
    # The judge passes timeout=20; the OpenAI-compat path must HONOR it, not drop
    # it into **_ignored (else a hung judge stalls the terminal ~600s).
    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            class _Msg:
                content = "{}"
                tool_calls = []
            class _Choice:
                message = _Msg()
                finish_reason = "stop"
            class _Resp:
                choices = [_Choice()]
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Raw:
        chat = _Chat()

    adapter = OpenAICompatAdapter(raw_client=_Raw())
    adapter.messages_create(model="m", messages=[{"role": "user", "content": "x"}], timeout=20)
    assert captured.get("timeout") == 20
