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


def test_cites_only_unread_paths_is_ungrounded():
    # Oriented with list_dir but cites a file it never read -> fabricated grounding.
    led = ReadLedger()
    led.record("list_dir", {"path": ".", "entries": ["a", "b"]})
    v = assess(
        question="how does the analyzer work?",
        blocks=[
            Block.lead("It walks the AST in analyzer.py."),
            Block.citation({"kind": "path", "path": "src/analyzer.py", "line_start": 10}),
        ],
        ledger=led,
    )
    assert v.status == FRAME_STATUS_UNGROUNDED
    assert "unread" in v.reason


def test_cites_a_read_path_is_answer():
    led = ReadLedger()
    led.record("read_file", {"path": "src/analyzer.py", "lines": [{"n": 1, "text": "x"}]})
    v = assess(
        question="how does the analyzer work?",
        blocks=[
            Block.lead("It walks the AST."),
            Block.citation({"kind": "path", "path": "src/analyzer.py"}),
        ],
        ledger=led,
    )
    assert v.status == FRAME_STATUS_ANSWER


def test_reads_but_no_citations_is_answer():
    led = ReadLedger()
    led.record("read_file", {"path": "README.md", "lines": [{"n": 1, "text": "x"}]})
    v = assess(question="how does it work?", blocks=[Block.lead("It does X.")], ledger=led)
    assert v.status == FRAME_STATUS_ANSWER


def test_verdict_carries_question_language():
    led = ReadLedger()
    led.record("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})
    v = assess(question="como funciona el analizador", blocks=[Block.lead("hi")], ledger=led)
    assert v.question_language == "es"


def test_grep_grounded_with_citation_is_not_falsely_ungrounded():
    # Read via grep_symbols (no top-level `path` -> read_paths stays empty).
    # Citing a real file must NOT be condemned as fabricated (we cannot verify).
    led = ReadLedger()
    led.record("grep_symbols", {"symbols": [{"name": "f", "path": "src/foo.py"}]})
    assert led.content_bearing_count == 1 and led.read_paths == set()
    v = assess(
        question="how does foo work?",
        blocks=[
            Block.lead("foo dispatches via the symbol table."),
            Block.citation({"kind": "path", "path": "src/foo.py"}),
        ],
        ledger=led,
    )
    assert v.status == FRAME_STATUS_ANSWER


def test_malformed_scalar_citations_does_not_crash():
    # A model could emit a kind-valid block with a scalar where a list belongs.
    led = ReadLedger()
    led.record("read_file", {"path": "a.py", "lines": [{"n": 1, "text": "x"}]})
    bad = Block.from_dict({"kind": "callout", "kicker": "k", "text": "t", "citations": 5})
    worse = Block.from_dict({"kind": "ordered_list", "items": "nope"})
    v = assess(question="how does it work?", blocks=[bad, worse], ledger=led)
    assert v.status == FRAME_STATUS_ANSWER  # no raise, no false seal
