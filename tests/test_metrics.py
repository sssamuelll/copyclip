from copyclip.llm.metrics import MetricsCollector


def test_summary_does_not_raise_nameerror(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("anthropic", "claude-sonnet-4-5", "answer",
                   input_text="hello world", output_text="hi", latency_ms=10)
    # print_summary used file=sys.stderr without importing sys -> NameError before the fix
    c.print_summary()


def test_real_models_have_nonzero_cost(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("anthropic", "claude-sonnet-4-5", "answer",
                   input_text="", output_text="",
                   input_tokens=1_000_000, output_tokens=1_000_000, latency_ms=5)
    row = c.metrics[-1]
    # sonnet-4-5 must be priced (3.00 in + 15.00 out per Mtok) -> 18.0, not 0
    assert row.cost_usd > 0
    assert row.estimated is False  # real tokens were provided


def test_word_count_path_is_flagged_estimated(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("deepseek", "deepseek-chat", "answer",
                   input_text="one two three", output_text="four five", latency_ms=5)
    assert c.metrics[-1].estimated is True


def test_unknown_model_warns_not_silent_zero(tmp_path, capsys):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.log_llm_call("anthropic", "claude-imaginary-9", "answer",
                   input_text="", output_text="", input_tokens=1000, output_tokens=1000,
                   latency_ms=5)
    err = capsys.readouterr().err
    assert "unknown model" in err.lower()


def test_run_snapshot_and_reset(tmp_path):
    c = MetricsCollector(log_file=str(tmp_path / "m.jsonl"))
    c.reset_run()
    c.log_llm_call("anthropic", "claude-haiku-4-5", "judge",
                   input_text="", output_text="", input_tokens=10, output_tokens=20, latency_ms=3)
    snap = c.run_rollup()
    assert snap["calls"] == 1
    assert snap["total_tokens"] == 30
    assert snap["by_model"]["claude-haiku-4-5"]["calls"] == 1
