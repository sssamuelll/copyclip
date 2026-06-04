from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .artifact import QuestionRecord
from ..quality import _walk_citations


@dataclass(frozen=True)
class AssertResult:
    type: str
    outcome: str   # "pass" | "fail" | "inconclusive"
    score: float   # 1.0 pass, 0.0 otherwise
    reason: str

    def to_dict(self) -> dict:
        return {"type": self.type, "outcome": self.outcome,
                "score": self.score, "reason": self.reason}


@dataclass
class AssertContext:
    # path -> line count of that file at the pinned SHA, or None if unresolvable
    file_length_fn: Callable[[str], Optional[int]]


def _ok(t: str, reason: str) -> AssertResult:
    return AssertResult(t, "pass", 1.0, reason)


def _fail(t: str, reason: str) -> AssertResult:
    return AssertResult(t, "fail", 0.0, reason)


def _incon(t: str, reason: str) -> AssertResult:
    return AssertResult(t, "inconclusive", 0.0, reason)


def _norm(p: str) -> str:
    p = p.strip()
    if p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def _a_status_in(r, spec, ctx):
    vals = spec["value"]
    return _ok("status_in", f"status={r.status}") if r.status in vals \
        else _fail("status_in", f"status={r.status} not in {vals}")


def _a_status_is(r, spec, ctx):
    return _ok("status_is", f"status={r.status}") if r.status == spec["value"] \
        else _fail("status_is", f"status={r.status} != {spec['value']}")


def _a_cites_path_matching(r, spec, ctx):
    rx = re.compile(spec["value"])
    hit = next((p for p in r.cited_paths if rx.search(p)), None)
    return _ok("cites_path_matching", f"matched {hit}") if hit \
        else _fail("cites_path_matching", f"no cited path matches {spec['value']!r}; cited={r.cited_paths}")


def _a_cites_commit(r, spec, ctx):
    has = any(isinstance(c, dict) and c.get("kind") == "commit" and c.get("commit")
              for c in r.citations)
    return _ok("cites_commit", "commit citation present") if has \
        else _fail("cites_commit", "no commit-kind citation")


def _a_mentions(r, spec, ctx):
    needle = str(spec["value"]).casefold()
    text = " ".join(b.get("text", "") for b in r.blocks if isinstance(b.get("text"), str)).casefold()
    return _ok("mentions", f"mentions {spec['value']!r}") if needle in text \
        else _fail("mentions", f"does not mention {spec['value']!r}")


def _a_language_is(r, spec, ctx):
    return _ok("language_is", f"answer_lang={r.answer_lang}") if r.answer_lang == spec["value"] \
        else _fail("language_is", f"answer_lang={r.answer_lang} != {spec['value']}")


def _a_min_content_bearing_reads(r, spec, ctx):
    n = int(spec["value"])
    return _ok("min_content_bearing_reads", f"{r.content_bearing_count} >= {n}") \
        if r.content_bearing_count >= n \
        else _fail("min_content_bearing_reads", f"{r.content_bearing_count} < {n}")


def _a_no_unread_citations(r, spec, ctx):
    cited = {_norm(p) for p in r.cited_paths}
    read = {_norm(p) for p in r.read_paths}
    if not cited:
        return _ok("no_unread_citations", "no path citations to verify")
    unread = cited - read
    return _ok("no_unread_citations", "all cited paths were read") if not unread \
        else _fail("no_unread_citations", f"cited but unread: {sorted(unread)}")


def _a_cited_lines_within_eof(r, spec, ctx):
    checked = 0
    for c in r.citations:
        if not isinstance(c, dict) or c.get("kind") != "path":
            continue
        path = c.get("path")
        ls, le = c.get("line_start"), c.get("line_end")
        if not path or ls is None and le is None:
            continue  # no range -> vacuously fine for this citation
        length = ctx.file_length_fn(_norm(str(path)))
        if length is None:
            return _incon("cited_lines_within_eof", f"cannot resolve length of {path}")
        top = le if le is not None else ls
        if top is not None and int(top) > length:
            return _fail("cited_lines_within_eof", f"{path}:{ls}-{le} past EOF ({length} lines)")
        checked += 1
    return _ok("cited_lines_within_eof", f"{checked} line range(s) within EOF")


def _harvested(axis: str):
    def fn(r, spec, ctx):
        t = f"harvested_{axis}"
        v = (r.verdict or {}).get(axis)
        if v is None:
            return _incon(t, f"{axis} unobserved (verdict source={(r.verdict or {}).get('source')})")
        expected = spec.get("value", True)
        return _ok(t, f"{axis}={v}") if v == expected else _fail(t, f"{axis}={v} != {expected}")
    return fn


def _a_has_artifact(r, spec, ctx):
    kinds: list = []
    cited_any = False
    for b in r.blocks:
        if not isinstance(b, dict) or b.get("kind") != "widget":
            continue
        w = b.get("widget")
        if not isinstance(w, dict):
            continue
        kinds.append(w.get("kind"))
        found: list = []
        _walk_citations(w, found)
        if found:
            cited_any = True
    if not kinds:
        return _fail("has_artifact", "no widget blocks in answer")
    want = spec.get("kind")
    if want and want not in kinds:
        return _fail("has_artifact", f"no widget of kind {want!r}; kinds={kinds}")
    if spec.get("cited") and not cited_any:
        return _fail("has_artifact", "widgets present but none carries a citation")
    return _ok("has_artifact", f"kinds={kinds}, cited={cited_any}")


ASSERTS: dict[str, Callable[[QuestionRecord, dict, AssertContext], AssertResult]] = {
    "status_in": _a_status_in,
    "status_is": _a_status_is,
    "cites_path_matching": _a_cites_path_matching,
    "cites_commit": _a_cites_commit,
    "mentions": _a_mentions,
    "language_is": _a_language_is,
    "min_content_bearing_reads": _a_min_content_bearing_reads,
    "no_unread_citations": _a_no_unread_citations,
    "cited_lines_within_eof": _a_cited_lines_within_eof,
    "harvested_responsive": _harvested("responsive"),
    "harvested_grounded": _harvested("grounded"),
    "has_artifact": _a_has_artifact,
}

KNOWN_ASSERT_TYPES = frozenset(ASSERTS)


def run_asserts(record: QuestionRecord, specs: list[dict],
                ctx: AssertContext) -> list[AssertResult]:
    """Run each assert spec against the record. Raises KeyError on an unknown
    assert type (corpus validation, Task 5, catches these earlier)."""
    out = []
    for spec in specs:
        fn = ASSERTS[spec["type"]]
        out.append(fn(record, spec, ctx))
    return out
