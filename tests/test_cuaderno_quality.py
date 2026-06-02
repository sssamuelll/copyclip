from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from copyclip.intelligence.cuaderno.quality import assess, looks_like_code_question
from copyclip.intelligence.cuaderno.schema import (
    Block, FRAME_STATUS_ANSWER, FRAME_STATUS_UNGROUNDED,
)


def _ledger(content_reads: int) -> ReadLedger:
    led = ReadLedger()
    for i in range(content_reads):
        led.record("read_file", {"path": f"f{i}.py", "lines": [{"n": 1, "text": "x"}]})
    return led


def test_code_question_with_zero_reads_is_ungrounded():
    v = assess(question="how does the analyzer work?",
               blocks=[Block.lead("It is a CLI that scans your codebase.")],
               ledger=_ledger(0))
    assert v.status == FRAME_STATUS_UNGROUNDED
    assert v.suspicion is True


def test_code_question_with_reads_is_answer():
    v = assess(question="how does the analyzer work?",
               blocks=[Block.lead("It walks the AST in analyzer.py.")],
               ledger=_ledger(2))
    assert v.status == FRAME_STATUS_ANSWER


def test_meta_question_with_zero_reads_is_answer():
    v = assess(question="what can I ask you?",
               blocks=[Block.lead("Ask broad, relational, or atomic questions.")],
               ledger=_ledger(0))
    assert v.status == FRAME_STATUS_ANSWER


def test_language_mismatch_sets_suspicion_but_not_ungrounded():
    v = assess(question="¿cómo funciona el analizador?",
               blocks=[Block.lead("It walks the AST in analyzer.py.")],
               ledger=_ledger(1))
    assert v.status == FRAME_STATUS_ANSWER
    assert v.suspicion is True
    assert v.language_mismatch is True


def test_looks_like_code_question_detects_meta():
    assert looks_like_code_question("how does read_file work?") is True
    assert looks_like_code_question("what can I ask you?") is False
    assert looks_like_code_question("por qué respondiste en inglés?") is False
