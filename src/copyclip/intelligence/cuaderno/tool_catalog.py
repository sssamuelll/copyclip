from __future__ import annotations

import sqlite3
from typing import Any

from . import anchor

ANSWER_TOOLS: frozenset[str] = frozenset({"emit_block", "finish"})


def build_tool_definitions() -> list[dict[str, Any]]:
    """Return Anthropic-format tool definitions for the cuaderno compositor."""
    return [
        {
            "name": "list_dir",
            "description": (
                "List a project-relative directory's entries (subdirectories "
                "and files). Use this FIRST to orient yourself before reading. "
                "read_file is for files, not directories."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project-relative directory (POSIX). Defaults to the project root '.'."},
                },
            },
        },
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
            "name": "get_module_graph",
            "description": (
                "Dependency topology (calls, inheritance); every node maps to a real "
                "file. Granularity follows your `scope`: pass a `scope` to FOCUS on a "
                "file or symbol — you get that FILE as a node (cited as itself) plus "
                "its direct-import neighbors, which is how you answer 'the graph "
                "around X'. Leave `scope` empty for the whole-project overview at "
                "directory granularity. Build a graph_view from it; emit only the "
                "exact node/edge ids it returned."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": (
                            "focus substring naming a file or symbol, matched against "
                            "file paths AND symbol names (so 'analyzer' finds "
                            "analyzer.py). Returns that file's neighborhood at file "
                            "granularity. Empty = whole project at directory granularity."
                        ),
                    }
                },
            },
        },
        {
            "name": "get_call_path",
            "description": (
                "Walk the STATIC downstream call slice from a symbol: every "
                "function it calls, transitively, breadth-first and capped. Each "
                "hop is a real citation (file + line range) — the slice IS its "
                "citations, so emit it as an ordered citation_stack, one citation "
                "per hop. Use for 'walk me through how X works end-to-end' / "
                "'trace this'. This is STATIC call STRUCTURE from the symbol "
                "index, NOT a runtime/execution trace — never present the order as "
                "execution order, and do not redraw it as a sequence_diagram "
                "(that reads as runtime). `truncated` means the node cap was hit; "
                "`depth_capped` means real callees sit below the depth limit, "
                "unshown — say so. An absent entry means the symbol is not indexed."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Entry symbol name to walk from."},
                    "file": {"type": "string", "description": "Project-relative file to disambiguate a name shared by several symbols. Optional."},
                    "max_depth": {"type": "integer", "default": 4, "description": "How many call levels deep to walk."},
                    "max_nodes": {"type": "integer", "default": 40, "description": "Hard cap on total hops."},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_rationale",
            "description": (
                "Recover the recorded intent behind a FILE — the deliberation that "
                "was delegated — and, when the ledger is silent, get a DETERMINISTIC "
                "verdict so you never invent a 'why'. The server (not you) decides: "
                "'recovered' (decisions reference the file → present them as a cited "
                "citation_stack, 'this exists because…'); 'accepted_not_decided' "
                "(committed but never deliberated → emit ONE callout carrying the "
                "`stamp` VERBATIM, and if `ai_shaped` add 'an AI burst shaped it', "
                "cited to a commit); 'untracked' (no history — say so). NEVER "
                "paraphrase a plausible purpose: recovering recorded intent is not "
                "the human holding it, and an invented why is the worst thing you "
                "can emit. Use for 'why does this exist / why this way'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Project-relative file path."},
                },
                "required": ["file"],
            },
        },
        {
            "name": "get_decisions",
            "description": (
                "Read the decision-ledger — the architectural decisions the human "
                "recorded (and their status). Optionally filter by status "
                "(proposed | accepted | resolved | ...). Cite a decision by its id."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status. Optional."},
                    "limit":  {"type": "integer", "default": 50},
                },
            },
        },
        {
            "name": "get_blast_radius",
            "description": (
                "What else does this touch — the STATIC blast radius of changing a "
                "symbol: the call sites that break on a signature change "
                "(`direct_callers`, symbol-level, each a citation) plus the modules "
                "transitively impacted (`impacted_modules`, directory-level reach). "
                "This is the REVEAL half of a predict-then-reveal: when the human "
                "asks 'what breaks if I change X', FIRST pose the prediction as a "
                "followup ('before I show you — which call sites break?') and STOP; "
                "reveal with this tool on the NEXT turn, beside their guess. It is "
                "STATIC topology, NOT runtime — say so; a matching guess matched "
                "THESE cited edges, never 'you understand the blast radius'. Do NOT "
                "score the guess. An absent entry means the symbol is not indexed."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol whose blast radius to compute."},
                    "file": {"type": "string", "description": "Project-relative file to disambiguate a shared name. Optional."},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_reverse_dependents",
            "description": (
                "Modules transitively impacted if a file changes (reverse-dependents "
                "/ blast radius). Resolves the path to its module, then walks the "
                "dependency graph upward. Use this for 'what breaks if I touch X'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Project-relative file path."}},
                "required": ["path"],
            },
        },
        {
            "name": "git_archaeology",
            "description": (
                "A file's recent commit history crossed with the decisions that "
                "reference it. Connects 'what changed here' to 'which decision you "
                "made about it' — the commit↔decision link git_log alone can't give."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"file": {"type": "string", "description": "Project-relative file path."}},
                "required": ["file"],
            },
        },
        {
            "name": "get_story_snapshots",
            "description": (
                "Narrative snapshots of how the project shifted over time (focus "
                "areas, major changes, open questions) — the connective tissue "
                "between work bursts. Empty until analysis has run; says so."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 5}},
            },
        },
        {
            "name": "get_reacquaintance_briefing",
            "description": (
                "Re-entry briefing after a gap: top changes, what to read first, "
                "relevant decisions, top risk — what reconnects you to your "
                "intention across bursts. Use for 'catch me up' / 'what did I miss'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "mode":       {"type": "string", "description": "baseline: last_seen | checkpoint | window. Default last_seen."},
                    "window":     {"type": "string", "description": "lookback window, e.g. '7d'. Default 7d."},
                    "checkpoint": {"type": "string", "description": "checkpoint name when mode=checkpoint. Optional."},
                },
            },
        },
        {
            "name": "get_risks",
            "description": (
                "Read the project's risk signals (churn, test_gap, complexity, "
                "intent_drift), highest score first. Each row is a deterministic "
                "heuristic over real git data, citable by `area` (file path). Use "
                "for 'what's risky' — emit cited callout blocks, never invent severity."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "kind":     {"type": "string", "description": "churn | test_gap | complexity | intent_drift. Optional."},
                    "severity": {"type": "string", "description": "Filter by severity. Optional."},
                    "limit":    {"type": "integer", "default": 50},
                },
            },
        },
        {
            "name": "get_entry_cue",
            "description": (
                "The cuaderno's ENTRY CUE: the single most-overdue AI burst the "
                "human has not returned to — the proactive launching point. Use it "
                "when the human opens the cuaderno or asks 'where do I start / what "
                "should I revisit / what did I miss'. Live-verified (never fires on "
                "a file the human came back to). On a cue, emit ONE cited callout "
                "('an AI burst shaped `X` ~N days ago; you haven't been back') and "
                "ONE followup that launches get_rationale or get_call_path on that "
                "file — NEVER the playground. If `stale` is true, scope the claim "
                "to 'as of the last analysis ~`analyzed_age_days` days ago', do not "
                "assert a present-tense gap. The FILE is stale, never the mind — "
                "recency and a launch, never a comprehension claim. A null "
                "entry_cue means nothing to surface: stay silent, do not invent one."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_last_contact",
            "description": (
                "Read Pulso 'Last contact': files an AI burst last shaped that the "
                "human has NOT returned to, longest gap (days) first, citable by "
                "`file_path`. Reads the Co-Authored-By trailer signal, never blame; "
                "files with no burst (or where the human is current) are absent, not "
                "zero. Use for 'what did AI change that I haven't gone back to?'. "
                "It proves elapsed TIME, never comprehension — say so, never imply "
                "the human does or does not understand the code."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "emit_block",
            "description": (
                "Emit ONE block of your answer. Call once per block, in order. "
                "Each block must conform to the Block schema in the system prompt. "
                "Your answer IS the ordered sequence of emit_block calls. "
                "Widget primitives (nodes, steps, callers) that assert something "
                "about the code MUST carry a `citation` "
                "({kind:'path', path, line_start?, line_end?}) on the asserting item."
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
    if name == "list_dir":
        return anchor.list_dir(project_root, args.get("path") or ".")
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
    if name == "get_module_graph":
        return anchor.get_module_graph(conn, project_id, args.get("scope", ""))
    if name == "get_call_path":
        return anchor.get_call_path(
            conn, project_id, args["symbol"],
            file=args.get("file"),
            max_depth=args.get("max_depth", 4),
            max_nodes=args.get("max_nodes", 40),
        )
    if name == "get_rationale":
        return anchor.get_rationale(conn, project_id, args["file"])
    if name == "get_decisions":
        return anchor.get_decisions(
            conn, project_id, status=args.get("status"), limit=args.get("limit", 50)
        )
    if name == "get_blast_radius":
        return anchor.get_blast_radius(conn, project_id, args["symbol"], file=args.get("file"))
    if name == "get_reverse_dependents":
        return anchor.get_reverse_dependents(conn, project_id, args["path"])
    if name == "git_archaeology":
        return anchor.git_archaeology(project_root, conn, project_id, args["file"])
    if name == "get_story_snapshots":
        return anchor.get_story_snapshots(conn, project_id, limit=args.get("limit", 5))
    if name == "get_reacquaintance_briefing":
        return anchor.get_reacquaintance_briefing(
            project_root,
            mode=args.get("mode", "last_seen"),
            window=args.get("window", "7d"),
            checkpoint=args.get("checkpoint"),
        )
    if name == "get_risks":
        return anchor.get_risks(
            conn, project_id,
            kind=args.get("kind"), severity=args.get("severity"),
            limit=args.get("limit", 50),
        )
    if name == "get_entry_cue":
        return anchor.get_entry_cue(conn, project_id)
    if name == "get_last_contact":
        return anchor.get_last_contact(conn, project_id, limit=args.get("limit", 20))
    return {"error": "unknown_tool", "name": name}
