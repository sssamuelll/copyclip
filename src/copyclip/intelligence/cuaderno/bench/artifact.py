from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class QuestionRecord:
    id: str
    category: str
    commit_sha: str
    question: str
    question_lang: str
    status: str
    verdict: Optional[dict]
    blocks: list[dict]
    cited_paths: list[str]
    citations: list[dict]
    read_paths: list[str]
    content_bearing_count: int
    answer_lang: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cost_estimated: bool
    asserts: list[dict] = field(default_factory=list)
    question_rollup: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class RunArtifact:
    run_id: str
    started_at: str
    corpus_path: str
    corpus_sha: str
    head_sha: str
    answer_model: str
    judge_model: str
    provider: str
    copyclip_version: str
    items: list[QuestionRecord] = field(default_factory=list)
    metrics_rollup: dict = field(default_factory=dict)


def write_artifact(art: RunArtifact, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(art), f, ensure_ascii=False, indent=2)


def read_artifact(path: str) -> RunArtifact:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    items = [QuestionRecord(**it) for it in d.pop("items", [])]
    return RunArtifact(items=items, **d)


def default_run_path(project_root: str, run_id: str) -> str:
    return os.path.join(project_root, ".copyclip", "bench", "runs", f"{run_id}.json")
