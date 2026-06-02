from copyclip.intelligence.cuaderno.bench.artifact import (
    QuestionRecord, RunArtifact, write_artifact, read_artifact,
)


def _rec():
    return QuestionRecord(
        id="q1", category="grounded_happy_path", commit_sha="e4400af",
        question="¿cómo funciona X?", question_lang="es",
        status="answer", verdict={"grounded": True, "responsive": True,
                                  "language_ok": True, "source": "judge"},
        blocks=[{"kind": "paragraph", "text": "X reads a.py"}],
        cited_paths=["a.py"],
        citations=[{"kind": "path", "path": "a.py", "line_start": 1, "line_end": 5}],
        read_paths=["a.py"], content_bearing_count=1, answer_lang="es",
        latency_ms=1200, input_tokens=100, output_tokens=50, cost_usd=0.0,
        cost_estimated=True, asserts=[{"type": "status_in", "outcome": "pass",
                                       "score": 1.0, "reason": "status=answer"}],
        question_rollup={"all_pass": True, "n_pass": 1, "n_fail": 0, "n_inconclusive": 0},
    )


def test_round_trip(tmp_path):
    art = RunArtifact(
        run_id="20260602-120000-abc123", started_at="2026-06-02T12:00:00",
        corpus_path="corpus/cuaderno-bench.jsonl", corpus_sha="deadbeef",
        head_sha="e4400af", answer_model="claude-sonnet-4-5",
        judge_model="claude-haiku-4-5", provider="anthropic",
        copyclip_version="0.4.0", items=[_rec()],
    )
    path = tmp_path / "run.json"
    write_artifact(art, str(path))
    back = read_artifact(str(path))
    assert back.run_id == art.run_id
    assert back.items[0].id == "q1"
    assert back.items[0].verdict["grounded"] is True
    assert back.items[0].question_rollup["all_pass"] is True
    assert back.items[0].cost_estimated is True


def test_default_run_path_under_dot_copyclip():
    from copyclip.intelligence.cuaderno.bench.artifact import default_run_path
    p = default_run_path("/proj", "20260602-120000-abc123")
    assert p.replace("\\", "/").endswith(".copyclip/bench/runs/20260602-120000-abc123.json")
