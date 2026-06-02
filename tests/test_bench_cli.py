from copyclip.intelligence import cli as intel_cli


def test_bench_is_a_registered_command():
    assert "bench" in intel_cli.COMMANDS


def test_bench_cli_invokes_run_bench(monkeypatch, tmp_path):
    captured = {}

    def fake_run_bench(**kwargs):
        captured.update(kwargs)
        return {"run_id": "fake", "scorecard": {"n_questions": 0}}

    import copyclip.intelligence.cuaderno.bench.cli as bench_cli
    monkeypatch.setattr(bench_cli, "run_bench", fake_run_bench)

    handled = intel_cli._maybe_handle_internal(
        ["copyclip", "bench", "--corpus", str(tmp_path / "c.jsonl"),
         "--path", str(tmp_path), "--limit", "3"])
    assert handled is True
    assert captured["corpus_path"].endswith("c.jsonl")
    assert captured["limit"] == 3
    assert captured["baseline"] is None


def test_bench_cli_passes_baseline(monkeypatch, tmp_path):
    captured = {}
    import copyclip.intelligence.cuaderno.bench.cli as bench_cli
    monkeypatch.setattr(bench_cli, "run_bench", lambda **kw: captured.update(kw) or {"run_id": "x"})
    intel_cli._maybe_handle_internal(
        ["copyclip", "bench", "--baseline", "run-123", "--path", str(tmp_path)])
    assert captured["baseline"] == "run-123"
