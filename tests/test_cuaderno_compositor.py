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
