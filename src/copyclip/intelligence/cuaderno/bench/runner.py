from __future__ import annotations

import subprocess
import time
from typing import Any, Optional

from ..compositor import iter_compose_events, _fallback_frame
from ..quality import _cited_paths, _answer_text, _norm_path
from ..language import detect_language
from ..read_ledger import ReadLedger
from ..schema import Block, frame_from_dict, FRAME_STATUS_PARTIAL
from .artifact import QuestionRecord
from .asserts import AssertContext, run_asserts
from .score import question_rollup


def _all_citations(blocks: list[dict]) -> list[dict]:
    """Every raw citation dict carried by the answer blocks (path or commit),
    walking the same shapes as quality._cited_paths."""
    out: list[dict] = []
    for b in blocks:
        d = b  # blocks here are already to_dict form: {"kind", ...data}
        if isinstance(d.get("citation"), dict):
            out.append(d["citation"])
        cits = d.get("citations")
        if isinstance(cits, list):
            out.extend(c for c in cits if isinstance(c, dict))
        items = d.get("items")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and isinstance(it.get("citation"), dict):
                    out.append(it["citation"])
    return out


def build_question_record(*, item: dict, frame_dict: dict, ledger: ReadLedger,
                          latency_ms: int, answer_model: str,
                          assert_ctx: AssertContext,
                          input_tokens: int = 0, output_tokens: int = 0,
                          cost_usd: float = 0.0, cost_estimated: bool = True,
                          error: Optional[str] = None) -> QuestionRecord:
    blocks = frame_dict.get("blocks", [])
    block_objs = [Block.from_dict(b) for b in blocks]
    cited_paths = sorted(_cited_paths(block_objs))
    answer_lang = detect_language(_answer_text(block_objs))
    rec = QuestionRecord(
        id=item["id"], category=item["category"], commit_sha=item["commit_sha"],
        question=item["question"], question_lang=item["question_lang"],
        status=frame_dict.get("status", "legacy"),
        verdict=frame_dict.get("verdict"),
        blocks=blocks,
        cited_paths=cited_paths,
        citations=_all_citations(blocks),
        read_paths=sorted(_norm_path(p) for p in ledger.read_paths),
        content_bearing_count=ledger.content_bearing_count,
        answer_lang=answer_lang,
        latency_ms=latency_ms, input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=cost_usd, cost_estimated=cost_estimated, error=error,
    )
    results = run_asserts(rec, item.get("asserts", []), assert_ctx)
    rec.asserts = [r.to_dict() for r in results]
    rec.question_rollup = question_rollup(rec.asserts)
    return rec


def run_one(*, item: dict, client: Any, judge: Any, answer_model: str,
            project_root: str, project_id: int, conn, assert_ctx: AssertContext,
            max_tool_rounds: int = 8) -> QuestionRecord:
    """Drive one corpus question to its terminal frame and build its record.
    Pure of any metrics side-effects here (cost is attached by run_bench)."""
    ledger = ReadLedger()
    last_frame_dict: Optional[dict] = None
    err: Optional[str] = None
    t0 = time.perf_counter()
    try:
        for ev in iter_compose_events(
            client=client, question=item["question"], project_root=project_root,
            project_id=project_id, conn=conn, model=answer_model,
            max_tool_rounds=max_tool_rounds, judge=judge, ledger=ledger,
        ):
            if ev["type"] == "frame":
                last_frame_dict = ev["frame"]
            elif ev["type"] == "error":
                err = ev["message"]
    except Exception as exc:  # noqa: BLE001 — a runner must never abort the whole corpus
        err = f"runner exception: {exc}"
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if last_frame_dict is None:
        # Total: synthesize a partial frame so every question yields a record.
        from ..schema import frame_to_dict
        last_frame_dict = frame_to_dict(_fallback_frame(item["question"], err or "no frame"))
        last_frame_dict["status"] = FRAME_STATUS_PARTIAL

    return build_question_record(
        item=item, frame_dict=last_frame_dict, ledger=ledger,
        latency_ms=latency_ms, answer_model=answer_model, assert_ctx=assert_ctx,
        error=err,
    )


def git_file_length_fn(project_root: str, sha: str):
    """Return a path -> line-count resolver reading the file at the pinned SHA
    via `git show <sha>:<path>`. Returns None for any path git cannot resolve."""
    def fn(path: str) -> Optional[int]:
        try:
            out = subprocess.run(
                ["git", "-C", project_root, "show", f"{sha}:{path}"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                return None
            return out.stdout.count("\n") + (0 if out.stdout.endswith("\n") else 1)
        except Exception:
            return None
    return fn
