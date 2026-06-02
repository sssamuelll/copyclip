import os
import pytest

from copyclip.llm.provider_config import PROVIDERS

LIVE_PROVIDER = os.environ.get("CUADERNO_LIVE_PROVIDER", "deepseek").strip().lower()
_KEY_ENV = PROVIDERS[LIVE_PROVIDER].api_key_env if LIVE_PROVIDER in PROVIDERS else None
_HAS_KEY = bool(_KEY_ENV and (os.environ.get(_KEY_ENV) or "").strip())

pytestmark = pytest.mark.skipif(
    not _HAS_KEY,
    reason=f"bench live smoke: set {_KEY_ENV or 'the provider key'} (provider={LIVE_PROVIDER})",
)


def test_bench_live_smoke_three_questions(tmp_path):
    from copyclip.intelligence.cuaderno.bench.cli import run_bench
    # Run against the real repo root (this checkout) with a 3-question cap.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = run_bench(
        project_root=repo_root,
        corpus_path=os.path.join(repo_root, "corpus", "cuaderno-bench.jsonl"),
        baseline=None, limit=3,
    )
    assert "run_id" in result
    sc = result["scorecard"]
    assert sc["n_questions"] == 3
    # Every question produced a status and an assert rollup
    from copyclip.intelligence.cuaderno.bench.artifact import read_artifact
    art = read_artifact(result["artifact_path"])
    assert len(art.items) == 3
    for it in art.items:
        assert it.status in {
            "answer", "ungrounded", "insufficient_evidence", "off_target",
            "partial", "fallback", "legacy",
        }
        assert "all_pass" in it.question_rollup
