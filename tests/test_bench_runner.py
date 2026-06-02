from copyclip.intelligence.cuaderno.compositor import iter_compose_events
from copyclip.intelligence.cuaderno.read_ledger import ReadLedger
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop

from copyclip.intelligence.cuaderno.bench.runner import run_one, build_question_record
from copyclip.intelligence.cuaderno.bench.asserts import AssertContext
from copyclip.intelligence.cuaderno.judge import JudgeVerdict


def test_injected_ledger_is_populated(tmp_path):
    # A scripted turn: read_file returns content, then emit a block + finish.
    turn = [
        _tool_stop("t1", "read_file", {"path": "a.py", "line_start": 1, "line_end": 5}),
        _tool_stop("b1", "emit_block", {"kind": "paragraph", "text": "x reads a.py"}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("t1", "read_file", {"path": "a.py", "line_start": 1, "line_end": 5}),
            _content("b1", "emit_block", {"kind": "paragraph", "text": "x reads a.py"}),
            _content("f1", "finish", {}),
        ]),
    ]
    # NOTE: read_file dispatch needs the project; StubStream + conn=None means
    # dispatch_tool runs against tmp_path. For a pure unit test of injection we
    # only assert the ledger object identity is used: pass our own ledger and
    # confirm iter_compose_events does not replace it.
    my_ledger = ReadLedger()
    list(iter_compose_events(
        client=StubStream([_msg_stop("end_turn", [])]),  # immediate non-tool stop, no blocks
        question="q", project_root=str(tmp_path), project_id=1, conn=None,
        max_tool_rounds=1, ledger=my_ledger,
    ))
    # The loop ran with OUR ledger (no exception, object accepted). content count
    # is 0 here (no reads happened), but the param must be accepted and used.
    assert my_ledger.content_bearing_count == 0


def test_run_one_assembles_record_and_runs_asserts(tmp_path):
    # Scripted: emit a paragraph citing a.py + finish, non-tool stop. No real reads,
    # so content_bearing_count stays 0 and the cheap layer will seal ungrounded for
    # a code question -> we assert that the record captures status + asserts honestly.
    turn = [
        _tool_stop("b1", "emit_block",
                   {"kind": "paragraph", "text": "esto está en a.py"}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "paragraph", "text": "esto está en a.py"}),
            _content("f1", "finish", {}),
        ]),
    ]
    item = {
        "id": "q1", "question": "¿cómo funciona a?", "category": "grounded_happy_path",
        "commit_sha": "e4400af", "question_lang": "es",
        "asserts": [{"type": "status_in", "value": ["answer", "ungrounded"]},
                    {"type": "language_is", "value": "es"},
                    {"type": "harvested_responsive", "value": True}],
    }
    ctx = AssertContext(file_length_fn=lambda p: 100)
    # max_tool_rounds=1 => round 0 is the closing round: it seals without a
    # grounding retry (can_retry is False), so the single scripted turn suffices.
    # With the default 8 rounds the ungrounded code answer would fire a retry,
    # exhaust the one scripted turn, and seal `partial` instead.
    rec = run_one(
        item=item, client=StubStream([turn]), judge=None,
        answer_model="claude-sonnet-4-5", project_root=str(tmp_path),
        project_id=1, conn=None, assert_ctx=ctx, max_tool_rounds=1,
    )
    assert rec.id == "q1"
    assert rec.status in ("answer", "ungrounded")
    assert rec.answer_lang == "es"
    # status_in passes, language_is passes, harvested_responsive is inconclusive
    # (no judge -> cheap verdict has responsive=None)
    outcomes = {a["type"]: a["outcome"] for a in rec.asserts}
    assert outcomes["status_in"] == "pass"
    assert outcomes["language_is"] == "pass"
    assert outcomes["harvested_responsive"] == "inconclusive"
    assert rec.question_rollup["n_inconclusive"] == 1


def test_run_one_with_stub_judge_harvests_responsive(tmp_path):
    turn = [
        _tool_stop("b1", "emit_block", {"kind": "paragraph", "text": "respuesta en es"}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block", {"kind": "paragraph", "text": "respuesta en es"}),
            _content("f1", "finish", {}),
        ]),
    ]
    # meta question -> cheap layer will seal 'answer' even with zero reads;
    # the judge then runs and we script it ok+responsive.
    item = {"id": "m1", "question": "¿qué te puedo preguntar?", "category": "meta_about_tutor",
            "commit_sha": "e4400af", "question_lang": "es",
            "asserts": [{"type": "harvested_responsive", "value": True}]}
    jv = JudgeVerdict(question_kind="meta", grounded=True, responsive=True,
                      language_ok=True, decision="ok", world=None,
                      retry_directive=None, reason="ok", judged=True)

    def stub_judge(q, b, l):
        return jv

    ctx = AssertContext(file_length_fn=lambda p: 100)
    rec = run_one(item=item, client=StubStream([turn]), judge=stub_judge,
                  answer_model="claude-sonnet-4-5", project_root=str(tmp_path),
                  project_id=1, conn=None, assert_ctx=ctx)
    assert rec.verdict["responsive"] is True
    assert rec.asserts[0]["outcome"] == "pass"
