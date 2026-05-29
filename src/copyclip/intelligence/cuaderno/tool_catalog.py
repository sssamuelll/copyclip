from __future__ import annotations

import sqlite3
from typing import Any

from . import anchor

ANSWER_TOOLS: frozenset[str] = frozenset({"emit_block", "finish"})


def build_tool_definitions() -> list[dict[str, Any]]:
    """Return Anthropic-format tool definitions for the cuaderno compositor."""
    return [
        {
            "name": "read_file",
            "description": "Read a project-relative file. Returns lines numbered from 1. Optionally slice by line range.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project-relative path (POSIX). Cannot escape root."},
                    "line_start": {"type": "integer", "description": "1-based start line (inclusive). Optional."},
                    "line_end":   {"type": "integer", "description": "1-based end line (inclusive). Optional."},
                },
                "required": ["path"],
            },
        },
        {
            "name": "grep_symbols",
            "description": "Query the symbols index. Filter by any combination of name, kind, file, module.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "kind":   {"type": "string", "description": "function | method | class | etc."},
                    "file":   {"type": "string", "description": "Exact project-relative path."},
                    "module": {"type": "string", "description": "Slash-style module path (analyzer's stored format)."},
                    "limit":  {"type": "integer", "default": 50},
                },
            },
        },
        {
            "name": "get_callers",
            "description": "List call sites of a symbol by name.",
            "input_schema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "get_callees",
            "description": "List symbols that a given symbol calls.",
            "input_schema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "git_log",
            "description": "Recent commits. Optionally filter by path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path":  {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "git_blame",
            "description": "Per-line blame for a file slice. Returns commit + author + timestamp per line.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string"},
                    "line_start": {"type": "integer"},
                    "line_end":   {"type": "integer"},
                },
                "required": ["path", "line_start", "line_end"],
            },
        },
        {
            "name": "git_diff",
            "description": "Show the diff of a commit. Optionally restrict to a path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "commit_sha": {"type": "string"},
                    "path":       {"type": "string"},
                },
                "required": ["commit_sha"],
            },
        },
        {
            "name": "find_tests",
            "description": "Scan the tests/ directory for files mentioning a symbol name (word-boundary match).",
            "input_schema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "emit_block",
            "description": (
                "Emit ONE block of your answer. Call once per block, in order. "
                "Each block must conform to the Block schema in the system prompt. "
                "Your answer IS the ordered sequence of emit_block calls."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "lead | paragraph | ordered_list | code_block | ascii_block | citation | citation_stack | callout | widget | followups",
                    },
                },
                "required": ["kind"],
                "additionalProperties": True,
            },
        },
        {
            "name": "finish",
            "description": "Call once, after you have emitted every block of your answer. Takes no arguments. Ends the answer.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


def dispatch_tool(
    name: str,
    args: dict[str, Any],
    *,
    project_root: str,
    project_id: int,
    conn: sqlite3.Connection | None,
) -> dict[str, Any]:
    """Execute a tool by name with the provided args + ambient project context."""
    if name == "read_file":
        return anchor.read_file(project_root, args["path"], args.get("line_start"), args.get("line_end"))
    if name == "grep_symbols":
        return anchor.grep_symbols(
            conn, project_id,
            name=args.get("name"), kind=args.get("kind"),
            file=args.get("file"), module=args.get("module"),
            limit=args.get("limit", 50),
        )
    if name == "get_callers":
        return anchor.get_callers(conn, project_id, args["symbol"])
    if name == "get_callees":
        return anchor.get_callees(conn, project_id, args["symbol"])
    if name == "git_log":
        return anchor.git_log(project_root, args.get("path"), args.get("limit", 20))
    if name == "git_blame":
        return anchor.git_blame(project_root, args["path"], args["line_start"], args["line_end"])
    if name == "git_diff":
        return anchor.git_diff(project_root, args["commit_sha"], args.get("path"))
    if name == "find_tests":
        return anchor.find_tests(project_root, args["symbol"])
    return {"error": "unknown_tool", "name": name}
