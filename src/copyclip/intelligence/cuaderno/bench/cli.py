from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from ....llm.metrics import metrics_collector
from ..provider import (
    resolve_cuaderno_provider, build_cuaderno_client, resolve_judge_model,
    CuadernoProviderError,
)
from ..judge import judge_answer
from .artifact import RunArtifact, write_artifact, read_artifact, default_run_path
from .asserts import AssertContext
from .corpus import load_corpus, corpus_sha
from .runner import run_one, git_file_length_fn
from .score import scorecard


def _head_sha(root: str) -> str:
    try:
        out = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _run_id(head: str, csha: str) -> str:
    # Deterministic-ish, sortable: timestamp + short content hash. time import is
    # local so tests can monkeypatch run_bench wholesale without time concerns.
    import time
    return time.strftime("%Y%m%d-%H%M%S") + f"-{head}-{csha[:6]}"


def run_bench(*, project_root: str, corpus_path: str, baseline: Optional[str] = None,
              limit: Optional[int] = None) -> dict[str, Any]:
    """Resolve the real client, run the corpus, write an artifact, print the
    scorecard, and (if baseline) the regression diff."""
    from ..db import connect, init_schema, init_cuaderno_schema
    from ..server_helpers import project_id as _project_id

    conn = connect(project_root)
    init_schema(conn)
    init_cuaderno_schema(conn)
    pid = _project_id(conn, project_root) or 1

    try:
        resolved = resolve_cuaderno_provider(conn)
    except CuadernoProviderError as exc:
        raise SystemExit(f"LLM not configured ({exc.provider}): {exc}")
    client = build_cuaderno_client(resolved)
    answer_model = resolved["model"]

    judge_overlay = None
    try:
        row = conn.execute("SELECT value FROM config WHERE key=?",
                           ("cuaderno_judge_model",)).fetchone()
        judge_overlay = row[0] if row and row[0] else None
    except Exception:
        judge_overlay = None
    judge_model = resolve_judge_model(resolved["provider"], answer_model, judge_overlay)

    def _judge(q, b, l):
        return judge_answer(client=client, question=q, blocks=b, ledger=l, model=judge_model)

    items = load_corpus(corpus_path)
    if limit:
        items = items[:limit]
    csha = corpus_sha(corpus_path)
    head = _head_sha(project_root)

    metrics_collector.reset_run()
    records = []
    for item in items:
        assert_ctx = AssertContext(file_length_fn=git_file_length_fn(project_root, item["commit_sha"]))
        rec = run_one(item=item, client=client, judge=_judge, answer_model=answer_model,
                      project_root=project_root, project_id=pid, conn=conn,
                      assert_ctx=assert_ctx)
        records.append(rec)
        mark = "OK " if rec.question_rollup.get("all_pass") else "XX "
        print(f"  {mark}{rec.id} [{rec.category}] status={rec.status} "
              f"pass={rec.question_rollup.get('n_pass')} fail={rec.question_rollup.get('n_fail')} "
              f"incon={rec.question_rollup.get('n_inconclusive')}")

    sc = scorecard(records)
    rollup = metrics_collector.run_rollup()
    run_id = _run_id(head, csha)
    art = RunArtifact(
        run_id=run_id, started_at=__import__("datetime").datetime.now().isoformat(),
        corpus_path=corpus_path, corpus_sha=csha, head_sha=head,
        answer_model=answer_model, judge_model=judge_model, provider=resolved["provider"],
        copyclip_version=_version(), items=records, metrics_rollup=rollup,
    )
    out_path = default_run_path(project_root, run_id)
    write_artifact(art, out_path)

    _print_scorecard(sc, rollup, out_path)
    result = {"run_id": run_id, "scorecard": sc, "artifact_path": out_path}

    if baseline:
        from .regress import paired_property_diff, SCOPE_A_CAVEAT
        base_art = read_artifact(default_run_path(project_root, baseline))
        print("\n=== REGRESSION vs", baseline, "===")
        for axis in ("grounded", "responsive", "language_ok"):
            d = paired_property_diff(base_art.items, records, axis=axis)
            print(f"  {axis}: {d['baseline_rate']} -> {d['candidate_rate']} "
                  f"(improved={d['improved']} regressed={d['regressed']} "
                  f"p={d['mcnemar']['p']} via {d['mcnemar']['method']})")
        print("\n  " + SCOPE_A_CAVEAT)
        result["baseline"] = baseline
    return result


def _version() -> str:
    try:
        here = os.path.dirname(__file__)
        vf = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "VERSION"))
        with open(vf) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def _print_scorecard(sc: dict, rollup: dict, out_path: str) -> None:
    print("\n=== SCORECARD ===")
    print(f"  questions: {sc['n_questions']}  all-pass-rate: {sc['all_pass_rate']}")
    print(f"  status: {sc['status_distribution']}")
    print(f"  axis rates: {sc['axis_rates']}")
    print(f"  abstention: {sc['abstention']}")
    print(f"  latency ms: {sc['latency_ms']}")
    est = " (ESTIMATED)" if sc['cost_usd']['estimated'] else ""
    print(f"  cost usd: {sc['cost_usd']['total']}{est}")
    print(f"  artifact: {out_path}")
