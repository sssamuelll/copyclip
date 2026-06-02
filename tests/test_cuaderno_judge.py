from copyclip.intelligence.cuaderno.judge import (
    JudgeVerdict, parse_judge_verdict, judge_answer, judge_verdict_dict,
)
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.schema import Block


def test_parses_a_clean_ok_verdict():
    v = parse_judge_verdict(
        '{"question_kind":"code_comprehension","grounded":true,"responsive":true,'
        '"language_ok":true,"decision":"ok","reason":"answers the mechanism"}'
    )
    assert v is not None
    assert v.decision == "ok" and v.responsive is True


def test_parses_retry_with_directive():
    v = parse_judge_verdict(
        '{"decision":"retry","responsive":false,"grounded":true,"language_ok":true,'
        '"question_kind":"code_comprehension","retry_directive":"explain the mechanism, not what it is","reason":"answered what not how"}'
    )
    assert v.decision == "retry" and v.responsive is False
    assert "mechanism" in v.retry_directive


def test_parses_insufficient_with_world():
    v = parse_judge_verdict(
        '{"decision":"insufficient","world":"consulted_empty","grounded":false,'
        '"responsive":true,"language_ok":true,"question_kind":"code_comprehension","reason":"no evidence in repo"}'
    )
    assert v.decision == "insufficient" and v.world == "consulted_empty"


def test_extracts_json_from_surrounding_prose():
    v = parse_judge_verdict('Here is my verdict:\n```json\n{"decision":"ok"}\n```\nDone.')
    assert v is not None and v.decision == "ok"


def test_unparseable_returns_none():
    assert parse_judge_verdict("not json at all") is None
    assert parse_judge_verdict('{"decision":"bogus"}') is None
    assert parse_judge_verdict("") is None


class _StubClient:
    def __init__(self, text=None, raises=False):
        self._text = text
        self._raises = raises
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise RuntimeError("api down")
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": self._text}]}


def _ledger():
    led = ReadLedger()
    led.record("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})
    return led


def test_judge_answer_parses_client_text():
    client = _StubClient(text='{"decision":"retry","responsive":false,"retry_directive":"explain how"}')
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("it is X")],
                     ledger=_ledger(), model="claude-haiku-4-5")
    assert v.decision == "retry" and v.responsive is False
    assert client.calls[0]["model"] == "claude-haiku-4-5"


def test_judge_answer_fails_open_on_exception():
    client = _StubClient(raises=True)
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("x")],
                     ledger=_ledger(), model="m")
    assert v.decision == "ok"


def test_judge_answer_fails_open_on_garbage():
    client = _StubClient(text="the model rambled and produced no json")
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("x")],
                     ledger=_ledger(), model="m")
    assert v.decision == "ok"


def test_judge_verdict_dict_shape():
    v = JudgeVerdict("code_comprehension", True, False, True, "retry", None, "redo", "off topic")
    d = judge_verdict_dict(v)
    assert d == {
        "grounded": True, "responsive": False, "language_ok": True,
        "question_kind": "code_comprehension", "world": None,
        "reason": "off topic", "source": "judge",
    }


def test_parse_unhashable_decision_returns_none():
    # The membership test must not raise on an unhashable `decision`.
    assert parse_judge_verdict('{"decision":["ok"]}') is None
    assert parse_judge_verdict('{"decision":{"x":1}}') is None


def test_judge_answer_fails_open_on_unhashable_decision():
    # The #124 invariant: valid JSON with a malformed decision must STILL
    # fail-open to ok, never raise out of judge_answer.
    client = _StubClient(text='{"decision":["ok"]}')
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("x")],
                     ledger=_ledger(), model="m")
    assert v.decision == "ok"


def test_failopen_verdict_is_recorded_as_unjudged():
    # A judge outage must NOT forge "the judge checked it and it's responsive".
    client = _StubClient(raises=True)
    v = judge_answer(client=client, question="how?", blocks=[Block.lead("x")],
                     ledger=_ledger(), model="m")
    assert v.judged is False
    d = judge_verdict_dict(v)
    assert d["source"] == "unjudged"
    assert d["responsive"] is None and d["grounded"] is None and d["language_ok"] is None


def test_parse_omitted_axes_stay_none_not_true():
    # An omitted assessment axis stays None (unknown), never defaults to True.
    v = parse_judge_verdict('{"decision":"retry"}')
    assert v is not None and v.decision == "retry"
    assert v.responsive is None and v.grounded is None and v.language_ok is None
    assert v.judged is True  # it WAS judged; the model just omitted the axes


def test_real_judge_verdict_is_source_judge():
    v = parse_judge_verdict('{"decision":"ok","responsive":true,"grounded":true,"language_ok":true}')
    assert judge_verdict_dict(v)["source"] == "judge"
