from __future__ import annotations

import hashlib
import json

from .asserts import KNOWN_ASSERT_TYPES

_REQUIRED = ("id", "question", "category", "commit_sha", "question_lang", "asserts")


class CorpusError(Exception):
    pass


def load_corpus(path: str) -> list[dict]:
    """Load + validate a JSONL corpus. Raises CorpusError on any structural
    problem (no LLM, CI-safe)."""
    items: list[dict] = []
    seen_ids: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorpusError(f"line {lineno}: invalid JSON ({exc})") from exc
            for k in _REQUIRED:
                if k not in row:
                    raise CorpusError(f"line {lineno} (id={row.get('id')!r}): missing field {k!r}")
            if row["id"] in seen_ids:
                raise CorpusError(f"line {lineno}: duplicate id {row['id']!r}")
            seen_ids.add(row["id"])
            if not isinstance(row["asserts"], list):
                raise CorpusError(f"line {lineno}: 'asserts' must be a list")
            for a in row["asserts"]:
                if not isinstance(a, dict) or "type" not in a:
                    raise CorpusError(f"line {lineno}: each assert needs a 'type'")
                if a["type"] not in KNOWN_ASSERT_TYPES:
                    raise CorpusError(
                        f"line {lineno}: unknown assert type {a['type']!r} "
                        f"(known: {sorted(KNOWN_ASSERT_TYPES)})")
            items.append(row)
    if not items:
        raise CorpusError("corpus is empty")
    return items


def corpus_sha(path: str) -> str:
    """A 12-char content hash of the corpus file (recorded in the run artifact
    so a regression compares two runs of the SAME corpus)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:12]
