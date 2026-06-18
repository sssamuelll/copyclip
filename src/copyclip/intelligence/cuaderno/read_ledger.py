from __future__ import annotations

from typing import Any

from .tool_catalog import ANSWER_TOOLS

# Per-tool key whose non-empty value means the read returned real content.
_CONTENT_KEYS: tuple[str, ...] = (
    "lines", "entries", "symbols", "callers", "callees",
    "commits", "blame", "diff", "tests", "modules",
    # Wave 4 tools each return real DB/git evidence the honesty gate must
    # recognize — otherwise a risks/decisions answer seals as ungrounded.
    "risks", "decisions", "impacted_modules", "snapshots",
    "related_decisions", "top_changes", "read_first", "relevant_decisions",
)


def is_content_bearing_read(tool_name: str, result: dict[str, Any]) -> bool:
    """True iff a research-tool call returned real evidence.

    Excludes answer tools (emit_block/finish), anything with an "error" key, and
    results whose content payload is empty (e.g. grep_symbols -> {"symbols": []},
    the NORMAL path on an unanalyzed project).
    """
    if tool_name in ANSWER_TOOLS:
        return False
    if not isinstance(result, dict) or result.get("error"):
        return False
    return any(result.get(k) for k in _CONTENT_KEYS)


def _harvest_file_paths(node: Any, out: set[str]) -> None:
    """Collect file_path fields recursively from a tool result. These are
    tool-EVIDENCED paths: a tool genuinely returned them this turn."""
    if isinstance(node, dict):
        fp = node.get("file_path")
        if isinstance(fp, str) and fp:
            out.add(fp)
        for v in node.values():
            _harvest_file_paths(v, out)
    elif isinstance(node, list):
        for v in node:
            _harvest_file_paths(v, out)


class ReadLedger:
    """Accumulates, across a turn, which reads returned content and which file
    paths were actually read. Request-local; never shared across threads."""

    def __init__(self) -> None:
        self.content_bearing_count = 0
        self.read_paths: set[str] = set()
        self.evidence_paths: set[str] = set()

    def record(self, tool_name: str, result: dict[str, Any]) -> None:
        if is_content_bearing_read(tool_name, result):
            self.content_bearing_count += 1
            path = result.get("path")
            if isinstance(path, str) and path:
                self.read_paths.add(path)
        if tool_name not in ANSWER_TOOLS and isinstance(result, dict) and not result.get("error"):
            _harvest_file_paths(result, self.evidence_paths)
